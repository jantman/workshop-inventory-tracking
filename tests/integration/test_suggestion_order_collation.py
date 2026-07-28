"""
Which spelling the suggestion endpoints offer, decided by a real MariaDB.

Both ``get_field_value_suggestions`` methods narrow in SQL and dedup in Python:
the rows arrive ordered, a case-insensitive pass keeps the FIRST spelling of
each value, and the loop stops once ``limit`` distinct values are in hand. That
makes the ORDER BY the thing that picks which spelling of a duplicated value the
operator sees -- and an ORDER BY only picks if it is TOTAL.

Under SQLite it always was, for free: that backend compares text byte-wise, so
the trailing column tiebreak separates ``McMaster`` from ``mcmaster`` and the
unit tier sees a stable answer. Under the deployed ``utf8mb4_unicode_ci`` it was
not: that collation folds case AND accents, so the tiebreak column compared
equal to the ``LOWER()`` key ahead of it, every duplicate row tied on every key,
and whichever row the plan emitted first won. Green unit runs proved nothing
about it, which is exactly how the divergence shipped (DW-96).

``db.binary_order_key`` collates that one key to ``utf8mb4_bin`` on
MySQL/MariaDB. This file is where that can be OBSERVED rather than reasoned
about, and it is organized to prove the two halves separately:

* the premise -- on this server, with this schema, the seeded spellings really
  are indistinguishable to the un-collated tiebreak, so the tests below are
  exercising the ambiguity they claim to;
* the behavior -- each service offers the binary-lowest spelling, identically on
  every repetition.

Coverage is by query SHAPE, not by field. The inventory service whitelists five
fields (`thread_size`, `purchase_location`, `vendor`, `location`,
`sub_location`); `vendor` stands for the four that share one code path and
`sub_location` is here on its own account, being the only one with a filter of
its own. Both catalog fields appear, because `tags` resolves its column on a
child table. Each of the two ORDER BY branches -- ranked and unranked -- is
exercised on both services.

What makes the old behavior FAIL these tests is the seed order: rows are
inserted binary-HIGHEST first, so the row a plan falling back to insertion order
emits first is the wrong one. Repetition is a weaker check and is not claimed to
be more than one -- five identical calls against identical data over one pool
would return five identical wrong answers just as readily as five right ones.
What it does cover is instability ACROSS calls (a plan that changes as the
optimizer's statistics warm, or ordering that varies with pooled connection
state), which a single call cannot see at all.
"""

import pytest
import sqlalchemy as sa

from app.database import InventoryItem, Product, ProductTag
from app.db import BINARY_COLLATION, MYSQL_DIALECTS
from tests.integration.conftest import REQUIRED_COLLATION

# How many times each assertion re-asks the question. Small, because the point
# is that the answer is decided by the ORDER BY rather than sampled -- see the
# module docstring for what the repetition does and does not cover.
REPETITIONS = 5

# One vendor, written three ways. One value to `utf8mb4_unicode_ci` and to the
# Python `v.lower()` dedup key alike; three distinct strings to `utf8mb4_bin`,
# where uppercase ASCII sorts first, so MCMASTER < McMaster < mcmaster.
VENDOR_UPPER = 'MCMASTER'
VENDOR_MIXED = 'McMaster'
VENDOR_LOWER = 'mcmaster'
# Binary-highest first: insertion order is id order, so a plan that fell back to
# it would offer `mcmaster` and fail every assertion below.
VENDOR_CASE_VARIANTS = (VENDOR_LOWER, VENDOR_MIXED, VENDOR_UPPER)

# A vendor that merely CONTAINS the query below, and is binary-lower than every
# spelling above ('A' < 'M'). It exists to prove the rank tiers still run ahead
# of the tiebreak: with the collated key alone deciding, this would be offered
# first.
VENDOR_CONTAINS_ONLY = 'ACME MC Supply'

# The query the ranked tests use. A prefix of the three case variants (rank 1,
# starts-with) and an interior substring of VENDOR_CONTAINS_ONLY (rank 2).
VENDOR_QUERY = 'mc'

# One vendor, written two ways -- and NOT one value in Python. `str.lower()`
# does not fold accents, so 'cafe' and 'café' are distinct dedup keys and both
# must still be offered; `utf8mb4_unicode_ci` folds them, so they tie on the
# LOWER() key and only the binary tiebreak orders them. 'e' (0x65) sorts before
# the two bytes of 'é', so Cafe < Café.
VENDOR_PLAIN = 'Cafe'
VENDOR_ACCENTED = 'Café'
VENDOR_ACCENT_VARIANTS = (VENDOR_ACCENTED, VENDOR_PLAIN)

