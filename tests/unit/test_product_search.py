"""
Unit tests for catalogue search, category filtering and tags.

Three properties: a category filter includes its sub-categories and stops at
segment boundaries, a tag filter ignores category entirely, and search reaches
description, specifications, part number and identifier alike (FR-030, FR-031,
FR-032, SC-009).
"""

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ValidationError


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def catalogue(service):
    """A small catalogue with nested categories and cross-cutting tags"""
    service.create_product(
        description='Carbon film resistor, 10k',
        specifications=[
            {'name': 'Power rating', 'value': '1/4W'},
            {'name': 'Tolerance', 'value': '5%'},
        ],
        category_path='electronics/passives/resistors',
        tags=['surplus'],
        identifiers=[{'id_type': 'MPN', 'value': 'CF14JT10K0'}],
    )
    service.create_product(
        description='Ceramic capacitor, 100nF',
        specifications=[
            {'name': 'Voltage', 'value': '50V'},
            {'name': 'Dielectric', 'value': 'X7R'},
        ],
        category_path='electronics/passives/capacitors',
        tags=['rohs'],
    )
    service.create_product(
        description='LM358 op-amp',
        category_path='electronics/active',
        manufacturer_part_number='LM358N',
        tags=['surplus', 'rohs'],
    )
    service.create_product(
        description='M4 hex bolt',
        category_path='hardware/fasteners',
        tags=['surplus'],
    )
    # A sibling whose name merely starts the same way: filtering "electronics"
    # must not pull this in.
    service.create_product(
        description='Electronics-adjacent thing',
        category_path='electronics-surplus',
    )
    return service


def descriptions(products):
    return sorted(p.description for p in products)


class TestCategoryFilter:
    """Story 7 scenario 1"""

    def test_a_category_includes_its_sub_categories(self, catalogue):
        found = catalogue.search_products(category='electronics')
        assert descriptions(found) == [
            'Carbon film resistor, 10k',
            'Ceramic capacitor, 100nF',
            'LM358 op-amp',
        ]

    def test_a_deeper_category_narrows_further(self, catalogue):
        found = catalogue.search_products(category='electronics/passives')
        assert descriptions(found) == [
            'Carbon film resistor, 10k',
            'Ceramic capacitor, 100nF',
        ]

    def test_a_leaf_category_returns_only_its_own(self, catalogue):
        found = catalogue.search_products(category='electronics/passives/resistors')
        assert descriptions(found) == ['Carbon film resistor, 10k']

    def test_a_sibling_sharing_a_prefix_is_not_included(self, catalogue):
        """The boundary is the separator, not the character count"""
        found = catalogue.search_products(category='electronics')
        assert 'Electronics-adjacent thing' not in descriptions(found)

    def test_the_filter_is_normalized_like_the_stored_path(self, catalogue):
        assert len(catalogue.search_products(category=' Electronics / Passives ')) == 2

    def test_a_blank_category_filter_selects_everything(self, catalogue):
        assert len(catalogue.search_products(category='')) == 5

    def test_an_unused_category_returns_nothing_rather_than_erroring(self, catalogue):
        assert catalogue.search_products(category='nonexistent') == []


class TestTagFilter:
    """Story 7 scenario 2: tags cut across categories"""

    def test_a_tag_returns_matches_regardless_of_category(self, catalogue):
        found = catalogue.search_products(tag='surplus')
        assert descriptions(found) == [
            'Carbon film resistor, 10k', 'LM358 op-amp', 'M4 hex bolt',
        ]

    def test_a_tag_filter_is_case_insensitive(self, catalogue):
        assert len(catalogue.search_products(tag='SURPLUS')) == 3

    def test_a_product_can_carry_several_tags(self, catalogue):
        assert 'LM358 op-amp' in descriptions(catalogue.search_products(tag='rohs'))
        assert 'LM358 op-amp' in descriptions(catalogue.search_products(tag='surplus'))

    def test_category_and_tag_narrow_together(self, catalogue):
        found = catalogue.search_products(category='electronics', tag='surplus')
        assert descriptions(found) == ['Carbon film resistor, 10k', 'LM358 op-amp']

    def test_an_unused_tag_returns_nothing(self, catalogue):
        assert catalogue.search_products(tag='nonexistent') == []


