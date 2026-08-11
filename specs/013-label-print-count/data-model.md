# Phase 1 Data Model: Label Print Count

**Feature**: [spec.md](./spec.md) | **Date**: 2026-08-11

## Nothing is persisted

This feature adds **no table, no column, no ORM model, no dataclass, and no Alembic revision**.

A label count exists for the duration of one HTTP request and is then gone. It is not a property of
an inventory item — two users printing the same JA ID a week apart have no shared state, and the
spec explicitly rules out remembering the count between dialog openings (Assumptions) and reprinting
from a history of past runs (Out of Scope). Persisting it would create a fact the application would
then have to keep true.

Constitution Principle V is therefore not engaged: there is no schema change, so there is no
migration to write and none to reverse.

What follows describes the shape of the value as it moves through the request, so that validation
lands in one place and the four dialogs agree on what they are sending.

## Print request

The thing the user asks for when they press print. Assembled in the browser, validated at the route,
consumed by the printing service, and discarded.

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `ja_id` | string | yes | — | `JA` followed by exactly 6 digits (existing rule, `routes.py:1797`) |
| `label_type` | string | yes | — | Must be a key of `LABEL_TYPES` (existing rule, `routes.py:1804`) |
| `label_count` | integer | no | `1` | Whole number, `1 <= n <= 99` (new) |

A bulk run is not a single entity — it is one print request per selected item, sharing a
`label_type` and a `label_count`. That is a deliberate consequence of Decision 2 in
[research.md](./research.md) and is why FR-006 (one count for the whole run) is a UI property rather
than a data one: the browser holds the count and stamps it onto each per-item request.

### `label_count` validation rules

Enforced at the route, which is the one place all four dialogs pass through. The browser helper
applies the same rules first so the user is told before a request is made, but the route does not
trust that.

| Input | Outcome | Message |
|-------|---------|---------|
| absent from the body | accepted as `1` | — |
| `1` … `99` | accepted | — |
| `0`, negative | rejected, 400 | `label_count must be between 1 and 99` |
| `100` or above | rejected, 400 | `label_count must be between 1 and 99` |
| `2.5`, `"3"`, `null`, `[]` | rejected, 400 | `label_count must be a whole number` |
| `true` / `false` | rejected, 400 | `label_count must be a whole number` |

The boolean row is not pedantry. In Python `isinstance(True, int)` is `True` and `True + 1 == 2`, so
a naïve `isinstance(v, int)` check accepts `true` and prints one label for it. The check must
exclude `bool` explicitly.

Absent-means-1 is what makes the rollout incremental (FR-010): every caller that has not yet been
updated — including the existing unit tests that post `{ja_id, label_type}` — keeps working
unchanged.

## Print outcome

What the dialog reports back. Not stored; rendered and then discarded when the modal closes.

| Field | Meaning |
|-------|---------|
| items attempted | How many JA IDs the run covered. `1` for the single-item dialogs. |
| labels produced | Items that succeeded × the label count. The number the user can count in their hand. |
| failures | Per item, not per copy — see Decision 6 in [research.md](./research.md). Each carries the JA ID and the message the endpoint returned. |

**The invariant that matters** (FR-009): *labels produced* must never exceed what actually emerged.
Because an item's copies are one indivisible `lp` job, a failed item contributes `0` to the total
rather than a partial figure — under-claiming, which the requirement allows, rather than
over-claiming, which it forbids.

## Relationship to the Add Item form's `quantity`

There is no relationship, and that is the point worth writing down.

| | Means | Lives on | Range |
|---|---|---|---|
| **quantity** | how many inventory items to create | Add Item form | existing rules, unchanged |
| **label count** | how many labels to print per item | the four print dialogs | 1–99 |

They meet in one flow: a user sets quantity to 8, the items are created, and the print dialog opens
over the top of the form offering a label count. Story 3 scenario 4 pins the consequence — the
label count starts at `1` regardless of the quantity that produced the batch. Nothing reads one to
seed the other, and FR-014 requires the labeling to keep them apart on screen.