# The value that makes accent ADJACENCY observable, and it has to be a separate
# seed because the two spellings above alone cannot show it: 'Cafe' < 'Café'
# under both a folding LOWER() key and a binary one, so an ordering that
# collated the primary key too would produce a byte-identical list. 'x' (0x78)
# sorts before the first byte of 'é' (0xC3), so under a binary primary key
# 'Cafex' would come BETWEEN the pair; under the folding one this code keeps, it
# sorts after both and the pair stays together.
VENDOR_ACCENT_NEIGHBOR = 'Cafex'
# Binary-highest first again: Cafe < Cafex < Café.
VENDOR_ACCENT_GROUP = (VENDOR_ACCENTED, VENDOR_ACCENT_NEIGHBOR, VENDOR_PLAIN)

# The location the sub_location lookup is scoped to, its three sub_location
# spellings (binary-highest first again), and a sub_location under a DIFFERENT
# location that the scope must exclude.
SCOPE_LOCATION = 'Shelf A'
OTHER_LOCATION = 'Rack 3'
SUB_UPPER = 'BIN 1'
SUB_MIXED = 'Bin 1'
SUB_LOWER = 'bin 1'
SUB_CASE_VARIANTS = (SUB_LOWER, SUB_MIXED, SUB_UPPER)
SUB_OUT_OF_SCOPE = 'Drawer 9'

# One category path, written three ways; uppercase-first binary order again, so
# ELECTRONICS/POWER < Electronics/Power < electronics/power. Seeded directly
# rather than through `create_product`, which canonicalizes to lower case --
# only a pre-canonicalization row can look like this, which is precisely the
# data this ordering exists to resolve.
CATEGORY_UPPER = 'ELECTRONICS/POWER'
CATEGORY_MIXED = 'Electronics/Power'
CATEGORY_LOWER = 'electronics/power'
CATEGORY_CASE_VARIANTS = (CATEGORY_LOWER, CATEGORY_MIXED, CATEGORY_UPPER)

# One tag, written three ways. Like the category paths above, these are
# spellings today's write path does not produce -- `normalize_tag` canonicalizes
# to lower case -- which is exactly the population this ordering is for: rows
# that predate the rule, or arrived before it covered this column. Each goes on
# a DIFFERENT product:
# `uq_product_tags_product_tag` folds under the deployed collation, so one
# product cannot hold two spellings of the same tag -- which is the constraint
# test_identifier_collation.py is about, and a precondition here.
TAG_UPPER = 'RELAY'
TAG_MIXED = 'Relay'
TAG_LOWER = 'relay'
TAG_CASE_VARIANTS = (TAG_LOWER, TAG_MIXED, TAG_UPPER)


def _seed_items(service, rows):
    """Insert one ``inventory_items`` row per entry, in the order given.

    Written through the ORM session rather than through ``add_item`` because
    the subject is stored TEXT, not the write path: ``add_item`` carries audit
    logging and an active-row check that have nothing to do with how a value is
    later ordered, and several of the spellings below are ones the write path
    would never produce in the first place. Insertion order is id order, which
    the module docstring explains is load-bearing.
    """
    session = service.Session()
    try:
        for index, overrides in enumerate(rows, start=1):
            session.add(InventoryItem(ja_id=f'JA{index:06d}', item_type='Bar',
                                      material='Steel', **overrides))
        session.commit()
    finally:
        session.close()


def _seed_vendors(service, vendors):
    """One item per vendor spelling, all under the same location."""
    _seed_items(service, [{'vendor': vendor, 'location': SCOPE_LOCATION}
                          for vendor in vendors])


def _seed_category_paths(service, paths):
    """One product per category_path spelling, in the order given."""
    session = service.Session()
    try:
        for index, path in enumerate(paths, start=1):
            session.add(Product(internal_id=f'SEED{index:06d}',
                                description='seed', category_path=path))
        session.commit()
    finally:
        session.close()


def _seed_tags(service, tags):
    """One product per tag spelling, each carrying exactly that one tag."""
    session = service.Session()
    try:
        for index, tag in enumerate(tags, start=1):
            product = Product(internal_id=f'SEED{index:06d}',
                              description='seed')
            session.add(product)
            session.flush()
            session.add(ProductTag(product_id=product.id, tag=tag))
        session.commit()
    finally:
        session.close()


def _repeated(call, times=REPETITIONS):
    """``call()`` run ``times`` times; returns the list of results."""
    return [call() for _ in range(times)]


