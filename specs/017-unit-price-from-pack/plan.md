# Implementation Plan: Unit Price From a Multi-Pack

**Branch**: `issues/97` | **Date**: 2026-08-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/017-unit-price-from-pack/spec.md`

## Summary

The capture confirmation form gains two inputs — what was paid for the pack, and how many
units the pack holds — and works the unit price out from them, in the page, before anything
is captured. The listing's extracted price moves to the pack-price field, which is where it
has always belonged; the unit price field stays exactly where it is, stays editable, and is
what gets recorded.

The arithmetic runs in the browser on integers, never on a double: both operands are parsed
out of their digit strings into `BigInt`, divided with an explicit half-up rounding step at
two decimal places, and formatted back to a decimal string. Nothing on the server changes.
The unit price still arrives as the same string it arrives as today and still becomes a
`Decimal` in `_validate_price`, so Principle III holds on a path that has no float anywhere
on it, in transit or otherwise.

Scope is one new static asset, one template, one user-manual section, and the screenshot that
the template change invalidates. No route, no service, no model, no migration.

## Technical Context

**Language/Version**: Python 3.13 (untouched by this feature); browser JavaScript, ES2020 for
`BigInt`

**Primary Dependencies**: Flask 3.1.x, Jinja2, Bootstrap 5.3.2. No new dependency, in either
language.

**Storage**: MariaDB. `purchases.unit_price` is `Numeric(10, 2)` and stays that way; the two
pack inputs are never persisted (FR-014), so there is no Alembic revision in this feature.

**Testing**: `nox -s tests` (unit, network-blocked) and `nox -s e2e` (Playwright). The
arithmetic lives in JavaScript and is therefore exercised through Playwright — directly, by
calling the exposed function with `page.evaluate` for the rounding table, and through the form
for the operator-facing behavior. `nox -s screenshots_headless` regenerates
`docs/images/screenshots/user-manual/order_capture.png`, which this template change
invalidates.

**Target Platform**: The LAN-only Flask application, in a desktop browser. `BigInt` has been
in every browser this application is opened in for years.

**Project Type**: Server-rendered web application with page-scoped plain-JavaScript
enhancements.

**Performance Goals**: None. The computation is a handful of integer operations on keystroke;
there is nothing here to measure and nothing to optimize.

**Constraints**: No IEEE-754 arithmetic on any price (Principle III). No round trip to the
server for the computation — the operator must see the result while typing (FR-003). Degrading
without JavaScript must leave today's behavior, not a broken form.

**Scale/Scope**: One page, two new inputs, one derived field, ~90 lines of JavaScript.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| **I. Simplicity First** | PASS. One static file and one template. No abstraction, no configuration, no new dependency, no server code. The rejected alternatives (a compute endpoint, a server round-trip button, a server-side re-derivation at capture) are each strictly more machinery for the same result — see [research.md](research.md). |
| **II. Layered Architecture Boundaries** | PASS, vacuously. No route, service, storage or model code is touched. `product_capture` already re-renders with `form_data=request.form`, so the new fields survive a `CaptureDecisionRequired` re-render with no route change at all. |
| **III. Exact Numerics** | PASS, and it is the whole point of the feature. Both operands are parsed from their digit strings into `BigInt`; the division is integer division with an explicit remainder-based half-up step; the result is formatted back to a decimal string by string assembly. No `parseFloat`, no `toFixed`, no `Number` arithmetic on a price. The submitted value takes the existing string → `_validate_price` → `Decimal` path unchanged. |
| **IV. Test Discipline Through Nox** | PASS. New tests are e2e and run through `nox -s e2e`. No new pytest marker. The recompute is synchronous on an `input` event with no fetch behind it, so every wait is `expect(locator).to_have_value(...)` — polling, no fixed duration, no `networkidle`. Screenshot regeneration stays in `nox -s screenshots_headless`, outside the e2e gate. |
| **V. MariaDB Is the Source of Truth** | PASS. No schema change and no migration; FR-014 forbids storing either pack value. |
| **VI. Item Lifecycle and History Invariants** | Not engaged. This feature touches the product catalog's purchase capture, not JA-ID inventory items. |
| **Operating Context / Threat Model** | Not engaged. No new input reaches the database that did not already; validation here exists so the operator does not record a wrong price, which is the correctness rationale the constitution names. |
| **Technology Constraints** | PASS. Server-rendered Jinja page with a plain-global JavaScript file, matching `app/static/js/label-count.js` — no framework, no build step. |
| **Workflow: screenshots** | ENGAGED. `app/templates/product/capture.html` changes, so `user-manual/order_capture.png` must be regenerated and committed with the change, and `nox -s screenshots_verify` must pass. |
| **Workflow: branching** | SATISFIED. Work is on `issues/97`, to be merged by pull request. |

No violations. The Complexity Tracking table below is empty by consequence.

## Project Structure

### Documentation (this feature)

```text
specs/017-unit-price-from-pack/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── README.md        # The capture form's field contract and the rounding rule
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── static/js/
│   └── pack-unit-price.js          # NEW. The whole feature.
└── templates/product/
    └── capture.html                # Two new inputs, a note, and the script tag

