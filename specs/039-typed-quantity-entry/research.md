# Research: Type a tracked count instead of clicking to it

**Feature**: 039-typed-quantity-entry | **Date**: 2026-09-06

Nothing in this feature needed new technology. What it needed was decisions about which of
several already-available shapes to use, and one careful reading of an existing validator. Those
are recorded here.

## 1. Where the missing capability actually is

**Decision**: No service-layer or storage change. The work is a template control, a JavaScript
handler, and one derived value passed to the template.

**Rationale**: `CatalogService.set_quantity()` (`app/catalog_service.py:410`) already takes an
absolute count and already reaches all three states — a number, zero, and `None` for "stop
counting". `PATCH /api/products/<id>/quantity` (`app/product/routes.py:2241`) already forwards
whatever number it is given. `tests/unit/test_stock_status.py` already asserts all of that,
including that setting a count stamps `quantity_updated_at` and that stopping clears it.

The only reason forty clicks are needed is that `app/static/js/product-stock.js` computes
`currentQuantity() + delta` and never offers any other input. The absolute path exists and is
unused.

**Alternatives considered**: Adding a `PATCH .../quantity/adjust` delta endpoint so the client
could send "+40". Rejected — it inverts the problem. The endpoint is already absolute; the client
is what turns an absolute intent into a sequence of deltas.

## 2. The tri-state, and the empty-string trap in `_validate_quantity`

**Decision**: The browser never sends an empty value. It refuses locally and shows the reason in
`#stock-alerts`. `_validate_quantity` is left exactly as it is.

**Rationale**: `CatalogService._validate_quantity()` (`app/catalog_service.py:4320`) opens with:

```python
if quantity is None or quantity == '':
    return None
```

So `{"quantity": ""}` would be read as **stop tracking**, not as an error. That is correct where
the validator is called from product creation, whose form posts `''` for a field the operator left
blank and genuinely means "not tracked". It is wrong as an answer to a typed on-hand entry, where
an empty box means the operator has not said anything yet.

The fix belongs in the client, which is the only thing that can tell the two apart, and which is
also the only client this endpoint has. Making the *endpoint* strict would either duplicate the
tri-state rules in a second place or change a validator that two other callers depend on for the
opposite behavior — both larger than the problem (Constitution I).

**Alternatives considered**:

- Narrowing `_validate_quantity` to reject `''`. Rejected: `create_product` and `update_product`
  pass form values through it, and `''` from a blank form field must keep meaning "not tracked".
- Rejecting `''` in `api_set_quantity` only. Rejected for now: nothing sends it, and the guard
  would be a defense against a client that does not exist. Recorded here so that the next person
  to read the validator knows the reading was done and the conclusion was deliberate.

## 3. Typed entry versus the thumb-sized-button rule

**Decision**: The typed entry is **added** to the stepper buttons. Neither stepper is removed,
resized, or repurposed.

**Rationale**: The Stock card carries an explicit comment (`app/templates/product/detail.html:299`)
that every action on it is a button large enough for a thumb, because the product page is used
from a handheld at the shelf. `tests/e2e/test_touch_readiness.py` enforces it: one test taps
through start-tracking, increment and decrement on a touch viewport, another asserts a 44px
minimum height on the card's controls. Replacing the steppers with a field would break both and
would remove the one interaction the steppers are genuinely good at.

The typed control is reachable by touch because a numeric input raises the on-screen numeric
keypad. Its commit button is a button, and it is held to the same 44px floor as the rest of the
card by extending the existing test's selector list.

**Alternatives considered**:

- Replacing the steppers with a field, per the issue's "alongside or instead of". Rejected: the
  issue itself concludes that keeping both is right, and the touch tests encode why.
- A long-press-to-repeat stepper. Rejected: still proportional to the number, and it invents an
  interaction the rest of the application does not use.

## 4. One control or two: what "commit" means in each state

**Decision**: One input, and one adjacent button whose label depends on the state.

| Product state | Input | Button | Empty input means |
|---|---|---|---|
| Being counted | pre-filled with the current count | **Set** | refused, with a message (FR-006) |
| Not counted | empty, labelled as a starting count | **Start counting this** | start at zero (FR-004) |