class TestTextSearch:
    """Story 7 scenario 3: across all four fields"""

    def test_matches_a_description(self, catalogue):
        assert descriptions(catalogue.search_products(query='resistor')) == [
            'Carbon film resistor, 10k'
        ]

    def test_matches_a_specification(self, catalogue):
        assert descriptions(catalogue.search_products(query='X7R')) == [
            'Ceramic capacitor, 100nF'
        ]

    def test_matches_a_manufacturer_part_number(self, catalogue):
        assert descriptions(catalogue.search_products(query='LM358N')) == ['LM358 op-amp']

    def test_matches_a_stored_identifier(self, catalogue):
        assert descriptions(catalogue.search_products(query='CF14JT10K0')) == [
            'Carbon film resistor, 10k'
        ]

    def test_matches_an_internal_code(self, catalogue):
        product = catalogue.search_products(query='resistor')[0]
        found = catalogue.search_products(query=product.internal_code)
        assert [p.id for p in found] == [product.id]

    def test_a_partial_match_works(self, catalogue):
        assert len(catalogue.search_products(query='capacit')) == 1

    def test_a_blank_query_returns_everything(self, catalogue):
        assert len(catalogue.search_products(query='   ')) == 5

    def test_nothing_matching_is_an_empty_list_not_an_error(self, catalogue):
        assert catalogue.search_products(query='nothing here matches this') == []


class TestStockFilter:
    """SC-007: 'none on hand' and 'not tracked' must stay tellable apart"""

    @pytest.fixture
    def stocked(self, service):
        service.create_product(description='never counted')
        service.create_product(description='counted, none left', quantity=0)
        service.create_product(description='counted, plenty', quantity=50)
        service.create_product(description='at its threshold', quantity=2, reorder_threshold=2)
        service.create_product(description='flagged by hand')
        return service

    def test_tracked(self, stocked):
        found = stocked.search_products(stock='tracked')
        assert descriptions(found) == [
            'at its threshold', 'counted, none left', 'counted, plenty',
        ]

    def test_untracked(self, stocked):
        found = stocked.search_products(stock='untracked')
        assert descriptions(found) == ['flagged by hand', 'never counted']

    def test_none_on_hand_is_distinct_from_untracked(self, stocked):
        assert descriptions(stocked.search_products(stock='none-on-hand')) == [
            'counted, none left'
        ]

    def test_low(self, stocked):
        assert descriptions(stocked.search_products(stock='low')) == ['at its threshold']

    def test_an_unknown_stock_filter_says_what_the_valid_ones_are(self, stocked):
        with pytest.raises(ValidationError) as excinfo:
            stocked.search_products(stock='banana')
        assert 'none-on-hand' in str(excinfo.value)


class TestCategoryListing:
    def test_lists_the_categories_in_use(self, catalogue):
        assert catalogue.list_categories() == [
            'electronics-surplus',
            'electronics/active',
            'electronics/passives/capacitors',
            'electronics/passives/resistors',
            'hardware/fasteners',
        ]

    def test_a_prefix_narrows_to_a_subtree(self, catalogue):
        assert catalogue.list_categories(prefix='electronics') == [
            'electronics/active',
            'electronics/passives/capacitors',
            'electronics/passives/resistors',
        ]

    def test_an_empty_category_cannot_exist(self, service):
        """There is no categories table, so nothing can be in one and empty"""
        product = service.create_product(description='x', category_path='temporary')
        assert service.list_categories() == ['temporary']

        service.update_product(product.id, category_path=None)
        assert service.list_categories() == []

    def test_the_tree_carries_direct_counts(self, catalogue):
        tree = {entry['path']: entry['count'] for entry in catalogue.category_tree()}
        assert tree['electronics/passives/resistors'] == 1
        assert tree['hardware/fasteners'] == 1

    def test_the_tree_carries_depth_and_leaf_name(self, catalogue):
        entry = next(
            e for e in catalogue.category_tree()
            if e['path'] == 'electronics/passives/resistors'
        )
        assert entry['depth'] == 3
        assert entry['name'] == 'resistors'