docs/
├── user-manual.md                  # "Capturing an Order When You Place It" gains the pack
│                                   #   fields and states the rounding
└── images/screenshots/user-manual/
    └── order_capture.png           # Regenerated; the form has two more fields

tests/e2e/
└── test_order_capture.py           # New tests: the rounding table, the operator-facing
                                    #   behavior, and survival across a question
```

**Structure Decision**: The existing structure absorbs this feature without a new directory.
The JavaScript goes where every other page-scoped script goes (`app/static/js/`), the tests go
in the file that already covers the capture form end to end (`tests/e2e/test_order_capture.py`)
rather than in a new file, because the subject is that same form. `tests/unit/` gains nothing:
there is no Python in this feature to unit test.

## Implementation Notes

### `app/static/js/pack-unit-price.js` (new)

A plain global in the idiom of `label-count.js` — no ES module, no build step, and a function
hung on `window` so Playwright can call it directly with the rounding table rather than
driving the form fifteen times.

Three pieces:

1. **`window.unitPriceFromPack(paid, packSize)`** — pure, no DOM. Takes two strings, returns
   `{ok: true, value: '9.99', exact: true}` or `{ok: false, error: '...', field: 'pack_size'}`.
   This is the function the rounding table is tested against, and it is the only place the
   arithmetic exists.
2. **The wiring** — `input` listeners on `#pack_price` and `#pack_size` that recompute, write
   `#unit_price`, and update the note. Nothing listens on `#unit_price`: an operator typing a
   unit price directly is overriding, and an override that recomputed itself away would be
   useless (FR-004).
3. **The note** — a `#unit-price-inexact` element shown when `exact` is false, and an error
   line naming the unusable field when `ok` is false (FR-011). Its visibility is also evaluated
   once on page load, so that an inexact division still explains itself after a re-render —
   but the load path does **not** write `#unit_price`, because a re-render may be carrying an
   override the operator typed before the question was asked.

**The arithmetic** (the rule, stated once, in [contracts/README.md](contracts/README.md)):

- `paid` must match `^\d+(\.\d+)?$` after trimming; `packSize` must match `^\d+$` and be
  greater than zero. Anything else is `ok: false` with the offending field named, and the
  caller leaves `#unit_price` alone. A deliberate strict *subset* of what `_validate_price`
  takes — it is `Decimal(str(...).strip())`, so `5.`, `.5`, `+5` and `1e2` get through there and
  not here. Everything this accepts, it accepts, which is the direction that matters;
  `1,249.50` is a price to neither.
- A pack size of `1`, or an empty pack size, returns `paid` **verbatim**: no parse, no round,
  no reformat. `1249.50` stays `1249.50` and today's single-unit capture is untouched (FR-010,
  FR-015).
- Otherwise, with `s` = the number of fractional digits in `paid` and `N` = its digits as a
  `BigInt`: `A = N * 100n`, `B = BigInt(packSize) * 10n ** BigInt(s)`, `q = A / B`,
  `r = A % B`, and `if (2n * r >= B) q += 1n`. The result is `q` cents, formatted as
  `${q / 100n}.${String(q % 100n).padStart(2, '0')}`. `exact` is `r === 0n`.
