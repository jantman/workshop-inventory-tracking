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
``find_products_by_tag``'s re-check and ``rename_category_path``'s
unclaimed-row handling all quietly become elaborate no-ops. It must fail a test,
not pass silently.
"""

import pytest
import sqlalchemy as sa

from app.exceptions import ValidationError
from app.models import ScanKind
from tests.integration.conftest import REQUIRED_COLLATION

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
def test_folding_columns_use_the_expected_collation(integration_schema):
    """The collation in force is observed, not assumed -- and it really folds.

    Two assertions, and the second is the one that matters. The first pins the
    collation name, which is worth stating but is partly a property of the
    harness: ``integration_db_url`` forces the database default and the schema
    pins nothing per-column (DW-51), so these columns inherit what the fixture
    set. The second asks the server directly whether that collation folds case
    and accents, which is the property every 'duplicate rejected' assertion
    below -- and ``set_product_tags``, ``find_products_by_tag`` and
    ``rename_category_path`` in production -- actually depends on. A collation
    that folded nothing would turn all of them into tests of the wrong thing.
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
