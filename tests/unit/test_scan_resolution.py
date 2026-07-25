"""
Unit tests for service-side scan resolution (Story 4.3).

Covers the two public read-only methods Story 4.3 adds to
`app/mariadb_catalog_service.py` — `resolve_scan()` and `search_products()` —
and the frozen `ScanResolution` shape they produce
(`app/models.py`):

- **FR36**: every scan resolves, and a classification that matches no record
  falls through to free-text search *within the same scan* rather than
  dead-ending.
- **AD-15**: `ScanResolution{classification, product, free_text_hits}` is the
  second of the epic's two frozen shapes — the contract Story 4.5's UI routing
  and Epics 7/9 are written against.
- **AD-16**: the AI/token pair is read from `Config` inside `resolve_scan` on
  every call and passed explicitly into the pure classifier, so one config
  change moves the label encoder and the scan router together. Story 4.2 could
  only assert that the *classifier* accepts the pair; this is the first story
  where the config flow itself exists, so `TestConfigSeam` proves it end to end.
- **AD-17**: `search_products()` is the single free-text entrypoint that both
  this fallthrough and Epic 8's search page use.
- **AD-7**: GTIN lookup is against the normalized-14 namespace, and
  `GTIN_UNVALIDATED` is outside it.
- **NFR8**: no scan datum, however hostile, makes resolution raise.

The `ScanResolution` shape is tested here rather than in `tests/unit/
test_models.py` for the same reason `ScanClassification` is tested in
`tests/unit/test_scan_router.py`: it is this epic's contract, not a metal-stock
domain model, and the tests that pin it belong beside the only code that
produces it.

Unlike the classifier suite, these tests need a database — resolution is the
half of the epic that performs lookup. They use the real SQLite
`catalog_service` fixture and create every product through `create_product()`;
there are no mocks of the service or the ORM. The only monkeypatching is of
`Config` (to prove the AD-16 seam) and of the service's own `Session` /
`search_products` (to prove WHICH text an arm searched, and that an envelope
carrying no part number issues no query at all — neither of which an assertion
about the *result* could show).

Classification precedence itself is `tests/unit/test_scan_router.py`'s subject
and is deliberately not re-tested here.
"""

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from app import mariadb_catalog_service
from app.mariadb_catalog_service import (CatalogService,
                                         SEARCH_QUERY_MAX_LENGTH,
                                         SEARCH_RESULTS_DEFAULT_LIMIT,
                                         SEARCH_RESULTS_MAX_LIMIT)
from app.models import IdentifierType, ScanClassification, ScanKind, ScanResolution
from app.utils import scan_router
from app.utils.gs1 import InvalidGs1PayloadError
from config import Config

# --- Vectors -----------------------------------------------------------------
#
# NOTE (AD-16): not one literal below holds the configured AI or token. Every
# internal element string is assembled from `Config` by `_internal_scan()`, and
# the alternate grammar `TestConfigSeam` reconfigures to is DERIVED from the
# configured pair by `_shifted()` rather than written down. `TestConfigSeam
# .test_no_executed_string_literal_holds_the_configured_grammar` enforces that
# over this file as well as over the service module, so a hardcoded grammar
# cannot hide in the tests that are supposed to be guarding against one.

# The repo's canonical ECIA vectors (tests/unit/test_gs1.py, test_scan_router.py).
# ECIA_FULL carries `1P` = 'ABC' (the supplier part number, tried first) and
# `P` = '12345' (the customer part number, tried second).
ECIA_FULL = '[)>\x1e06\x1dP12345\x1d1PABC\x1dQ10\x1d\x1e\x04'
ECIA_FULL_SUPPLIER_PN = 'ABC'
ECIA_FULL_CUSTOMER_PN = '12345'


def _envelope(*records: str) -> str:
    """An ISO/IEC 15434 format-06 message carrying `records` verbatim.

    Assembled rather than written out per test so that a vector says which data
    identifiers it carries and nothing else. The grammar itself is
    tests/unit/test_ecia.py's subject; here it is only a way to state input.
    """
    return '[)>\x1e06' + ''.join(f'\x1d{record}' for record in records) + '\x1d\x1e\x04'


# A manufacturer part number for the fallthrough-search assertions. It contains
# a character the internal-id alphabet does not (`app/utils/internal_id.py` is
# Crockford base-32, digits and letters only), so a generated `internal_id` can
# never substring-match it and the hit lists below are deterministic rather
# than one-in-a-few-thousand flaky.
MPN = 'RC0805-10K'

# A distributor's own part number, for the cases where `1P` and `P` must hold
# two DIFFERENT numbers. Hyphenated for the same determinism reason as `MPN`,
# and sharing no substring with it, so a search on one can never return a
# product carrying the other.
CUSTOMER_MPN = '296-1234-ND'

# One trade item number per accepted encoding family, each with the canonical
# 14-digit key `gtin.normalize_gtin` folds every form of it onto.
GTIN13 = '9506000134352'
GTIN13_KEY = '09506000134352'
UPCA = '012345678905'
UPCA_KEY = '00012345678905'
GTIN8 = '40170725'
GTIN8_KEY = '00000040170725'
# A second, check-digit-valid trade item number that is never stored anywhere.
GTIN_UNSTORED = '4006381333931'

# An internal id that no product will ever hold, for the internal-miss arm. It
# must still be an id the grammar can carry, or the scan would classify as free
# text and test a different arm than the one it names.
ABSENT_INTERNAL_ID = 'ZZZZZZZZZZ'


def _internal_scan(internal_id: str, *, ai: str = None, token: str = None) -> str:
    """The bare element string a label carries: `<ai><token><id>`.

    Built from the CONFIGURED grammar by default (AD-16) — the deployed Tera
    HW0009 strips FNC1 and emits exactly this form (FR37a).
    """
    ai = Config.GS1_INTERNAL_AI if ai is None else ai
    token = Config.GS1_INTERNAL_TOKEN if token is None else token
    return f'{ai}{token}{internal_id}'


def _shifted(text: str) -> str:
    """Advance every character one step within its own class.

    Used to derive an alternate grammar for `TestConfigSeam` from the
    configured one instead of writing a second pair down. Two properties make
    it safe for that purpose, and both follow from every character changing:
    the result is the same length as the input, so "is a substring of" reduces
    to "is equal to", and it cannot be equal because no character survives. So
    the alternate grammar can never accidentally *be* the configured grammar,
    whatever the configured grammar is — and, being computed, it is not a
    string literal at all, so it cannot trip the AD-16 literal guard either.
    """
    out = []
    for char in text:
        if char.isdigit():
            out.append(str((int(char) + 1) % 10))
        elif char.isalpha():
            out.append(chr((ord(char.upper()) - ord('A') + 1) % 26 + ord('A')))
        else:  # pragma: no cover - the configured grammar is alphanumeric
            out.append(char)
    return ''.join(out)


@pytest.fixture
def catalog_service(test_storage):
    """The same real-SQLite service fixture tests/unit/test_catalog_service.py
    uses — no mocks, no Flask app, no MariaDB."""
    return CatalogService(test_storage)


@pytest.fixture
def product(catalog_service):
    """Product P from the story's I/O matrix: created through the service, so
    it owns a generated `internal_id` and a mirrored INTERNAL identifier row."""
    pid = catalog_service.create_product(description='RES 10K 0805 1%')
    return catalog_service.get_product(pid)


def _spy_on_search(catalog_service, monkeypatch):
    """Record every `search_products` call, still performing it.

    Some rows of the I/O matrix are claims about *which text was searched*, not
    about the hits — and an assertion on the hits alone would pass just as well
    against a resolver that searched the wrong string and found nothing.
    """
    calls = []
    real = catalog_service.search_products

    def spy(query, *args, **kwargs):
        calls.append(query)
        return real(query, *args, **kwargs)

    monkeypatch.setattr(catalog_service, 'search_products', spy)
    return calls


