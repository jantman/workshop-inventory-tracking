"""
Unit tests for the taxonomy constants and their agreement with the record.

Covers app/utils/catalog_taxonomy.py. Two jobs: the shape invariants the rest of the
application relies on (025 FR-004, FR-013, SC-003), and the agreement between the
constants and ``docs/category-taxonomy.md`` (025 FR-019).

The agreement test is the one that matters. The record is the authority and the
module is a transcription of it, so nothing but a test stands between "renamed a
branch in the document" and "the filing screen still offers the old name". Parsing
the document here rather than at import time was a deliberate choice: it buys the
same guarantee without putting a markdown parser in the request path.
"""

import json
import re
from pathlib import Path

import pytest

from app import create_app
from app.catalog_service import CatalogService
from app.utils.catalog_taxonomy import (
    CATEGORY_TAXONOMY_ENV,
    DEFAULT_CATEGORY_PATHS,
    DEFAULT_SPECIFICATION_KEYS,
    MAX_CATEGORY_PATH_LENGTH,
    MAX_SPECIFICATION_NAME_LENGTH,
    SPECIFICATION_KEYS_ENV,
    TaxonomyFileError,
    category_paths,
    specification_keys,
)
from app.utils.category import canonical

RECORD = Path(__file__).resolve().parents[2] / "docs" / "category-taxonomy.md"

# The record's roots, which are also the headings its branch tables live under.
ROOTS = ("fasteners", "electrical", "electronics")

# app/database.py: Product.category_path is String(512).
MAX_PATH_LENGTH = 512
# FR-004: the tree is at most three levels deep.
MAX_SEGMENTS = 3
# app/database.py: ProductSpecification.name is String(100).
MAX_KEY_LENGTH = 100
# SC-003: a picklist nobody can scan has stopped helping anyone find anything.
MAX_CHILDREN = 20


def _record_lines():
    return RECORD.read_text().splitlines()


def _record_branches():
    """Every branch the record names, parents included, derived from its tables.

    A row is ``| `path` | definition |`` under a ``## <root>`` heading; the path is
    written relative to the root, so the root is prefixed back on here.
    """
    root = None
    leaves = []
    for line in _record_lines():
        heading = re.match(r"^## (%s)\s*$" % "|".join(ROOTS), line)
        if heading:
            root = heading.group(1)
            continue
        if line.startswith("## "):
            root = None
            continue
        if root:
            cell = re.match(r"^\| `([^`]+)` \|", line)
            if cell:
                leaves.append(f"{root}/{cell.group(1)}")

    branches = set()
    for leaf in leaves:
        parts = leaf.split("/")
        for depth in range(1, len(parts) + 1):
            branches.add("/".join(parts[:depth]))
    return branches


def _record_specification_keys():
    """The keys named in the record's per-branch-family registry.

    Only that table. The normalization table below it maps *vendor* names onto these
    keys, and reading it would fold vendor vocabulary into the pinned set -- which is
    the exact drift the registry exists to prevent.
    """
    keys = []
    in_section = False
    for line in _record_lines():
        if line.startswith("## Specification keys"):
            in_section = True
            continue
        if in_section and line.startswith("### "):
            break
        if in_section and line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 2:
                keys.extend(re.findall(r"`([^`]+)`", cells[1]))
    return set(keys)


def _children_by_parent():
    counts = {}
    for path in DEFAULT_CATEGORY_PATHS:
        if "/" in path:
            counts.setdefault(path.rsplit("/", 1)[0], 0)
            counts[path.rsplit("/", 1)[0]] += 1
    return counts


