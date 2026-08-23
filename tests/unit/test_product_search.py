"""
Unit tests for catalog search, category filtering and tags.

Three properties: a category filter includes its sub-categories and stops at
segment boundaries, a tag filter ignores category entirely, and search reaches
description, specifications, part number, identifier and notes alike (FR-030,
FR-031, FR-032, SC-009, and 009 FR-010).
"""

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ValidationError
from app.utils.catalog_taxonomy import CATEGORY_PATHS, SPECIFICATION_KEYS


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def catalog(service):
    """A small catalog with nested categories and cross-cutting tags"""
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
        # Names LM358, which is another product's description. Searching for it
        # must return both products, once each (009 FR-010, FR-011).
        notes='bought with the LM358 order',
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
    # The notes case: a phrase in the operator's own words that appears in no
    # other field on any product. Deliberately outside every category and tag
    # the filter tests assert on, so it constrains only the notes cases.
    service.create_product(
        description='Toroidal transformer',
        category_path='workshop/salvage',
        notes='left over from the lathe stand rebuild',
    )
    return service


def descriptions(products):
    return sorted(p.description for p in products)


class TestCategoryFilter:
    """Story 7 scenario 1"""

    def test_a_category_includes_its_sub_categories(self, catalog):
        found = catalog.search_products(category='electronics')
        assert descriptions(found) == [
            'Carbon film resistor, 10k',
            'Ceramic capacitor, 100nF',
            'LM358 op-amp',
        ]

    def test_a_deeper_category_narrows_further(self, catalog):
        found = catalog.search_products(category='electronics/passives')
        assert descriptions(found) == [
            'Carbon film resistor, 10k',
            'Ceramic capacitor, 100nF',
        ]

    def test_a_leaf_category_returns_only_its_own(self, catalog):
        found = catalog.search_products(category='electronics/passives/resistors')
        assert descriptions(found) == ['Carbon film resistor, 10k']

    def test_a_sibling_sharing_a_prefix_is_not_included(self, catalog):
        """The boundary is the separator, not the character count"""
        found = catalog.search_products(category='electronics')
        assert 'Electronics-adjacent thing' not in descriptions(found)

    def test_the_filter_is_normalized_like_the_stored_path(self, catalog):
        assert len(catalog.search_products(category=' Electronics / Passives ')) == 2

    def test_a_blank_category_filter_selects_everything(self, catalog):
        assert len(catalog.search_products(category='')) == 6

    def test_an_unused_category_returns_nothing_rather_than_erroring(self, catalog):
        assert catalog.search_products(category='nonexistent') == []


class TestTagFilter:
    """Story 7 scenario 2: tags cut across categories"""

    def test_a_tag_returns_matches_regardless_of_category(self, catalog):
        found = catalog.search_products(tag='surplus')
        assert descriptions(found) == [
            'Carbon film resistor, 10k', 'LM358 op-amp', 'M4 hex bolt',
        ]

    def test_a_tag_filter_is_case_insensitive(self, catalog):
        assert len(catalog.search_products(tag='SURPLUS')) == 3

    def test_a_product_can_carry_several_tags(self, catalog):
        assert 'LM358 op-amp' in descriptions(catalog.search_products(tag='rohs'))
        assert 'LM358 op-amp' in descriptions(catalog.search_products(tag='surplus'))

    def test_category_and_tag_narrow_together(self, catalog):
        found = catalog.search_products(category='electronics', tag='surplus')
        assert descriptions(found) == ['Carbon film resistor, 10k', 'LM358 op-amp']

    def test_an_unused_tag_returns_nothing(self, catalog):
        assert catalog.search_products(tag='nonexistent') == []


class TestTextSearch:
    """Story 7 scenario 3: across all four fields"""

    def test_matches_a_description(self, catalog):
        assert descriptions(catalog.search_products(query='resistor')) == [
            'Carbon film resistor, 10k'
        ]

    def test_matches_a_specification(self, catalog):
        assert descriptions(catalog.search_products(query='X7R')) == [
            'Ceramic capacitor, 100nF'
        ]

    def test_matches_a_manufacturer_part_number(self, catalog):
        assert descriptions(catalog.search_products(query='LM358N')) == ['LM358 op-amp']

    def test_matches_a_stored_identifier(self, catalog):
        assert descriptions(catalog.search_products(query='CF14JT10K0')) == [
            'Carbon film resistor, 10k'
        ]

    def test_matches_an_internal_code(self, catalog):
        product = catalog.search_products(query='resistor')[0]
        found = catalog.search_products(query=product.internal_code)
        assert [p.id for p in found] == [product.id]

    def test_a_partial_match_works(self, catalog):
        assert len(catalog.search_products(query='capacit')) == 1

    def test_a_blank_query_returns_everything(self, catalog):
        assert len(catalog.search_products(query='   ')) == 6

    def test_nothing_matching_is_an_empty_list_not_an_error(self, catalog):
        assert catalog.search_products(query='nothing here matches this') == []