**Rationale**: This is what lets FR-004 and FR-006 both hold without either being a special case
of the other. The two states have different buttons saying different things, so an empty field
means what the pressed button says it means. It also preserves the existing behavior of
`#start-tracking-btn` exactly — an untouched field and a press still produces a count of zero —
which is what three existing E2E tests already assert
(`test_touch_readiness.py:70`, `test_reorder_view.py:193`).

**Alternatives considered**:

- A single always-present "Set" button, with "Start counting this" removed. Rejected: it deletes
  a control that three tests and the reorder workflow depend on, to save one button.
- Committing on `Enter` / blur with no button at all. Rejected: it is keyboard-only, which the
  card's whole design rules out, and a blur-commit fires when the operator taps away to check
  something.

## 5. Where the received total is computed

**Decision**: In `product_detail`, from the purchase list the route has already fetched, passed to
the template as `received_total`.

**Rationale**: The route already holds every purchase — `purchases = service.get_purchase_history(product_id)`
— and already derives a list from them in exactly this shape:

```python
outstanding=[p for p in purchases if p.is_outstanding],
```

Summing the received ones is the same operation over the same list. It is not an ORM query in a
route (Constitution II forbids those), because the query already happened; it is arithmetic on a
result. Adding a `CatalogService.get_received_total()` would open a second session to re-read rows
the route is holding, for one `sum()`.

`Purchase.is_outstanding` is `received_date is None`, so "received" is its negation.
`Purchase.quantity` is nullable, and a purchase with no quantity contributes nothing.

**Alternatives considered**:

- A service method. Rejected as above — a second query for a sum over data already in hand
  (Constitution I).
- Computing it in the Jinja template. Rejected: it would be untestable except through rendered
  HTML, and the route context is the seam the unit tests already use.

## 6. What the received total does and does not do

**Decision**: Stated as text next to the starting-count entry. Never pre-filled into the input.
Never shown for a product that is already being counted. Never shown when the sum is zero.

**Rationale**: This is the open question the issue raised, and it is answered in the spec's
Assumptions. The record says how much arrived; it says nothing about how much has since been used.
A pre-filled 100 that the operator commits without reading writes a count nobody verified — a
worse outcome than the clicking, because a wrong count looks exactly like a right one. Stated as a
figure the operator reads and then types, it costs three keystrokes and the committed number is
one somebody chose.

Suppressing it on a tracked product is not cosmetic: receiving into a tracked product already adds
the purchase quantity to the count, so restating the total there invites the operator to add it a
second time.

**Alternatives considered**:

- Pre-filling the input. Rejected as above.
- A "use this" button that fills the input in one tap. Rejected: it is machinery for saving three
  keystrokes, and the tap is close enough to a pre-fill to carry the same risk of an unread commit.
- Netting received against consumption. Rejected: nothing in the record says what has been
  consumed, so the number would be an invention.

### 6a. What the line may claim *(revised after review of PR #151)*

**Decision**: the line states the received total and says nothing about whether any of it has been
counted. It reads "N received for this product to date."

**Rationale**: the first version read "N received for this product, none of it counted", and that
second clause is not knowable. The sum is over every received purchase for the product's whole
life; the guard is on whether the product is tracked *now*. Those come apart in a reachable
sequence:

1. the product is tracked, so `receive_purchase` adds an arriving 100 to its count — the count
   *did* absorb them;
2. the operator later presses "Stop counting this", which clears the count and leaves the purchase
   history untouched;
3. the product is now untracked with a lifetime received total of 100, and the line claimed none of
   it had been counted.

False, and false in exactly the direction the FR-013 suppression exists to prevent: it invites the
operator to enter stock that was already counted once.

Two ways out. Scope the sum to purchases received while the product was untracked — which needs a
per-purchase flag recording whether the count absorbed it, i.e. a schema change and a migration to
caption an advisory hint. Or claim only what the record supports. The second is right here: the
total is the useful part, the operator is standing at the shelf about to count the thing anyway,
and Constitution I does not let a hint earn a column. **The hint says less rather than guessing.**

**Alternatives considered**: a per-purchase "absorbed by a count" flag (rejected — a schema change
for a caption); suppressing the line entirely whenever the product has ever been tracked (rejected
— it would hide the total in the issue's own scenario as soon as the operator experimented with the
tracking buttons once, and "has ever been tracked" is not recorded either).

## 7. Client-side validation and how it reports

