"""
Unit tests for the shared location and vendor vocabulary.

The first class is the suggestion coverage that moved here with
``get_field_value_suggestions`` when it left ``MariaDBInventoryService`` -- the
ranking, LIKE-escaping, clamping and case-insensitive dedup behaviour is
unchanged, so the tests are unchanged too, save for the call they make.

The second class is what is new: the same field answered from both halves of the
application at once.
"""

import pytest

from app.catalog_service import CatalogService
from app.database import InventoryItem
from app.mariadb_inventory_service import InventoryService
from app.services.vocabulary import VocabularyService


class TestFieldValueSuggestions:
    """Tests for VocabularyService.suggest, moved from InventoryService."""

    @pytest.fixture
    def items(self, test_storage, app):
        return InventoryService(test_storage)

    @pytest.fixture
    def service(self, test_storage, app):
        return VocabularyService(test_storage)

    def _make_item(self, ja_id, **overrides):
        defaults = dict(
            item_type='Bar',
            shape='Round',
            material='Steel',
            length=100,
            width=10,
            location='Shelf A',
            active=True,
            precision=False,
        )
        defaults.update(overrides)
        return InventoryItem(ja_id=ja_id, **defaults)

    @pytest.fixture
    def populated(self, items, service):
        # Active items
        items.add_item(self._make_item(
            'JA000001',
            location='Shelf A', sub_location='Top',
            vendor='McMaster-Carr', purchase_location='McMaster-Carr',
            thread_size='1/4-20',
        ))
        items.add_item(self._make_item(
            'JA000002',
            location='Shelf A', sub_location='Bottom',
            vendor='Online Metals', purchase_location='OnlineMetals.com',
            thread_size='M10x1.5',
        ))
        items.add_item(self._make_item(
            'JA000003',
            location='Rack 3', sub_location='Bin 7',
            vendor='Grainger', purchase_location='Grainger',
            thread_size='1/2-13',
        ))

        # Inactive item to confirm history still seeds suggestions
        items.add_item(self._make_item(
            'JA000004',
            location='Old Cabinet', sub_location='Drawer 1',
            vendor='Discontinued Vendor',
            purchase_location='Discontinued Place',
            thread_size='3/8-16',
        ))
        items.deactivate_item('JA000004')

        return service

    @pytest.mark.unit
    def test_unsupported_field_raises(self, service):
        with pytest.raises(ValueError):
            service.suggest('material')
        with pytest.raises(ValueError):
            service.suggest('not_a_field')

    @pytest.mark.unit
    def test_vendor_suggestions_include_inactive(self, populated):
        result = populated.suggest('vendor', limit=20)
        assert 'McMaster-Carr' in result
        assert 'Online Metals' in result
        assert 'Grainger' in result
        # Inactive item's vendor still seeds suggestions
        assert 'Discontinued Vendor' in result

    @pytest.mark.unit
    def test_no_query_returns_alphabetized_distinct(self, populated):
        result = populated.suggest('location', limit=20)
        # Distinct, sorted case-insensitively
        assert result == sorted(result, key=str.lower)
        # Distinct
        assert len(result) == len(set(v.lower() for v in result))
        assert 'Shelf A' in result  # appears twice in DB but once in result
        assert 'Rack 3' in result
        assert 'Old Cabinet' in result

    @pytest.mark.unit
    def test_query_filters_substring_case_insensitive(self, populated):
        result = populated.suggest('vendor', query='metal')
        assert 'Online Metals' in result
        assert 'McMaster-Carr' not in result

    @pytest.mark.unit
    def test_exact_match_first_then_starts_then_contains(self, populated, items):
        # Add a few overlapping entries to exercise ordering
        items.add_item(self._make_item(
            'JA000010', vendor='Steel', location='Shelf X',
        ))
        items.add_item(self._make_item(
            'JA000011', vendor='Steel Supply', location='Shelf Y',
        ))
        items.add_item(self._make_item(
            'JA000012', vendor='Acme Steel Inc', location='Shelf Z',
        ))

        result = populated.suggest('vendor', query='steel')
        # Exact match should come first
        assert result[0] == 'Steel'
        # Then starts-with
        assert result[1] == 'Steel Supply'
        # Then contains
        assert result[2] == 'Acme Steel Inc'

    @pytest.mark.unit
    def test_limit_clamping(self, populated, items, service):
        for i in range(60):
            items.add_item(self._make_item(
                f'JA{200 + i:06d}', vendor=f'Vendor-{i:02d}'
            ))
        result = service.suggest('vendor', limit=999)
        assert len(result) == 50  # clamped to 50

        result_zero = service.suggest('vendor', limit=0)
        assert len(result_zero) == 1  # clamped to 1

    @pytest.mark.unit
    def test_empty_and_whitespace_values_excluded(self, service, items):
        items.add_item(self._make_item('JA000050', vendor='Real Vendor'))
        # Item without vendor (None) — should not pollute suggestions
        items.add_item(self._make_item('JA000051'))
        result = service.suggest('vendor')
        assert result == ['Real Vendor']

    @pytest.mark.unit
    def test_sub_location_filtered_by_location(self, populated):
        # Without filter: includes all sub-locations
        unfiltered = populated.suggest('sub_location', limit=20)
        assert 'Top' in unfiltered
        assert 'Bin 7' in unfiltered
        assert 'Drawer 1' in unfiltered

        # Scoped to "Shelf A" only
        scoped = populated.suggest('sub_location', location='Shelf A', limit=20)
        assert 'Top' in scoped
        assert 'Bottom' in scoped
        assert 'Bin 7' not in scoped
        assert 'Drawer 1' not in scoped

    @pytest.mark.unit
    def test_sub_location_location_filter_case_insensitive(self, populated):
        scoped = populated.suggest('sub_location', location='shelf a', limit=20)
        assert 'Top' in scoped
        assert 'Bottom' in scoped

    @pytest.mark.unit
    def test_thread_size_field(self, populated):
        result = populated.suggest('thread_size', limit=20)
        assert '1/4-20' in result
        assert 'M10x1.5' in result
        assert '1/2-13' in result
        assert '3/8-16' in result

    @pytest.mark.unit
    def test_purchase_location_field(self, populated):
        result = populated.suggest('purchase_location', query='mc')
        assert any('McMaster' in v for v in result)

    @pytest.mark.unit
    def test_like_wildcards_in_the_query_are_escaped(self, service, items):
        """A query of "10%" matches the literal string, not everything"""
        items.add_item(self._make_item('JA000060', vendor='10% Supply'))
        items.add_item(self._make_item('JA000061', vendor='Anything Else'))

        result = service.suggest('vendor', query='10%')
        assert result == ['10% Supply']