@pytest.mark.integration
def test_the_deployed_collation_ties_what_the_binary_one_separates(
        integration_inventory_service):
    """The premise, asked of the server rather than assumed.

    Two questions in one statement. The first pair is what breaks the ordering:
    under ``utf8mb4_unicode_ci`` the case variants and the accent variants are
    each ONE value, so a tiebreak on the bare column decides nothing. The second
    pair is what the fix relies on: under ``utf8mb4_bin`` they are distinct, so
    a tiebreak collated to it decides everything.

    If either pair ever changed, every assertion below would still pass while
    testing something else entirely -- a folding collation that stopped folding
    would make the bare column a perfectly good tiebreak, and this file's
    subject would quietly cease to exist.

    The dialect is asserted first, and it is the assertion this whole file
    depends on: ``binary_order_key`` collates only for a name in
    ``MYSQL_DIALECTS``, so a driver or URL scheme that ever reported something
    outside that set would silently take the identity branch and every test
    below would fail as an ordering bug rather than as the skipped branch it
    actually was.

    ``BINARY_COLLATION`` is imported from ``app.db`` rather than from this
    tier's conftest on purpose: the constant probed here has to be the one
    production sorts by, or a helper repointed at a folding collation would
    still find this test green.
    """
    dialect_name = integration_inventory_service.engine.dialect.name
    assert dialect_name in MYSQL_DIALECTS, (
        f'the integration engine reports dialect {dialect_name!r}, which is '
        f'not in {sorted(MYSQL_DIALECTS)} -- binary_order_key would take its '
        f'identity branch and nothing in this file would test the fix')

    with integration_inventory_service.engine.connect() as conn:
        folded, binary = conn.execute(sa.text(
            'SELECT (:upper = :lower COLLATE ' + REQUIRED_COLLATION + ') '
            '     + (:plain = :accented COLLATE ' + REQUIRED_COLLATION + '), '
            '       (:upper = :lower COLLATE ' + BINARY_COLLATION + ') '
            '     + (:plain = :accented COLLATE ' + BINARY_COLLATION + ')'),
            {'upper': VENDOR_UPPER, 'lower': VENDOR_LOWER,
             'plain': VENDOR_PLAIN, 'accented': VENDOR_ACCENTED}).one()

    assert folded == 2, (
        f'{REQUIRED_COLLATION} did not fold both pairs this file is built on; '
        f'the un-collated tiebreak would already be total and there would be '
        f'nothing here to fix')
    assert binary == 0, (
        f'{BINARY_COLLATION} folded a pair it must separate; the collated '
        f'tiebreak cannot order what it cannot tell apart')


@pytest.mark.integration
def test_the_stored_column_itself_cannot_distinguish_the_spellings(
        integration_inventory_service):
    """The same premise, of the COLUMN rather than of two literals.

    The literals above prove the collation folds; this proves the column is
    stored under it, which is the property the ORDER BY actually meets.
    ``COUNT(DISTINCT vendor)`` collapsing five rows to two says the bare column
    is worth nothing as a tiebreak here -- one group for the three case
    variants, one for the two accent variants.
    """
    seeded = VENDOR_CASE_VARIANTS + VENDOR_ACCENT_VARIANTS
    _seed_vendors(integration_inventory_service, seeded)

    with integration_inventory_service.engine.connect() as conn:
        rows, distinct = conn.execute(sa.text(
            'SELECT COUNT(*), COUNT(DISTINCT vendor) FROM inventory_items')).one()

    assert rows == len(seeded), 'the seed did not land'
    # Two, being the number of FOLDING GROUPS seeded: the case variants are one
    # value to the collation and the accent variants are the other.
    assert distinct == 2, (
        f'inventory_items.vendor distinguished {distinct} of {len(seeded)} '
        f'spellings; it is meant to be stored under the folding '
        f'{REQUIRED_COLLATION}, which is what makes the bare column useless as '
        f'a tiebreak')