- Both values are non-negative by the patterns above, so half-up and half-away-from-zero
  coincide and no sign handling is needed.

### `app/templates/product/capture.html`

The Order Date / Quantity / Unit Price row becomes a four-field arrangement: Order Date and
Quantity keep their places, and **Paid for the pack** and **Units in the pack** join Unit Price
so the derivation reads left to right.

- `#pack_price` — `name="pack_price"`, `inputmode="decimal"`, value
  `form_data.get('pack_price') or (listing.price if listing else '')`. This is FR-013: the
  extracted price is the pack price.
- `#pack_size` — `name="pack_size"`, `type="number"`, `min="1"`, `step="1"`, value
  `form_data.get('pack_size') or '1'`.
- `#unit_price` — unchanged, including its existing prefill from `listing.price`. With a pack
  size of 1 the two agree, so nothing has moved for a single-unit capture and the existing
  assertions in `test_product_page_capture.py` (`#unit_price` == `24.99`, `1249.50`) still
  hold. Without JavaScript the page behaves exactly as it does today.
- `#unit-price-inexact` — a `form-text` line, hidden by default, naming the shortfall in
  words: the pack size, the unit price, and what it does not add back up to.
- The script tag joins `field-autocomplete.js` in the `scripts` block.

`form_data` is `request.form` on the re-render path and `request.args` on first load, so both
new fields survive a `CaptureDecisionRequired` question with no route change (FR-012). The
route passes neither to `capture_order`, which satisfies FR-014 by doing nothing.

### Tests (`tests/e2e/test_order_capture.py`)

- **The rounding table**, via `page.evaluate("window.unitPriceFromPack(...)")` on the capture
  page: `29.97 / 3 → 9.99` exact; `17.99 / 3 → 6.00` inexact; `0.01 / 3 → 0.00` inexact;
  `1249.50 / 1 → 1249.50` verbatim; `10.00 / 4 → 2.50` exact; `17.995 / 2 → 9.00` inexact
  (the half-up step, on the boundary); `0` and `-1` and `2.5` pack sizes rejected naming
  `pack_size`; `1,249.50` and `abc` rejected naming `pack_price`.
- **The operator's flow**: fill `#pack_price` and `#pack_size`, assert `#unit_price` with
  `expect(...).to_have_value('9.99')`, capture, and assert the recorded price on the receive
  screen.
- **The override wins**: compute, type over `#unit_price`, capture, assert the typed value was
  recorded (US1 scenario 2).
- **Recompute is from the inputs**: compute, override, change `#pack_size`, assert the field
  holds the value derived from the two inputs and not from the override (US1 scenario 3).
- **The note**: visible for `17.99 / 3`, absent for `29.97 / 3`, and gone again when the pack
  size is changed to one that divides evenly (US2).
- **Across a question**: a capture that trips `#duplicate-warning` comes back with
  `#pack_price`, `#pack_size` and `#unit_price` all still populated (US3).

Every assertion is an `expect(locator)`; the recompute is synchronous with no request behind
it, so there is nothing to await and no fixed wait is warranted anywhere in this set.

### Documentation

`docs/user-manual.md`, "Capturing an Order When You Place It": a short paragraph on the pack
fields and one sentence stating the rounding and its consequence — that a pack price which
does not divide evenly leaves the unit price a fraction of a cent off, and the page says so.
Then `nox -s screenshots_headless` for `order_capture.png`, and `nox -s screenshots_verify`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Nothing to justify.

## Post-Design Constitution Re-check

Re-evaluated after Phase 1. Unchanged: no gate moved, and the design got smaller rather than
larger once the route turned out to need no change (`form_data=request.form` already carries
arbitrary fields through a re-render). The one gate the design *adds* work for is the
screenshot workflow rule, which is a task, not an exception. Principle III is satisfied by
construction rather than by care: the only division in the feature is `BigInt / BigInt`, and
the value never exists as a `Number` at any point between the operator's keystroke and the
`Decimal` in `_validate_price`.
