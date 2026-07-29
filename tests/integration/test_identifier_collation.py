"""
Identifier uniqueness under the deployed MariaDB collation.

This is the seam where the SQLite unit tier is not merely thinner than
production but actively LOOSER than it. ``uq_product_identifiers_type_value_scope``
compares ``value`` under the column's collation: binary on SQLite, so
``'SHARED-1'`` and ``'shared-1'`` are two different identifiers there and both
insert happily; case- and accent-folding on MariaDB, so the second is a
duplicate and ``add_identifier`` rejects it. tests/unit/test_catalog_service.py
therefore *passes* on a pair production refuses. Asserting the real behavior
here turns that divergence from an assumption into a checked fact.

The collation guard at the top is the load-bearing assertion: if the deployed
collation ever stops folding, ``set_product_tags``' flush ordering,
``find_products_by_tag``'s re-check, ``rename_tag``'s Python partition and
``rename_category_path``'s unclaimed-row handling all quietly become elaborate
no-ops. It must fail a test, not pass silently.
"""

import pytest
import sqlalchemy as sa

from app.database import Base
from app.exceptions import ValidationError
from app.models import ScanKind
from tests.integration.conftest import (BINARY_COLLATION, CONTRAST_COLLATION,
                                        REQUIRED_COLLATION,
                                        assert_schema_is_pinned,
                                        database_default)

# The (table, column) pairs whose collation the catalog's folding assumptions
# depend on: identifier uniqueness (Story 2.1) and per-product tag uniqueness
# (Story 3.3).
FOLDING_COLUMNS = (('product_identifiers', 'value'), ('product_tags', 'tag'))

# One MPN, written three ways. Same string under a case- and accent-insensitive
# collation; three distinct strings under a binary one.
MPN_CANONICAL = 'SHARED-1'
MPN_CASE_DIFFERING = 'shared-1'
MPN_ACCENT_BASE = 'REF-1'
MPN_ACCENT_DIFFERING = 'RÉF-1'

# One tag, written two ways. Two DISTINCT canonical tags in Python -- nothing
# in app/utils/tag.py folds accents -- and one and the same value to
# ``uq_product_tags_product_tag`` under utf8mb4_unicode_ci. Every rename
# decision below turns on that gap.
TAG_ACCENTED = 'café'
TAG_UNACCENTED = 'cafe'

# One internal id, written two ways. Two rows under products.internal_id's
# pinned utf8mb4_bin; a UNIQUE violation under any folding collation -- which
# is the whole point of pinning that one column against the schema default.
INTERNAL_ID_UPPER = 'ABC1234567'
INTERNAL_ID_LOWER = 'abc1234567'


def _envelope(*records: str) -> str:
    """An ISO/IEC 15434 format-06 message carrying ``records`` verbatim.

    Same construction tests/unit/test_scan_resolution.py uses. The grammar is
    tests/unit/test_ecia.py's subject; here it is only a way to state input.
    """
    return '[)>\x1e06' + ''.join(f'\x1d{record}' for record in records) + '\x1d\x1e\x04'


@pytest.fixture
def two_products(integration_catalog_service):
    """Products A and B, created through the service so both carry a real
    generated internal_id and its derived row. Returns (a_id, b_id).

    ``create_product`` returns ``Optional[int]`` -- it converts any failure to
    None -- so the ids are checked here. Without this, a setup failure would
    surface further down as ``add_identifier(None, ...)`` raising something
    unrelated to the behavior under test.
    """
    service = integration_catalog_service
    product_a = service.create_product(description='product A')
    product_b = service.create_product(description='product B')
    assert product_a is not None and product_b is not None, (
        f'setup failed: create_product returned {product_a!r}, {product_b!r}')
    return product_a, product_b


@pytest.mark.integration
def test_create_all_schema_pins_the_charset_and_collation(integration_schema):
    """``Base.metadata.create_all`` states the collation itself.

    The same claim test_migrations.py makes of the MIGRATED schema, made here
    of the one the models build -- the two are maintained by hand and
    independently, and every other test in this tier runs against this one.
    Since DW-34 both declare it rather than inherit it: ``mysql_charset`` /
    ``mysql_collate`` on every table, plus the ``utf8mb4_bin`` overrides on
    ``products.internal_id`` (DW-73) and ``products.stock_status`` (Story 5.3),
    enumerated by ``BINARY_COLUMNS``. A model change that dropped either would leave
    ``create_all`` emitting a bare ``CREATE TABLE``, and every column would
    quietly go back to whatever the server's default happened to be.
    """
    assert_schema_is_pinned(integration_schema)


