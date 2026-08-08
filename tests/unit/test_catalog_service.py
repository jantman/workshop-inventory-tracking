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
            specifications=[{'name': 'Diameter', 'value': '10mm'}],
            location='Bin 4',
            notes='from the surplus bin',
        )
        assert product.manufacturer == 'Acme'
        assert product.manufacturer_part_number == 'ACME-1'
        assert [(s.name, s.value) for s in product.specifications] == [
            ('Diameter', '10mm')
        ]
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


def _paths(service):
    """Every product's category path, keyed by description"""
    return {p.description: p.category_path for p in service.list_products()}


class TestRenameCategory:
    """FR-001..FR-007: one action moves the subtree, or nothing moves at all"""

    @pytest.fixture
    def tree(self, service):
        """A subtree plus a sibling that merely shares a prefix"""
        service.create_product(description='top', category_path='elctronics')
        service.create_product(description='child', category_path='elctronics/passives')
        service.create_product(
            description='grandchild', category_path='elctronics/passives/resistors'
        )
        service.create_product(description='prefix sibling', category_path='elctronics-surplus')
        return service

    def test_carries_the_whole_subtree(self, tree):
        tree.rename_category('elctronics', 'electronics')
        paths = _paths(tree)
        assert paths['top'] == 'electronics'
        assert paths['child'] == 'electronics/passives'
        assert paths['grandchild'] == 'electronics/passives/resistors'

    def test_a_sibling_sharing_a_prefix_is_untouched(self, tree):
        """The boundary is the separator, not the character count"""
        tree.rename_category('elctronics', 'electronics')
        assert _paths(tree)['prefix sibling'] == 'elctronics-surplus'

    def test_reports_what_moved(self, tree):
        report = tree.rename_category('elctronics', 'electronics')
        assert report == {
            'from': 'elctronics',
            'to': 'electronics',
            'products': 3,
            'categories': 3,
        }

    def test_counts_distinct_categories_not_rows(self, service):
        service.create_product(description='a', category_path='old')
        service.create_product(description='b', category_path='old')
        report = service.rename_category('old', 'new')
        assert report['products'] == 2
        assert report['categories'] == 1

    def test_renaming_a_deeper_path_leaves_its_parent_and_siblings_alone(self, service):
        service.create_product(description='parent', category_path='power')
        service.create_product(description='target', category_path='power/dc dc')
        service.create_product(description='deep', category_path='power/dc dc/buck')
        service.create_product(description='sibling', category_path='power/linear')

        service.rename_category('power/dc dc', 'power/converters')
        paths = _paths(service)
        assert paths['parent'] == 'power'
        assert paths['target'] == 'power/converters'
        assert paths['deep'] == 'power/converters/buck'
        assert paths['sibling'] == 'power/linear'

    def test_operands_are_canonicalized(self, tree):
        tree.rename_category(' ELCTRONICS ', ' Electronics ')
        assert _paths(tree)['top'] == 'electronics'

    def test_renaming_into_a_subtree_that_is_coming_along_is_allowed(self, service):
        """"a" -> "b" with "a/b" present: "a/b" becomes "b/b", and "b" was free"""
        service.create_product(description='root', category_path='a')
        service.create_product(description='inner', category_path='a/b')

        service.rename_category('a', 'b')
        paths = _paths(service)
        assert paths['root'] == 'b'
        assert paths['inner'] == 'b/b'


