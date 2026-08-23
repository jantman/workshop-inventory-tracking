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

import re
from pathlib import Path

from app.utils.catalog_taxonomy import CATEGORY_PATHS, SPECIFICATION_KEYS
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
    for path in CATEGORY_PATHS:
        if "/" in path:
            counts.setdefault(path.rsplit("/", 1)[0], 0)
            counts[path.rsplit("/", 1)[0]] += 1
    return counts


class TestCategoryPathShape:
    """What every consumer of CATEGORY_PATHS is entitled to assume."""

    def test_not_empty(self):
        assert CATEGORY_PATHS

    def test_every_path_is_already_canonical(self):
        """FR-013: choosing a branch stores the record's path, not a variant of it.

        A path here that canonicalizes to something else would be offered in one
        form and stored in another, which is two categories wearing one name.
        """
        assert [p for p in CATEGORY_PATHS if canonical(p) != p] == []

    def test_no_path_exceeds_three_segments(self):
        """FR-004."""
        assert [p for p in CATEGORY_PATHS if len(p.split("/")) > MAX_SEGMENTS] == []

    def test_no_path_exceeds_the_column_width(self):
        assert [p for p in CATEGORY_PATHS if len(p) > MAX_PATH_LENGTH] == []

    def test_no_duplicates(self):
        assert len(set(CATEGORY_PATHS)) == len(CATEGORY_PATHS)

    def test_sorted(self):
        assert list(CATEGORY_PATHS) == sorted(CATEGORY_PATHS)

    def test_every_parent_is_present(self):
        """A branch whose parent is missing renders at a depth with nothing above it.

        ``category_tree`` indents by segment count, so an orphaned grandchild draws
        an indent under a row that is not there.
        """
        known = set(CATEGORY_PATHS)
        orphans = [
            p for p in CATEGORY_PATHS
            if "/" in p and p.rsplit("/", 1)[0] not in known
        ]
        assert orphans == []

    def test_roots_are_the_three_agreed(self):
        assert sorted({p.split("/")[0] for p in CATEGORY_PATHS}) == sorted(ROOTS)

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
        assert SPECIFICATION_KEYS

    def test_no_key_is_blank_or_untrimmed(self):
        assert [k for k in SPECIFICATION_KEYS if not k or k != k.strip()] == []

    def test_no_key_exceeds_the_column_width(self):
        assert [k for k in SPECIFICATION_KEYS if len(k) > MAX_KEY_LENGTH] == []

    def test_no_case_folded_duplicates(self):
        """``Thread`` and ``thread`` filter as one but read as two."""
        folded = [k.lower() for k in SPECIFICATION_KEYS]
        assert len(set(folded)) == len(folded)

    def test_sorted(self):
        assert list(SPECIFICATION_KEYS) == sorted(SPECIFICATION_KEYS)


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
        module = set(CATEGORY_PATHS)
        assert recorded - module == set(), "in the record, missing from the module"
        assert module - recorded == set(), "in the module, missing from the record"

    def test_specification_keys_match_exactly(self):
        recorded = _record_specification_keys()
        module = set(SPECIFICATION_KEYS)
        assert recorded - module == set(), "in the record, missing from the module"
        assert module - recorded == set(), "in the module, missing from the record"