class TestCategoryPathShape:
    """What every consumer of DEFAULT_CATEGORY_PATHS is entitled to assume."""

    def test_not_empty(self):
        assert DEFAULT_CATEGORY_PATHS

    def test_every_path_is_already_canonical(self):
        """FR-013: choosing a branch stores the record's path, not a variant of it.

        A path here that canonicalizes to something else would be offered in one
        form and stored in another, which is two categories wearing one name.
        """
        assert [p for p in DEFAULT_CATEGORY_PATHS if canonical(p) != p] == []

    def test_no_path_exceeds_three_segments(self):
        """FR-004."""
        assert [p for p in DEFAULT_CATEGORY_PATHS if len(p.split("/")) > MAX_SEGMENTS] == []

    def test_no_path_exceeds_the_column_width(self):
        assert [p for p in DEFAULT_CATEGORY_PATHS if len(p) > MAX_PATH_LENGTH] == []

    def test_no_duplicates(self):
        assert len(set(DEFAULT_CATEGORY_PATHS)) == len(DEFAULT_CATEGORY_PATHS)

    def test_sorted(self):
        assert list(DEFAULT_CATEGORY_PATHS) == sorted(DEFAULT_CATEGORY_PATHS)

    def test_every_parent_is_present(self):
        """A branch whose parent is missing renders at a depth with nothing above it.

        ``category_tree`` indents by segment count, so an orphaned grandchild draws
        an indent under a row that is not there.
        """
        known = set(DEFAULT_CATEGORY_PATHS)
        orphans = [
            p for p in DEFAULT_CATEGORY_PATHS
            if "/" in p and p.rsplit("/", 1)[0] not in known
        ]
        assert orphans == []

    def test_roots_are_the_three_agreed(self):
        assert sorted({p.split("/")[0] for p in DEFAULT_CATEGORY_PATHS}) == sorted(ROOTS)

    def test_no_parent_has_more_than_twenty_children(self):
        """SC-003."""
        crowded = {
            parent: count
            for parent, count in _children_by_parent().items()
            if count > MAX_CHILDREN
        }
        assert crowded == {}


class TestSpecificationKeyShape:
    """SC-010: there is no rename for a specification name, so the set is pinned."""

    def test_not_empty(self):
        assert DEFAULT_SPECIFICATION_KEYS

    def test_no_key_is_blank_or_untrimmed(self):
        assert [k for k in DEFAULT_SPECIFICATION_KEYS if not k or k != k.strip()] == []

    def test_no_key_exceeds_the_column_width(self):
        assert [k for k in DEFAULT_SPECIFICATION_KEYS if len(k) > MAX_KEY_LENGTH] == []

    def test_no_case_folded_duplicates(self):
        """``Thread`` and ``thread`` filter as one but read as two."""
        folded = [k.lower() for k in DEFAULT_SPECIFICATION_KEYS]
        assert len(set(folded)) == len(folded)

    def test_sorted(self):
        assert list(DEFAULT_SPECIFICATION_KEYS) == sorted(DEFAULT_SPECIFICATION_KEYS)


class TestAgreementWithTheRecord:
    """FR-019: the record and the reference data must not be left disagreeing.

    These are the tests that fail when someone edits one and not the other. If the
    record's table shape ever changes, they fail loudly rather than silently parsing
    nothing -- which is what the emptiness guards below are for.
    """

    def test_the_record_exists(self):
        assert RECORD.is_file(), f"the taxonomy record is missing: {RECORD}"

    def test_the_parse_found_branches(self):
        """Guard: a table-shape change must not read as "the record names nothing"."""
        assert _record_branches(), (
            "parsed no branches from the record -- its table shape changed"
        )

    def test_the_parse_found_keys(self):
        assert _record_specification_keys(), (
            "parsed no specification keys from the record -- its table shape changed"
        )

    def test_branches_match_exactly(self):
        recorded = _record_branches()
        module = set(DEFAULT_CATEGORY_PATHS)
        assert recorded - module == set(), "in the record, missing from the module"
        assert module - recorded == set(), "in the module, missing from the record"

    def test_specification_keys_match_exactly(self):
        recorded = _record_specification_keys()
        module = set(DEFAULT_SPECIFICATION_KEYS)
        assert recorded - module == set(), "in the record, missing from the module"
        assert module - recorded == set(), "in the module, missing from the record"


