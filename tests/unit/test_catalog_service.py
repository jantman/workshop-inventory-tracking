"""
Unit tests for CatalogService product CRUD.

Built through the project's test_storage fixture so the same code path runs
against SQLite here and MariaDB in production.

The FR-008 group is the centre of gravity: a product's identity is its own row,
never a vendor's reusable item identifier, and nothing else in the suite covers
the edge case the spec raises ("a vendor reuses an item identifier for a
completely different product over time").
"""

import pytest

from app.catalog_service import CatalogService
from app.exceptions import DuplicateItemError, ItemNotFoundError, ValidationError


@pytest.fixture
def service(test_storage):
    """A CatalogService bound to the test database"""
    return CatalogService(test_storage)


class TestCreateProduct:
    def test_creates_with_a_description(self, service):
        product = service.create_product(description='Blue widget')
        assert product.id is not None
        assert product.description == 'Blue widget'

    def test_description_is_stripped(self, service):
        assert service.create_product(description='  Blue widget  ').description == 'Blue widget'

    def test_every_product_is_scannable_from_the_moment_it_exists(self, service):
        """FR-015: the internal code is assigned at creation, not at first print"""
        product = service.create_product(description='Blue widget')
        assert product.internal_code is not None
        assert product.internal_code.startswith('WIT')

    def test_two_products_get_different_internal_codes(self, service):
        first = service.create_product(description='first')
        second = service.create_product(description='second')
        assert first.internal_code != second.internal_code

    def test_optional_fields_are_stored(self, service):
        product = service.create_product(
            description='Blue widget',
            manufacturer='Acme',
            manufacturer_part_number='ACME-1',
            specifications='10mm, blue',
            location='Bin 4',
            notes='from the surplus bin',
        )
        assert product.manufacturer == 'Acme'
        assert product.manufacturer_part_number == 'ACME-1'
        assert product.specifications == '10mm, blue'
        assert product.location == 'Bin 4'
        assert product.notes == 'from the surplus bin'

    def test_category_is_normalized(self, service):
        product = service.create_product(
            description='Blue widget', category_path=' Electronics / Passives '
        )
        assert product.category_path == 'electronics/passives'

    def test_blank_category_means_uncategorized(self, service):
        assert service.create_product(description='x', category_path='  ').category_path is None

    def test_quantity_defaults_to_untracked(self, service):
        """FR-023"""
        product = service.create_product(description='Blue widget')
        assert product.quantity is None
        assert product.quantity_updated_at is None

    def test_a_supplied_quantity_is_stamped(self, service):
        product = service.create_product(description='Blue widget', quantity=4)
        assert product.quantity == 4
        assert product.quantity_updated_at is not None

    def test_tags_are_created_inline_and_lowercased(self, service):
        product = service.create_product(description='Blue widget', tags=['Surplus', 'RoHS'])
        assert sorted(t.name for t in product.tags) == ['rohs', 'surplus']

    def test_two_products_share_one_tag_row(self, service):
        first = service.create_product(description='first', tags=['surplus'])
        second = service.create_product(description='second', tags=['surplus'])
        assert first.tags[0].id == second.tags[0].id


class TestCreateProductValidation:
    def test_empty_description_rejects(self, service):
        with pytest.raises(ValidationError):
            service.create_product(description='')

    def test_whitespace_description_rejects(self, service):
        with pytest.raises(ValidationError):
            service.create_product(description='   ')

    def test_over_length_description_rejects(self, service):
        with pytest.raises(ValidationError):
            service.create_product(description='x' * 256)

    def test_negative_quantity_rejects(self, service):
        with pytest.raises(ValidationError):
            service.create_product(description='x', quantity=-1)

    def test_threshold_without_a_tracked_quantity_rejects(self, service):
        """FR-026: a threshold with nothing to compare against means nothing"""
        with pytest.raises(ValidationError):
            service.create_product(description='x', reorder_threshold=2)

    def test_threshold_with_a_tracked_quantity_is_accepted(self, service):
        product = service.create_product(description='x', quantity=0, reorder_threshold=2)
        assert product.reorder_threshold == 2


