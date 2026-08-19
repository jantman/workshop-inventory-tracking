# Phase 1 Data Model: Capture Reads the "About this item" Bullets

**Feature**: `specs/020-capture-about-this-item` | **Date**: 2026-08-19

## There is no schema change

No table, column, index or constraint is added or altered, and **no Alembic revision ships with this
feature**. The bullets row is an ordinary `product_specifications` row; this feature adds a source
for one, not a kind of one.

Stated explicitly because Principle V makes migrations the only legitimate way to change the schema,
and the easiest way to get this feature wrong would be to invent somewhere new to put the bullets.

## The one entity involved

### Bullets row — a `ProductSpecification` (`app/database.py:1182`)

| Field | Value for this row | Constraint it must satisfy |
|-------|--------------------|----------------------------|
| `product_id` | the product the capture landed on | FK to `products.id`, `ON DELETE CASCADE` |
| `name` | `About this item` — 15 characters | `String(100)`, and `MAX_SPECIFICATION_NAME_LENGTH = 100` in `CatalogService`. Comfortable. |
| `value` | the listing's bullets, one per line, `\n`-separated | `MEDIUMTEXT` (widened in `b1a0c0d10009`). No application-level width check exists; the largest values in this table are already A+ descriptions of 20k+ characters, so a six-bullet list is unremarkable. |
| `display_order` | assigned by `merge_specifications`, after the highest existing order | Set by the service, never by this feature |

There is deliberately no `UniqueConstraint('product_id', 'name')` on this table — the deployed
collation folds accents as well as case, which would be stricter than the requirement. Uniqueness of
the `About this item` name is enforced in Python by `CatalogService._validate_specifications` and by
`merge_specifications`' drop rule, exactly as it is for every other captured name.

## The in-flight shape

### `ListingCapture.specifications` (`app/models.py:677`)

A `List[Dict[str, str]]` of `{'name', 'value'}`. The bullets row is one more entry in that list, in
first position. **`LISTING_CAPTURE_VERSION` stays `1`** — the payload's *shape* is unchanged, only
its contents, so a cached agent from before this feature degrades to today's behavior rather than
being rejected. Bumping the version here would be wrong and would break every stale bookmarklet for
no gain.

`_payload_specifications` (`app/models.py:783`) drops any entry with an empty name or value before
anything else sees it. That is the backstop behind FR-008, not the mechanism: the agent must not
emit the row in the first place.

## Validation, and where each rule lives

| Rule | Enforced by | Note |
|------|-------------|------|
| Entry has both a name and a value | `_payload_specifications` | Drops silently; see research.md §4 |
| Name ≤ 100 chars | `CatalogService._validate_specifications` | Raises `ValidationError` |
| Name unique within one submission, case- and whitespace-insensitively | `_validate_specifications` (`key = name.lower()`) | Compared in Python, never in SQL |
| A captured name the product already carries is dropped whole | `CatalogService.merge_specifications` | This is FR-009's second half — US2 is satisfied by existing code, and the feature's job is not to defeat it |
| Names differing only in case/whitespace within one *reading* fold to the first | `specificationsFrom()` in `capture-agent.js` | FR-009's first half. Emitting the bullets row first is what decides the collision in its favor |

## State transitions

None. A specification row has no lifecycle: it is created, edited, or deleted. In particular there
is **no "re-capture updates the row" transition** — FR-009 and US2 scenario 2 require the opposite,
and `merge_specifications` already implements it by dropping the incoming duplicate rather than
overwriting.
