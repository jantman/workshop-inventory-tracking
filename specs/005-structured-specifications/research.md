# Phase 0 Research: Structured Specifications

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

The spec left no `[NEEDS CLARIFICATION]` markers — its five decisions were settled in its Assumptions section. What remained for this phase was the technical shape underneath them. Each decision below records what was chosen, why, and what was rejected.

---

## The collation question

**Decision**: Every comparison this feature makes is classified as either *deciding* or *filtering*. Deciding comparisons — which rows to write, replace, or refuse — happen in Python against loaded values. Filtering comparisons — which rows to show — happen in SQL, are made explicitly case-insensitive with `func.lower()` where SQLite would otherwise differ, and their accent-folding under MariaDB is accepted and documented rather than fought.

**Rationale**: The deployment configures `utf8mb4_unicode_ci`, which resolves to `utf8mb4_uca1400_ai_ci` on MariaDB 11 and folds case **and** accents. SQLite, which the unit suite runs on, collates `BINARY`. Commit `091e918` is the record of what that gap costs: `rename_tag` deleted a tag and every one of its product associations because a Python guard and a SQL lookup disagreed about whether two strings were the same, and the unit suite passed throughout and always would have.

The distinction matters because the consequences are asymmetric. A *deciding* comparison that folds unexpectedly destroys data. A *filtering* comparison that folds unexpectedly returns a near-spelling the operator probably wanted anyway. So:

| Comparison | Where | Behaviour |
|---|---|---|
| FR-004 duplicate name within a product | Python, on the submitted list, `strip().lower()` | Case-insensitive. `Volt` and `Vôlt` are **different** names, as FR-004 describes. |
| FR-015 filter by specification name | SQL, `func.lower(name) == value.lower()` | Case-insensitive on both backends. Also accent-insensitive on MariaDB. **Accepted**: it is a read, it returns a near-spelling, and nothing is written. |
| FR-014 filter by value | SQL, escaped `LIKE '%…%'` | Case-insensitive on both backends by default. Accent-insensitive on MariaDB. Accepted for the same reason. |
| FR-019/FR-020 suggestion dedup | Python, after the query | Case-insensitive on both backends. `SELECT DISTINCT` is **not** relied on. |

**Alternatives considered**:

- *Force a binary collation on the two columns.* Would make MariaDB and SQLite agree, but at the cost of making the filter case-sensitive — the opposite of FR-015 — and introducing a column whose collation differs from every other column in the schema.
- *Do all comparisons in SQL and accept whatever the server says.* This is exactly what `091e918` fixed. The unit suite cannot see it.
- *Do all comparisons in Python, including the filter.* Would mean loading every product to filter it. Rejected as a real cost for no benefit on a read.

---

## Why no unique constraint

**Decision**: `product_specifications` gets **no** `UniqueConstraint('product_id', 'name')`. FR-004 is enforced in `CatalogService._validate_specifications`, in Python, against the submitted list.

**Rationale**: Three reasons, in order of weight.

1. **The constraint would mean different things on the two backends.** Under the deployed collation it rejects `Volt` against `Vôlt` — stricter than FR-004, which speaks only of case and whitespace. Under SQLite it accepts `Voltage` against `voltage` — looser than FR-004. There is no single constraint that expresses the requirement on both.
2. **It would surface as the wrong error.** FR-008 requires a refusal that identifies the offending entry. An `IntegrityError` escaping the session context manager is not that, so the service check has to exist regardless — the constraint would be a second, differently-behaved gate behind a gate that already works.
3. **The invariant is cosmetic, not integrity.** This is the line the constitution draws: Principle I yields to data integrity, and this is not data integrity. A product carrying two `Voltage` rows is untidy and the filter returns it twice-over for one of them; nothing is lost or corrupted. Contrast `uq_identifier_type_value_vendor`, which is deliberately a database property because two products sharing a GTIN *is* corruption.