class TestGetProduct:
    def test_returns_the_product(self, service):
        created = service.create_product(description='Blue widget')
        assert service.get_product(created.id).description == 'Blue widget'

    def test_missing_product_is_none_not_an_error(self, service):
        assert service.get_product(99999) is None


class TestUpdateProduct:
    def test_updates_a_field(self, service):
        product = service.create_product(description='Blue widget')
        updated = service.update_product(product.id, description='Blue widget, 10mm')
        assert updated.description == 'Blue widget, 10mm'

    def test_omitted_fields_are_left_alone(self, service):
        product = service.create_product(description='Blue widget', location='Bin 4')
        updated = service.update_product(product.id, description='Renamed')
        assert updated.location == 'Bin 4'

    def test_category_is_normalized_on_update(self, service):
        product = service.create_product(description='x')
        updated = service.update_product(product.id, category_path='Hardware/Fasteners')
        assert updated.category_path == 'hardware/fasteners'

    def test_updating_a_missing_product_raises(self, service):
        with pytest.raises(ItemNotFoundError):
            service.update_product(99999, description='x')

    def test_invalid_field_rejects(self, service):
        product = service.create_product(description='x')
        with pytest.raises(ValidationError):
            service.update_product(product.id, description='')

    def test_unknown_field_rejects_rather_than_being_ignored(self, service):
        product = service.create_product(description='x')
        with pytest.raises(ValidationError):
            service.update_product(product.id, quantity=5)


class TestIdentifiers:
    def test_add_and_read_back(self, service):
        product = service.create_product(description='Blue widget')
        service.add_identifier(product.id, id_type='MPN', value='ACME-1')

        reloaded = service.get_product(product.id)
        assert 'ACME-1' in [i.value for i in reloaded.identifiers]

    def test_gtin_is_stored_normalized(self, service):
        """FR-009: normalizing on write is what makes the unique index enough"""
        product = service.create_product(description='Blue widget')
        identifier = service.add_identifier(product.id, id_type='GTIN', value='012345678905')
        assert identifier.value == '00012345678905'

    def test_equivalent_barcode_forms_resolve_to_one_product(self, service):
        product = service.create_product(description='Blue widget')
        service.add_identifier(product.id, id_type='GTIN', value='012345678905')

        by_upc = service.find_product_by_identifier('00012345678905')
        assert by_upc.id == product.id

    def test_bad_check_digit_rejects(self, service):
        product = service.create_product(description='Blue widget')
        with pytest.raises(ValidationError):
            service.add_identifier(product.id, id_type='GTIN', value='012345678906')

    def test_operator_can_override_a_failed_check_digit(self, service):
        """FR-010, recorded on the row so the override is visible"""
        product = service.create_product(description='Blue widget')
        identifier = service.add_identifier(
            product.id, id_type='GTIN', value='012345678906', override=True
        )
        assert identifier.validation_overridden is True

    def test_an_all_zero_no_read_cannot_be_overridden(self, service):
        product = service.create_product(description='Blue widget')
        with pytest.raises(ValidationError):
            service.add_identifier(
                product.id, id_type='GTIN', value='00000000', override=True
            )

    def test_vendor_identifier_requires_a_vendor(self, service):
        product = service.create_product(description='Blue widget')
        with pytest.raises(ValidationError):
            service.add_identifier(product.id, id_type='VENDOR', value='B0ABCDEFGH')

    def test_internal_codes_cannot_be_entered_by_hand(self, service):
        product = service.create_product(description='Blue widget')
        with pytest.raises(ValidationError):
            service.add_identifier(product.id, id_type='INTERNAL', value='not-a-code')

    def test_unknown_identifier_type_rejects(self, service):
        product = service.create_product(description='Blue widget')
        with pytest.raises(ValidationError):
            service.add_identifier(product.id, id_type='BANANA', value='x')

    def test_adding_the_same_identifier_twice_to_one_product_is_a_no_op(self, service):
        product = service.create_product(description='Blue widget')
        first = service.add_identifier(product.id, id_type='MPN', value='ACME-1')
        second = service.add_identifier(product.id, id_type='MPN', value='ACME-1')
        assert first.id == second.id

    def test_adding_to_a_missing_product_raises(self, service):
        with pytest.raises(ItemNotFoundError):
            service.add_identifier(99999, id_type='MPN', value='x')

    def test_remove_identifier(self, service):
        product = service.create_product(description='Blue widget')
        identifier = service.add_identifier(product.id, id_type='MPN', value='ACME-1')

        assert service.remove_identifier(product.id, identifier.id) is True
        assert service.find_product_by_identifier('ACME-1') is None

    def test_removing_a_missing_identifier_is_false_not_an_error(self, service):
        product = service.create_product(description='Blue widget')
        assert service.remove_identifier(product.id, 99999) is False


