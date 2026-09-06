# Phase 0 Research: An Explicit "I Counted the Shelf" at Receipt

**Feature**: `specs/041-counted-at-receipt` | **Date**: 2026-09-06

The spec left no `[NEEDS CLARIFICATION]` markers, so this document records the decisions the
design had to make anyway — where the existing code puts the boundary this feature moves, and
which of several plausible placements is the one that keeps feature 008's rule intact.

## Where receiving happens, and how many places have to change

**Decision**: One service method, one route, one template.

**Finding**: `CatalogService.receive_purchase` (`app/catalog_service.py:1571`) is called from
exactly one place in the application — `product.purchase_receive`
(`app/product/routes.py:957`), which renders `app/templates/product/receive.html`. Every other
caller is a unit test. Every scan-driven path into receiving (`_receive_url`,
`purchase_receive_choice`, the order screen's receive buttons) resolves to a URL that lands on
that same route, so the control appears on all of them by appearing once.

**Rationale**: The narrow surface is why this feature is small. Nothing needs a new endpoint, a
new service, or a flag threaded through several layers.

**Alternatives considered**: Adding a separate "record a count" action to the receive screen
that calls `set_quantity`. Rejected: two writes where one will do, a second thing that can fail
half-way, and it asks the operator for a number the spec deliberately does not want.

## What the operator's assertion is called in code

**Decision**: `counted` — a form field `name="counted"`, and a keyword argument
`counted: bool = False` on `receive_purchase`.

**Rationale**: The name says what the operator asserted, not what the system does with it. The
alternative names — `update_quantity_age`, `stamp_counted_at`, `refresh_age` — describe the
mechanism, and a reader six months later has to work backwards from a column name to the human
claim. Spec FR-012 makes the same point about the visible label; the code should not undo it.

**Alternatives considered**: `verified`. Rejected as ambiguous — a receipt verifies several
things (the price, the part number), and this asserts one specific act.

## Boolean default and the shape of the parameter

**Decision**: `counted: bool = False`, parsed in the route as
`request.form.get('counted') == 'on'`.

**Rationale**: An unchecked HTML checkbox posts nothing at all, so absence *is* the default and
no hidden companion field is needed. `== 'on'` is the pattern already in this file for
`identifier_override` (`app/product/routes.py:226`), and matching it costs nothing. The default
on the service method keeps all twenty-odd existing unit-test call sites compiling and
asserting the unchanged behaviour, which is exactly the regression net spec Story 2 asks for.

**Alternatives considered**: `Optional[bool] = None` with three states, to distinguish "not
asserted" from "explicitly denied". Rejected under Constitution I — nothing needs the third
state, and there is no denial to record.

## Which clock the recorded moment comes from

**Decision**: `utc_now()` from `app/utils/clock.py`, taken at the moment the receipt is
processed.

**Rationale**: `app/utils/clock.py` draws the distinction this decision turns on. A count age is
"an instant the application recorded ... its only use is comparison", which is `utc_now`. The
purchase's `received_date` is "a day the operator stated", which is `local_now`, and it may be
backdated by the operator on this very form. `Product.quantity_age` subtracts
`quantity_updated_at` from `utc_now()`, so writing anything else there produces a wrong age —
which is issue #134 all over again. This is spec FR-008.

Every other writer of `quantity_updated_at` already uses `utc_now()`
(`catalog_service.py:224`, `:446`), so this adds no new basis.

**Alternatives considered**: Using the submitted `received_date`. Rejected: a receipt backdated
three days would claim the shelf was counted three days ago, and a receipt backdated a year
would produce an age nobody asserted.

## Where the write goes relative to the already-received guard

**Decision**: Outside it. The count age is stamped whenever `counted` is true and the product
has a tracked count, whether or not this submission is the first receipt.

**Rationale**: `receive_purchase` already sorts its writes into two groups, and the split is
principled rather than incidental. Inside `if not already_received` go the things a second
submission must not repeat — the received date, the count increment. Outside it, with a comment
naming 029 FR-025, goes the description, because "a description the operator has just corrected
with the thing in front of them" is a fresh assertion regardless of what the purchase's state
was before. The count assertion is that same kind of thing: the operator either looked at the
shelf just now or did not, and whether this purchase was already marked received a week ago has
no bearing on it. This is spec FR-010.

**Alternatives considered**: Stamping only on a first receipt, so that everything the tick does
is confined to the same guard as the count increment. Rejected: it makes the tick silently do
nothing in a case the screen offers it in, which is the exact failure mode spec FR-007 exists to
avoid, and it would make the already-received banner's list of what still applies wrong.

## Not creating a count that was not being tracked

**Decision**: The write is guarded by `product.quantity is not None`, the same condition the
increment already uses.

**Rationale**: Spec FR-006, which is feature 008's FR-009 restated. `set_quantity` is the only
thing that starts or stops tracking; receiving must never do it. Note that this guard is *not*
the same as the increment's full condition — the increment also requires
`purchase.quantity` to be truthy, and the age write deliberately does not (spec Story 1
scenario 5 and the no-quantity edge case): the operator looked at the shelf whether or not the
delivery had a number on it.

## Hiding the control where it would do nothing

**Decision**: The template wraps the control in `{% if product.quantity is not none %}`.

**Rationale**: Spec FR-007. `product` is already in the template's context on both the GET and
the refused-POST render, and `quantity` is the tri-state column — `None` is "not tracked",
`0` is "tracked, none on hand". The Jinja test must be `is not none` and not truthiness, or a
product counted down to zero loses the control (spec Story 3 scenario 2). The service-side guard
above stays regardless: hiding a control is a UI decision, and the rule about what receiving may
assert is a service rule.

## Surviving a validation refusal

**Decision**: The checkbox's `checked` attribute is driven from `form_data`, alongside the
description and quantity that already work this way.

**Rationale**: Spec FR-009. The route's refusal path re-renders with `form_data=request.form`
and a comment explaining that a refused value the operator spent time on should still be on the
page. A tick that silently clears itself on a refusal about the unit price would be the operator
asserting something once and having it discarded. On the GET render `form_data` is `None` and
the control is unticked, which is spec FR-002.

Note that a refusal happens before the session opens — `receive_purchase` validates quantity,
price and description ahead of `with self._session()` — so nothing is written, including the
age. That property is existing and needs no work; the test asserting it does.

## The docstring that forbids what this feature adds

**Decision**: `Product.quantity_age` (`app/database.py:951`) has its warning amended, not
deleted.

**Finding**: That docstring currently reads "Do not restore a timestamp write to
`receive_purchase` -- it looks like a missing update and it is the bug that feature removed."
After this feature there *is* a timestamp write in `receive_purchase`, and a future reader
following that instruction would delete it.

**Rationale**: The warning is still right about the unconditional write it was written against.
It needs to say that the write is now conditional on the operator's assertion, and that the
thing that must not come back is stamping the age on every receipt.

## Schema, migration and API surface

**Decision**: None of them change.

**Rationale**: `quantity_updated_at` already exists and already has exactly the meaning this
feature writes into it. Nothing records, per purchase, whether its receipt carried the assertion
(spec Assumptions), so no column is added and there is no Alembic revision. `Purchase.to_dict`
and `Product.to_dict` are unchanged. Constitution V is satisfied by there being nothing to
migrate.

## Amending feature 008

**Decision**: `specs/008-trustworthy-stock-age/spec.md` is edited in place — FR-008, SC-001,
SC-003, one Overview sentence, one Edge Case and one Assumption — rather than left to be read
against a codebase that contradicts it.

**Rationale**: Issue #149 asks for this directly, and spec SC-006 makes it checkable. The
repository's rule that `specs/` is a frozen record (CLAUDE.md, on spelling) is about not
rewriting history for cosmetics; a requirement that the shipped code now contradicts is a
different thing, and 008's own text is what a future reader will consult before touching
`receive_purchase`. The carve-out is not reversed — it is given its one named exception, with a
pointer to this feature.

`plan.md`, `data-model.md`, `tasks.md` and the checklists under `008-trustworthy-stock-age/`
are **not** edited: they are the record of how that feature was built, and they were accurate.
Only `spec.md`, which states what the application must do, is brought into agreement with what
it does.

## Documentation and screenshots

**Decision**: `docs/user-manual.md` is amended in the two places that state the old absolute
rule. Screenshots are regenerated per Constitution ("Development Workflow and Quality Gates"),
and only genuinely-changed images are committed.

**Finding**: No screenshot in `docs/images/screenshots/` shows the receive screen — the
eighteen generated images cover the inventory list, add/edit item, search, move, shorten, the
photo pages, the product detail and add pages, the reorder list, the category tree and the
DigiKey order pages. A template change to `receive.html` therefore should not alter any PNG.
`metadata.json` carries a `generated_at` that churns on every run, so the regeneration is run to
prove no image moved, not to produce a commit.