class TestOverridingTheDefaults:
    """The shipped taxonomy is one workshop's; another points at its own JSON.

    Every test here writes a file and passes its path explicitly. The loaders
    accept ``source`` for exactly that reason -- reaching through os.environ in
    a test leaves the variable set for whatever runs next in the process.
    """

    @staticmethod
    def _write(tmp_path, name, content):
        target = tmp_path / name
        target.write_text(json.dumps(content) if not isinstance(content, str) else content)
        return str(target)

    def test_unset_means_the_built_in_defaults(self):
        assert category_paths() == DEFAULT_CATEGORY_PATHS
        assert specification_keys() == DEFAULT_SPECIFICATION_KEYS

    def test_a_file_replaces_rather_than_merges(self, tmp_path):
        """The whole objection to a built-in list is inheriting someone else's."""
        source = self._write(tmp_path, 'c.json', ['pottery/glazes', 'pottery/clay'])

        loaded = category_paths(source)

        assert 'fasteners/machine screws & bolts/carriage bolts' not in loaded
        assert set(loaded) == {'pottery', 'pottery/clay', 'pottery/glazes'}

    def test_parents_are_filled_in(self, tmp_path):
        """An override lists what its author cares about, not the scaffolding."""
        source = self._write(tmp_path, 'c.json', ['a/b/c/d'])

        assert category_paths(source) == ('a', 'a/b', 'a/b/c', 'a/b/c/d')

    def test_an_override_may_nest_deeper_than_the_defaults(self, tmp_path):
        """Three levels was this shop's decision, never the application's."""
        source = self._write(tmp_path, 'c.json', ['a/b/c/d/e/f'])

        assert 'a/b/c/d/e/f' in category_paths(source)

    def test_paths_are_canonicalized(self, tmp_path):
        source = self._write(tmp_path, 'c.json', ['  Pottery / Glazes  '])

        assert category_paths(source) == ('pottery', 'pottery/glazes')

    def test_duplicates_collapse(self, tmp_path):
        source = self._write(tmp_path, 'c.json', ['a/b', 'A/B', 'a/b'])

        assert category_paths(source) == ('a', 'a/b')

    def test_an_empty_array_is_allowed(self, tmp_path):
        """"I want no suggestions" is a legitimate answer, not a broken file.

        It is also why the categories page kept its empty state: with this and
        no products, the tree really is empty.
        """
        source = self._write(tmp_path, 'c.json', [])

        assert category_paths(source) == ()

    def test_specification_keys_are_replaced_trimmed_and_folded(self, tmp_path):
        source = self._write(tmp_path, 's.json', ['  Glaze  ', 'glaze', 'Cone'])

        assert specification_keys(source) == ('Cone', 'Glaze')
        assert 'Thread' not in specification_keys(source)

    def test_the_two_overrides_are_independent(self, tmp_path):
        """Set one and the other keeps its default."""
        source = self._write(tmp_path, 'c.json', ['pottery'])

        assert category_paths(source) == ('pottery',)
        assert specification_keys() == DEFAULT_SPECIFICATION_KEYS