@pytest.mark.integration
def test_create_all_pins_even_inside_a_contrary_database(blank_database):
    """``create_all`` beats a database default that is NOT the target.

    The test above cannot distinguish a schema that declares its collation from
    one that merely inherited the right default from ``integration_db_url`` --
    they produce identical catalogs. Here the schema is built inside a database
    defaulting to ``utf8mb4_bin``, so only the declaration can produce the
    pinned values, and a model change that dropped ``mysql_charset`` /
    ``mysql_collate`` fails rather than passing on the fixture's coat-tails.
    This is what DW-51 said could not be checked; it can now.

    The default is restored unconditionally -- the database is session-scoped
    and shared with every other test in the tier.
    """
    with database_default(blank_database, CONTRAST_COLLATION):
        Base.metadata.create_all(blank_database)

        assert_schema_is_pinned(blank_database)


@pytest.mark.integration
def test_internal_id_does_not_fold_under_the_create_all_schema(integration_schema):
    """``products.internal_id`` compares byte-wise (as does ``stock_status``).

    Stated as BEHAVIOR beside the name check above, because what depends on it
    is behavioral: ``is_valid_internal_id`` is deliberately case-sensitive, so
    a folding collation here would let a lower-cased scan resolve to a product
    on MariaDB and not under SQLite (DW-73). Two ids differing only in case
    both persisting is the direct question -- ``uq_products_internal_id`` would
    have rejected the second under any ``_ci`` collation, which is precisely
    what the column would have inherited without the ``utf8mb4_bin`` pin.
    """
    with integration_schema.begin() as conn:
        for value in (INTERNAL_ID_UPPER, INTERNAL_ID_LOWER):
            conn.execute(sa.text(
                'INSERT INTO products (internal_id, created_at, updated_at) '
                'VALUES (:v, NOW(), NOW())'), {'v': value})

    with integration_schema.connect() as conn:
        stored = {row[0] for row in
                  conn.execute(sa.text('SELECT internal_id FROM products'))}
        # ...and the exact-equality lookup resolve_scan performs agrees, rather
        # than folding onto the upper-case row the way a _ci column would.
        matched = [row[0] for row in conn.execute(
            sa.text('SELECT internal_id FROM products WHERE internal_id = :v'),
            {'v': INTERNAL_ID_LOWER})]

    assert stored == {INTERNAL_ID_UPPER, INTERNAL_ID_LOWER}, (
        f'uq_products_internal_id folded two ids differing only in case; '
        f'products.internal_id is meant to be {BINARY_COLLATION}')
    assert matched == [INTERNAL_ID_LOWER]


@pytest.mark.integration
def test_folding_columns_use_the_expected_collation(integration_schema):
    """The collation in force is observed, not assumed -- and it really folds.

    Two assertions. The first pins the collation name on the two columns whose
    folding the catalog depends on; since DW-34 that is a schema decision
    (``app/database.py``'s MYSQL_TABLE_OPTIONS) rather than an inheritance from
    ``integration_db_url``'s database-level force, and the test above makes the
    same check exhaustively. The second asks the server directly whether that
    collation folds case and accents, which is the property every 'duplicate
    rejected' assertion below -- and ``set_product_tags``,
    ``find_products_by_tag`` and ``rename_category_path`` in production --
    actually depends on. Note what each one can and cannot see: the first is a
    NAME comparison, so any move to a different collation fails it even if the
    replacement folded identically -- deliberate, because such a move is a
    decision this repo wants made on purpose. The second interrogates
    ``utf8mb4_unicode_ci`` by name on string literals, so it proves that
    collation still folds; it does not read the columns, which is what the
    first assertion is for.
    """
    with integration_schema.connect() as conn:
        observed = {
            (row[0], row[1]): row[2]
            for row in conn.execute(sa.text(
                'SELECT table_name, column_name, collation_name '
                'FROM information_schema.columns WHERE table_schema = database() '
                'AND table_name IN :tables'
            ).bindparams(sa.bindparam(
                'tables', [table for table, _ in FOLDING_COLUMNS],
                expanding=True)))
        }

    for key in FOLDING_COLUMNS:
        assert observed.get(key) == REQUIRED_COLLATION, (
            f'{key[0]}.{key[1]} is stored under collation '
            f'{observed.get(key)!r}, not {REQUIRED_COLLATION!r}; every '
            f'case/accent-folding assumption in the catalog subsystem rests on '
            f'this column folding.')

    with integration_schema.connect() as conn:
        folds = conn.execute(sa.text(
            f"SELECT '{MPN_CANONICAL}' = '{MPN_CASE_DIFFERING}' "
            f'COLLATE {REQUIRED_COLLATION}, '
            f"'{MPN_ACCENT_BASE}' = '{MPN_ACCENT_DIFFERING}' "
            f'COLLATE {REQUIRED_COLLATION}')).one()
    assert tuple(folds) == (1, 1), (
        f'{REQUIRED_COLLATION} did not fold case and accents (got '
        f'{tuple(folds)} for the two pairs this file is built on)')


