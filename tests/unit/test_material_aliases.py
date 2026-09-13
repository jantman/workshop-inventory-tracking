"""Feature 043: material aliases are read and compared as whole names.

``MaterialTaxonomy.aliases`` is comma-separated text. Iterating that string
yields characters, which is how the admin page came to render
``aliases: O, i, l, i, t, e, ...``. These tests pin that every reader goes
through ``MaterialTaxonomy.aliases_list`` instead.
"""

import pytest

from app.database import MaterialTaxonomy
from app.mariadb_materials_admin_service import (
    MariaDBMaterialsAdminService,
    TaxonomyAddRequest,
)

pytestmark = pytest.mark.unit

CATEGORY = 'Alias Test Metals'
FAMILY = 'Alias Test Bronzes'


@pytest.fixture
def admin(test_storage):
    return MariaDBMaterialsAdminService(test_storage)


def seed(admin, *rows):
    """Insert taxonomy rows directly, storing ``aliases`` exactly as given.

    Bypasses the service's validation, so alias text the add form would never
    write (stray separators, no space after a comma) can still be stored.
    """
    session = admin.Session()
    try:
        for row in rows:
            session.add(MaterialTaxonomy(**row))
        session.commit()
    finally:
        session.close()


def hierarchy(*materials):
    """A category and family, plus the given level-3 ``materials`` under them."""
    return [
        {'name': CATEGORY, 'level': 1, 'parent': None},
        {'name': FAMILY, 'level': 2, 'parent': CATEGORY},
        *({'level': 3, 'parent': FAMILY, **material} for material in materials),
    ]


def find_node(overview, name):
    """Depth-first search of the taxonomy tree for the node called ``name``."""
    for node in overview:
        if node['name'] == name:
            return node
        found = find_node(node.get('children', []), name)
        if found is not None:
            return found
    return None


class TestOverviewAliases:
    """FR-001 to FR-003: the admin tree carries aliases as a list of whole names"""

    @pytest.fixture
    def overview(self, admin):
        seed(admin, *hierarchy(
            {'name': 'Oil Embedded Bronze', 'aliases': 'Oilite, Sintered Bronze, 841 Bronze'},
            {'name': 'Test 304', 'aliases': '304 Stainless,SS304'},
            {'name': 'Test Stray', 'aliases': 'Oilite2,, Sintered Two ,'},
            {'name': 'Test Single', 'aliases': 'TIM'},
            {'name': 'Test None', 'aliases': None},
            {'name': 'Test Inactive', 'aliases': 'Old Name, Older Name', 'active': False},
        ))
        return admin.get_taxonomy_overview(include_inactive=True)

    def test_the_reported_material_lists_its_three_aliases(self, overview):
        node = find_node(overview, 'Oil Embedded Bronze')
        assert node['aliases'] == ['Oilite', 'Sintered Bronze', '841 Bronze']

    def test_aliases_stored_without_a_space_after_the_comma(self, overview):
        assert find_node(overview, 'Test 304')['aliases'] == ['304 Stainless', 'SS304']

    def test_empty_entries_are_dropped_and_names_trimmed(self, overview):
        assert find_node(overview, 'Test Stray')['aliases'] == ['Oilite2', 'Sintered Two']

    def test_a_single_alias_is_one_name_not_its_letters(self, overview):
        assert find_node(overview, 'Test Single')['aliases'] == ['TIM']

    def test_no_aliases_is_an_empty_list(self, overview):
        assert find_node(overview, 'Test None')['aliases'] == []

    def test_an_inactive_material_lists_its_aliases_the_same_way(self, overview):
        node = find_node(overview, 'Test Inactive')
        assert node['active'] is False
        assert node['aliases'] == ['Old Name', 'Older Name']


# (alias, conflicts): data-model.md's comparison table. Whole names only,
# ignoring case and surrounding whitespace; an existing material's name counts.
CONFLICT_CASES = [
    ('Oilite', True),
    ('OILITE', True),
    (' Oilite ', True),
    ('Sintered Bronze', True),
    ('Bronze', False),
    ('841', False),
    ('Alias Test Carbon Steel', True),
    ('alias test carbon steel', True),
]


class TestAliasConflicts:
    """FR-004 to FR-007: both validation paths judge aliases the same way"""

    @pytest.fixture(autouse=True)
    def existing(self, admin):
        seed(admin, *hierarchy(
            {'name': 'Oil Embedded Bronze', 'aliases': 'Oilite, Sintered Bronze, 841 Bronze'},
            {'name': 'Alias Test Carbon Steel', 'aliases': None},
        ))

    @staticmethod
    def request_with(alias):
        return TaxonomyAddRequest(
            name=f'Conflict Probe {alias.strip()}', level=3, parent=FAMILY, aliases=[alias],
        )

    @pytest.mark.parametrize('alias, conflicts', CONFLICT_CASES)
    def test_the_live_check(self, admin, alias, conflicts):
        ok, errors = admin.validate_add_request(self.request_with(alias))
        assert any('conflicts' in e for e in errors) == conflicts, errors

    @pytest.mark.parametrize('alias, conflicts', CONFLICT_CASES)
    def test_the_check_on_save(self, admin, alias, conflicts):
        ok, message = admin.add_taxonomy_entry(self.request_with(alias))
        assert ok is (not conflicts), message
        if conflicts:
            assert 'conflicts' in message

    @pytest.mark.parametrize('alias, conflicts', CONFLICT_CASES)
    def test_the_two_checks_agree(self, admin, alias, conflicts):
        """FR-006. Live runs first: the save, when accepted, adds a row."""
        request = self.request_with(alias)
        _, errors = admin.validate_add_request(request)
        saved, _ = admin.add_taxonomy_entry(request)
        refused_live = any('conflicts' in e for e in errors)
        assert refused_live is (not saved)