class TestScanResolutionShape:
    """AD-15: the frozen three-field contract Story 4.5 and Epics 7/9 consume."""

    def _classification(self):
        return ScanClassification(kind=ScanKind.FREE_TEXT, normalized_value=None,
                                  ecia_fields=None, raw='anything')

    @pytest.mark.unit
    def test_has_exactly_the_three_ad15_fields_in_order(self):
        names = tuple(f.name for f in dataclasses.fields(ScanResolution))
        assert names == ('classification', 'product', 'free_text_hits')

    @pytest.mark.unit
    @pytest.mark.parametrize('field_name',
                             ['classification', 'product', 'free_text_hits'])
    def test_every_field_is_mutation_proof(self, field_name):
        r = ScanResolution(classification=self._classification(), product=None,
                           free_text_hits=())
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(r, field_name, None)

    @pytest.mark.unit
    @pytest.mark.parametrize('kwargs', [
        {},                                                    # nothing at all
        {'classification': True},                              # classification only
        {'classification': True, 'product': None},             # missing free_text_hits
        {'product': None, 'free_text_hits': ()},               # missing classification
    ])
    def test_all_three_fields_are_required_with_no_defaults(self, kwargs):
        """No producer can build a half-populated resolution. The sentinel
        `True` stands in for the classification because the constructor must
        fail on the missing ARGUMENT before it ever validates a type."""
        with pytest.raises(TypeError):
            ScanResolution(**kwargs)

    @pytest.mark.unit
    def test_no_field_carries_a_default(self):
        for f in dataclasses.fields(ScanResolution):
            assert f.default is dataclasses.MISSING
            assert f.default_factory is dataclasses.MISSING

    @pytest.mark.unit
    def test_hashing_works_without_ecia_fields_and_raises_with_them(
            self, catalog_service):
        """The class docstring used to say a resolution "is not usefully
        hashable", which was wrong in both directions and worth pinning rather
        than re-asserting in prose.

        `frozen=True` synthesizes `__hash__`, so hashing SUCCEEDS for any
        resolution whose classification carries no `ecia_fields` — and the
        value it returns is built from the ORM rows' identity hashes, so it
        says nothing about what was resolved. A resolution carrying a parsed
        envelope raises instead, because a mapping is not hashable. Both halves
        are asserted here so that whichever one changes, the docstring is
        forced to change with it.

        The third assertion is the one that matters now rather than in the
        abstract: a consumer holding the return value of `resolve_scan` on a
        real distributor label — not a hand-built instance — cannot put it in a
        set or use it as a dict key. That was unreachable before Story 4.4,
        because no arm could produce a populated `ecia_fields`."""
        resolvable = ScanResolution(classification=self._classification(),
                                    product=None, free_text_hits=())
        assert isinstance(hash(resolvable), int)

        with_envelope = ScanResolution(
            classification=ScanClassification(
                kind=ScanKind.ECIA, normalized_value=None,
                ecia_fields={'P': ECIA_FULL_CUSTOMER_PN}, raw='[)>'),
            product=None, free_text_hits=())
        with pytest.raises(TypeError):
            hash(with_envelope)

        with pytest.raises(TypeError):
            hash(catalog_service.resolve_scan(ECIA_FULL))

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', [None, 'free_text', ScanKind.FREE_TEXT, 42,
                                     {'kind': 'free_text'}])
    def test_a_non_classification_is_a_typeerror(self, bad):
        with pytest.raises(TypeError) as exc:
            ScanResolution(classification=bad, product=None, free_text_hits=())
        assert 'classification' in str(exc.value)
        assert type(bad).__name__ in str(exc.value)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', ['abc', b'abc', bytearray(b'abc'),
                                     {'a': 'b'}])
    def test_a_string_or_mapping_is_not_a_sequence_of_hits(self, bad):
        """The coercion lesson `ecia_fields` learned one class up: `tuple('abc')`
        is a perfectly good three-element tuple, so without this guard a caller
        that passed a description where a product list was meant would build a
        resolution claiming three hits."""
        with pytest.raises(TypeError) as exc:
            ScanResolution(classification=self._classification(), product=None,
                           free_text_hits=bad)
        assert 'free_text_hits' in str(exc.value)
        assert type(bad).__name__ in str(exc.value)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', [None, 42, object()])
    def test_a_non_sequence_is_a_typeerror(self, bad):
        """`None` is the realistic one: "no hits" is `()`, not `None`."""
        with pytest.raises(TypeError) as exc:
            ScanResolution(classification=self._classification(), product=None,
                           free_text_hits=bad)
        assert 'free_text_hits' in str(exc.value)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', [
        {'a', 'b'},                    # a set: iterable, but has no order
        frozenset({'a'}),
        iter(['a', 'b']),              # a one-shot iterator
        (c for c in 'ab'),             # ...and a generator
    ])
    def test_an_unordered_or_one_shot_iterable_is_refused(self, bad):
        """The attribute documents an order ("oldest id first"), so accepting
        any iterable would make that promise false by construction.

        A set copied into a tuple takes whatever order the hash table yields —
        which varies per process — and a generator reads as a sequence at the
        call site but leaves the producer holding something it can no longer
        re-read. Requiring a `Sequence` makes the stated ordering true instead
        of aspirational; `search_products` returns a list, so the sole producer
        is unaffected."""
        with pytest.raises(TypeError) as exc:
            ScanResolution(classification=self._classification(), product=None,
                           free_text_hits=bad)
        assert 'free_text_hits' in str(exc.value)
        assert 'sequence' in str(exc.value).lower()

    @pytest.mark.unit
    def test_type_checks_run_before_the_combination_check(self):
        """House taxonomy (`ScanClassification.__post_init__`): a wrong type is
        reported as a wrong type even when it would ALSO trip the cross-field
        rule, so the message names what is actually wrong."""
        with pytest.raises(TypeError):
            ScanResolution(classification=self._classification(),
                           product=object(), free_text_hits='hits')

    @pytest.mark.unit
    @pytest.mark.parametrize('hits, expected', [
        ([], ()),
        (['a', 'b'], ('a', 'b')),          # a list, the shape search_products returns
        (('a',), ('a',)),                  # already a tuple — still copied
        (range(2), (0, 1)),                # any ordered Sequence, not just list/tuple
    ])
    def test_hits_are_normalized_to_a_tuple(self, hits, expected):
        r = ScanResolution(classification=self._classification(), product=None,
                           free_text_hits=hits)
        assert isinstance(r.free_text_hits, tuple)
        assert r.free_text_hits == expected

    @pytest.mark.unit
    def test_the_copy_is_unconditional_so_caller_aliasing_cannot_reach_in(self):
        """AD-15: mutating the list you passed must not change the resolution."""
        caller_list = ['first']
        r = ScanResolution(classification=self._classification(), product=None,
                           free_text_hits=caller_list)
        caller_list.append('smuggled')
        caller_list[0] = 'rewritten'
        assert r.free_text_hits == ('first',)

    @pytest.mark.unit
    def test_matched_and_searched_is_a_valueerror(self):
        """A resolution cannot both match and fall through: FR36 searches only
        when the lookup missed, so both being set means the producer conflated
        the arms and a consumer would need a precedence rule nothing states."""
        with pytest.raises(ValueError) as exc:
            ScanResolution(classification=self._classification(),
                           product=object(), free_text_hits=[object()])
        assert 'free_text_hits' in str(exc.value)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', ['a product', b'p', bytearray(b'p'),
                                     {'id': 1}, ['hit', 'hit'], ('hit',)])
    def test_an_obviously_wrong_product_is_a_typeerror(self, bad):
        """`product` cannot be checked against `Product` (leaf module), but the
        wrong shapes can still be refused. The one that matters is a sequence:
        the arguments swapped — the hits list handed to `product` — passes
        every other guard, because the matched-and-searched rule only inspects
        `free_text_hits`, and would freeze into a resolution Story 4.5 renders
        by dereferencing a list as a row."""
        with pytest.raises(TypeError) as exc:
            ScanResolution(classification=self._classification(),
                           product=bad, free_text_hits=())
        assert 'product' in str(exc.value)
        assert type(bad).__name__ in str(exc.value)

    @pytest.mark.unit
    def test_the_product_check_runs_before_the_combination_check(self):
        """Type before combination, the taxonomy `ScanClassification` settled:
        a swapped pair must report the wrong TYPE, not the wrong pairing."""
        with pytest.raises(TypeError):
            ScanResolution(classification=self._classification(),
                           product=['hit'], free_text_hits=['hit'])

    @pytest.mark.unit
    @pytest.mark.parametrize('product, hits', [
        (object(), []),        # matched, did not search
        (None, ['hit']),       # missed, searched, found something
        (None, []),            # missed, searched, found nothing (FR40's seam)
    ])
    def test_the_three_legal_states_are_accepted(self, product, hits):
        r = ScanResolution(classification=self._classification(),
                           product=product, free_text_hits=hits)
        assert r.product is product

    @pytest.mark.unit
    def test_a_frozen_dataclass_the_service_actually_produces(self, catalog_service):
        """The shape assertions above construct resolutions by hand; this one
        pins that the service's own return value is the same type."""
        assert isinstance(catalog_service.resolve_scan('anything'), ScanResolution)


class TestInternalResolution:
    """Rule 1: a label this shop printed (AD-3 makes internal_id the key)."""

    @pytest.mark.unit
    def test_a_printed_label_resolves_to_its_product(self, catalog_service, product):
        r = catalog_service.resolve_scan(_internal_scan(product.internal_id))
        assert r.classification.kind is ScanKind.INTERNAL
        assert r.product is not None and r.product.id == product.id
        assert r.free_text_hits == ()

    @pytest.mark.unit
    @pytest.mark.parametrize('decorate', [
        lambda scan: '\x1d' + scan,             # a wedge that transmits FNC1
        lambda scan: ']d1' + scan,              # an AIM symbology identifier
        lambda scan: ']C1' + '\x1d' + scan,     # both, GS1 DataMatrix style
    ], ids=['fnc1', 'aim', 'aim+fnc1'])
    def test_transmission_variants_resolve_identically(self, catalog_service,
                                                        product, decorate):
        r = catalog_service.resolve_scan(decorate(_internal_scan(product.internal_id)))
        assert r.classification.kind is ScanKind.INTERNAL
        assert r.product.id == product.id
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_a_miss_falls_through_and_searches_the_bare_id(
            self, catalog_service, product, monkeypatch):
        """The `<ai><token>` prefix is an encoding artefact stored in no column,
        so searching the raw scan would find nothing by construction. The bare
        token-stripped id is what `products.internal_id` holds."""
        calls = _spy_on_search(catalog_service, monkeypatch)
        scan = _internal_scan(ABSENT_INTERNAL_ID)

        r = catalog_service.resolve_scan(scan)

        assert r.classification.kind is ScanKind.INTERNAL
        assert r.product is None
        assert calls == [ABSENT_INTERNAL_ID]
        assert scan not in calls

    @pytest.mark.unit
    def test_a_miss_whose_bare_id_appears_in_a_description_finds_it(
            self, catalog_service):
        """Behavioral proof of the same thing: only a search on the bare id can
        reach this product."""
        pid = catalog_service.create_product(
            description=f'spare tray for {ABSENT_INTERNAL_ID}')

        r = catalog_service.resolve_scan(_internal_scan(ABSENT_INTERNAL_ID))

        assert r.product is None
        assert [p.id for p in r.free_text_hits] == [pid]