**Alternatives considered**:

- *Add the constraint anyway as a backstop.* Rejected on (1): a backstop that fires on a case the requirement permits is not a backstop, it is a bug that only appears in production.
- *Store a normalized `name_key` column alongside the display name and make that unique.* This is the standard trick and it does work — it is what `Tag.name` effectively does by storing lowercase. Rejected because FR-005 requires the display name be stored as typed, so this buys a second column and a synchronization obligation to enforce a cosmetic rule. If duplicate names ever become a real problem in practice, this is the fix to reach for.

---

## Reusing the name `specifications`

**Decision**: `Product.specifications` keeps its name and changes from a `Column(Text)` to a relationship returning `ProductSpecification` rows.

**Rationale**: There is one concept here, and it should have one name. The question was only whether the type change would break readers *silently* or *loudly*, and that was checked rather than assumed — every reader is enumerated in [data-model.md](./data-model.md#every-reader-of-the-old-field). The two that would fail silently are the detail template's `{{ product.specifications }}` and the add/edit textarea, and both are rewritten by this feature. Everything else — `Product.specifications.like(...)` in `search_products`, `_clean(specifications)` in the service — raises immediately on the changed type.

**Alternatives considered**:

- *Name the relationship `specs` or `specification_entries` and drop the old name.* Every reader then fails loudly, which is a real advantage. Rejected because the cost is permanent — a second vocabulary for one concept, forever — to buy a one-time safety margin on a change whose readers fit on one screen.
- *Keep `specifications` as the text column and add `specification_entries` alongside.* This is the "unstructured remainder" design the spec explicitly rejected. Two fields to maintain, two places to search, and a permanent question about which one a given fact belongs in.

---

## Where the vocabulary readers live

**Decision**: `list_specification_names` and `list_specification_values` go on `CatalogService`, beside `list_tags` and `list_categories`, served by two new endpoints modelled on `/api/categories` and `/api/tags`. Not on `VocabularyService`.

**Rationale**: `app/services/vocabulary.py` exists for names recorded by **both halves of the application** — a shelf, a bin, a vendor — so that metal stock and the catalogue stop drifting apart by spelling. That is its whole stated purpose. Metal stock has no specifications and never will, so a specification name has nothing to share. It is catalogue vocabulary, exactly like a category or a tag, and the catalogue already has two methods and two endpoints of precisely this shape to sit next to.

**Alternatives considered**:

- *Add `specification_name` and `specification_value` to `FIELD_SUGGESTION_COLUMNS`.* Genuinely tempting: the `(model, value_column, scope_column)` tuple fits `(ProductSpecification, 'value', 'name')` exactly, mirroring how `sub_location` is scoped by `location`, and it would inherit ranking, LIKE-escaping, dedup and the limit for free. Rejected on two counts. The scoping query parameter is literally named `location`, so a specification name would travel to the server under the name of a shelf — a wart a future reader has to decode. And it would put catalogue-only vocabulary inside the module whose reason for existing is cross-half sharing, which blurs the one line that makes that module's contents predictable.
- *A third service module for catalogue vocabulary.* Speculative generality for two methods.

---

## Client-side: datalists, not FieldAutocomplete

**Decision**: Specification name and value suggestions use plain `<datalist>` elements — one shared list for names, one per-row list for values, refilled when that row's name changes.

**Rationale**: `field-autocomplete.js` is constructed per DOM id (`opts.inputId`), and these rows are cloned at runtime and removed at will, so there are no stable ids to construct against. Making it work would mean giving the component a lifecycle it does not have. Datalists need none: the browser owns the dropdown, and `catalog-suggestions.js` already establishes the pattern for filling one from an endpoint. FR-021 — suggestions must never restrict entry — then holds by construction rather than by care, because a datalist cannot constrain an input.

**Alternatives considered**:

- *Instantiate `FieldAutocomplete` per row with generated ids.* Rejected: the component would need destruction on row removal and construction on row add, which is a lifecycle it does not currently have and would exist for one caller.
- *One shared value datalist filled from all values regardless of name.* Simpler, but offers `barrel 5.5 mm` while the operator is typing a voltage. The per-row refill is a few lines and makes the suggestion actually useful.

---

## Form encoding: repeated names, paired positionally

**Decision**: Every row's inputs are named `spec_name` and `spec_value`. The route pairs them by index via `request.form.getlist`.

**Rationale**: The alternative is indexed names (`spec-0-name`), which requires renumbering on every row removal — client-side bookkeeping that exists solely to reconstruct an ordering the DOM already has. Positional pairing needs no bookkeeping, and `display_order` falls out of the list index for free (FR-006).

**The catch, and its resolution**: `product-form.js` builds its draft as a flat `{name: value}` object keyed by `field.name`, so repeated names collide and only the last row would survive a draft restore. `tests/e2e/test_draft_persistence.py:26` fills `#specifications` today and asserts it comes back, so this is a live regression with a test already written for it, not a hypothetical. `collect()` therefore learns to store an array when a name repeats, and `apply()` clicks the add-row button until the row count matches before assigning positionally.

**Alternatives considered**:

- *Exclude specification rows from draft persistence.* Cheapest, and rejected: it silently removes an existing feature from the field this one replaces. Losing a carefully typed specification list to a dropped connection is exactly what FR-035 was built to prevent.
- *Mirror the rows into one hidden JSON input and let the draft code keep working unchanged.* Rejected: a second source of truth for the same data on the page, synchronized on every keystroke, which is more moving parts than teaching `collect()` about arrays.

---

## The migration's data step

**Decision**: The copy and the join both run in Python over `op.get_bind()`, with bound parameters, rather than as a single dialect-specific `INSERT … SELECT` / `GROUP_CONCAT` statement.

**Rationale**: The join direction is where this bites. MariaDB spells ordered concatenation `GROUP_CONCAT(x ORDER BY y SEPARATOR '\n')`; SQLite's `group_concat` takes no `ORDER BY` and its separator argument does not compose with one. Writing the downgrade twice, once per dialect, to save a loop over tens of rows is a poor trade — and this is the one step in the feature that cannot be re-run to fix a mistake. A Python loop is obviously correct, reads the same on both backends, and is fast enough at this scale that the question does not arise.

**Alternatives considered**:

- *Raw SQL with a dialect check.* Two code paths, one of which is never exercised in this deployment, guarding the feature's only irreversible operation.
- *Leave the old column in place instead of dropping it, so the downgrade is trivial.* Rejected: a permanently dead column that no code reads is exactly the "unstructured remainder" the spec ruled out, wearing a different hat.

---

## What the tests can and cannot prove

**Decision**: FR-004, FR-015 and FR-019 get e2e coverage, and those tests must be confirmed to fail against a deliberately case-sensitive implementation before being trusted.

**Rationale**: SQLite collates BINARY, so `nox -s tests` passes whether or not any of the three is implemented case-insensitively. The e2e testcontainer runs the deployed collation and is the only place the requirement is observable. `091e918` confirmed each of its four regression tests failed without the fix; the same discipline applies here for the same reason.

**A gap that cannot be closed the same way**: the Alembic revision is not run by either suite — `tests/conftest.py:51` and `tests/e2e/test_server.py:61` both call `Base.metadata.create_all`. Adding an integration test that drives `alembic upgrade`/`downgrade` against the testcontainer was considered and rejected for this feature: it means a second schema-provisioning path in the test infrastructure, which is a change to how the suite works rather than to what it covers, and it is not warranted by one revision. The mitigation is the scripted manual round-trip in [quickstart.md](./quickstart.md#the-migration-round-trip), performed against MariaDB with real rows including a paragraph containing a colon and a newline. If a future feature ships a second data-carrying revision, that trade should be revisited.