class TestInventorySuggestionOrdering:
    """``InventoryService.get_field_value_suggestions`` on the real backend."""

    @pytest.mark.integration
    def test_case_variants_offer_the_binary_lowest_spelling(
            self, integration_inventory_service):
        """Three spellings of one vendor, one offered, the same one every time.

        The Python dedup keeps the FIRST spelling it sees and the three rows are
        one key to it, so this asserts nothing about dedup and everything about
        which row arrived first.
        """
        service = integration_inventory_service
        _seed_vendors(service, VENDOR_CASE_VARIANTS)

        results = _repeated(lambda: service.get_field_value_suggestions('vendor'))

        assert results == [[VENDOR_UPPER]] * REPETITIONS

    @pytest.mark.integration
    def test_case_variants_under_a_query_still_rank_before_they_tiebreak(
            self, integration_inventory_service):
        """The ranked branch builds its own ORDER BY, and the tiebreak is its
        THIRD key -- the exact/starts-with/contains tiers come first.

        ``ACME MC Supply`` is binary-lower than every McMaster spelling, so a
        tiebreak that had been promoted ahead of the rank tiers (or a rank tier
        that stopped being applied) would offer it first. It only ever appears
        second, and the McMaster group still collapses to its binary-lowest
        spelling within its own tier.
        """
        service = integration_inventory_service
        _seed_vendors(service,
                      (VENDOR_CONTAINS_ONLY,) + VENDOR_CASE_VARIANTS)

        results = _repeated(lambda: service.get_field_value_suggestions(
            'vendor', query=VENDOR_QUERY))

        assert results == [[VENDOR_UPPER, VENDOR_CONTAINS_ONLY]] * REPETITIONS

    @pytest.mark.integration
    def test_only_the_case_variants_collapse_and_the_accent_pair_survives(
            self, integration_inventory_service):
        """Both halves of the rule in one list.

        ``Cafe`` and ``Café`` are two dedup keys in Python -- ``str.lower()``
        does not fold accents -- so both must still be offered even though the
        database considers them one value; the case variants are one key, so
        exactly one of them may be. The order is the binary one throughout, and
        the accented pair stays ADJACENT because the ``LOWER()`` key ahead of the
        tiebreak is deliberately left folding -- which is what ``Cafex`` is here
        to make observable, since it would sort BETWEEN the pair if that key
        were collated too (see ``VENDOR_ACCENT_NEIGHBOR``).
        """
        service = integration_inventory_service
        _seed_vendors(service, VENDOR_CASE_VARIANTS + VENDOR_ACCENT_GROUP)

        results = _repeated(lambda: service.get_field_value_suggestions('vendor'))

        assert results == [[VENDOR_PLAIN, VENDOR_ACCENTED,
                            VENDOR_ACCENT_NEIGHBOR,
                            VENDOR_UPPER]] * REPETITIONS

    @pytest.mark.integration
    def test_scoped_sub_location_is_deterministic_within_its_location(
            self, integration_inventory_service):
        """``sub_location`` is the one field with a filter of its own, and the
        tiebreak has to follow the SELECTed column rather than the scoping one.

        The out-of-scope row sorts AFTER every in-scope spelling ('D' > 'B'),
        so a scope silently dropped shows up as an extra suggestion appended to
        the list rather than as a reordering of it -- a failure that names its
        own cause.
        """
        service = integration_inventory_service
        _seed_items(service,
                    [{'location': SCOPE_LOCATION, 'sub_location': value}
                     for value in SUB_CASE_VARIANTS]
                    + [{'location': OTHER_LOCATION,
                        'sub_location': SUB_OUT_OF_SCOPE}])

        results = _repeated(lambda: service.get_field_value_suggestions(
            'sub_location', location=SCOPE_LOCATION))

        assert results == [[SUB_UPPER]] * REPETITIONS


class TestCatalogSuggestionOrdering:
    """The catalog half, whose two fields live on different tables."""

    @pytest.mark.integration
    def test_category_path_case_variants_offer_the_binary_lowest(
            self, integration_catalog_service):
        service = integration_catalog_service
        _seed_category_paths(service, CATEGORY_CASE_VARIANTS)

        results = _repeated(
            lambda: service.get_field_value_suggestions('category_path'))

        assert results == [[CATEGORY_UPPER]] * REPETITIONS

    @pytest.mark.integration
    def test_category_path_case_variants_under_a_query(
            self, integration_catalog_service):
        """The ranked branch, where the query normalizes to the canonical form
        and every row is an exact match -- so the tiebreak is the only key with
        anything left to say."""
        service = integration_catalog_service
        _seed_category_paths(service, CATEGORY_CASE_VARIANTS)

        results = _repeated(lambda: service.get_field_value_suggestions(
            'category_path', query='Electronics / Power'))

        assert results == [[CATEGORY_UPPER]] * REPETITIONS

    @pytest.mark.integration
    def test_tag_case_variants_offer_the_binary_lowest(
            self, integration_catalog_service):
        """``tags`` resolves its column on ``ProductTag`` rather than on
        ``Product``, so it is a genuinely different query with the same shape --
        and the one whose folding collation a unique constraint also depends
        on."""
        service = integration_catalog_service
        _seed_tags(service, TAG_CASE_VARIANTS)

        results = _repeated(
            lambda: service.get_field_value_suggestions('tags'))

        assert results == [[TAG_UPPER]] * REPETITIONS

    @pytest.mark.integration
    def test_tag_case_variants_under_a_query(self, integration_catalog_service):
        """The child table's RANKED branch, the one shape no other test here
        reaches: `tags` builds its own `order_by` with the rank CASE ahead of
        the tiebreak, and it resolves its column on `ProductTag` while the only
        other ranked test resolves on `Product`.

        `normalize_tag` lowercases the query, so all three spellings are exact
        matches and share rank 0 -- leaving the tiebreak as the only key with
        anything left to decide."""
        service = integration_catalog_service
        _seed_tags(service, TAG_CASE_VARIANTS)

        results = _repeated(lambda: service.get_field_value_suggestions(
            'tags', query=TAG_MIXED))

        assert results == [[TAG_UPPER]] * REPETITIONS
