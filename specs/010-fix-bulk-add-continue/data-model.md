# Phase 1 Data Model: Fix Add & Continue With Quantity Greater Than One

## Persistent model: unchanged

**No entity, column, index, constraint, or relationship changes.** No Alembic revision is created,
and Constitution V's migration requirements are not engaged.

The two entities the spec names already exist and are not modified:

| Spec entity | Where it lives | Change |
|-------------|----------------|--------|
| **Inventory item** | `Item` (`app/models.py`) ↔ `InventoryItem` (`app/database.py`) | None. Bulk creation already produces N ordinary items differing only in `ja_id`. |
| **Add submission** | Not persisted. It is one HTTP request built from the form. | None to its shape; see the contract in [contracts/add-item-submission.md](./contracts/add-item-submission.md). |

The defect is that one **Add submission** was being constructed twice from a single user action.
That is a client-side lifecycle problem, not a data-shape problem — which is why this file is
short.

## Invariant this feature restores

Constitution VI requires exactly one active row per JA ID and consistent item history. Bulk
creation with **Add & Continue** could violate the *intent* of that invariant in a way the schema
cannot catch: each of the 2N rows is individually well-formed and uniquely keyed, so the database
is internally consistent while the inventory is wrong. Nothing in the data model can detect
"the user asked for 6 and the system recorded 12" — only the count assertion in the new e2e
coverage can.

Stated as the property under test:

> For one press of a submit control on the Add Item form with **Quantity to Create** = *N*,
> the number of `InventoryItem` rows created is exactly *N*.

## Client-side state (the part that does change)

`InventoryAdd` (`app/static/js/inventory-add.js`) gains and loses state as follows. This is
in-memory browser state within a single page load; none of it is persisted server-side.

| Field | Status | Purpose |
|-------|--------|---------|
| `submitting` | **new** — boolean, default `false` | Re-entrancy guard (D2). Set after `preventDefault()`, cleared in `finally`. Prevents a second submission from a repeated press or an Enter keypress while the first is in flight. |
| `continueAfterBulk` | **new** — boolean, default `false` | Records that the in-flight bulk submission came from **Add & Continue**, so the `hidden.bs.modal` handler knows whether to navigate (D4). Set from `event.submitter` at submit time. |
| `createdJaIds` | existing | JA IDs returned by a bulk creation; drives the label-printing dialog. Unchanged. |
| `bulkCreationCount` | existing | Count returned by a bulk creation. Unchanged. |
| `lastItemData` | existing | Carry-forward values, mirrored into `sessionStorage` under `workshop_inventory_last_item`. Unchanged — it already survives a page load, which is what makes D4's navigation safe for FR-008. |

### Removed

- The per-submission `<input type="hidden" name="submit_type">` created by
  `document.createElement` is replaced by a static field in the template (D3). Beyond being
  clearer, this removes a latent defect: a failed bulk submission does not navigate away, so its
  appended input survived and a later press appended a second one. `request.form.get('submit_type')`
  returns the *first* value, so a subsequent plain **Add** would have been read as a `continue`.
- `clearFormForContinue()` — dead code, called from nowhere in `app/` or `tests/` (D7).

## State transitions

One press of a submit control on the Add Item form:

```
                        ┌─────────────────────────────────────────┐
                        │ idle  (submitting = false)              │
                        └────────────────┬────────────────────────┘
                                         │ submit event
                                         │ (from either button, or Enter)
                                         ▼
                         ┌───────────────────────────────┐
      invalid form ◄─────┤ preventDefault()              │
      (report, no        │ guard: submitting? → return   │
       request sent,     │ checkValidity()               │
       FR-010)           │ submitting = true             │
                         │ submit_type ← submitter value │
                         │ stash carry-forward data      │
                         └───────────┬───────────────────┘
                                     │
                  quantity == 1 ─────┴───── quantity > 1
                         │                        │
                         ▼                        ▼
              form.submit()              ONE fetch POST
              (native, navigates)        (buttons disabled)
                         │                        │
                         ▼                        ▼
              server redirect            JSON response
              /inventory/add             │
              (continue) or              ├─ ok      → toast + label dialog
              /inventory (add)           ├─ partial → count message (FR-009)
                                         └─ error   → error message
                                                    │
                                    buttons restored in `finally` (FR-005)
                                                    │
                                         dialog dismissed
                                                    │
                        continueAfterBulk ──────────┴────────── else
                                │                                 │
                                ▼                                 ▼
                    navigate to /inventory/add           stay on page, form
                    (FR-006, matches the                  intact (FR-007 — the
                     quantity-1 continue path)            two buttons stay
                                                          distinguishable)
```

The property that makes this correct is that there is exactly **one** arrow out of `idle`. Today
there are two, and above quantity 1 both fire.