class TestDuplicateIdentifierRejection:
    """``add_identifier``'s duplicate check with the real collation deciding."""

    @pytest.mark.integration
    def test_exact_duplicate_is_rejected(self, integration_catalog_service, two_products):
        """The baseline both backends agree on, stated here so the two folding
        cases below are read as extensions of it rather than as the whole
        behavior."""
        service = integration_catalog_service
        product_a, product_b = two_products
        service.add_identifier(product_a, identifier_type='MPN', value=MPN_CANONICAL)

        with pytest.raises(ValidationError) as exc_info:
            service.add_identifier(product_b, identifier_type='MPN',
                                   value=MPN_CANONICAL)
        assert exc_info.value.field == 'value'
        assert f'product {product_a}' in str(exc_info.value)

    @pytest.mark.integration
    def test_case_differing_value_is_rejected(self, integration_catalog_service,
                                              two_products):
        """The divergence, asserted: SQLite accepts this pair today.

        The rejection has to survive the round trip -- InnoDB raises the UNIQUE
        violation at flush, and ``add_identifier`` then re-queries by
        ``value == 'shared-1'`` to name the conflicting product. That re-query
        only finds the stored ``'SHARED-1'`` because the same collation folds
        both ways; if it did not, the service would re-raise a raw
        IntegrityError instead of the caught ValidationError.
        """
        service = integration_catalog_service
        product_a, product_b = two_products
        service.add_identifier(product_a, identifier_type='MPN', value=MPN_CANONICAL)

        with pytest.raises(ValidationError) as exc_info:
            service.add_identifier(product_b, identifier_type='MPN',
                                   value=MPN_CASE_DIFFERING)
        assert exc_info.value.field == 'value'
        assert f'product {product_a}' in str(exc_info.value)

        # B gained nothing from the rejected call (it still carries only the
        # INTERNAL row create_product derived for it).
        assert [row.identifier_type
                for row in service.get_identifiers_for_product(product_b)] == \
               ['INTERNAL']

    @pytest.mark.integration
    def test_accent_differing_value_is_rejected(self, integration_catalog_service,
                                                two_products):
        """utf8mb4_unicode_ci is accent-insensitive as well as case-insensitive,
        so 'RÉF-1' and 'REF-1' are one identifier here and two under SQLite."""
        service = integration_catalog_service
        product_a, product_b = two_products
        service.add_identifier(product_a, identifier_type='MPN', value=MPN_ACCENT_BASE)

        with pytest.raises(ValidationError) as exc_info:
            service.add_identifier(product_b, identifier_type='MPN',
                                   value=MPN_ACCENT_DIFFERING)
        assert exc_info.value.field == 'value'
        assert f'product {product_a}' in str(exc_info.value)


class TestEciaScanUnderFoldingCollation:
    """The consequence of the above for scan resolution (Story 4.3/4.5)."""

    @pytest.mark.integration
    def test_ecia_scan_lands_on_the_only_possible_holder(
            self, integration_catalog_service, two_products):
        """A case-differing ECIA part number resolves to a product, not to a
        hit list.

        The ambiguity SQLite can stage -- two products each holding their own
        casing of the same MPN, so the resolver finds two matches and declines
        to pick -- is unreachable on the real backend, because the second
        identifier cannot exist. This test asserts both halves in order: the
        duplicate is refused, and the scan therefore LANDS with no fallthrough
        search.
        """
        service = integration_catalog_service
        product_a, product_b = two_products
        service.add_identifier(product_a, identifier_type='MPN', value=MPN_CANONICAL)
        with pytest.raises(ValidationError):
            service.add_identifier(product_b, identifier_type='MPN',
                                   value=MPN_CASE_DIFFERING)

        resolution = service.resolve_scan(_envelope(f'1P{MPN_CASE_DIFFERING}'))

        assert resolution.classification.kind is ScanKind.ECIA
        assert resolution.product is not None
        assert resolution.product.id == product_a
        assert resolution.free_text_hits == ()


