# Phase 1 Data Model: Find By Any Code Or Note

**Feature**: `specs/009-find-by-code-or-note` | **Date**: 2026-08-09

## Summary: nothing is stored

**No table is added, no column is added, no column changes type or nullability, and there is no Alembic revision.** All three changes are read-path work over data the catalogue already holds. This section exists to record that claim explicitly, because it is the strongest constraint on the implementation: any task that finds itself needing a migration has misunderstood the design and should stop.

Constitution Principle V requires every schema change to ship as a reversible Alembic revision. The corresponding obligation for a feature with no schema change is to say so and mean it.

---

## Entities read

### Product (`app/database.py:820`)

Existing. Two of its columns are newly relevant.

| Field | Type | Role in this feature |
|---|---|---|
| `id` | Integer, PK | Remains the canonical address (FR-017). The code-formed route redirects *to* it. |
| `description` | String | Already searched. Unchanged. |
| `notes` | `Text`, nullable | **Newly searched** (FR-010). Nullable matters: `NULL LIKE '%x%'` is NULL, so a product with no notes is never returned on the strength of the field. No default is added; absent stays absent. |
| `manufacturer`, `manufacturer_part_number` | String | Already searched. Unchanged. |
| `internal_code` | *derived property* (`app/database.py:986`) | Reads the product's `INTERNAL` identifier. The value a code-formed address is built from. Already exists; not modified. |

`Product.internal_code` is a Python property over the `identifiers` relationship, not a column. It is already eager-loaded by `search_products` via `selectinload(Product.identifiers)` — a detail worth knowing, because a caller reading it off a detached result would otherwise fail. This feature adds no new reader of it outside a session.

### ProductIdentifier (`app/database.py:1123`)

Existing, unchanged. Relevant because it is what makes the code-formed address unambiguous.

| Field | Role in this feature |
|---|---|
| `id_type` | `INTERNAL` is the row a code-formed address resolves through. |
| `value` | The printed code. Unique per `(id_type, value, vendor)`, which is what guarantees FR-018 — a code-formed address can never be ambiguous, because two products cannot carry the same code. |
| `product_id` | The product the address redirects to. |

**Every product has exactly one `INTERNAL` identifier from the moment it is created** (`app/catalog_service.py:185-191`, comment: "Every product carries its own code from the start"). So FR-015 has no products to exclude and this feature needs no backfill — a fact worth stating because a "some rows lack a code" assumption would otherwise justify a migration that must not be written.

---

## Value objects (in memory only)

### ScanClassification (`app/models.py`)

Existing dataclass. **Its shape does not change** — no new `ScanKind` member, no new field.

| Field | Effect of this feature |
|---|---|
| `kind` | A recognized element string produces `ScanKind.GTIN`. Not a new kind: the point of R2 is that a structured scan *is* a GTIN scan by the time it leaves the classifier. |
| `value` | The 14-digit normalized GTIN key, produced by the same `gtin.normalize_and_validate` call a bare barcode goes through. |
| `raw` | The scan exactly as captured, decorations and all — the AIM prefix, the FNC1 and any trailing element strings are preserved here even though they are ignored for matching. |
| `ecia_fields` | `None`, as for any non-ECIA scan. |

The consequence: `ScanResolution`, `CatalogService.resolve_scan`, `POST /api/scan` and every UI surface handle a manufacturer's 2D barcode without knowing it exists.

### Trade item number (transient)

The output of `gs1.decode_trade_item_number` — a plain `Optional[str]` of exactly 14 ASCII digits, **verbatim and unjudged**. Not persisted, not passed beyond `scan_router`, and never itself a GTIN key: `gtin.py` alone decides whether those digits are a valid trade item.

This is the whole seam. `decode_trade_item_number('0109506000134353')` returns `'09506000134353'` — a number with a *bad* check digit — and `'0100000000000000'` returns fourteen zeros. Both are correct returns, and both are refused a moment later by `gtin.normalize_and_validate`. Extraction and validity are separate questions asked by separate modules.

---

## Validation rules, and where each one lives

| Rule | Source | Enforced by |
|---|---|---|
| A payload opens with `01` + exactly 14 ASCII digits | FR-001, FR-005 | `gs1.decode_trade_item_number` |
| What follows is end-of-input, GS, or an ASCII digit | FR-004, FR-005 | `gs1.decode_trade_item_number` |
| Only a payload *opening* with the trade item number is read | FR-007 | `gs1.decode_trade_item_number` (anchored at head) |
| At most one AIM identifier, at most one leading FNC1, surrounding whitespace absorbed | FR-003 | `gs1.decode_trade_item_number` |
| Accepted GTIN lengths, mod-10 check digit, all-zero refusal | FR-002, FR-006 | `gtin.normalize_and_validate` — **unchanged**, and reached by the same single call a bare barcode uses |
| Precedence: internal → ECIA → element string → GTIN → free text | FR-008 | `scan_router.classify` |
| A scan always yields a kind | FR-009 | `scan_router.classify`'s final rule, which always matches |
| A code-formed address resolves to at most one product | FR-018 | the existing unique key on `ProductIdentifier` |
| A well-formed code naming no product reports missing | FR-016 | `ItemNotFoundError` → existing 404 handler |

Nothing in this table is a new *kind* of validation. Every row is either an existing rule reached by a new path, or a structural check on a string.

---

## State transitions

None. No entity in this feature has a lifecycle, nothing changes status, and no write path is touched. The item history invariants of Constitution Principle VI are not in scope — this feature does not read or write `InventoryItem` at all.