class TestRenameCategoryRefusals:
    """Every refusal names the obstruction and leaves the data byte-identical"""

    @pytest.fixture
    def tree(self, service):
        service.create_product(description='top', category_path='electronics')
        service.create_product(description='child', category_path='electronics/passives')
        service.create_product(description='other', category_path='hardware')
        return service

    def _unchanged(self, service):
        return {
            'top': 'electronics',
            'child': 'electronics/passives',
            'other': 'hardware',
        }

    def test_blank_source_is_refused(self, tree):
        with pytest.raises(ValidationError) as excinfo:
            tree.rename_category('  ', 'electronics')
        assert 'blank' in str(excinfo.value.message).lower()
        assert _paths(tree) == self._unchanged(tree)

    def test_blank_target_is_refused(self, tree):
        with pytest.raises(ValidationError) as excinfo:
            tree.rename_category('electronics', '   ')
        assert 'blank' in str(excinfo.value.message).lower()
        assert _paths(tree) == self._unchanged(tree)

    def test_a_case_only_rename_is_refused_as_a_no_op(self, tree):
        with pytest.raises(ValidationError) as excinfo:
            tree.rename_category('electronics', 'Electronics')
        assert 'nothing to rename' in str(excinfo.value.message).lower()
        assert _paths(tree) == self._unchanged(tree)

    def test_self_nesting_is_refused(self, tree):
        with pytest.raises(ValidationError) as excinfo:
            tree.rename_category('electronics', 'electronics/passives')
        message = str(excinfo.value.message)
        assert 'electronics' in message and 'inside' in message
        assert _paths(tree) == self._unchanged(tree)

    def test_a_collision_is_refused_and_names_the_colliding_path(self, tree):
        with pytest.raises(ValidationError) as excinfo:
            tree.rename_category('electronics', 'hardware')
        assert 'hardware' in str(excinfo.value.message)
        assert _paths(tree) == self._unchanged(tree)

    def test_a_collision_beneath_the_target_is_also_refused(self, service):
        """Renaming into a target that only exists as an ancestor still merges"""
        service.create_product(description='source', category_path='a')
        service.create_product(description='occupant', category_path='b/c')

        with pytest.raises(ValidationError) as excinfo:
            service.rename_category('a', 'b')
        assert 'b/c' in str(excinfo.value.message)
        assert _paths(service) == {'source': 'a', 'occupant': 'b/c'}

    def test_an_over_length_descendant_is_refused_not_truncated(self, service):
        from app.catalog_service import MAX_CATEGORY_PATH_LENGTH

        service.create_product(description='top', category_path='a')
        service.create_product(description='deep', category_path='a/' + 'x' * 400)
        long_name = 'y' * (MAX_CATEGORY_PATH_LENGTH - 200)

        with pytest.raises(ValidationError) as excinfo:
            service.rename_category('a', long_name)
        assert str(MAX_CATEGORY_PATH_LENGTH) in str(excinfo.value.message)
        assert _paths(service) == {'top': 'a', 'deep': 'a/' + 'x' * 400}

    def test_renaming_a_category_nothing_is_in_is_refused(self, tree):
        with pytest.raises(ValidationError) as excinfo:
            tree.rename_category('nonexistent', 'something')
        assert 'nonexistent' in str(excinfo.value.message)
        assert _paths(tree) == self._unchanged(tree)


def _tag_names(service, product_id):
    return sorted(t.name for t in service.get_product(product_id).tags)


class TestRenameTag:
    """FR-008..FR-012: rename onto a free name, merge onto an occupied one"""

    def test_plain_rename_keeps_the_products(self, service):
        product = service.create_product(description='w', tags=['surpluss'])

        report = service.rename_tag('surpluss', 'surplus')
        assert report == {
            'from': 'surpluss', 'to': 'surplus', 'merged': False, 'products': 1
        }
        assert _tag_names(service, product.id) == ['surplus']
        assert [t['name'] for t in service.tag_list_with_counts()] == ['surplus']

    def test_the_target_name_is_normalized(self, service):
        product = service.create_product(description='w', tags=['surpluss'])
        service.rename_tag('surpluss', '  SURPLUS  ')
        assert _tag_names(service, product.id) == ['surplus']

    def test_merge_moves_products_onto_the_survivor(self, service):
        source = service.create_product(description='source', tags=['surpluss'])
        target = service.create_product(description='target', tags=['surplus'])

        report = service.rename_tag('surpluss', 'surplus')
        assert report['merged'] is True
        assert report['products'] == 1
        assert _tag_names(service, source.id) == ['surplus']
        assert _tag_names(service, target.id) == ['surplus']
        assert [t['name'] for t in service.tag_list_with_counts()] == ['surplus']

    def test_a_product_carrying_both_survives_the_merge_carrying_it_once(self, service):
        """FR-010: already carrying both is a no-op, not an integrity error"""
        both = service.create_product(description='both', tags=['surpluss', 'surplus'])

        report = service.rename_tag('surpluss', 'surplus')
        assert report['products'] == 0  # it already carried the survivor
        assert _tag_names(service, both.id) == ['surplus']

    def test_the_merge_carries_the_union(self, service):
        a = service.create_product(description='a', tags=['surpluss'])
        b = service.create_product(description='b', tags=['surplus'])
        both = service.create_product(description='both', tags=['surpluss', 'surplus'])

        service.rename_tag('surpluss', 'surplus')
        counts = service.tag_list_with_counts()
        assert counts == [{'id': counts[0]['id'], 'name': 'surplus', 'count': 3}]
        for product in (a, b, both):
            assert _tag_names(service, product.id) == ['surplus']

    def test_a_merge_does_not_depend_on_direction(self, service):
        """Merging a into b and b into a leave the same product set"""
        forward = CatalogService(service.storage)
        a1 = forward.create_product(description='a1', tags=['alpha'])
        b1 = forward.create_product(description='b1', tags=['beta'])
        both1 = forward.create_product(description='both1', tags=['alpha', 'beta'])
        forward.rename_tag('alpha', 'beta')
        forward_set = {
            p.description for p in forward.search_products(tag='beta')
        }

        assert forward_set == {'a1', 'b1', 'both1'}
        assert _tag_names(forward, a1.id) == ['beta']
        assert _tag_names(forward, b1.id) == ['beta']
        assert _tag_names(forward, both1.id) == ['beta']

        a2 = forward.create_product(description='a2', tags=['gamma'])
        b2 = forward.create_product(description='b2', tags=['delta'])
        both2 = forward.create_product(description='both2', tags=['gamma', 'delta'])
        forward.rename_tag('delta', 'gamma')
        reverse_set = {
            p.description for p in forward.search_products(tag='gamma')
        }

        assert reverse_set == {'a2', 'b2', 'both2'}
        assert _tag_names(forward, a2.id) == ['gamma']
        assert _tag_names(forward, b2.id) == ['gamma']
        assert _tag_names(forward, both2.id) == ['gamma']