**Decision**: The handler validates before sending, and writes any refusal into the existing
`#stock-alerts` region via the class's existing `showAlert()`. The server's own `ValidationError`
path is unchanged and still reaches the same region.

**Rationale**: `StockControls.showAlert()` already exists and already renders into `#stock-alerts`;
the class already routes server errors there. Rejecting locally means the page does not reload, so
FR-008 — correct the entry and commit again without losing the displayed count — falls out for
free, since `patch()` only reloads on success.

Browser constraint validation is deliberately *not* the mechanism. A control that is not inside a
form never runs it, and where it does run the failure is a transient native bubble — which is
precisely the "submissions that never happen are silent" failure mode `CLAUDE.md` warns about.

**Alternatives considered**: Wrapping the control in a `<form>` and relying on constraint
validation. Rejected: a native bubble is not observable from an E2E test, and this is not a form.

## 7a. Why the field is not `type="number"` *(decided during implementation)*

**Decision**: `type="text"` with `inputmode="numeric"` and `pattern="[0-9]*"`. Not `type="number"`
with `min` and `step`, which is what §7 originally assumed.

**Rationale**: a number input **discards non-numeric keystrokes and reports `value` as `''`** for
content it considers invalid. So "abc" and an untouched field would arrive at the handler
identically empty — and those are exactly the two cases FR-006 and FR-007 refuse with *different*
messages ("type a count first" versus "the count must be a whole number"). Collapsing them would
make one of the two requirements unimplementable and the other's message wrong half the time.

It would also make the handler's non-numeric branch dead code, and dead code that a test cannot
reach: Playwright refuses to `fill()` a number input with non-numeric text, so the E2E case for
FR-007 could not be written at all.

`inputmode="numeric"` is what actually raises the numeric keypad on a touchscreen, which is the
only thing FR-010 needs from the input's type. `pattern` is there for the same reason (historically
required alongside `inputmode` on iOS) and validates nothing, since the control is not in a form —
the template says so at the call site so that nobody later reads it as validation that is somehow
not firing.

**Alternatives considered**: `type="number"` with the empty/invalid distinction dropped. Rejected —
it deletes a requirement to keep an attribute.

## 8. Screenshots

**Decision**: Run `nox -s screenshots_headless` and `nox -s screenshots_verify` after the UI
change, and commit only screenshots whose content actually changed.

**Rationale**: The constitution requires regenerating documentation screenshots for any change to
`app/templates/**` or `app/static/js/**`. Screenshot output churns byte-for-byte between runs
regardless of content, so the diff must be inspected rather than committed wholesale — committing
incidental churn is noise in review, and `nox -s screenshots_verify` does not catch it (it checks
size, format and colour mode, nothing about content).

**Corrected after running it.** This section originally predicted the regeneration would be a
no-op, on the grounds that `tests/e2e/screenshot_config.yaml` has no product-detail entry. That
was wrong: `docs/images/screenshots/user-manual/product_detail.png` exists and does depict the
Stock card, generated from `tests/e2e/test_screenshot_generation.py` rather than from the YAML.
The run changed six PNGs; `product_detail.png` grew by ~2.5KB, a real content change showing the
new label, entry and Set button, and the other five moved by under 800 bytes each, which is churn.
Only `product_detail.png` and `metadata.json` were committed.

`.github/workflows/screenshots.yml` does **not** diff or block — it posts a reminder comment on
PRs touching UI files and, in its own words, "leaves the judgment" to a person. So there is no
staleness gate to satisfy, which is what makes reverting the churn the right call rather than a
risk.

## 9. How the E2E tests wait

**Decision**: Every new E2E assertion waits on an `expect()` over an element the change produces.
No fixed waits, per Constitution IV.

**Rationale**: `StockControls.patch()` reloads the page on success, so the completion signal for a
committed count is `#quantity-value` holding the new number — pattern C in `CLAUDE.md`
("render-implies-completion"): the reloaded value cannot predate the completed PATCH. For a
*refused* entry there is no reload, and the signal is `#stock-alert` appearing inside
`#stock-alerts`, which `showAlert()` writes only after the refusal.

The negative assertion — "the received total is not shown on a tracked product" — is the dangerous
one, because it passes trivially against a page that has not rendered. It is guarded by first
establishing the card with a positive `expect()` on `#quantity-value`, then asserting the absence.

## Open questions

None.