class TestGtinResolution:
    """Rule 3, AD-7: lookup is against the normalized-14 namespace, so every
    encoding of one trade item number reaches the same product."""

    @pytest.mark.unit
    @pytest.mark.parametrize('stored, scanned', [
        (GTIN13, GTIN13),            # EAN-13 as printed
        (GTIN13, GTIN13_KEY),        # ...and its zero-padded GTIN-14 form
        (UPCA, UPCA),                # UPC-A as printed
        (UPCA, '0' + UPCA),          # ...as an EAN-13
        (UPCA, UPCA_KEY),            # ...as a GTIN-14
        (GTIN8, GTIN8),              # GTIN-8 as printed
        (GTIN8, GTIN8_KEY),          # ...as a GTIN-14
        (GTIN8_KEY, GTIN8),          # stored in the padded form, scanned bare
    ])
    def test_every_encoding_collapses_to_one_product(self, catalog_service,
                                                     product, stored, scanned):
        catalog_service.add_identifier(product.id,
                                       identifier_type=IdentifierType.GTIN,
                                       value=stored)

        r = catalog_service.resolve_scan(scanned)

        assert r.classification.kind is ScanKind.GTIN
        assert r.product is not None and r.product.id == product.id
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_a_valid_gtin_that_matches_nothing_falls_through(
            self, catalog_service, product, monkeypatch):
        """FR36: a structurally valid GTIN with no stored identifier becomes a
        search within the same scan — never a dead end."""
        calls = _spy_on_search(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(GTIN_UNSTORED)

        assert r.classification.kind is ScanKind.GTIN
        assert r.product is None
        assert calls == [GTIN_UNSTORED]
        # Compared by id, not by row. `Product` defines no `__eq__`, so tuple
        # equality between two separately-fetched result sets is identity
        # equality and is False even when both hold "the same" product — which
        # would make this assertion vacuously true for the empty case only, and
        # therefore carry no information about where the hits came from.
        assert ([p.id for p in r.free_text_hits]
                == [p.id for p in catalog_service.search_products(GTIN_UNSTORED)])

    @pytest.mark.unit
    def test_an_aim_prefixed_gtin_resolves_to_the_same_product(
            self, catalog_service, product):
        """A wedge that emits AIM identifiers must reach the same row. The
        encodings above vary the KEY; this varies the transmission, which is
        the other axis and the one the internal arm already covers."""
        catalog_service.add_identifier(product.id,
                                       identifier_type=IdentifierType.GTIN,
                                       value=GTIN13)

        r = catalog_service.resolve_scan(']d1' + GTIN13)

        assert r.classification.kind is ScanKind.GTIN
        assert r.product is not None and r.product.id == product.id

    @pytest.mark.unit
    def test_the_aim_prefix_is_stripped_before_the_fallthrough_search(
            self, catalog_service, monkeypatch):
        """The GTIN arm searches `strip_aim_prefix(raw)`, not `raw`. Without
        this vector every GTIN test used a bare, undecorated scan, for which
        the two are equal — so replacing the call with `classification.raw`
        left the whole suite green while the fallthrough searched `']d1...'`,
        which no column can contain."""
        calls = _spy_on_search(catalog_service, monkeypatch)

        catalog_service.resolve_scan(']d1' + GTIN_UNSTORED)

        assert calls == [GTIN_UNSTORED]

    @pytest.mark.unit
    def test_the_miss_searches_the_digits_as_scanned_not_the_14_digit_key(
            self, catalog_service, monkeypatch):
        """The key was just searched exactly by the lookup arm, so re-searching
        it adds nothing; the scanned form is what can substring-match a
        GTIN_UNVALIDATED row, which is stored exactly as it was typed."""
        calls = _spy_on_search(catalog_service, monkeypatch)

        catalog_service.resolve_scan(GTIN13)

        assert calls == [GTIN13]

    @pytest.mark.unit
    def test_gtin_unvalidated_is_outside_the_namespace_but_inside_the_search(
            self, catalog_service, product):
        """AD-7: a GTIN_UNVALIDATED row shares no key space with GTIN, so the
        exact arm must miss it — and the fallthrough search over identifier
        values is then the only way the operator ever sees that product."""
        catalog_service.add_identifier(
            product.id, identifier_type=IdentifierType.GTIN_UNVALIDATED,
            value=GTIN13)

        r = catalog_service.resolve_scan(GTIN13)

        assert r.classification.kind is ScanKind.GTIN
        assert r.product is None
        assert [p.id for p in r.free_text_hits] == [product.id]

    @pytest.mark.unit
    def test_the_unvalidated_fallthrough_bridges_encodings_one_way_only(
            self, catalog_service, product):
        """The previous test scans the SHORT form of a row stored short, which
        is the direction substring containment happens to serve. Pin the other
        direction too, because the docstrings claim reachability and only half
        of it is true.

        A GTIN_UNVALIDATED row is stored exactly as typed, so scanning a
        13-digit form finds a row stored zero-padded to 14 (the stored value
        CONTAINS the scanned one), while scanning the 14-digit ITF form of a
        row stored in 13 digits finds nothing — `'04006381333931'` is not a
        substring of `'4006381333931'`. That second scan is a real FR36 dead
        end: no product AND no hits. It is deferred rather than fixed here
        (normalizing on write, or Epic 8's mechanism), so this test exists to
        make the gap visible and to fail loudly if someone closes it.
        """
        padded = catalog_service.create_product(description='PADDED')
        catalog_service.add_identifier(
            padded, identifier_type=IdentifierType.GTIN_UNVALIDATED,
            value='0' + GTIN_UNSTORED)

        reachable = catalog_service.resolve_scan(GTIN_UNSTORED)
        assert reachable.classification.kind is ScanKind.GTIN
        assert reachable.product is None
        assert [p.id for p in reachable.free_text_hits] == [padded]

        short = catalog_service.create_product(description='SHORT')
        catalog_service.add_identifier(
            short, identifier_type=IdentifierType.GTIN_UNVALIDATED,
            value=GTIN13)

        dead_end = catalog_service.resolve_scan(GTIN13_KEY)
        assert dead_end.classification.kind is ScanKind.GTIN
        assert dead_end.product is None
        assert dead_end.free_text_hits == ()


def _count_sessions(catalog_service, monkeypatch):
    """Record every session the service opens, still opening it.

    Some rows of the I/O matrix are claims about whether a query was ISSUED,
    not about what came back — and an assertion on an empty result would pass
    just as well against an arm that queried and found nothing.
    """
    opened = []
    real_session = catalog_service.Session

    def counting_session(*args, **kwargs):
        opened.append(1)
        return real_session(*args, **kwargs)

    monkeypatch.setattr(catalog_service, 'Session', counting_session)
    return opened


class TestEciaResolution:
    """Rule 2, FR38/FR39: a distributor label resolves on the part numbers
    `app/utils/ecia.py` read off it.

    Both candidates (`1P` then `P`) are tried against both places a
    manufacturer part number lives — the `products.mpn` column and an `MPN`
    identifier row — because which physical number a distributor prints in
    which identifier is a property of that label, not of this system.
    """

    @pytest.mark.unit
    def test_the_parsed_fields_reach_the_resolution(self, catalog_service):
        """The seam Story 4.5 consumes: the envelope's contents arrive on the
        classification, so a create form can pre-fill without re-parsing the
        raw scan (FR38, AD-15)."""
        r = catalog_service.resolve_scan(ECIA_FULL)

        assert r.classification.kind is ScanKind.ECIA
        assert dict(r.classification.ecia_fields) == {
            'P': ECIA_FULL_CUSTOMER_PN, '1P': ECIA_FULL_SUPPLIER_PN, 'Q': '10'}

    @pytest.mark.unit
    def test_a_supplier_part_number_matching_the_mpn_column_resolves(
            self, catalog_service):
        pid = catalog_service.create_product(description='plain',
                                             mpn=ECIA_FULL_SUPPLIER_PN)

        r = catalog_service.resolve_scan(ECIA_FULL)

        assert r.classification.kind is ScanKind.ECIA
        assert r.product is not None and r.product.id == pid
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_a_supplier_part_number_matching_an_mpn_identifier_row_resolves(
            self, catalog_service, product):
        """Both places are searched, in one query. A product whose part number
        was recorded as a typed identifier rather than in the column must
        resolve identically — the two are equally legitimate homes for it."""
        catalog_service.add_identifier(product.id,
                                       identifier_type=IdentifierType.MPN,
                                       value=ECIA_FULL_SUPPLIER_PN)

        r = catalog_service.resolve_scan(ECIA_FULL)

        assert r.product is not None and r.product.id == product.id
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_the_customer_part_number_resolves_when_the_supplier_one_misses(
            self, catalog_service):
        """The arm deliberately does not decide which of `1P` and `P` holds the
        manufacturer part number: a rule that hard-coded one would fail
        silently on any label that does it the other way, the scan would
        resolve to nothing, and the operator would create a duplicate."""
        pid = catalog_service.create_product(description='plain',
                                             mpn=ECIA_FULL_CUSTOMER_PN)

        r = catalog_service.resolve_scan(ECIA_FULL)

        assert r.product is not None and r.product.id == pid
        assert r.free_text_hits == ()

    @pytest.mark.unit
    @pytest.mark.parametrize('stored', ['abc', 'AbC', 'ABC'])
    def test_the_match_is_case_folded(self, catalog_service, stored):
        """`func.lower()` explicitly on both sides, as `search_products` folds:
        without it SQLite's binary default collation would make this lookup
        case-sensitive under the unit suite and case-insensitive in
        production."""
        pid = catalog_service.create_product(description='plain', mpn=stored)

        r = catalog_service.resolve_scan(ECIA_FULL)

        assert r.product is not None and r.product.id == pid

    @pytest.mark.unit
    def test_a_non_ascii_part_number_matches_itself(self, catalog_service):
        """The case a fold-only comparison could not answer: `str.lower()` is
        full-Unicode and SQLite's `LOWER()` is not, so `lower(col) == lower(v)`
        can never be true for a non-ASCII value and a byte-identical stored
        part number matched NOTHING — an exact lookup failing on an exact
        value. The unfolded equality disjunct beside the folded one closes it
        on every backend."""
        pid = catalog_service.create_product(description='plain', mpn='WÜRTH-1')

        r = catalog_service.resolve_scan(_envelope('1PWÜRTH-1'))

        assert r.product is not None and r.product.id == pid
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_non_ascii_case_insensitivity_is_still_out_of_reach(
            self, catalog_service):
        """The other half, pinned in the direction it fails: the fix above buys
        byte-identical matching, not non-ASCII case-insensitivity. Under SQLite
        a differently-cased 'ü' misses the lookup AND the substring search that
        follows, because both sides fold ASCII-only. Closing it needs an
        engine-level collation or Epic 8's mechanism decision; deferred, and
        stated here so the docstring cannot quietly claim more."""
        catalog_service.create_product(description='plain', mpn='WÜRTH-1')

        r = catalog_service.resolve_scan(_envelope('1Pwürth-1'))

        assert r.product is None
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_a_padded_part_number_still_matches_exactly(self, catalog_service):
        """The parser keeps a value exactly as the label carried it, which is
        right for Story 4.5's pre-fill — but an untrimmed candidate can only
        ever MISS the exact lookup while `search_products`, which strips its
        own query, silently succeeds. A padded label would therefore degrade to
        a hit list for no reason. The arm trims what it queries BY; the
        classification still carries what was printed."""
        pid = catalog_service.create_product(description='plain', mpn=MPN)

        r = catalog_service.resolve_scan(_envelope(f'1P {MPN} '))

        assert r.product is not None and r.product.id == pid
        assert dict(r.classification.ecia_fields)['1P'] == f' {MPN} '

    @pytest.mark.unit
    def test_a_whitespace_only_identifier_never_becomes_the_candidate(
            self, catalog_service, monkeypatch):
        """A blank-but-present `1P` is truthy, so before trimming it became
        `candidates[0]` and the fallthrough searched for nothing — dead-ending
        a label whose OTHER identifier was perfectly usable."""
        pid = catalog_service.create_product(description=f'reel of {MPN}')
        calls = _spy_on_search(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(_envelope('1P   ', f'P{MPN}'))

        assert calls == [MPN]
        assert [p.id for p in r.free_text_hits] == [pid]

    @pytest.mark.unit
    def test_a_trailer_delivered_without_its_rs_still_resolves(
            self, catalog_service):
        """The `RS EOT` trailer's two characters arrive as separate keystrokes,
        so `<data> EOT` with no RS is a reachable shape — and it used to glue
        `'\\x04'` onto the part number, which is not whitespace and so survived
        the candidate trim, turning a product stored character-for-character
        into no product AND no hits. `app/utils/ecia.py` ends the body at
        either terminator now; asserted here as well as in the parser's own
        suite because this is where the cost was paid."""
        pid = catalog_service.create_product(description='plain', mpn=MPN)

        r = catalog_service.resolve_scan(f'[)>\x1e06\x1d1P{MPN}\x04')

        assert dict(r.classification.ecia_fields) == {'1P': MPN}
        assert r.product is not None and r.product.id == pid

    @pytest.mark.unit
    def test_the_same_number_in_both_identifiers_resolves(self, catalog_service):
        """The routine single-source part, where a distributor prints one
        number in both fields. One candidate after the dedupe, one product,
        no false ambiguity."""
        pid = catalog_service.create_product(description='plain', mpn=MPN)

        r = catalog_service.resolve_scan(_envelope(f'1P{MPN}', f'P{MPN}'))

        assert r.product is not None and r.product.id == pid
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_the_match_is_exact_not_substring(self, catalog_service):
        """A part number that merely CONTAINS the scanned one is a different
        part. It is still reachable — through the fallthrough search, which is
        a substring match — so the operator lands on it as a candidate rather
        than having it silently chosen for them."""
        pid = catalog_service.create_product(description='plain',
                                             mpn=f'{MPN}-1PCT')

        r = catalog_service.resolve_scan(_envelope(f'1P{MPN}'))

        assert r.classification.kind is ScanKind.ECIA
        assert r.product is None
        assert [p.id for p in r.free_text_hits] == [pid]

    @pytest.mark.unit
    def test_two_products_sharing_a_part_number_resolve_to_neither(
            self, catalog_service):
        """`products.mpn` is nullable and carries no unique constraint, so any
        number of products can hold the same one (a re-order under a second
        catalog entry, an equivalent part). Returning the oldest of several
        would be a wrong answer rather than a thin one; the ambiguous set comes
        back as hits and Story 4.5 renders a choice.

        The column is the only home where a REPEAT is reachable: `MPN`
        identifier rows are global-scoped, so
        `uq_product_identifiers_type_value_scope` forbids a second product
        holding the same value and `add_identifier` raises there. The other
        ambiguity is cross-home, and
        `test_an_ambiguity_across_the_two_homes_also_falls_through` covers
        it."""
        first = catalog_service.create_product(description='first', mpn=MPN)
        second = catalog_service.create_product(description='second', mpn=MPN)

        r = catalog_service.resolve_scan(_envelope(f'1P{MPN}'))

        assert r.product is None
        assert [p.id for p in r.free_text_hits] == sorted([first, second])

    @pytest.mark.unit
    def test_an_ambiguity_across_the_two_homes_also_falls_through(
            self, catalog_service, product):
        """The same rule when the two matches are of different kinds — one on
        the column, one on an identifier row. A lookup that queried the two
        places separately and took the first non-empty answer would resolve
        this to a product instead."""
        other = catalog_service.create_product(description='other', mpn=MPN)
        catalog_service.add_identifier(product.id,
                                       identifier_type=IdentifierType.MPN,
                                       value=MPN)

        r = catalog_service.resolve_scan(_envelope(f'1P{MPN}'))

        assert r.product is None
        assert sorted(p.id for p in r.free_text_hits) == sorted([product.id, other])

    @pytest.mark.unit
    def test_a_product_matching_in_both_homes_at_once_still_resolves(
            self, catalog_service):
        """The EXISTS-not-join half of the same idiom `search_products` uses:
        one product matching on its column AND on an identifier row must count
        as ONE match, or it would look like an ambiguity and fall through."""
        pid = catalog_service.create_product(description='plain', mpn=MPN)
        catalog_service.add_identifier(pid, identifier_type=IdentifierType.MPN,
                                       value=MPN)

        r = catalog_service.resolve_scan(_envelope(f'1P{MPN}'))

        assert r.product is not None and r.product.id == pid
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_a_miss_falls_through_searching_the_first_candidate(
            self, catalog_service, product, monkeypatch):
        """FR36: a parsed label matching no product becomes a search within the
        same scan — on the part number, never on the raw envelope, whose
        control characters and record separators no column can contain. `1P`
        leads because the ECIA spec makes the supplier part number the required
        field, and that ordering matters only here."""
        calls = _spy_on_search(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(ECIA_FULL)

        assert r.classification.kind is ScanKind.ECIA
        assert r.product is None
        assert calls == [ECIA_FULL_SUPPLIER_PN]
        assert ECIA_FULL not in calls

    @pytest.mark.unit
    def test_a_miss_whose_part_number_appears_in_a_description_finds_it(
            self, catalog_service):
        """Behavioral proof of the same thing: only a search on the parsed part
        number can reach this product."""
        pid = catalog_service.create_product(description=f'reel of {MPN}')

        r = catalog_service.resolve_scan(_envelope(f'1P{MPN}'))

        assert r.product is None
        assert [p.id for p in r.free_text_hits] == [pid]

    @pytest.mark.unit
    def test_a_unique_supplier_hit_is_lost_when_the_customer_number_collides(
            self, catalog_service):
        """Pinned, not endorsed — the first of two consequences of "one query
        over both candidates".

        The row count is over the UNION of the candidates, so `1P` matching
        exactly one product and `P` matching a DIFFERENT one reads as an
        ambiguity and resolves to neither, even though the supplier part number
        — the field the ECIA spec makes required — was unambiguous. `1P` leads
        the candidate list but takes no precedence in the query. The operator
        still reaches the right product, as a hit rather than a landing.
        Closing this means querying per candidate, which the frozen intent
        contract for this arm forbids; deferred, and pinned here so the
        behavior cannot change unnoticed."""
        wanted = catalog_service.create_product(description='wanted', mpn=MPN)
        catalog_service.create_product(description='unrelated',
                                       mpn=CUSTOMER_MPN)

        r = catalog_service.resolve_scan(
            _envelope(f'1P{MPN}', f'P{CUSTOMER_MPN}'))

        assert r.product is None
        assert [p.id for p in r.free_text_hits] == [wanted]

    @pytest.mark.unit
    def test_a_product_reachable_only_by_the_customer_number_dead_ends(
            self, catalog_service):
        """The second consequence: only the FIRST candidate is searched, so a
        product reachable only by the second one comes back with no product and
        no hits. Presence of an extra identifier makes this label resolve to
        LESS than the same label carrying `P` alone — which the second half
        asserts, because "it dead-ends" is only a defect if the product was
        reachable at all. Same root, same deferral."""
        pid = catalog_service.create_product(description=f'reel of {CUSTOMER_MPN}')

        dead_end = catalog_service.resolve_scan(
            _envelope('1PSUP-99999', f'P{CUSTOMER_MPN}'))
        assert dead_end.product is None
        assert dead_end.free_text_hits == ()

        reachable = catalog_service.resolve_scan(_envelope(f'P{CUSTOMER_MPN}'))
        assert [p.id for p in reachable.free_text_hits] == [pid]

    @pytest.mark.unit
    def test_an_envelope_with_no_part_number_issues_no_query_at_all(
            self, catalog_service, product, monkeypatch):
        """A legal terminal state and the one place `resolve_scan` still
        answers without searching: an envelope carrying only quantity, order
        and date identifiers has no part number, so there is no question a
        part-number search could be asking. An empty result is not the claim —
        "nothing was asked" is — so both the search entrypoint and the session
        factory are watched."""
        searches = _spy_on_search(catalog_service, monkeypatch)
        sessions = _count_sessions(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(_envelope('Q10', '9D2612'))

        assert r.classification.kind is ScanKind.ECIA
        assert dict(r.classification.ecia_fields) == {'Q': '10', '9D': '2612'}
        assert r.product is None
        assert r.free_text_hits == ()
        assert searches == []
        assert sessions == []

    @pytest.mark.unit
    def test_a_blank_part_number_reaches_the_same_terminal_state(
            self, catalog_service, product, monkeypatch):
        """The precondition for "no query at all" is no NON-BLANK part-number
        identifier, not no part-number identifier — a distinction the trim
        introduced and the docstring now states. A `1P` holding only spaces IS
        a part-number identifier and does reach `ecia_fields`, but it is
        trimmed away before the candidates are counted, so the label answers
        with no product, no hits and no query, exactly as a `Q`/`9D`-only one
        does. Asserted because the two look nothing alike from the outside and
        a reader planning around the zero-query state needs both."""
        searches = _spy_on_search(catalog_service, monkeypatch)
        sessions = _count_sessions(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(_envelope('1P   '))

        assert r.classification.kind is ScanKind.ECIA
        assert dict(r.classification.ecia_fields) == {'1P': '   '}
        assert r.product is None
        assert r.free_text_hits == ()
        assert searches == []
        assert sessions == []

    @pytest.mark.unit
    def test_two_exact_matches_are_discarded_while_the_other_candidate_is_searched(
            self, catalog_service, monkeypatch):
        """The third consequence of "one query over both candidates, one search
        on the first", and the worst of the three: `1P` matches nothing while
        `P` matches two products EXACTLY, so the union is ambiguous and both
        exact matches are dropped, and then the fallthrough searches `1P` and
        finds nothing. The arm held two exact matches and answered with no
        product and no hits.

        The control is the assertion that makes it a defect rather than a
        preference: the SAME label carrying `P` alone returns both products as
        hits, so the extra identifier made the label resolve to less."""
        first = catalog_service.create_product(description='w1', mpn=MPN)
        second = catalog_service.create_product(description='w2', mpn=MPN)
        searches = _spy_on_search(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(_envelope('1PSUP-99999', f'P{MPN}'))

        assert r.product is None
        assert r.free_text_hits == ()
        assert searches == ['SUP-99999']

        control = catalog_service.resolve_scan(_envelope(f'P{MPN}'))
        assert control.product is None
        assert [p.id for p in control.free_text_hits] == [first, second]

    @pytest.mark.unit
    def test_a_lookup_that_hits_opens_exactly_one_session(
            self, catalog_service, monkeypatch):
        """The session-count rule the docstring states: one for the lookup, and
        no second one because a hit never reaches the fallthrough. Both
        candidates are tried in that ONE query rather than in one query each."""
        catalog_service.create_product(description='plain', mpn=MPN)
        sessions = _count_sessions(catalog_service, monkeypatch)

        assert catalog_service.resolve_scan(
            _envelope(f'1P{MPN}')).product is not None
        assert len(sessions) == 1

    @pytest.mark.unit
    def test_a_vendor_sku_identifier_row_is_never_matched(
            self, catalog_service, product):
        """A distributor part number in `P` is conceptually a vendor SKU, but
        `VENDOR_SKU` is vendor-scoped (AD-9): its uniqueness is per vendor, so
        an unscoped exact match could resolve a DigiKey label to a product
        identified by an identical Mouser number. The scan carries no vendor,
        so the row is reachable only through the fallthrough search."""
        catalog_service.add_identifier(product.id,
                                       identifier_type=IdentifierType.VENDOR_SKU,
                                       value=MPN, vendor='Acme')

        r = catalog_service.resolve_scan(_envelope(f'1P{MPN}'))

        assert r.product is None
        assert [p.id for p in r.free_text_hits] == [product.id]

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '[)>\x1e06',                          # a legal but empty message
        '[)>\x1e06\x1d!!!garbage!!!',         # a valid header, an unreadable body
        ']d1[)>\x1e06\x1d!!!garbage!!!',      # ...behind an AIM identifier
    ])
    def test_a_degraded_envelope_lands_on_the_free_text_arm(
            self, catalog_service, product, monkeypatch, raw):
        """AD-5/NFR8: an envelope nothing could be read out of is not `ecia` at
        all — the classifier degrades it — so it arrives here as free text and
        is searched as scanned (AIM prefix stripped). It lands somewhere and it
        never raises, which is the whole of "surfaced for manual handling"."""
        calls = _spy_on_search(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(raw)

        assert r.classification.kind is ScanKind.FREE_TEXT
        assert r.classification.ecia_fields is None
        assert r.classification.raw == raw
        assert calls == [scan_router.strip_aim_prefix(raw)]

    @pytest.mark.unit
    def test_a_degraded_envelope_can_still_reach_a_product(
            self, catalog_service):
        """The half the spy cannot show: the raw scan really is searched, so an
        operator whose label parsed badly still lands on a record if anything
        in the catalog carries that text."""
        pid = catalog_service.create_product(description='plain',
                                             notes='[)>\x1e06\x1d!!!garbage!!!')

        r = catalog_service.resolve_scan('[)>\x1e06\x1d!!!garbage!!!')

        assert [p.id for p in r.free_text_hits] == [pid]

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '[)>\x1e06\x1d1P' + '\x00' * 10 + '\x1e\x04',   # a NUL-bearing part number
        '[)>\x1e06\x1d1P\ud800\x1e\x04',                # ...and a lone surrogate
        '[)>\x1e06\x1d1P' + '9' * SEARCH_QUERY_MAX_LENGTH,   # a field value ON the pattern bound
        '[)>\x1e06\x1d1P' + '9' * (SEARCH_QUERY_MAX_LENGTH + 1),  # ...and one past it
        '[)>\x1e06' + '\x1d' * 4096,                    # four kilobytes of empty records
        '[)>\x1e06\x1dP%\x1d1P_\x1e\x04',               # bare LIKE wildcards as part numbers
    ])
    def test_a_hostile_envelope_still_yields_a_resolution(
            self, catalog_service, product, raw):
        """NFR8, and the half that actually failed elsewhere in this module:
        never "every product". Whatever the label carries, resolution answers
        with a `ScanResolution` and never with the whole catalog.

        Read `test_which_hostile_vectors_actually_reach_the_lookup` before
        trusting this parametrization as ECIA-arm coverage: three of these six
        vectors never reach the lookup, and one of those three is not even an
        ECIA scan. That test names each one and where it is answered."""
        catalog_service.create_product(description='an unrelated widget',
                                       manufacturer='ACME', mpn='XYZ-1')

        r = catalog_service.resolve_scan(raw)

        assert isinstance(r, ScanResolution)
        assert r.classification.raw == raw
        assert r.product is None
        assert r.free_text_hits == ()

    @pytest.mark.unit
    @pytest.mark.parametrize('raw, kind, reaches_the_lookup', [
        ('[)>\x1e06\x1d1P' + '\x00' * 10 + '\x1e\x04',
         ScanKind.ECIA, False),                                  # NUL
        ('[)>\x1e06\x1d1P\ud800\x1e\x04',
         ScanKind.ECIA, False),                                  # lone surrogate
        ('[)>\x1e06' + '\x1d' * 4096,
         ScanKind.FREE_TEXT, True),                              # empty records
        ('[)>\x1e06\x1d1P' + '9' * SEARCH_QUERY_MAX_LENGTH,
         ScanKind.ECIA, True),
        ('[)>\x1e06\x1d1P' + '9' * (SEARCH_QUERY_MAX_LENGTH + 1),
         ScanKind.ECIA, True),
        ('[)>\x1e06\x1dP%\x1d1P_\x1e\x04',
         ScanKind.ECIA, True),                                   # LIKE wildcards
    ])
    def test_which_hostile_vectors_actually_reach_the_lookup(
            self, catalog_service, product, monkeypatch, raw, kind,
            reaches_the_lookup):
        """Where each hostile vector is answered, asserted rather than assumed.
        Every vector the class above parametrizes appears here, in the same
        order, so the two lists cannot drift apart silently.

        Two things divert a vector before this story's lookup, and the class
        above cannot tell either from a real ECIA-arm pass.

        `_is_storable_text(raw)` judges the WHOLE envelope and runs before the
        four-way branch, so a NUL or a lone surrogate anywhere in the scan is
        answered with no product and no hits without the ECIA arm ever running.
        That is worth pinning in both directions, because the deferred-work
        ledger proposes moving that guard from `raw` to the text each arm
        binds: on the day it moves, those two vectors start reaching a query
        built from a lone surrogate, and this test goes red where the one above
        would stay green.

        And four kilobytes of empty records is not an ECIA scan at all. Every
        element is empty, so `parse_fields` recognizes nothing and rule 2
        degrades it to `FREE_TEXT` (AD-5, NFR8) — it exercises the free-text
        arm, which does open a session. Asserting the kind here is the point:
        without it the vector reads as ECIA-arm coverage in a class that says
        it is."""
        catalog_service.create_product(description='an unrelated widget',
                                       manufacturer='ACME', mpn='XYZ-1')
        sessions = _count_sessions(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(raw)

        assert r.classification.kind is kind
        assert bool(sessions) is reaches_the_lookup
        assert r.product is None
        assert r.free_text_hits == ()


class TestFallthrough:
    """Rule 4 and the FR36 miss paths: no scan dead-ends, and each arm searches
    the text that can actually match something."""

    @pytest.mark.unit
    def test_free_text_finds_a_described_product(self, catalog_service, product):
        r = catalog_service.resolve_scan('RES 10K')
        assert r.classification.kind is ScanKind.FREE_TEXT
        assert r.product is None
        assert [p.id for p in r.free_text_hits] == [product.id]

    @pytest.mark.unit
    def test_an_aim_prefix_is_stripped_before_searching_but_kept_on_raw(
            self, catalog_service, product, monkeypatch):
        """`classification.raw` is the verbatim scan (AD-15); text that gets
        *used* is AIM-stripped via the exported helper."""
        calls = _spy_on_search(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(']d1RES 10K')

        assert calls == ['RES 10K']
        assert r.classification.raw == ']d1RES 10K'
        assert [p.id for p in r.free_text_hits] == [product.id]

    @pytest.mark.unit
    def test_nothing_matching_anything_is_a_legal_terminal_state(
            self, catalog_service, product):
        """FR40's seam: Story 4.5 renders this as a pre-filled create form."""
        r = catalog_service.resolve_scan('nothing matches this')
        assert r.classification.kind is ScanKind.FREE_TEXT
        assert r.product is None
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_an_empty_scan_is_never_every_product(self, catalog_service, product):
        r = catalog_service.resolve_scan('')
        assert r.classification.kind is ScanKind.FREE_TEXT
        assert r.product is None
        assert r.free_text_hits == ()

    @pytest.mark.unit
    def test_the_fallthrough_goes_through_the_single_ad17_entrypoint(
            self, catalog_service, product, monkeypatch):
        """AD-17: there is no second search implementation to keep in step. If
        `search_products` is neutered, every fallthrough goes quiet with it."""
        monkeypatch.setattr(catalog_service, 'search_products',
                            lambda *a, **k: [])

        assert catalog_service.resolve_scan('RES 10K').free_text_hits == ()


class TestConfigSeam:
    """AD-16, and the flow `4-2-pure-scan-classifier.md` recorded as unproven:
    the grammar comes from the one named config pair, read in the service on
    every call and passed into the pure classifier."""

    SOURCE_PATH = Path(mariadb_catalog_service.__file__)

    def _string_literals_outside_docstrings(self, path: Path):
        """Every `str` constant the file actually executes.

        Docstrings are excluded because they are prose, not behavior — the same
        reasoning `tests/unit/test_scan_router.py`'s guard records. A substring
        scan over raw source is a false-positive machine here: the AI is two
        characters and both files are dense with explanatory prose.
        """
        tree = ast.parse(path.read_text(encoding='utf-8'))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docstrings.add(id(first.value))
        return [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings]

    @pytest.mark.unit
    def test_reconfiguring_the_pair_moves_recognition_with_it(
            self, catalog_service, product, monkeypatch):
        """The acceptance criterion: two calls in ONE process, differing only in
        the config pair, classify the same shape of scan differently. That can
        only hold if the pair is read during the call rather than captured at
        import or cached on the service."""
        configured_scan = _internal_scan(product.internal_id)
        alt_ai = _shifted(Config.GS1_INTERNAL_AI)
        alt_token = _shifted(Config.GS1_INTERNAL_TOKEN)
        # Precondition, not an assertion about the code: if the derived pair
        # were the configured one the test below would be vacuous.
        assert (alt_ai, alt_token) != (Config.GS1_INTERNAL_AI,
                                       Config.GS1_INTERNAL_TOKEN)

        # Before: the configured grammar is what resolves.
        assert catalog_service.resolve_scan(
            configured_scan).classification.kind is ScanKind.INTERNAL

        monkeypatch.setattr(Config, 'GS1_INTERNAL_AI', alt_ai)
        monkeypatch.setattr(Config, 'GS1_INTERNAL_TOKEN', alt_token)

        # After: the new grammar resolves to the same product...
        reconfigured = catalog_service.resolve_scan(
            _internal_scan(product.internal_id, ai=alt_ai, token=alt_token))
        assert reconfigured.classification.kind is ScanKind.INTERNAL
        assert reconfigured.product.id == product.id

        # ...and the old one no longer does, which is the half that proves
        # nothing cached the previous grammar.
        stale = catalog_service.resolve_scan(configured_scan)
        assert stale.classification.kind is not ScanKind.INTERNAL
        assert stale.product is None

    @pytest.mark.unit
    def test_the_pair_is_read_on_every_call_not_captured_once(
            self, catalog_service, product, monkeypatch):
        """A grammar cached on `self` at construction would survive the first
        assertion above only if the service had never been used beforehand.
        Here it is used first, deliberately."""
        catalog_service.resolve_scan(_internal_scan(product.internal_id))

        monkeypatch.setattr(Config, 'GS1_INTERNAL_AI',
                            _shifted(Config.GS1_INTERNAL_AI))

        assert catalog_service.resolve_scan(
            _internal_scan(product.internal_id)
        ).classification.kind is ScanKind.INTERNAL

    @pytest.mark.unit
    @pytest.mark.parametrize('path_name', ['module', 'this test file'])
    def test_no_executed_string_literal_holds_the_configured_grammar(self, path_name):
        """AD-16's literal ban, enforced over the new service code AND over
        this file.

        The values are read from `Config`, never restated: hardcoding them here
        would defeat the rule the test enforces, because changing the config
        pair would leave a literal test guarding a grammar that is no longer
        deployed while the code hardcoded the new one and stayed green.

        The test file is checked too because a suite that asserted resolution
        against a hardcoded `'96WIT…'` would go red the moment the pair was
        reconfigured — turning a supported config change into a broken build,
        which is the same drift from the other direction.
        """
        path = self.SOURCE_PATH if path_name == 'module' else Path(__file__)
        literals = self._string_literals_outside_docstrings(path)
        ai, token = Config.GS1_INTERNAL_AI, Config.GS1_INTERNAL_TOKEN
        assert ai and token, 'the pair must be configured for this test to mean anything'

        # What counts as "holding the grammar" has to be stated precisely, or
        # the guard red-builds correct code. A naked substring scan does: the
        # AI is two characters, so it appears inside ordinary data. Verified
        # over all 100 two-digit AIs against this suite's own literals — 40
        # collide, among them AI='91' with token='ZZ', which is the exact pair
        # the story's I/O matrix names for the reconfiguration scenario (it
        # matched ABSENT_INTERNAL_ID, 'ZZZZZZZZZZ'); AI='95' and AI='40' match
        # the GTIN vectors, and AI='17' matches the service module's own
        # "AD-17" in a NotImplementedError message. A test that fails whenever
        # a supported config change is made is the very drift it exists to
        # prevent, from the other direction.
        #
        # A literal holds the grammar when it IS one half of the pair, or when
        # it carries the two joined — which is the shape a hardcoded default
        # ('96', 'WIT') or a hardcoded scan ('96WITABC1234567') actually takes.
        # Mutation-tested both ways; see the two tests below, which are the
        # executable form of that claim.
        marker = f'{ai}{token}'
        offenders = [lit for lit in literals
                     if lit in (ai, token) or marker in lit]
        assert not offenders, (
            f'{path.name} executes a string literal holding the configured '
            f'grammar (ai={ai!r}, token={token!r}): {offenders!r}. AD-16 '
            f'requires the grammar to arrive from Config.')

    @pytest.mark.unit
    @pytest.mark.parametrize('injected', [
        'AI_ALONE',        # a hardcoded default for one half of the pair
        'TOKEN_ALONE',     # ...and for the other
        'JOINED_IN_SCAN',  # a hardcoded element string, the realistic mistake
    ])
    def test_the_literal_guard_catches_a_hardcoded_grammar(self, injected):
        """The guard above is only worth its false-negative risk if it still
        fires on the thing it bans. Rather than trusting a manual mutation that
        has to be remembered and reverted, run the same predicate over a
        synthetic literal set."""
        ai, token = Config.GS1_INTERNAL_AI, Config.GS1_INTERNAL_TOKEN
        literals = {
            'AI_ALONE': [ai],
            'TOKEN_ALONE': [token],
            'JOINED_IN_SCAN': [f'{ai}{token}ABC1234567'],
        }[injected]

        marker = f'{ai}{token}'
        offenders = [lit for lit in literals
                     if lit in (ai, token) or marker in lit]

        assert offenders, (
            f'the AD-16 predicate failed to flag {literals!r} — it would let a '
            f'hardcoded grammar through.')

    @pytest.mark.unit
    def test_the_literal_guard_does_not_fire_on_ordinary_data(self):
        """The other half: data that merely CONTAINS the two-character AI is
        not a hardcoded grammar. These are this suite's own vectors, which a
        substring scan flagged for 40 of the 100 legal AI values.

        Both dimensions are swept, not just the AI. The collision that made the
        old predicate fire on `ABSENT_INTERNAL_ID = 'ZZZZZZZZZZ'` was in the
        TOKEN dimension (`token='ZZ'`), so an AI-only sweep with the token
        pinned to the configured value cannot reproduce the very failure this
        test is named for."""
        innocent = [GTIN13, GTIN8, GTIN_UNSTORED, ABSENT_INTERNAL_ID,
                    'RES 10K 0805 1%',
                    Config.GS1_INTERNAL_AI, Config.GS1_INTERNAL_TOKEN]

        # EVERY token probe is COMPUTED, with no exceptions, for the reason
        # stated two lines down — and the two that were spelled out anyway are
        # why the rule now has no exceptions. `'AB'` and `'XY'` sat here as
        # literals directly beneath a comment explaining that spelling a probe
        # plants it in the file the guard scans, and they did exactly that: a
        # deployment configuring `token='AB'` or `token='XY'` red-built this
        # file on its own probe list, which is the false positive this whole
        # class exists to eliminate. It went unnoticed because the pass that
        # added them recorded `17/AB` and `40/XY` as verified green without
        # re-running them after the edit. The fourth demonstration in this
        # class that a literal ban has to be enforced against itself.
        #
        # Residual, and inherent rather than fixable here: the predicate is an
        # exact match on a CONFIGURABLE string, and `gs1` permits any printable
        # ASCII token, so any short literal anywhere in these two files
        # ('mpn', 'kind', 'ACME', 'raw', …) collides with a deployment that
        # picks that exact token. Narrowing the predicate further is what
        # reintroduces the substring false positives; the practical bound is
        # that a shop's token is an uppercase mnemonic and the remaining
        # short literals are lowercase identifiers and test data.
        token_probes = (
            Config.GS1_INTERNAL_TOKEN,        # the deployed half
            chr(ord('A') + 25) * 2,           # the historic ABSENT_INTERNAL_ID hit
            chr(ord('A') + 16) * 2,
            chr(ord('A')) + chr(ord('A') + 1),
            chr(ord('A') + 23) + chr(ord('A') + 24),
        )
        for ai_probe in (f'{n:02d}' for n in range(100)):
            for token_probe in token_probes:
                probe_marker = f'{ai_probe}{token_probe}'
                # The configured pair itself is excluded per probe, not from
                # the vector list: a vector that IS one half of the pair being
                # probed is a true positive of the predicate, and the two
                # entries above are in the list precisely so the pinned
                # assertion below sees them.
                offenders = [lit for lit in innocent
                             if lit not in (ai_probe, token_probe)
                             and probe_marker in lit]
                assert not offenders, (
                    f'AD-16 predicate false-positived on ordinary data for '
                    f'ai={ai_probe!r} token={token_probe!r}: {offenders!r}')

        # And the predicate's positive direction still holds for the pair this
        # deployment actually runs: the two halves ARE offenders.
        ai, token = Config.GS1_INTERNAL_AI, Config.GS1_INTERNAL_TOKEN
        marker = f'{ai}{token}'
        assert [lit for lit in innocent if lit in (ai, token)] == [ai, token]
        assert not [lit for lit in (GTIN13, GTIN8, 'RES 10K 0805 1%')
                    if lit in (ai, token) or marker in lit]

    @pytest.mark.unit
    def test_the_suite_survives_the_stories_own_reconfiguration_pair(
            self, catalog_service, product, monkeypatch):
        """The Verification section requires that reconfiguring the pair leaves
        the suite green. The pair the story's I/O matrix names is ('91','ZZ'),
        which the previous substring form of this guard rejected because 'ZZ'
        occurs inside ABSENT_INTERNAL_ID. Pin the end-to-end behavior under
        exactly that pair, so the requirement is executable rather than a
        manual ritual nobody re-runs.

        The pair is COMPUTED, not written down: spelling it as a literal here
        would plant it in this very file and the guard would flag it — which is
        the same self-defeat in miniature, and a neat demonstration of why the
        rule has to be "is the grammar" rather than "contains the AI"."""
        alt_ai = ''.join(str(digit) for digit in (9, 1))
        alt_token = chr(ord('A') + 25) * 2
        monkeypatch.setattr(Config, 'GS1_INTERNAL_AI', alt_ai)
        monkeypatch.setattr(Config, 'GS1_INTERNAL_TOKEN', alt_token)

        literals = self._string_literals_outside_docstrings(Path(__file__))
        literals += self._string_literals_outside_docstrings(self.SOURCE_PATH)
        marker = f'{alt_ai}{alt_token}'
        assert not [lit for lit in literals
                    if lit in (alt_ai, alt_token) or marker in lit]

        resolved = catalog_service.resolve_scan(
            _internal_scan(product.internal_id))
        assert resolved.classification.kind is ScanKind.INTERNAL
        assert resolved.product.id == product.id

    @pytest.mark.unit
    def test_the_service_passes_the_pair_as_keyword_arguments(
            self, catalog_service, monkeypatch):
        """`classify(raw, *, ai, token)` is keyword-only, so this cannot be
        anything else — but it also pins that the values handed over are the
        Config ones and not, say, re-derived from the raw scan."""
        seen = {}
        real = scan_router.classify

        def spy(raw, *, ai, token):
            seen.update(raw=raw, ai=ai, token=token)
            return real(raw, ai=ai, token=token)

        monkeypatch.setattr(mariadb_catalog_service.scan_router, 'classify', spy)

        catalog_service.resolve_scan('anything')

        assert seen['ai'] == Config.GS1_INTERNAL_AI
        assert seen['token'] == Config.GS1_INTERNAL_TOKEN
        assert seen['raw'] == 'anything'


class TestNeverRaisesOnScanData:
    """NFR8: no value of a `str` scan makes resolution raise. The scanner is
    the least trustworthy input in the system and an operator holding a bad
    label must land somewhere, never on an error page."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '',
        ' ',
        '\x00' * 4096,                       # four kilobytes of NULs
        ''.join(chr(c) for c in range(1, 32)) * 128,   # every C0 control, repeated
        '\x1d' * 512,
        ']',                                 # a lone AIM opener
        ']d',                                # a truncated AIM prefix
        ']d1',                               # a prefix and nothing else
        '[)>',                               # a truncated ECIA header
        '[)>\x1e0',                          # ...truncated mid format indicator
        '[)>\x1e06',                         # a legal but empty envelope
        '[)>\x1e07\x1dP1',                   # a different format indicator
        '%',                                 # bare LIKE wildcards
        '_',
        '\\',
        '%_\\%',
        "'; DROP TABLE products; --",
        '\\%' * 1000,
        '\U0001f600' * 100,                  # astral-plane emoji
        '‮' + 'gnihtemos',              # a right-to-left override
        '9' * 4096,                          # all digits, no valid check digit
        '00000000',                          # the classic wedge no-read
        '\ud800',                            # an unpaired surrogate: legal in a
        '\ud800abc',                         # Python str, unencodable as UTF-8
        'abc\udfff',                         # ...and as a trailing one
    ])
    def test_hostile_scan_data_always_yields_a_resolution(self, catalog_service,
                                                          product, raw):
        """Not raising is only half of NFR8. The other half — every hit
        actually contains what was searched — is asserted here because it is
        the half that failed: `'\\x00' * 4096` sat in this parametrization for
        two review passes returning the ENTIRE catalog as scan hits, and a test
        that checked only the return type could not see it.

        The invariant is the mechanism's own definition (case-folded contiguous
        substring), so it holds for every vector without special-casing any of
        them, and it is checked against the same six columns
        `search_products` searches."""
        catalog_service.create_product(description='an unrelated widget',
                                       manufacturer='ACME', mpn='XYZ-1')
        catalog_service.create_product(description='another unrelated thing')

        r = catalog_service.resolve_scan(raw)

        assert isinstance(r, ScanResolution)
        assert r.classification.raw == raw
        assert r.product is None, 'no hostile vector matches a real record'
        needle = scan_router.strip_aim_prefix(raw).strip().lower()
        for hit in r.free_text_hits:
            haystack = ' '.join(
                v.lower() for v in
                [hit.internal_id, hit.description, hit.notes, hit.manufacturer,
                 hit.mpn]
                + [i.value for i in
                   catalog_service.get_identifiers_for_product(hit.id)]
                if v)
            assert needle in haystack, (
                f'{raw!r} was reported as matching product {hit.id}, whose '
                f'searched text does not contain it')

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', ['\ud800', '\ud800abc', 'abc\udfff'])
    def test_an_unencodable_scan_resolves_to_nothing_instead_of_raising(
            self, catalog_service, product, monkeypatch, raw):
        """The one NFR8 hole a pure classifier cannot have: this method is the
        first to put scan text on the wire to a database.

        An unpaired surrogate is a legal `str` that `_clean_scan_input` passes
        through untouched, but it has no UTF-8 encoding, so binding it as a
        query parameter raises `UnicodeEncodeError` — verified identically
        under SQLite and documented the same for PyMySQL. Nothing stored can
        equal or contain a string that cannot exist in the database, so the
        no-match resolution is not merely the safe answer, it is the correct
        one — and it is reached without issuing a query at all."""
        calls = _spy_on_search(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(raw)

        assert r.classification.kind is ScanKind.FREE_TEXT
        assert r.product is None
        assert r.free_text_hits == ()
        assert calls == [], 'the unencodable text must never reach the search'

    @pytest.mark.unit
    def test_an_unencodable_search_query_returns_no_hits_instead_of_raising(
            self, catalog_service, product):
        """`resolve_scan` short-circuits before the fallthrough, but
        `search_products` is a public entrypoint Epic 8 calls directly and must
        not be the one that raises."""
        assert catalog_service.search_products('\ud800abc') == []

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '\x00',                  # a bare NUL: the pattern becomes '%'
        '\x00' * 4096,           # the wedge no-read, at scan length
        '\x00RES',               # leading — everything after it is discarded
        'RES\x0010K',            # embedded — the pattern becomes '%RES'
        'RES 10K\x00',           # trailing — the closing '%' is discarded
    ])
    def test_a_scan_carrying_a_nul_never_matches_anything(self, catalog_service,
                                                          product, monkeypatch,
                                                          raw):
        """A NUL binds without error and then compares WRONG: SQLite reads a
        LIKE pattern as a C string and stops at the first NUL, so `'%…%'`
        silently becomes a PREFIX of itself.

        Measured before the guard, against the real SQLite backend: with five
        products stored, `search_products('\\x00')` returned all five (the
        pattern degenerated to a bare `'%'`) and `'a\\x00b'` ran as `'%a'` and
        returned the rows ENDING in `a`. Both break the rule stated three ways
        in this module — "never every product", "wildcards match literally",
        and the `search_products` length bound's own reason for answering `[]`
        rather than truncating: a truncated pattern answers a different
        question. The trailing case is the subtle one — it still starts with
        the query, so it reads as correct while actually anchoring the match to
        the end of the column.

        `[]` is the correct answer and not merely the safe one: no value this
        application stores contains a NUL. And it is reached without a query,
        which the spy asserts — `_is_storable_text` runs on `raw` before any
        arm, so no NUL text ever reaches a pattern.

        Note the direction of the divergence: PyMySQL escapes `\\0` in the
        literal it emits, so MariaDB compares the whole pattern and would have
        answered nothing all along. SQLite is the only backend that fails, and
        the only backend any test here runs — invert that and this defect
        would be unreachable from the suite forever.
        """
        for i in range(4):
            catalog_service.create_product(description=f'FILLER {i}')
        calls = _spy_on_search(catalog_service, monkeypatch)

        r = catalog_service.resolve_scan(raw)

        assert r.product is None
        assert r.free_text_hits == ()
        assert calls == [], 'NUL text must never reach a LIKE pattern'

    @pytest.mark.unit
    @pytest.mark.parametrize('query', ['\x00', 'a\x00b', 'RES 10K\x00'])
    def test_a_search_query_carrying_a_nul_returns_no_hits(self, catalog_service,
                                                           product, query):
        """The `search_products` counterpart, for the same reason the
        unencodable-query test has one: Epic 8's search box calls this method
        directly and does not pass through `resolve_scan`'s guard."""
        for i in range(4):
            catalog_service.create_product(description=f'FILLER {i}')
        assert catalog_service.search_products(query) == []

    @pytest.mark.unit
    @pytest.mark.parametrize('needle', ['%', '_', '\\'])
    def test_wildcard_characters_match_literally_not_as_patterns(
            self, catalog_service, needle):
        """If they were passed through unescaped, a bare `%` would return the
        whole catalog — the "never every product" rule from the other side."""
        matching = catalog_service.create_product(description=f'part {needle} one')
        catalog_service.create_product(description='an unrelated widget')

        hits = catalog_service.resolve_scan(needle).free_text_hits

        assert [p.id for p in hits] == [matching]


class TestCallerAndDeploymentFaults:
    """The only two exceptions `resolve_scan` raises that are not the
    database's: one is a malformed caller, the other a broken deployment.
    Neither is a property of the scan."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [123, None, 12.5, ['a'], object()])
    def test_a_non_string_scan_is_a_typeerror_from_classify(self, catalog_service,
                                                            raw):
        with pytest.raises(TypeError):
            catalog_service.resolve_scan(raw)

    @pytest.mark.unit
    def test_bytes_are_rejected_too(self, catalog_service, product):
        """The most plausible wrong type: a transport that forgot to decode."""
        with pytest.raises(TypeError):
            catalog_service.resolve_scan(
                _internal_scan(product.internal_id).encode('ascii'))

    @pytest.mark.unit
    @pytest.mark.parametrize('attr, value', [
        ('GS1_INTERNAL_AI', ''),
        ('GS1_INTERNAL_AI', None),
        ('GS1_INTERNAL_AI', ' 1 '),          # padded, invisible in an editor
        ('GS1_INTERNAL_TOKEN', ''),
        ('GS1_INTERNAL_TOKEN', None),
    ])
    def test_a_malformed_configured_grammar_propagates_unchanged(
            self, catalog_service, monkeypatch, attr, value):
        """Deliberately NOT translated to a ValidationError, unlike
        `encode_internal_payload`: that method's bad input is a user-supplied
        id, whereas this is a deployment fault. Translating it would dress a
        broken configuration up as a rejected scan, and swallowing it would
        silently disable rule 1 so every label this shop printed would quietly
        resolve as free text."""
        monkeypatch.setattr(Config, attr, value)
        with pytest.raises(InvalidGs1PayloadError):
            catalog_service.resolve_scan('anything at all')

    @pytest.mark.unit
    def test_the_deployment_fault_is_not_a_validationerror(self, catalog_service,
                                                            monkeypatch):
        from app.exceptions import ValidationError

        monkeypatch.setattr(Config, 'GS1_INTERNAL_TOKEN', '')
        with pytest.raises(InvalidGs1PayloadError) as exc:
            catalog_service.resolve_scan('anything at all')
        assert not isinstance(exc.value, ValidationError)


class TestSearchProducts:
    """AD-17's single free-text entrypoint, which Epic 8 consumes unchanged."""

    ZEBRA = 'ZEBRA'

    def _one_product_per_covered_field(self, catalog_service):
        """A product carrying the needle in each of the six covered places."""
        ids = {
            'description': catalog_service.create_product(
                description=f'{self.ZEBRA} striped resistor'),
            'notes': catalog_service.create_product(
                description='plain', notes=f'kept beside the {self.ZEBRA} reel'),
            'manufacturer': catalog_service.create_product(
                description='plain', manufacturer=f'{self.ZEBRA} Components'),
            'mpn': catalog_service.create_product(
                description='plain', mpn=f'{self.ZEBRA}-1234'),
        }
        ids['identifier'] = catalog_service.create_product(description='plain')
        catalog_service.add_identifier(ids['identifier'],
                                       identifier_type=IdentifierType.VENDOR_SKU,
                                       value=f'SKU-{self.ZEBRA}-9', vendor='Acme')

        # internal_id is generated by create_product and is immutable through
        # the service (Story 2.4), so the only way to stage a product whose
        # internal_id carries the needle is to set the column directly — the
        # same direct-session staging tests/unit/test_catalog_service.py uses to
        # backdate updated_at. The mirrored INTERNAL identifier row is left
        # holding the generated value on purpose, so this row can only be
        # reached through the internal_id column itself.
        from app.database import Product
        ids['internal_id'] = catalog_service.create_product(description='plain')
        session = catalog_service.Session()
        try:
            session.query(Product).filter(Product.id == ids['internal_id']).update(
                {'internal_id': f'{self.ZEBRA}0001'}, synchronize_session=False)
            session.commit()
        finally:
            session.close()
        return ids

    @pytest.mark.unit
    def test_every_covered_field_group_is_searched(self, catalog_service):
        ids = self._one_product_per_covered_field(catalog_service)
        catalog_service.create_product(description='an unrelated widget')

        found = [p.id for p in catalog_service.search_products(self.ZEBRA)]

        assert sorted(found) == sorted(ids.values())
        assert len(found) == len(set(found))   # each exactly once

    @pytest.mark.unit
    def test_a_generated_internal_id_is_searchable_as_stored(self, catalog_service):
        """The natural-path version of the internal_id row above: whatever
        create_product generated must be findable without staging."""
        pid = catalog_service.create_product(description='plain')
        internal_id = catalog_service.get_product(pid).internal_id

        assert [p.id for p in catalog_service.search_products(internal_id)] == [pid]

    @pytest.mark.unit
    @pytest.mark.parametrize('query', ['zebra', 'ZeBrA', 'ZEBRA', 'zEbRa'])
    def test_matching_is_case_folded(self, catalog_service, query):
        pid = catalog_service.create_product(description='ZEBRA striped resistor')
        assert [p.id for p in catalog_service.search_products(query)] == [pid]

    @pytest.mark.unit
    def test_a_product_matching_several_identifiers_appears_once(
            self, catalog_service):
        """The EXISTS subquery, not a join: a join would emit one row per
        matching identifier, and a SQL DISTINCT would be the wrong fix."""
        pid = catalog_service.create_product(description='plain')
        for suffix, itype in (('1', IdentifierType.ASIN),
                              ('2', IdentifierType.MPN),
                              ('3', IdentifierType.VENDOR_SKU)):
            catalog_service.add_identifier(pid, identifier_type=itype,
                                           value=f'ZEBRA-{suffix}', vendor='Acme')

        assert [p.id for p in catalog_service.search_products('zebra')] == [pid]

    @pytest.mark.unit
    @pytest.mark.parametrize('needle, stored, decoy', [
        ('10%', '10%25', '10025 ordinary'),
        ('a_b', 'a_b marked', 'axb ordinary'),
        ('c\\d', 'c\\d marked', 'cd ordinary'),
    ])
    def test_user_wildcards_are_escaped_and_match_literally(
            self, catalog_service, needle, stored, decoy):
        wanted = catalog_service.create_product(description='plain', mpn=stored)
        catalog_service.create_product(description=decoy, mpn=decoy)

        assert [p.id for p in catalog_service.search_products(needle)] == [wanted]

    @pytest.mark.unit
    @pytest.mark.parametrize('query', ['', '   ', '\t\n', None])
    def test_a_blank_query_returns_nothing_not_the_whole_catalog(
            self, catalog_service, query):
        catalog_service.create_product(description='a widget')
        assert catalog_service.search_products(query) == []

    @pytest.mark.unit
    def test_a_query_is_matched_after_trimming(self, catalog_service):
        pid = catalog_service.create_product(description='ZEBRA striped resistor')
        assert [p.id for p in catalog_service.search_products('  zebra  ')] == [pid]

    @pytest.mark.unit
    def test_results_are_ascending_by_id_and_stable(self, catalog_service):
        ids = [catalog_service.create_product(description=f'ZEBRA {i}')
               for i in range(5)]
        first = [p.id for p in catalog_service.search_products('zebra')]
        second = [p.id for p in catalog_service.search_products('zebra')]
        assert first == sorted(ids) == second

    @pytest.mark.unit
    def test_the_default_limit_bounds_the_result_set(self, catalog_service):
        ids = [catalog_service.create_product(description=f'ZEBRA {i}')
               for i in range(SEARCH_RESULTS_DEFAULT_LIMIT + 5)]
        found = [p.id for p in catalog_service.search_products('zebra')]
        assert found == sorted(ids)[:SEARCH_RESULTS_DEFAULT_LIMIT]

    @pytest.mark.unit
    def test_the_max_limit_caps_what_a_caller_may_ask_for(self, catalog_service):
        for i in range(SEARCH_RESULTS_MAX_LIMIT + 5):
            catalog_service.create_product(description=f'ZEBRA {i}')
        assert len(catalog_service.search_products(
            'zebra', limit=SEARCH_RESULTS_MAX_LIMIT * 10)) == SEARCH_RESULTS_MAX_LIMIT

    @pytest.mark.unit
    @pytest.mark.parametrize('limit', [0, -1, -1000])
    def test_a_non_positive_limit_clamps_up_to_one(self, catalog_service, limit):
        for i in range(3):
            catalog_service.create_product(description=f'ZEBRA {i}')
        assert len(catalog_service.search_products('zebra', limit=limit)) == 1

    @pytest.mark.unit
    @pytest.mark.parametrize('limit', ['ten', None, object(), 1.5,
                                       float('inf'), float('nan'),
                                       Decimal('Infinity'), True, False])
    def test_a_non_integer_limit_falls_back_to_the_default(self, catalog_service,
                                                            limit):
        """Mirrors get_field_value_suggestions' clamp. `1.5` is not a fallback
        case — int() accepts it — so it lands on 1, which is the point of
        listing it: the fallback covers what int() REFUSES, nothing more.

        `True`/`False` are the exception that proves the rule and are checked
        by type ahead of it: `bool` IS an `int`, so `int(True)` is 1 and both
        silently returned exactly one row from a method documented to fall back
        to the default — the shape a caller passing a feature flag or a
        truthiness-coerced request argument produces."""
        ids = [catalog_service.create_product(description=f'ZEBRA {i}')
               for i in range(SEARCH_RESULTS_DEFAULT_LIMIT + 5)]
        found = catalog_service.search_products('zebra', limit=limit)
        expected = 1 if limit == 1.5 else SEARCH_RESULTS_DEFAULT_LIMIT
        assert len(found) == expected
        assert [p.id for p in found] == sorted(ids)[:expected]

    @pytest.mark.unit
    @pytest.mark.parametrize('filters', [None, {}])
    def test_absent_or_empty_filters_mean_no_filters(self, catalog_service, filters):
        pid = catalog_service.create_product(description='ZEBRA striped resistor')
        assert [p.id for p in
                catalog_service.search_products('zebra', filters)] == [pid]

    @pytest.mark.unit
    @pytest.mark.parametrize('filters', [
        {'category_path': 'x'},
        {'tag': 'smd', 'manufacturer': 'Acme'},
    ])
    def test_a_non_empty_filter_is_refused_loudly(self, catalog_service, filters):
        """Silently ignoring a filter would hand a caller unfiltered rows it
        believes are filtered — the loud failure is the file's convention for
        an unregistered dispatch."""
        with pytest.raises(NotImplementedError) as exc:
            catalog_service.search_products('zebra', filters)
        message = str(exc.value)
        assert '8.2' in message
        for key in filters:
            assert key in message

    @pytest.mark.unit
    @pytest.mark.parametrize('filters', [5, True, object(), ['a'], 'abc'])
    def test_a_non_mapping_filters_is_rejected_by_type_not_by_accident(
            self, catalog_service, filters):
        """Type before combination, the taxonomy `ScanResolution` uses.

        Without the guard, a truthy non-mapping reached the message builder and
        `sorted(5)` raised a bare `TypeError: 'int' object is not iterable` —
        not the `NotImplementedError` the `Raises:` block promises — while
        `sorted('abc')` exploded a string into `['a','b','c']`, the same
        coercion trap `ScanResolution.__post_init__` rejects one module over.
        """
        with pytest.raises(TypeError) as exc:
            catalog_service.search_products('zebra', filters)
        assert 'filters' in str(exc.value)
        assert type(filters).__name__ in str(exc.value)

    @pytest.mark.unit
    @pytest.mark.parametrize('query', [b'zebra', bytearray(b'zebra'),
                                       ['zebra'], {'q': 'zebra'}, 10,
                                       object(), 1.5])
    def test_a_non_string_query_is_rejected_rather_than_searched_as_its_repr(
            self, catalog_service, query):
        """`str(b'zebra')` is `"b'zebra'"`, which would be searched literally
        and return nothing — a transport that forgot to decode would look like
        a catalog with no matches. `resolve_scan` already rejects a non-`str`
        at its own door; the sibling entrypoint must not be quietly more
        forgiving.

        Bytes are not the only shape with that failure and not the worst one:
        `str(object())` is a query derived from a MEMORY ADDRESS, which differs
        between runs, and `search_products(10)` searched `'10'` and returned
        real rows for a product described `'RES 10K'` — a wrong-typed caller
        getting plausible hits is worse than one getting none. All of them are
        refused by one type check rather than the single case someone thought
        of."""
        catalog_service.create_product(description='ZEBRA striped resistor')
        catalog_service.create_product(description='RES 10K 0805 1%')
        with pytest.raises(TypeError) as exc:
            catalog_service.search_products(query)
        assert 'str' in str(exc.value)
        assert type(query).__name__ in str(exc.value)

    @pytest.mark.unit
    @pytest.mark.parametrize('query', ['a' * (SEARCH_QUERY_MAX_LENGTH + 1),
                                       '%' * (SEARCH_QUERY_MAX_LENGTH + 1)])
    def test_an_over_long_query_answers_instead_of_raising(
            self, catalog_service, query):
        """A LIKE pattern has a length ceiling a search box has no reason to
        respect. Verified before the bound: `search_products('a' * 50000)`
        raised `OperationalError: LIKE or GLOB pattern too complex` from
        SQLite, and 25000 `%` characters did the same because escaping doubles
        them — an exception escaping a method NFR8 says never raises on scan
        text. Unreachable from a scan (the route caps at 4096 first), reachable
        from Epic 8's search box."""
        catalog_service.create_product(description='ZEBRA striped resistor')
        assert catalog_service.search_products(query) == []

    @pytest.mark.unit
    def test_an_over_long_scan_resolves_instead_of_raising(self, catalog_service):
        """The same bound seen from `resolve_scan`, which promises a
        `ScanResolution` for every `str` (NFR8)."""
        r = catalog_service.resolve_scan('a' * (SEARCH_QUERY_MAX_LENGTH * 20))
        assert r.product is None and r.free_text_hits == ()

    @pytest.mark.unit
    def test_a_filter_with_incomparable_keys_still_raises_notimplementederror(
            self, catalog_service):
        """The documented exception must survive the message builder: keys of
        mixed types are not mutually comparable, and `sorted({1: 'a', 'b': 2})`
        raised a bare `TypeError: '<' not supported between instances of 'str'
        and 'int'` — the same substitution the non-mapping guard above exists
        to prevent, one line further in."""
        with pytest.raises(NotImplementedError) as exc:
            catalog_service.search_products('zebra', {1: 'a', 'b': 2})
        assert '8.2' in str(exc.value)

    @pytest.mark.unit
    def test_both_arguments_are_type_checked_before_either_verdict(
            self, catalog_service):
        """Type before combination applies ACROSS the arguments, not just
        within one: the `Raises:` block presents the query's `TypeError` and
        the filters' `NotImplementedError` as unconditional, and only one of
        them can be raised first.

        `search_products(b'zebra', {'a': 1})` used to report the unimplemented
        FEATURE while quietly holding a wrong-typed query, so a caller who
        removed the filter would hit the second fault on the next run. The
        wrong type is the fault that is already certain; the filter is a fault
        only because Story 8.2 has not shipped."""
        with pytest.raises(TypeError) as exc:
            catalog_service.search_products(b'zebra', {'category_path': 'x'})
        assert 'query' in str(exc.value)

    @pytest.mark.unit
    @pytest.mark.parametrize('query, hits', [
        ('RES 10K', True),      # a contiguous substring of the description
        ('10K 0805', True),
        ('RES 0805', False),    # the words are there, in order, not adjacent
        ('10K RES', False),     # ...and reordered
        ('Yageo 10K', False),   # ...and spread across two columns
    ])
    def test_matching_is_contiguous_substring_only_not_tokenized(
            self, catalog_service, query, hits):
        """Pins the mechanism's reach, because FR36's "a miss becomes a search"
        is only as good as what the search can find. There is no tokenization:
        a query matches one column or nothing, so the realistic free-text scan
        — a distributor's human-readable line — usually finds nothing. This is
        the mechanism AD-17 defers to Epic 8, deliberate here and recorded in
        the ledger; the test exists so it is visible rather than assumed."""
        pid = catalog_service.create_product(
            description='RES 10K 0805 1%', manufacturer='Yageo',
            mpn='RC0805FR-0710KL')
        found = [p.id for p in catalog_service.search_products(query)]
        assert found == ([pid] if hits else [])

    @pytest.mark.unit
    def test_non_ascii_folding_is_ascii_only_and_backend_dependent(
            self, catalog_service):
        """Pins what `func.lower()` does and does NOT buy, because the docstring
        used to claim the two backends agree and they do not.

        Python's `str.lower()` is full-Unicode; SQLite's built-in `LOWER()` is
        ASCII-only, so a stored uppercase non-ASCII letter is unreachable by any
        casing of the query under the unit harness — while MariaDB's
        `utf8mb4_unicode_ci` would match it. Asserted rather than fixed: closing
        it means a custom SQLite collation (an app-level engine change) or the
        Epic 8 mechanism decision AD-17 defers. Deferred to the ledger."""
        upper = catalog_service.create_product(description='WÜRTH ELEKTRONIK')
        lower = catalog_service.create_product(description='würth elektronik')

        # ASCII case-folding works in both directions — the part that IS bought.
        assert {p.id for p in catalog_service.search_products('ELEKTRONIK')} == \
            {upper, lower}

        # Non-ASCII does not: only the already-lowercase row is reachable.
        assert [p.id for p in catalog_service.search_products('würth')] == [lower]
        assert [p.id for p in catalog_service.search_products('WÜRTH')] == [lower]

    @pytest.mark.unit
    def test_the_bounds_are_module_constants_not_inline_numbers(self):
        assert SEARCH_RESULTS_DEFAULT_LIMIT <= SEARCH_RESULTS_MAX_LIMIT
        assert mariadb_catalog_service.SEARCH_RESULTS_DEFAULT_LIMIT == \
            SEARCH_RESULTS_DEFAULT_LIMIT


class TestNamespaceAgreement:
    """`resolve_scan` queries the normalized-14 GTIN namespace inline rather
    than calling `find_product_id_by_gtin` (which re-normalizes an already
    normalized value, returns an id rather than a row, and would open a third
    session per scan). The duplication is one filter pair; this pins the two
    against drifting apart."""

    @pytest.mark.unit
    @pytest.mark.parametrize('stored, scanned', [
        (GTIN13, GTIN13),
        (GTIN13, GTIN13_KEY),
        (UPCA, '0' + UPCA),
        (GTIN8, GTIN8_KEY),
    ])
    def test_both_paths_reach_the_same_product(self, catalog_service, product,
                                               stored, scanned):
        catalog_service.add_identifier(product.id,
                                       identifier_type=IdentifierType.GTIN,
                                       value=stored)

        resolved = catalog_service.resolve_scan(scanned)

        assert resolved.product is not None
        assert resolved.product.id == catalog_service.find_product_id_by_gtin(scanned)

    @pytest.mark.unit
    def test_both_paths_agree_on_a_miss(self, catalog_service, product):
        assert catalog_service.find_product_id_by_gtin(GTIN_UNSTORED) is None
        assert catalog_service.resolve_scan(GTIN_UNSTORED).product is None

    @pytest.mark.unit
    def test_both_paths_agree_that_gtin_unvalidated_is_outside_the_namespace(
            self, catalog_service, product):
        catalog_service.add_identifier(
            product.id, identifier_type=IdentifierType.GTIN_UNVALIDATED,
            value=GTIN13)
        assert catalog_service.find_product_id_by_gtin(GTIN13) is None
        assert catalog_service.resolve_scan(GTIN13).product is None


class TestReadOnlyPosture:
    """Both methods are reads: `POST /api/scan` is CSRF-exempt and the scan
    transport has at-least-once semantics on a client timeout, so resolution
    being idempotent by construction is what keeps a rescan free."""

    @pytest.mark.unit
    def test_resolution_writes_nothing(self, catalog_service, product):
        from app.database import Product, ProductIdentifier

        def _snapshot():
            session = catalog_service.Session()
            try:
                return (
                    [(p.id, p.internal_id, p.description, p.updated_at)
                     for p in session.query(Product).order_by(Product.id).all()],
                    [(r.id, r.product_id, r.identifier_type, r.value)
                     for r in session.query(ProductIdentifier)
                     .order_by(ProductIdentifier.id).all()],
                )
            finally:
                session.close()

        catalog_service.add_identifier(product.id,
                                       identifier_type=IdentifierType.GTIN,
                                       value=GTIN13)
        before = _snapshot()

        for raw in (_internal_scan(product.internal_id), GTIN13, GTIN_UNSTORED,
                    ECIA_FULL, 'RES 10K', '', 'nothing matches this'):
            catalog_service.resolve_scan(raw)
        catalog_service.search_products('res')

        assert _snapshot() == before

    @pytest.mark.unit
    def test_repeated_resolution_is_identical(self, catalog_service, product):
        """Idempotent by construction, which is what a rescan after a client
        timeout relies on."""
        scan = _internal_scan(product.internal_id)
        first, second = (catalog_service.resolve_scan(scan) for _ in range(2))
        assert first.classification == second.classification
        assert first.product.id == second.product.id == product.id
        assert first.free_text_hits == second.free_text_hits == ()

    @pytest.mark.unit
    def test_returned_rows_are_detached_but_scalar_readable(self, catalog_service,
                                                            product):
        """The documented consequence of the no-commit read idiom: scalars stay
        readable after the session closes. (Relationship attributes must not be
        touched — that is what the docstrings warn about.)"""
        r = catalog_service.resolve_scan(_internal_scan(product.internal_id))
        assert r.product.description == 'RES 10K 0805 1%'
        assert r.product.internal_id == product.internal_id