class TestRenameTagRefusals:
    def test_blank_source_is_refused(self, service):
        with pytest.raises(ValidationError):
            service.rename_tag('  ', 'surplus')

    def test_blank_target_is_refused(self, service):
        service.create_product(description='w', tags=['surplus'])
        with pytest.raises(ValidationError):
            service.rename_tag('surplus', '   ')

    def test_a_case_only_rename_is_refused_as_a_no_op(self, service):
        product = service.create_product(description='w', tags=['surplus'])
        with pytest.raises(ValidationError) as excinfo:
            service.rename_tag('surplus', 'Surplus')
        assert 'nothing to rename' in str(excinfo.value.message).lower()
        assert _tag_names(service, product.id) == ['surplus']

    def test_an_over_length_target_is_refused(self, service):
        from app.catalog_service import MAX_TAG_LENGTH

        product = service.create_product(description='w', tags=['surplus'])
        with pytest.raises(ValidationError):
            service.rename_tag('surplus', 'x' * (MAX_TAG_LENGTH + 1))
        assert _tag_names(service, product.id) == ['surplus']

    def test_renaming_a_tag_that_does_not_exist_is_refused(self, service):
        with pytest.raises(ValidationError) as excinfo:
            service.rename_tag('nonexistent', 'something')
        assert 'nonexistent' in str(excinfo.value.message)


class TestTagListWithCounts:
    def test_empty_catalogue_is_an_empty_list(self, service):
        assert service.tag_list_with_counts() == []

    def test_counts_the_products_carrying_each_tag(self, service):
        service.create_product(description='a', tags=['surplus', 'rohs'])
        service.create_product(description='b', tags=['surplus'])

        assert [
            (t['name'], t['count']) for t in service.tag_list_with_counts()
        ] == [('rohs', 1), ('surplus', 2)]

    def test_alphabetical_by_name(self, service):
        service.create_product(description='a', tags=['zulu', 'alpha', 'mike'])
        assert [
            t['name'] for t in service.tag_list_with_counts()
        ] == ['alpha', 'mike', 'zulu']

    def test_an_orphan_tag_is_shown_with_a_count_of_zero(self, service):
        """Debris is exactly what the page exists to reveal"""
        product = service.create_product(description='a', tags=['surplus'])
        service.set_tags(product.id, [])

        assert service.tag_list_with_counts() == [
            {'id': service.tag_list_with_counts()[0]['id'],
             'name': 'surplus', 'count': 0}
        ]


