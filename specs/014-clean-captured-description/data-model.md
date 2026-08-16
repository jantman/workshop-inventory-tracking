# Phase 1 Data Model: Clean Captured Description

**No persisted schema changes. No Alembic revision. No new table, column, index, or constraint.**

The `product_specifications` table already stores what this feature produces. `b1a0c0d10009` widened the value column to hold a full description, and this feature makes the stored value *smaller* while keeping more of its meaning. Principle V is satisfied trivially: there is nothing to migrate.

What follows is the three shapes the data takes while in flight, and what each must guarantee.

---

## 1. The extracted description — `listing.description_text`

**Where it lives**: one string field of the capture payload (`contracts/capture-payload.md` in feature 007, schema unchanged), produced by `extract()` in the browser and consumed by `ListingCapture.from_json`.

**Produced by**: `proseOf(descriptionBlock(doc))`.

| Property | Before | After |
|---|---|---|
| Contains stylesheet or script text | Yes, on A+ listings | No (FR-001) |
| Contains `\n` | Never | Where the page shows a break (FR-005, FR-006) |
| Runs of blank lines | N/A | At most one (FR-007) |
| Leading/trailing whitespace | Trimmed | Trimmed (FR-008) |
| Length cap | None | None (FR-010) |
| Absent-description representation | field omitted | field omitted — unchanged |

**Invariants**:

- **D1** — It is either absent or a non-empty, non-whitespace string. `extract()` sets it only when `descriptionBlock` returned a block, and after this change a block of nothing but non-content yields `''`, which `descriptionBlock`'s own truthiness test rejects (FR-004).
- **D2** — It is never truncated. Nothing in the agent, in `_payload_string`, or in `_validate_specifications` shortens it; the only reductions are the removal of non-content and the whitespace rules.
- **D3** — For a listing whose description contains no `<br>` and no block element, it is byte-identical to what today's code produces. This is contract guarantee G6, and it is what makes SC-003 checkable rather than a matter of opinion.

**Python path, unchanged and verified**: `_payload_string` (`app/models.py:640`) does `.strip()` and nothing else; `_clean` (`app/catalog_service.py:2301`) does the same. Newlines pass through both untouched. `CatalogService._store_listing_extras` appends it as `{'name': 'Description', 'value': …}` and `merge_specifications` writes it. No Python change is required and none is planned.

---

## 2. A specification row — `listing.specifications[]`

**Shape**: `{name: string, value: string}`. Unchanged.

| Field | Helper | Invariant |
|---|---|---|
| `name` | `textOf` | **S1** — contains no `\n`, ever (contract G3). This is not cosmetic: `specificationsFrom` folds names with `name.toLowerCase()` into a `seen` map, and `CatalogService.merge_specifications` folds them again against the product's existing rows. A newline in a name would make two spellings of one name and defeat both folds. |
| `name` | | **S2** — `MAX_SPECIFICATION_NAME_LENGTH` is 100 and is enforced server-side. Unaffected: stripping only makes names shorter. |
| `value` | `proseOf` | **S3** — may contain `\n`; obeys contract guarantee G4 (no leading/trailing whitespace, no line with edge spaces, no run over two newlines). |
| `value` | | **S4** — contains no stylesheet or script text (FR-002). This is the `Customer Reviews` row on `B09GM8FB3X`. |

**Ordering and dedup are untouched.** `specificationsFrom` merges the page's containers first-occurrence-wins on the lower-cased name; `display_order` is still assigned from the surviving list index server-side. Invariant S1 is what keeps both true.

**Already-present-wins is untouched.** `merge_specifications` keeps a value the product already has. That is the correct rule and this feature does not change it — but it means re-capturing a contaminated product does **not** replace its `Description`. See `quickstart.md`, "Verifying against the real listings".

---

## 3. The walker's working state — internal, never persisted

Two transient objects, both scoped to a single `proseOf` call.

**The content clone.** A detached deep copy with `style`, `script`, `noscript` and `template` removed.

- **W1** — It is detached and discarded when the call returns. It is never inserted into any document.
- **W2** — The node it was cloned from is not modified (contract G2, FR-003). This is the invariant that protects the operator's live page on the fallback path, where `canonicalDocument()` returns `document` itself.
- **W3** — It is not used for image work. `descriptionImages()` reads the **original** block, because `knownEdges()` consults `img.naturalWidth`, which is 0 on a detached clone.

**The accumulated parts.** The strings the walk appends, in document order, before normalization.

- **W4** — Every `\n` in it was emitted by the walk at a `<br>` or a block boundary. Text-node content is whitespace-collapsed as it is appended, so source indentation contributes none (contract G5).
- **W5** — Normalization is applied once, to the joined result, in the four-step order the contract fixes. Applying it per-part would fold separators before they had neighbours to fold against.

---

## What is *not* modeled here

- **No entity, table, or column is added.** If the implementation reaches for one, something has gone wrong with the plan.
- **No representation of "which part of the description was markup".** The removed text is discarded, not recorded. Storing it would recreate the problem under a new name.
- **No structured form of the description** — no list of paragraphs, no Markdown, no HTML. It is one plain string whose newlines are meaningful. The display layer already renders it that way (`white-space: pre-wrap`) and the edit form already round-trips it (a textarea whenever the value holds a newline).