class TestNotesAreSearched:
    """009 FR-010 .. FR-014: the field the operator writes prose in is findable.

    There is deliberately no case-insensitivity test here. SQLite's LIKE and
    MariaDB's utf8mb4 _ci collation both fold ASCII case, so the two backends
    agree and such a test would pass whether the query said `like` or `ilike` --
    it would assert nothing about which. What guarantees 009 FR-012 is that
    notes use the identical construct as the five clauses beside it, and the
    test that shows it is test_a_term_in_one_description_and_another_note below.
    """

    def test_a_phrase_held_only_in_notes_finds_the_product(self, catalog):
        assert descriptions(catalog.search_products(query='lathe stand')) == [
            'Toroidal transformer'
        ]

    def test_a_partial_word_from_the_notes_matches(self, catalog):
        assert descriptions(catalog.search_products(query='salvag')) == []
        assert descriptions(catalog.search_products(query='rebuild')) == [
            'Toroidal transformer'
        ]

    def test_a_product_with_no_notes_is_not_returned_for_someone_elses(self, catalog):
        found = descriptions(catalog.search_products(query='lathe stand'))
        assert 'M4 hex bolt' not in found
        assert 'Electronics-adjacent thing' not in found

    def test_a_term_in_one_description_and_another_note(self, catalog):
        """009 FR-011: both, once each. An or_ disjunct cannot multiply a row,
        which is why notes needs no de-duplication the way identifiers do."""
        found = [p.description for p in catalog.search_products(query='LM358')]
        assert sorted(found) == ['Ceramic capacitor, 100nF', 'LM358 op-amp']
        assert len(found) == len(set(found))

    def test_the_other_filters_still_bind_a_notes_match(self, catalog):
        """009 FR-013: matching through notes is not an escape from the filters"""
        assert descriptions(
            catalog.search_products(query='lathe stand', category='workshop')
        ) == ['Toroidal transformer']
        assert catalog.search_products(
            query='lathe stand', category='electronics'
        ) == []
        assert catalog.search_products(query='lathe stand', tag='surplus') == []


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
    """The listing is the union of what is in use and what the taxonomy names.

    These assertions became containment rather than equality when 025 added the
    taxonomy: the list now carries every branch of docs/category-taxonomy.md
    whether or not a product occupies it. What each test is actually about --
    in-use paths surviving, the subtree boundary, and a category vanishing with
    its last product -- is unchanged, so each is expressed against the paths it
    is about rather than against the whole list.
    """

    IN_USE = [
        'electronics-surplus',
        'electronics/active',
        'electronics/passives/capacitors',
        'electronics/passives/resistors',
        'hardware/fasteners',
        'workshop/salvage',
    ]

    def test_lists_the_categories_in_use(self, catalog):
        listed = catalog.list_categories()
        assert set(self.IN_USE) <= set(listed)
        assert listed == sorted(listed)

    def test_lists_taxonomy_branches_no_product_occupies(self, catalog):
        """025 FR-012: the branch has to be offered before anything is in it"""
        listed = catalog.list_categories()
        assert set(CATEGORY_PATHS) <= set(listed)

    def test_each_path_appears_once(self, catalog):
        """025 FR-018: offered and occupied are one branch, not two"""
        listed = catalog.list_categories()
        assert len(listed) == len(set(listed))

    def test_a_prefix_narrows_to_a_subtree(self, catalog):
        """The boundary is the separator, not the character count.

        ``electronics-surplus`` is a different category that merely starts with
        the same letters, and it is the reason this test exists.
        """
        listed = catalog.list_categories(prefix='electronics')

        assert {
            'electronics/active',
            'electronics/passives/capacitors',
            'electronics/passives/resistors',
        } <= set(listed)
        assert 'electronics-surplus' not in listed
        assert 'hardware/fasteners' not in listed
        assert 'workshop/salvage' not in listed
        assert all(
            path == 'electronics' or path.startswith('electronics/')
            for path in listed
        )

    def test_a_category_the_taxonomy_does_not_name_exists_only_while_occupied(
        self, service
    ):
        """Still no categories table: such a category dies with its last product.

        The taxonomy did not change this. It named 142 branches that are offered
        regardless, and left everything else exactly as it was -- a string on a
        product and nothing more.
        """
        assert 'temporary' not in CATEGORY_PATHS

        product = service.create_product(description='x', category_path='temporary')
        assert 'temporary' in service.list_categories()

        service.update_product(product.id, category_path=None)
        assert 'temporary' not in service.list_categories()

    def test_the_tree_carries_direct_counts(self, catalog):
        tree = {entry['path']: entry['count'] for entry in catalog.category_tree()}
        assert tree['electronics/passives/resistors'] == 1
        assert tree['hardware/fasteners'] == 1

    def test_the_tree_carries_depth_and_leaf_name(self, catalog):
        entry = next(
            e for e in catalog.category_tree()
            if e['path'] == 'electronics/passives/resistors'
        )
        assert entry['depth'] == 3
        assert entry['name'] == 'resistors'

    def test_the_tree_offers_taxonomy_branches_at_a_count_of_zero(self, catalog):
        """An entry that could not previously exist: on offer, unoccupied.

        Anything rendering a rename control has to gate on this count --
        rename_category refuses a category no product carries.
        """
        entry = self._entry(catalog, 'fasteners/machine screws & bolts/socket head cap')
        assert entry['count'] == 0
        assert entry['in_taxonomy'] is True

    def test_the_tree_flags_a_path_the_taxonomy_does_not_name(self, catalog):
        """025 FR-019: the only thing that makes that divergence visible"""
        entry = self._entry(catalog, 'electronics/passives/resistors')
        assert entry['count'] == 1
        assert entry['in_taxonomy'] is False

    def test_the_tree_flags_an_occupied_taxonomy_branch_as_both(self, service):
        branch = 'electronics/dev boards/arduino'
        service.create_product(description='Uno', category_path=branch)

        entry = self._entry(service, branch)
        assert entry['count'] == 1
        assert entry['in_taxonomy'] is True

    def test_the_tree_lists_each_path_once(self, service):
        """025 FR-018, at the other consumer of the union"""
        service.create_product(
            description='Uno', category_path='electronics/dev boards/arduino'
        )
        paths = [entry['path'] for entry in service.category_tree()]
        assert len(paths) == len(set(paths))

    def test_the_tree_never_drops_an_occupied_path(self, catalog):
        """025 FR-017: the taxonomy adds branches, it does not prune the catalog"""
        paths = {entry['path'] for entry in catalog.category_tree()}
        assert set(self.IN_USE) <= paths

    @staticmethod
    def _entry(catalog, path):
        return next(e for e in catalog.category_tree() if e['path'] == path)


