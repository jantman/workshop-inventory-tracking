# Research: 055 Tool Taxonomy

The taxonomy content was settled in the spec's review with the owner. The decisions below are
about how to carry it.

## R1. Where the new branches live

- **Decision**: Append them to `DEFAULT_CATEGORY_PATHS` and `docs/category-taxonomy.md`, in the
  same shape 025 used.
- **Rationale**: That is the only mechanism, and a unit test already binds the two together.
- **Alternatives considered**:
  - A second tuple per root. Rejected: it would be a new abstraction for one list.
  - An override JSON file. Rejected: overrides are for *other* deployments, and this is the
    shipped default.

## R2. The record's key-meaning table

- **Decision**: Put the "what the new keys mean" table under a `### Key meanings` heading after
  the registry table and before `### Normalizing a vendor's names`.
- **Rationale**: `_record_specification_keys()` stops at the first `###` under
  `## Specification keys`. A second `| \`...\`` table before that heading would fold example
  values such as `Taper` and `Plug` into the pinned set and fail the agreement test, or worse,
  pass once someone "fixed" it by adding them.
- **Alternatives considered**:
  - Widening the parser. Rejected: it is unnecessary.

## R3. Test `ROOTS`

- **Decision**: Grow `ROOTS` to six roots.
- **Rationale**: The constant is both the list of record headings the parser reads and the
  assertion of the agreed roots. Both change together, by design.

## R4. Sort order

- **Decision**: Keep `DEFAULT_CATEGORY_PATHS` in Python `sorted()` order. It is asserted, and
  `adhesives & chemicals` sorts before `electrical`. Generate the ordering mechanically rather
  than by hand.

## R5. Screenshot

- **Decision**: Regenerate with `nox -s screenshots_headless`. Measure baseline churn on a clean
  tree first, and commit only files that changed because of this feature (expected: only
  `category_tree.png`).
