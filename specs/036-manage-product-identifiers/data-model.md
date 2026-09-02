# Phase 1 Data Model: Manage Product Identifiers After Creation

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-09-02

**No schema change. No Alembic revision.** Every column this feature writes already exists and
already carries data. This document records what is there, and — more usefully for the
implementation — where each rule already lives, so that none of them is restated in the browser.

---

## Entities

### Product

The cataloged thing. Unchanged by this feature.

| Field | Notes |
|---|---|
| `id` | Primary key; the `<product_id>` in both endpoints. |
| `internal_code` | The system's own code. Rendered at `detail.html:391` as `#internal-code`. |
| `identifiers` | Zero or more `ProductIdentifier` rows, one of which is the `INTERNAL` one. |

**Invariant this feature must not break**: identity is the product row, never one of its names
(`catalog_service.py:849`). Removing every identifier leaves the product intact and still
reachable by its internal code — FR-017, SC-005.

### ProductIdentifier

One coded name for a product.

| Field | Type | Written by this feature | Notes |
|---|---|---|---|
| `id` | int | — | The `<identifier_id>` in the DELETE path. |
| `product_id` | int | via the URL | Owning product. |
| `id_type` | str | yes | An `IdentifierType` value. |
| `value` | str | yes, **normalized** | What is stored is not always what was typed. |
| `vendor` | str | yes | `''` when absent — never NULL (`catalog_service.py:3557`). |
| `validation_overridden` | bool | yes | True only when a failing GTIN was accepted on an explicit opt-in. Already rendered on the card at `detail.html:403`. |

---

## Type vocabulary

`IdentifierType` (`app/models.py:402`) has five members. Four are operator-settable; `INTERNAL`
is generated and never typed.

| Type | Vendor required | Value normalized | Offered in the UI |
|---|---|---|---|
| `MPN` | no | trimmed | yes |
| `GTIN` | no | **to a 14-digit key** | yes |
| `VENDOR` | **yes** | trimmed | yes |
| `DISTRIBUTOR` | **yes** | trimmed | yes |
| `INTERNAL` | — | — | **no** |

**New constant**: `OPERATOR_IDENTIFIER_TYPES` in `app/models.py`, derived from the enum with
`INTERNAL` excluded. It is the single source for both the Add Product form's `<select>` and the
detail card's — which is what makes FR-003 a property of the code rather than a convention.
Nothing else about the enum changes.

---

## Rules, and where each one already lives

The browser enforces **none** of these. It sends what the operator typed and renders what comes
back. This is the whole of FR-004: one rule set, not two.

| Rule | Requirement | Where it lives today |
|---|---|---|
| Value must be non-empty | FR-011 edge case | `_normalize_identifier_value`, `catalog_service.py:3602` |
| Unknown type refused | FR-003 | `_validate_identifier_type` |
| Vendor-scoped type needs a vendor | FR-008 | `_add_identifier`, `catalog_service.py:3559` |
| GTIN normalized to the 14-digit key | FR-005 | `gtin_utils.normalize_and_validate` |
| Bad check digit refused unless overridden | FR-006 | `catalog_service.py:3622` |
| Override recorded on the row, not silent | FR-006 | `validation_overridden` column |
| All-zero read always refused, no override | FR-007 | `gtin_utils.is_all_zero`, `catalog_service.py:3609` |
| Same value already on **this** product → return the existing row | FR-010 | `_add_identifier`, `catalog_service.py:3576` |
| Same value on **another** product → `DuplicateItemError` naming it | FR-009 | `_add_identifier`, `catalog_service.py:3582` |
| Product must exist | FR-019 | `add_identifier`, `catalog_service.py:831` (raises `ItemNotFoundError`) |
| Removing a row that is not there → `False`, not an exception | FR-018 | `remove_identifier`, `catalog_service.py:863` |
| A removed name does not remove the product | FR-017 | `remove_identifier` deletes only the identifier row |

### The normalization consequence the UI must respect

`687117723741` is stored as `00687117723741`. FR-012 says the shown list must match what is
stored, so the card must render the **stored** value — which is one more reason the success path
reloads from the server (research [D1](./research.md)) rather than echoing the typed text.

---

## State

Identifiers have no lifecycle: a row exists or it does not. There is no soft delete, no history
table and no audit trail for them, and this feature adds none — that machinery exists for
inventory items (constitution VI) and deliberately does not extend to the catalog.

---

## What is deliberately not modeled

- **No edit.** There is no update path for an identifier and this feature does not add one; a
  correction is a remove plus an add (spec Assumptions).
- **No backfill.** The three products carrying a valid UPC as a *specification row* keep that
  row. Nothing promotes it; the operator adds the `GTIN` by hand, which is the point of the
  feature (spec Out of Scope).
- **No uniqueness change.** Duplicate detection stays exactly as it is: keyed on
  (`id_type`, `value`, `vendor`), so the same value under two different vendors is two legitimate
  identifiers.