class TestTagRenameUnderFoldingCollation:
    """``rename_tag``'s partition with the real collation deciding (DW-48).

    The method narrows with one ``tag = old OR tag = new`` and then partitions
    the rows by exact Python equality, on the premise that the SQL hands back
    MORE than it asked for. Under SQLite it never does -- the binary collation
    makes that filter exact, so the unit tier can only reach these branches by
    widening the query on purpose. Here the collation does the widening itself,
    which is the only place the premise is checked rather than simulated.
    """

    @pytest.mark.integration
    def test_a_folded_near_miss_is_not_dragged_along(self,
                                                     integration_catalog_service):
        """Product A carries 'café', product B carries 'cafe'; renaming 'cafe'
        moves ONLY B.

        The SELECT returns both rows here -- that is what the folding does --
        so leaving A's tag alone is a decision the Python partition makes, not
        something the query did for it. Getting this wrong would silently
        rewrite a tag its product's owner deliberately spelled with an accent.
        """
        service = integration_catalog_service
        near_miss = service.create_product(description='accented')
        carrier = service.create_product(description='plain')
        assert near_miss is not None and carrier is not None
        service.set_product_tags(near_miss, [TAG_ACCENTED])
        service.set_product_tags(carrier, [TAG_UNACCENTED])

        assert service.rename_tag(TAG_UNACCENTED, 'ssr') == (1, 0)

        assert service.get_tags_for_product(near_miss) == [TAG_ACCENTED]
        assert service.get_tags_for_product(carrier) == ['ssr']

    @pytest.mark.integration
    def test_a_folded_destination_conflict_is_refused(self,
                                                      integration_catalog_service):
        """One product carrying both 'ssr' and 'café' cannot take a rename of
        'ssr' -> 'cafe'.

        The destination is a distinct string in Python and the same value to
        the unique index, so the rewrite would collide with a row the product
        also means to keep, and discarding either is the one outcome neither
        ``rename_tag`` nor ``set_product_tags`` allows. The refusal is decided
        BEFORE the write, so the message can name the product -- a rolled-back
        flush cannot. This is the branch the unit tier stages by hand; here the
        collation produces it.
        """
        service = integration_catalog_service
        conflicted = service.create_product(description='both spellings')
        clean = service.create_product(description='just ssr')
        assert conflicted is not None and clean is not None
        service.set_product_tags(conflicted, ['ssr', TAG_ACCENTED])
        service.set_product_tags(clean, ['ssr'])

        with pytest.raises(ValidationError) as exc_info:
            service.rename_tag('ssr', TAG_UNACCENTED)
        assert exc_info.value.field == 'new_tag'
        assert str(conflicted) in str(exc_info.value)

        # Atomic: the product that COULD have moved did not, either.
        assert service.get_tags_for_product(conflicted) == sorted(
            ['ssr', TAG_ACCENTED])
        assert service.get_tags_for_product(clean) == ['ssr']

    @pytest.mark.integration
    def test_fixing_an_accent_renames_in_place(self, integration_catalog_service):
        """'cafe' -> 'café' is a real rename, not a no-op and not a merge.

        The two are one value to the index, so the UPDATE rewrites the row to a
        key that folds onto the key it already had -- legal only because it is
        the SAME row. Nothing in the unit tier can tell this apart from any
        other rename; here it is the case most likely to trip the unique index
        if the method ever grew a delete-then-insert shortcut.
        """
        service = integration_catalog_service
        product = service.create_product(description='misspelled')
        assert product is not None
        service.set_product_tags(product, [TAG_UNACCENTED, 'keepme'])

        assert service.rename_tag(TAG_UNACCENTED, TAG_ACCENTED) == (1, 0)

        assert service.get_tags_for_product(product) == sorted(
            [TAG_ACCENTED, 'keepme'])

    @pytest.mark.integration
    def test_a_merge_leaves_one_row_and_loses_no_other_tag(
            self, integration_catalog_service):
        """The merge, run where the unique constraint is the real one.

        Product B already carries the destination, so its source row is deleted
        rather than rewritten -- and the deletes are flushed before the
        rewrites, which is what keeps a row on its way out from colliding with
        one being rewritten under the folding index.
        """
        service = integration_catalog_service
        moved = service.create_product(description='source only')
        merged = service.create_product(description='both tags')
        assert moved is not None and merged is not None
        service.set_product_tags(moved, ['ssr'])
        service.set_product_tags(merged, ['ssr', 'relay', 'keepme'])

        assert service.rename_tag('ssr', 'relay') == (1, 1)

        assert service.get_tags_for_product(moved) == ['relay']
        assert service.get_tags_for_product(merged) == ['keepme', 'relay']