class TestRefusingABadOverride:
    """A named file that cannot be used stops the application.

    Falling back to the defaults would file another shop's products under this
    shop's branches, and the operator who set the variable would never see it.
    """

    def test_a_missing_file_raises(self, tmp_path):
        with pytest.raises(TaxonomyFileError) as excinfo:
            category_paths(str(tmp_path / 'nope.json'))
        assert 'CATEGORY_TAXONOMY_FILE' in str(excinfo.value)
        assert 'nope.json' in str(excinfo.value)

    def test_malformed_json_raises(self, tmp_path):
        source = tmp_path / 'c.json'
        source.write_text('["unterminated')
        with pytest.raises(TaxonomyFileError) as excinfo:
            category_paths(str(source))
        assert 'not valid JSON' in str(excinfo.value)

    def test_a_json_object_raises(self, tmp_path):
        source = tmp_path / 'c.json'
        source.write_text('{"categories": ["a"]}')
        with pytest.raises(TaxonomyFileError) as excinfo:
            category_paths(str(source))
        assert 'array of strings' in str(excinfo.value)

    def test_a_non_string_entry_raises(self, tmp_path):
        source = tmp_path / 'c.json'
        source.write_text('["a", 7]')
        with pytest.raises(TaxonomyFileError) as excinfo:
            category_paths(str(source))
        assert 'strings' in str(excinfo.value)

    def test_an_entry_that_is_not_a_category_raises(self, tmp_path):
        """Blank, whitespace and a bare separator all mean "no category"."""
        source = tmp_path / 'c.json'
        source.write_text('["a", "  /  "]')
        with pytest.raises(TaxonomyFileError) as excinfo:
            category_paths(str(source))
        assert 'not a category' in str(excinfo.value)

    def test_an_over_long_path_raises(self, tmp_path):
        source = tmp_path / 'c.json'
        source.write_text(json.dumps(['x' * (MAX_CATEGORY_PATH_LENGTH + 1)]))
        with pytest.raises(TaxonomyFileError) as excinfo:
            category_paths(str(source))
        assert str(MAX_CATEGORY_PATH_LENGTH) in str(excinfo.value)

    def test_a_blank_specification_key_raises(self, tmp_path):
        source = tmp_path / 's.json'
        source.write_text('["Thread", "   "]')
        with pytest.raises(TaxonomyFileError) as excinfo:
            specification_keys(str(source))
        assert 'blank' in str(excinfo.value)

    def test_an_over_long_specification_key_raises(self, tmp_path):
        source = tmp_path / 's.json'
        source.write_text(json.dumps(['k' * (MAX_SPECIFICATION_NAME_LENGTH + 1)]))
        with pytest.raises(TaxonomyFileError) as excinfo:
            specification_keys(str(source))
        assert str(MAX_SPECIFICATION_NAME_LENGTH) in str(excinfo.value)


class TestTheEnvironmentVariables:
    """The `source` argument exists for tests; the variables are the feature.

    Everything above passes a path explicitly, which would leave the actual
    os.environ lookup -- the only thing an operator ever touches -- unproven.
    """

    def test_the_category_variable_is_read(self, tmp_path, monkeypatch):
        source = tmp_path / 'c.json'
        source.write_text(json.dumps(['pottery/glazes']))
        monkeypatch.setenv(CATEGORY_TAXONOMY_ENV, str(source))

        assert category_paths() == ('pottery', 'pottery/glazes')

    def test_the_specification_variable_is_read(self, tmp_path, monkeypatch):
        source = tmp_path / 's.json'
        source.write_text(json.dumps(['Cone', 'Glaze']))
        monkeypatch.setenv(SPECIFICATION_KEYS_ENV, str(source))

        assert specification_keys() == ('Cone', 'Glaze')

    def test_an_empty_variable_is_treated_as_unset(self, tmp_path, monkeypatch):
        """`CATEGORY_TAXONOMY_FILE=` in a .env means "no override", not "read ''"."""
        monkeypatch.setenv(CATEGORY_TAXONOMY_ENV, '')

        assert category_paths() == DEFAULT_CATEGORY_PATHS

    def test_the_service_sees_the_override(self, test_storage, monkeypatch, tmp_path):
        """End to end: what the datalist would actually be offered."""
        source = tmp_path / 'c.json'
        source.write_text(json.dumps(['pottery/glazes']))
        monkeypatch.setenv(CATEGORY_TAXONOMY_ENV, str(source))

        listed = CatalogService(test_storage).list_categories()

        assert 'pottery/glazes' in listed
        assert not any(path.startswith('fasteners') for path in listed)

    def test_creating_the_app_refuses_a_broken_file(self, tmp_path, monkeypatch):
        """Fail at boot, naming the file -- not on the first page that asks.

        Starting anyway would mean serving another shop's branches to an
        operator who explicitly asked for their own.
        """
        source = tmp_path / 'c.json'
        source.write_text('{"not": "an array"}')
        monkeypatch.setenv(CATEGORY_TAXONOMY_ENV, str(source))

        with pytest.raises(TaxonomyFileError) as excinfo:
            create_app()
        assert str(source) in str(excinfo.value)

    def test_creating_the_app_is_unaffected_when_unset(self, monkeypatch):
        monkeypatch.delenv(CATEGORY_TAXONOMY_ENV, raising=False)
        monkeypatch.delenv(SPECIFICATION_KEYS_ENV, raising=False)

        assert create_app() is not None