class TestProductSubLocation:
    """FR-020..FR-023: a product records a sub-location the same way an item does"""

    def test_round_trips_through_create(self, service):
        product = service.create_product(
            description='w', location='Drawer 3', sub_location='Bin 7'
        )
        assert service.get_product(product.id).sub_location == 'Bin 7'

    def test_round_trips_through_update(self, service):
        product = service.create_product(description='w', location='Drawer 3')
        service.update_product(product.id, sub_location='Bin 7')
        assert service.get_product(product.id).sub_location == 'Bin 7'

    def test_update_product_accepts_it_rather_than_refusing_it(self, service):
        """A field absent from `editable` raises; this one must be in the set"""
        product = service.create_product(description='w')
        service.update_product(product.id, sub_location='Bin 7')  # must not raise

    def test_a_product_created_without_one_has_none(self, service):
        """FR-023: no sub-location recorded is an ordinary state, not an error"""
        product = service.create_product(description='w', location='Drawer 3')
        assert service.get_product(product.id).sub_location is None

    def test_blank_is_stored_as_none(self, service):
        product = service.create_product(description='w', sub_location='   ')
        assert service.get_product(product.id).sub_location is None

    def test_it_appears_in_to_dict(self, service):
        product = service.create_product(description='w', sub_location='Bin 7')
        assert service.get_product(product.id).to_dict()['sub_location'] == 'Bin 7'


def spec_pairs(product):
    """A product's specifications as (name, value) tuples, in display order"""
    return [(s.name, s.value) for s in product.specifications]