class TestTags:
    def test_a_category_typed_during_creation_needs_no_setup_step(self, service):
        """Story 7 scenario 4, and the same is true of tags"""
        service.create_product(
            description='x', category_path='brand/new/category', tags=['brand-new-tag']
        )
        assert 'brand/new/category' in service.list_categories()
        assert 'brand-new-tag' in service.list_tags()

    def test_tags_are_listed_alphabetically(self, catalogue):
        assert catalogue.list_tags() == ['rohs', 'surplus']

    def test_a_prefix_narrows_the_tag_list(self, catalogue):
        assert catalogue.list_tags(prefix='sur') == ['surplus']

    def test_set_tags_replaces_the_whole_set(self, service):
        product = service.create_product(description='x', tags=['one', 'two'])
        updated = service.set_tags(product.id, ['two', 'three'])
        assert sorted(t.name for t in updated.tags) == ['three', 'two']

    def test_set_tags_can_clear_them_all(self, service):
        product = service.create_product(description='x', tags=['one'])
        assert service.set_tags(product.id, []).tags == []

    def test_detaching_a_tag_does_not_delete_it_from_another_product(self, service):
        first = service.create_product(description='first', tags=['shared'])
        second = service.create_product(description='second', tags=['shared'])

        service.set_tags(first.id, [])
        assert [t.name for t in service.get_product(second.id).tags] == ['shared']

    def test_an_unused_tag_row_is_left_alone(self, service):
        """Not garbage-collected on a schedule -- clutter would be the measurement"""
        product = service.create_product(description='x', tags=['orphan'])
        service.set_tags(product.id, [])
        assert 'orphan' in service.list_tags()


@pytest.fixture
def converters(service):
    """The SC-001 catalogue: two recorded voltages and one that only says so"""
    service.create_product(
        description='12 V buck converter',
        specifications=[
            {'name': 'Voltage', 'value': '12 V'},
            {'name': 'Output current', 'value': '3 A'},
        ],
        category_path='electronics/power',
    )
    service.create_product(
        description='5 V buck converter',
        specifications=[{'name': 'Voltage', 'value': '5 V'}],
        category_path='electronics/power',
    )
    service.create_product(
        # Mentions 12 V and records nothing. This is the product the feature
        # exists to stop returning.
        description='Bench supply, 12 V input, no recorded specs',
        category_path='electronics/test-gear',
    )
    return service


class TestSpecificationFilter:
    """FR-012..FR-016.

    FR-015's case-insensitivity *is* provable here, and only here. MariaDB's
    deployed collation folds case inside the comparison operator, so the e2e
    suite cannot tell ``func.lower(name) == ...`` from ``name == ...``; SQLite
    collates BINARY, so this is the backend that disagrees when the
    ``func.lower`` is dropped. See test_the_name_filter_is_case_insensitive.
    """

    def test_a_name_returns_every_value_under_it(self, converters):
        assert descriptions(converters.search_products(spec_name='Voltage')) == [
            '12 V buck converter', '5 V buck converter'
        ]

    def test_a_name_and_value_narrow_to_one(self, converters):
        """SC-001: the question the feature exists to answer"""
        assert descriptions(
            converters.search_products(spec_name='Voltage', spec_value='12 V')
        ) == ['12 V buck converter']

    def test_the_product_that_only_mentions_it_is_excluded(self, converters):
        found = descriptions(converters.search_products(spec_name='Voltage'))
        assert 'Bench supply, 12 V input, no recorded specs' not in found

    def test_a_value_matches_when_contained_not_only_when_equal(self, converters):
        """FR-014"""
        assert descriptions(
            converters.search_products(spec_name='Voltage', spec_value='12')
        ) == ['12 V buck converter']

    def test_a_value_without_a_name_is_ignored_rather_than_raising(self, converters):
        assert len(converters.search_products(spec_value='12 V')) == 3

    def test_an_unrecorded_name_is_an_empty_list_not_an_error(self, converters):
        assert converters.search_products(spec_name='Nobody records this') == []

    def test_a_blank_name_adds_no_clause(self, converters):
        assert len(converters.search_products(spec_name='   ')) == 3

    def test_the_name_filter_is_case_insensitive(self, converters):
        """FR-015, and this one *is* SQLite's to prove.

        MariaDB's deployed collation makes a bare ``==`` case-insensitive on its
        own, so the e2e suite cannot tell ``func.lower(name) == ...`` from
        ``name == ...``. SQLite collates BINARY, so here -- and only here --
        dropping the ``func.lower`` turns this red.
        """
        assert descriptions(converters.search_products(spec_name='voltage')) == [
            '12 V buck converter', '5 V buck converter'
        ]
        assert descriptions(converters.search_products(spec_name='VOLTAGE')) == [
            '12 V buck converter', '5 V buck converter'
        ]

    def test_the_name_is_matched_whole_not_as_a_prefix(self, converters):
        """FR-015 is whole-name: "Volt" must not match "Voltage" """
        assert converters.search_products(spec_name='Volt') == []

    def test_the_value_filter_is_case_insensitive(self, service):
        """FR-014. SQLite folds ASCII in LIKE only by default, so lowering both
        sides is what makes the two backends agree rather than coincide."""
        service.create_product(
            description='Mixed case value',
            specifications=[{'name': 'Finish', 'value': 'Blue Anodized'}],
        )
        assert descriptions(service.search_products(
            spec_name='Finish', spec_value='blue anodized'
        )) == ['Mixed case value']
        assert descriptions(service.search_products(
            spec_name='Finish', spec_value='ANODIZED'
        )) == ['Mixed case value']

    def test_wildcards_in_the_value_are_matched_literally(self, service):
        """An unescaped % would return the wrong answers"""
        service.create_product(
            description='Tolerance-tagged',
            specifications=[{'name': 'Tolerance', 'value': '5%'}],
        )
        service.create_product(
            description='Other',
            specifications=[{'name': 'Tolerance', 'value': 'tight'}],
        )
        assert descriptions(
            service.search_products(spec_name='Tolerance', spec_value='%')
        ) == ['Tolerance-tagged']

    def test_it_narrows_together_with_a_category(self, converters):
        """FR-016"""
        assert descriptions(converters.search_products(
            spec_name='Voltage', category='electronics/power'
        )) == ['12 V buck converter', '5 V buck converter']
        assert converters.search_products(
            spec_name='Voltage', category='electronics/test-gear'
        ) == []

    def test_it_narrows_together_with_a_text_query(self, converters):
        assert descriptions(converters.search_products(
            spec_name='Voltage', query='buck'
        )) == ['12 V buck converter', '5 V buck converter']

    def test_it_narrows_together_with_a_tag_and_stock_filter(self, service):
        service.create_product(
            description='Tracked and tagged',
            specifications=[{'name': 'Voltage', 'value': '12 V'}],
            tags=['surplus'], quantity=3,
        )
        service.create_product(
            description='Same spec, no tag',
            specifications=[{'name': 'Voltage', 'value': '12 V'}],
            quantity=3,
        )
        assert descriptions(service.search_products(
            spec_name='Voltage', tag='surplus', stock='tracked'
        )) == ['Tracked and tagged']