class TestFr008ProductIdentityIsItsOwnRow:
    """The spec edge case: a vendor reuses an item identifier over time.

    Nothing else in the suite covers this, and every assertion here is about the
    catalogue refusing to conflate two things a vendor happened to give the same
    name.
    """

    def test_the_same_vendor_item_id_under_two_vendors_yields_two_products(self, service):
        amazon = service.create_product(
            description='Blue widget',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        ebay = service.create_product(
            description='Green widget',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'eBay'}],
        )

        assert amazon.id != ebay.id
        assert service.find_product_by_identifier(
            'B0ABCDEFGH', id_type='VENDOR', vendor='Amazon'
        ).id == amazon.id
        assert service.find_product_by_identifier(
            'B0ABCDEFGH', id_type='VENDOR', vendor='eBay'
        ).id == ebay.id

    def test_reusing_one_vendors_item_id_creates_a_second_product(self, service):
        """It must not mutate or merge the first"""
        first = service.create_product(
            description='Blue widget, 2019 listing',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        second = service.create_product(
            description='Something else entirely, same ASIN',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )

        assert second.id != first.id
        assert second.description == 'Something else entirely, same ASIN'

        # The first product is exactly as it was: same description, and it still
        # owns the identifier.
        unchanged = service.get_product(first.id)
        assert unchanged.description == 'Blue widget, 2019 listing'
        assert service.find_product_by_identifier(
            'B0ABCDEFGH', id_type='VENDOR', vendor='Amazon'
        ).id == first.id

    def test_attaching_a_claimed_identifier_explicitly_says_who_claims_it(self, service):
        first = service.create_product(description='first')
        second = service.create_product(description='second')
        service.add_identifier(first.id, id_type='MPN', value='ACME-1')

        with pytest.raises(DuplicateItemError) as excinfo:
            service.add_identifier(second.id, id_type='MPN', value='ACME-1')

        assert excinfo.value.item_id == str(first.id)

    def test_deleting_every_identifier_leaves_the_product_intact(self, service):
        """Identity is the product row, never one of its names"""
        product = service.create_product(
            description='Blue widget',
            identifiers=[{'id_type': 'MPN', 'value': 'ACME-1'}],
        )
        for identifier in service.get_product(product.id).identifiers:
            assert service.remove_identifier(product.id, identifier.id) is True

        survivor = service.get_product(product.id)
        assert survivor is not None
        assert survivor.description == 'Blue widget'
        assert survivor.identifiers == []


class TestListProducts:
    def test_lists_what_was_created(self, service):
        service.create_product(description='first')
        service.create_product(description='second')
        assert {p.description for p in service.list_products()} == {'first', 'second'}

    def test_empty_catalogue_is_an_empty_list(self, service):
        assert service.list_products() == []