class TestSpecifications:
    """FR-004..FR-009: named values, replaced wholesale, validated in one place.

    Note what this file *cannot* prove: SQLite collates BINARY, so a
    case-sensitive duplicate check passes every test here and always would. The
    case that matters runs in tests/e2e/test_product_specifications.py against
    the deployed collation.
    """

    def test_create_stores_a_list_in_order(self, service):
        product = service.create_product(
            description='Buck converter',
            specifications=[
                {'name': 'Voltage', 'value': '12 V'},
                {'name': 'Output current', 'value': '3 A'},
            ],
        )
        assert spec_pairs(service.get_product(product.id)) == [
            ('Voltage', '12 V'), ('Output current', '3 A')
        ]

    def test_create_without_any_is_an_ordinary_state(self, service):
        assert spec_pairs(service.create_product(description='w')) == []

    def test_both_fields_are_trimmed(self, service):
        """FR-005: stored as typed, minus the surrounding whitespace"""
        product = service.create_product(
            description='w', specifications=[{'name': '  Voltage  ', 'value': '  12 V  '}]
        )
        assert spec_pairs(product) == [('Voltage', '12 V')]

    def test_interior_whitespace_is_left_alone(self, service):
        """Only the surrounding whitespace goes -- a newline inside a value stays"""
        product = service.create_product(
            description='w',
            specifications=[{'name': 'Notes', 'value': 'first line\nsecond line'}],
        )
        assert spec_pairs(product) == [('Notes', 'first line\nsecond line')]

    def test_a_fully_blank_entry_is_dropped_not_refused(self, service):
        """FR-009: an untouched row on the form is not an error"""
        product = service.create_product(
            description='w',
            specifications=[
                {'name': 'Voltage', 'value': '12 V'},
                {'name': '   ', 'value': ''},
                {'name': 'Current', 'value': '3 A'},
            ],
        )
        assert spec_pairs(product) == [('Voltage', '12 V'), ('Current', '3 A')]

    def test_display_order_has_no_gap_after_a_dropped_blank(self, service):
        """FR-006: the order is the *surviving* list index"""
        product = service.create_product(
            description='w',
            specifications=[
                {'name': 'Voltage', 'value': '12 V'},
                {'name': '', 'value': ''},
                {'name': 'Current', 'value': '3 A'},
            ],
        )
        assert [s.display_order for s in product.specifications] == [0, 1]

    def test_a_name_with_no_value_is_refused(self, service):
        """FR-008, and the message names the offender"""
        with pytest.raises(ValidationError) as refusal:
            service.create_product(
                description='w', specifications=[{'name': 'Voltage', 'value': '  '}]
            )
        assert 'Voltage' in refusal.value.message

    def test_a_value_with_no_name_is_refused(self, service):
        with pytest.raises(ValidationError) as refusal:
            service.create_product(
                description='w', specifications=[{'name': '', 'value': '12 V'}]
            )
        assert '12 V' in refusal.value.message

    def test_a_duplicate_name_is_refused(self, service):
        with pytest.raises(ValidationError):
            service.create_product(
                description='w',
                specifications=[
                    {'name': 'Voltage', 'value': '12 V'},
                    {'name': 'Voltage', 'value': '5 V'},
                ],
            )

    def test_a_duplicate_name_is_refused_case_insensitively(self, service):
        """FR-004. SQLite would pass this either way -- see the class docstring"""
        with pytest.raises(ValidationError):
            service.create_product(
                description='w',
                specifications=[
                    {'name': 'Voltage', 'value': '12 V'},
                    {'name': 'voltage', 'value': '5 V'},
                ],
            )

    def test_names_differing_only_by_accent_are_two_names(self, service):
        """FR-004 speaks of case and whitespace, not accents -- both must save.

        This is the case a UniqueConstraint would have broken under the deployed
        accent-folding collation, which is why there is not one.
        """
        product = service.create_product(
            description='w',
            specifications=[
                {'name': 'Volt', 'value': '12'},
                {'name': 'Vôlt', 'value': '5'},
            ],
        )
        assert spec_pairs(product) == [('Volt', '12'), ('Vôlt', '5')]

    @pytest.mark.parametrize("malformed", [
        # The shape this endpoint had before feature 005: one block of text. A
        # str is iterable, so without an explicit refusal it gets walked
        # character by character and crashes on the first one.
        'Voltage: 12 V',
        # A list of the wrong thing, which is the other obvious mistake.
        ['Voltage: 12 V'],
        [None],
        [42],
        {'name': 'Voltage', 'value': '12 V'},
    ])
    def test_a_malformed_specifications_payload_is_a_validation_error(
        self, service, malformed
    ):
        """Not an AttributeError.

        POST /api/products passes whatever a client sends straight through, and
        its `except ValidationError` is what turns a bad payload into a 400. An
        AttributeError escapes that and surfaces as a 500, which is both the
        wrong status and a contradiction of the route's own contract.
        """
        with pytest.raises(ValidationError):
            service.create_product(description='w', specifications=malformed)

    def test_an_over_long_name_is_refused(self, service):
        with pytest.raises(ValidationError):
            service.create_product(
                description='w',
                specifications=[{'name': 'V' * 101, 'value': '12 V'}],
            )

    def test_a_refusal_creates_no_product_at_all(self, service):
        with pytest.raises(ValidationError):
            service.create_product(
                description='Never created',
                specifications=[{'name': 'Voltage', 'value': ''}],
            )
        assert [p.description for p in service.list_products()] == []

    def test_update_replaces_the_whole_set(self, service):
        product = service.create_product(
            description='w',
            specifications=[
                {'name': 'Voltage', 'value': '12 V'},
                {'name': 'Current', 'value': '3 A'},
            ],
        )
        updated = service.update_product(
            product.id, specifications=[{'name': 'Connector', 'value': 'barrel'}]
        )
        assert spec_pairs(updated) == [('Connector', 'barrel')]

    def test_update_without_the_key_leaves_the_rows_untouched(self, service):
        """The method's existing contract: knowing three fields cannot blank ten"""
        product = service.create_product(
            description='w', specifications=[{'name': 'Voltage', 'value': '12 V'}]
        )
        updated = service.update_product(product.id, description='Renamed')
        assert spec_pairs(updated) == [('Voltage', '12 V')]

    def test_update_with_an_empty_list_clears_them(self, service):
        product = service.create_product(
            description='w', specifications=[{'name': 'Voltage', 'value': '12 V'}]
        )
        assert spec_pairs(service.update_product(product.id, specifications=[])) == []

    def test_update_reorders_when_the_list_order_changes(self, service):
        product = service.create_product(
            description='w',
            specifications=[
                {'name': 'Voltage', 'value': '12 V'},
                {'name': 'Current', 'value': '3 A'},
            ],
        )
        updated = service.update_product(
            product.id,
            specifications=[
                {'name': 'Current', 'value': '3 A'},
                {'name': 'Voltage', 'value': '12 V'},
            ],
        )
        assert spec_pairs(updated) == [('Current', '3 A'), ('Voltage', '12 V')]

    def test_a_refused_update_leaves_the_other_fields_unchanged_too(self, service):
        """The session context manager rolls the whole update back"""
        product = service.create_product(
            description='Original',
            specifications=[{'name': 'Voltage', 'value': '12 V'}],
        )
        with pytest.raises(ValidationError):
            service.update_product(
                product.id,
                description='Renamed',
                specifications=[{'name': 'Current', 'value': ''}],
            )

        unchanged = service.get_product(product.id)
        assert unchanged.description == 'Original'
        assert spec_pairs(unchanged) == [('Voltage', '12 V')]

    def test_they_appear_in_to_dict(self, service):
        """FR-011: a machine-readable list, in display order"""
        product = service.create_product(
            description='w',
            specifications=[
                {'name': 'Voltage', 'value': '12 V'},
                {'name': 'Current', 'value': '3 A'},
            ],
        )
        assert service.get_product(product.id).to_dict()['specifications'] == [
            {'name': 'Voltage', 'value': '12 V'},
            {'name': 'Current', 'value': '3 A'},
        ]