class TestFreeTextReachesSpecifications:
    """FR-017: nothing findable before this change may stop being findable"""

    def test_free_text_matches_a_specification_value(self, converters):
        assert descriptions(converters.search_products(query='3 A')) == [
            '12 V buck converter'
        ]

    def test_free_text_matches_a_specification_name(self, converters):
        assert descriptions(converters.search_products(query='Output current')) == [
            '12 V buck converter'
        ]


class TestSpecificationVocabulary:
    """FR-019, FR-020. The case-folding dedup is e2e's to prove, not SQLite's."""

    def test_names_in_use_are_listed(self, converters):
        assert converters.list_specification_names() == ['Output current', 'Voltage']

    def test_names_are_empty_when_nothing_is_recorded(self, service):
        assert service.list_specification_names() == []

    def test_a_prefix_narrows_the_names(self, converters):
        assert converters.list_specification_names(prefix='Vol') == ['Voltage']

    def test_a_prefix_narrows_case_insensitively(self, converters):
        assert converters.list_specification_names(prefix='vol') == ['Voltage']

    def test_a_prefix_matching_nothing_is_an_empty_list(self, converters):
        assert converters.list_specification_names(prefix='zzz') == []

    def test_one_name_is_offered_once_however_many_products_record_it(self, converters):
        assert converters.list_specification_names().count('Voltage') == 1

    def test_values_are_scoped_to_one_name(self, converters):
        # Alphabetical, like every other vocabulary reader here -- "12 V" sorts
        # before "5 V" because these are labels, not numbers (Constitution III:
        # a specification value is never parsed as one).
        assert converters.list_specification_values('Voltage') == ['12 V', '5 V']
        assert converters.list_specification_values('Output current') == ['3 A']

    def test_the_name_is_matched_case_insensitively(self, converters):
        assert converters.list_specification_values('voltage') == ['12 V', '5 V']

    def test_a_blank_name_returns_nothing_rather_than_everything(self, converters):
        assert converters.list_specification_values('   ') == []

    def test_an_unrecorded_name_returns_nothing_rather_than_raising(self, converters):
        assert converters.list_specification_values('Nobody records this') == []

    def test_a_prefix_narrows_the_values(self, converters):
        assert converters.list_specification_values('Voltage', prefix='12') == ['12 V']