class TestVocabularyUnion:
    """One vocabulary, drawn from both halves of the application (FR-014..FR-019)."""

    @pytest.fixture
    def items(self, test_storage, app):
        return InventoryService(test_storage)

    @pytest.fixture
    def catalog(self, test_storage, app):
        return CatalogService(test_storage)

    @pytest.fixture
    def service(self, test_storage, app):
        return VocabularyService(test_storage)

    def _make_item(self, ja_id, **overrides):
        defaults = dict(
            item_type='Bar',
            shape='Round',
            material='Steel',
            length=100,
            width=10,
            location='Shelf A',
            active=True,
            precision=False,
        )
        defaults.update(overrides)
        return InventoryItem(ja_id=ja_id, **defaults)

    @pytest.mark.unit
    def test_catalogue_only_location_is_offered(self, service, catalog):
        catalog.create_product(description='Widget', location='Drawer 3')
        assert 'Drawer 3' in service.suggest('location', limit=20)

    @pytest.mark.unit
    def test_metal_stock_only_location_is_offered(self, service, items):
        items.add_item(self._make_item('JA000001', location='M1-A'))
        assert 'M1-A' in service.suggest('location', limit=20)

    @pytest.mark.unit
    def test_catalogue_only_sub_location_is_offered(self, service, catalog):
        catalog.create_product(
            description='Widget', location='Drawer 3', sub_location='Bin 7'
        )
        assert 'Bin 7' in service.suggest('sub_location', limit=20)

    @pytest.mark.unit
    def test_purchase_vendor_is_offered(self, service, catalog):
        product = catalog.create_product(description='Widget')
        catalog.record_purchase(product.id, vendor='Digi-Key')
        assert 'Digi-Key' in service.suggest('vendor', limit=20)

    @pytest.mark.unit
    def test_metal_stock_only_vendor_is_offered(self, service, items):
        items.add_item(self._make_item('JA000001', vendor='McMaster-Carr'))
        assert 'McMaster-Carr' in service.suggest('vendor', limit=20)

    @pytest.mark.unit
    def test_a_value_in_both_differing_only_in_case_is_offered_once(
        self, service, items, catalog
    ):
        items.add_item(self._make_item('JA000001', vendor='Amazon'))
        product = catalog.create_product(description='Widget')
        catalog.record_purchase(product.id, vendor='amazon')

        result = service.suggest('vendor', limit=20)
        assert len([v for v in result if v.lower() == 'amazon']) == 1

    @pytest.mark.unit
    def test_a_location_in_both_differing_only_in_case_is_offered_once(
        self, service, items, catalog
    ):
        items.add_item(self._make_item('JA000001', location='Drawer 3'))
        catalog.create_product(description='Widget', location='drawer 3')

        result = service.suggest('location', limit=20)
        assert len([v for v in result if v.lower() == 'drawer 3']) == 1

    @pytest.mark.unit
    def test_sub_location_scoping_uses_each_source_own_location_column(
        self, service, items, catalog
    ):
        # Same sub-location name under two different locations, one recorded on
        # each half. Scoping must filter each source against its own location.
        items.add_item(self._make_item(
            'JA000001', location='Shelf A', sub_location='Item Bin'
        ))
        catalog.create_product(
            description='Widget', location='Drawer 3', sub_location='Product Bin'
        )

        shelf = service.suggest('sub_location', location='Shelf A', limit=20)
        assert 'Item Bin' in shelf
        assert 'Product Bin' not in shelf

        drawer = service.suggest('sub_location', location='Drawer 3', limit=20)
        assert 'Product Bin' in drawer
        assert 'Item Bin' not in drawer

    @pytest.mark.unit
    def test_thread_size_reads_metal_stock_only(self, service, items, catalog):
        """Nothing in the catalogue records a thread size"""
        items.add_item(self._make_item('JA000001', thread_size='1/4-20'))
        catalog.create_product(description='Widget', location='1/4-20')

        result = service.suggest('thread_size', limit=20)
        assert result == ['1/4-20']

    @pytest.mark.unit
    def test_purchase_location_reads_metal_stock_only(self, service, items, catalog):
        items.add_item(self._make_item('JA000001', purchase_location='Grainger'))
        product = catalog.create_product(description='Widget')
        catalog.record_purchase(product.id, vendor='Digi-Key')

        result = service.suggest('purchase_location', limit=20)
        assert result == ['Grainger']

    @pytest.mark.unit
    def test_an_inactive_item_still_contributes(self, service, items):
        """FR-019: a name is not withdrawn because its item was deactivated"""
        items.add_item(self._make_item('JA000001', vendor='Discontinued Vendor'))
        items.deactivate_item('JA000001')

        assert 'Discontinued Vendor' in service.suggest('vendor', limit=20)

    @pytest.mark.unit
    def test_sources_are_re_ranked_as_a_whole(self, service, items, catalog):
        """A better match on either side outranks a worse one on the other"""
        items.add_item(self._make_item('JA000001', vendor='Acme Steel Inc'))
        product = catalog.create_product(description='Widget')
        catalog.record_purchase(product.id, vendor='Steel')

        result = service.suggest('vendor', query='steel', limit=20)
        assert result[0] == 'Steel'
        assert result[1] == 'Acme Steel Inc'