class TestSpecificationNameVocabulary:
    """025 SC-010: the one vocabulary with no rename to repair it afterwards."""

    def test_offers_the_pinned_keys_before_any_product_carries_them(self, service):
        assert set(SPECIFICATION_KEYS) <= set(service.list_specification_names())

    def test_still_offers_a_name_in_use_that_the_record_does_not_pin(self, catalog):
        """The record is a default, not a whitelist -- here as much as anywhere"""
        names = catalog.list_specification_names()
        assert 'Dielectric' not in SPECIFICATION_KEYS
        assert 'Dielectric' in names

    def test_a_pinned_key_and_a_typed_variant_collapse_to_one(self, service):
        """And the surviving spelling is the record's, not the typed one"""
        service.create_product(
            description='resistor',
            specifications=[{'name': 'material', 'value': 'carbon film'}],
        )
        names = service.list_specification_names()

        assert [n for n in names if n.lower() == 'material'] == ['Material']

    def test_a_prefix_narrows_the_union_not_just_the_names_in_use(self, service):
        names = service.list_specification_names(prefix='thr')
        assert 'Thread' in names
        assert all(name.lower().startswith('thr') for name in names)

    def test_each_name_appears_once(self, catalog):
        names = catalog.list_specification_names()
        assert len(names) == len(set(names))


class TestTags:
    def test_a_category_typed_during_creation_needs_no_setup_step(self, service):
        """Story 7 scenario 4, and the same is true of tags"""
        service.create_product(
            description='x', category_path='brand/new/category', tags=['brand-new-tag']
        )
        assert 'brand/new/category' in service.list_categories()
        assert 'brand-new-tag' in service.list_tags()

    def test_tags_are_listed_alphabetically(self, catalog):
        assert catalog.list_tags() == ['rohs', 'surplus']

    def test_a_prefix_narrows_the_tag_list(self, catalog):
        assert catalog.list_tags(prefix='sur') == ['surplus']

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
    """The SC-001 catalog: two recorded voltages and one that only says so"""
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
        """Folded, because 025 lets the record's spelling win.

        The fixture records "Output current"; the record pins "Output Current".
        Those are one name to every filter, and the listing keeps the record's
        capitalization -- which is the point, not an accident. See
        TestSpecificationNameVocabulary for that behaviour on its own.
        """
        listed = {name.lower() for name in converters.list_specification_names()}
        assert {'output current', 'voltage'} <= listed

    def test_only_the_pinned_keys_remain_when_nothing_is_recorded(self, service):
        """025: with no products there are no names in use, so the keys are all
        that is left. Previously this was the empty list."""
        assert set(service.list_specification_names()) == set(SPECIFICATION_KEYS)

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
