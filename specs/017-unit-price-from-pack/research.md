# Research: Unit Price From a Multi-Pack

Phase 0 for [plan.md](plan.md). The spec left exactly one thing open — issue #97 named it
too: *where the division runs*, given that a division done in JavaScript is a division done
in IEEE-754. Everything below is downstream of that.

## Where the division runs

**Decision**: In the browser, on `BigInt` integers, with the result written into the existing
`#unit_price` field as a decimal string. No server code changes.

**Rationale**: The requirement that forces the issue is FR-003/FR-004 — the operator sees the
unit price and can type over it *before* capturing. That rules out computing it during the
capture POST, which is the only place the server currently gets to see these values. So the
number has to appear in the page, and the choices are: compute it there, or fetch it from
somewhere.

Computing it there is exact if the arithmetic is integer arithmetic, and prices are integers
in disguise. A price is a digit string; `BigInt` parses digit strings exactly and divides them
exactly; the rounding is one explicit comparison on the remainder. No value ever exists as a
`Number`, so there is no float to have an opinion about. The constitution prohibits float
arithmetic for these quantities, not JavaScript.

**Alternatives considered**:

- **A `POST /api/unit-price` returning the `Decimal` result as a string.** Correct, and the
  arithmetic would be Python, which is the comfortable answer. Rejected on Principle I: it is
  a new endpoint, a new contract, CSRF handling, a fetch, an error path for the fetch, and a
  new awaited-fetch boundary that every e2e test on this page then has to wait across
  (CLAUDE.md pattern A) — all to divide two numbers the browser can divide exactly. It also
  buys nothing in correctness: the server would be computing from strings the browser sent
  and returning a string the browser displays. The exactness is in the algorithm, not in the
  language.
- **A "work it out" button that submits the form and re-renders it with the field filled.**
  No JavaScript at all, arithmetic in Python, unit-testable in the fast suite. Genuinely
  tempting. Rejected because `product_capture`'s POST is *the write path* — its docstring
  says so — and teaching it to sometimes not write, distinguished by which submit button was
  pressed, puts a "did this capture?" question into the one route where the answer must never
  be in doubt. A wrong guess there records a purchase the operator did not mean to record.
  Making the operator press a button and wait for a page load to see an arithmetic result is
  also worse than the calculator this feature is replacing.
- **Compute in the browser for display, recompute server-side at capture as the authority.**
  Rejected: it needs the server to know whether the operator overrode the field, which means a
  third piece of state travelling with the form, and it puts the same rounding rule in two
  languages where they can drift. The browser's value is already just a string the operator
  can edit; there is nothing for a second computation to add.
- **`Number` arithmetic on integer cents instead of `BigInt`.** Would in fact be exact — cents
  here are nowhere near 2^53. Rejected because it cannot be *seen* to be exact: every reviewer
  of this file, forever, would have to re-derive the safe-integer argument. `BigInt` costs
  nothing and ends the question.
- **A decimal library (decimal.js, big.js).** Rejected on Principle I: a dependency, plus a
  build or vendoring step this project does not have, for one division.

## The rounding rule

**Decision**: Round the quotient to two decimal places, half away from zero, and treat a
non-zero remainder as the trigger for telling the operator (FR-006, FR-008).

**Rationale**: The spec decided this and the schema agrees — `purchases.unit_price` is
`Numeric(10, 2)`. Keeping more precision than that would mean a migration, and issue #97 rules
schema changes out. Half-away-from-zero matches the `ROUND_HALF_UP` normalization the project
applies to every other exact quantity, and with both operands non-negative it is simply
"round half up".

There is a second, quieter reason to round *here*. Today a hand-typed `5.996` is accepted by
`_validate_price` and then silently rounded by the `Numeric(10, 2)` column on the way in — the
operator is never shown the value that got stored. Rounding in the page before submission
makes the recorded number and the displayed number the same number, which is the property that
matters when the price history is later read back.

**Alternatives considered**:

- **Truncate.** Rejected: `17.99 / 3` would read `5.99`, understating a price for no reason
  beyond being easier to implement, which it is not.
- **Widen the column and keep four decimals.** Rejected by the issue, and it would push the
  imprecision to every screen that displays a price rather than removing it.
- **Round the last unit to absorb the difference.** That is what a real invoice does, but this
  application records one unit price for a purchase, not a line per unit. There is nowhere to
  put the odd penny.

## What the extracted listing price becomes

**Decision**: The listing's price prefills the new pack-price field (FR-013) **and** continues
to prefill `#unit_price` as it does today, with the pack size defaulting to `1`.

**Rationale**: The two agree at a pack size of one, so nothing has changed for the ordinary
single-unit capture — which is FR-015, and is also what keeps the existing assertions in
`test_product_page_capture.py` (`#unit_price` == `24.99`, `1249.50`) meaningful rather than
merely passing. It is also the graceful-degradation story: with JavaScript unavailable the
page is exactly the page it is today, plus two inputs that do nothing.

**Alternative considered**: prefill only the pack price and leave `#unit_price` empty until
the operator triggers a computation. Rejected — it makes a capture that never touches the pack
fields record no price at all, a regression for the common case, and it makes the feature
mandatory rather than available.

## A pack size of one is not a division

**Decision**: A pack size of `1`, or an empty pack size, returns the amount paid *verbatim* —
the same string, not a reformatted one.

**Rationale**: `1249.50` must stay `1249.50`, and a hand-typed `12.345` must not be quietly
rounded to `12.35` by a feature the operator did not ask for. Routing the identity case
through the divide-and-round path would reformat values the operator never asked to be
reformatted, which is a change in behavior disguised as a no-op (FR-010, FR-015).

## Validation strictness

**Decision**: `^\d+(\.\d+)?$` for the amount paid, `^\d+$` and greater than zero for the pack
size. On failure, leave `#unit_price` untouched and name the offending field.

**Rationale**: `$1,249.50` is not a price to `_validate_price` either (there is a test
asserting exactly that), and accepting it here would produce a unit price the server would then
reject — worse than refusing it in place.

This is a strict *subset* of the server's rule rather than the same rule, and the difference is
worth stating because it looks like a bug and is not. `_validate_price` is
`Decimal(str(price).strip())`, which also accepts `5.`, `.5`, `+5`, `1e2`, and — a genuine
latent quirk, out of scope here — `Infinity` and `NaN`. The property that matters is one-way:
**everything this accepts, the server accepts**, so the page cannot derive a price the capture
would refuse. Loosening to match would be the wrong repair; none of those forms is how a person
writes what they paid, and one of them is not a price at all.

Leaving `#unit_price` alone on failure is FR-011 and matters more than it sounds: clearing it
would destroy a price the operator typed by hand and never intended to derive.

## Testing the arithmetic without a JavaScript test runner

**Decision**: Expose the pure function as `window.unitPriceFromPack` and drive the rounding
table from Playwright with `page.evaluate`; test the operator-facing behavior through the form.

**Rationale**: This repository has no `package.json` and no JS test runner, and adding one for
90 lines of JavaScript fails Principle I on its own. `page.evaluate` against a function on
`window` is already how this suite reaches into page scripts (`test_ecia_scan.py`,
`test_field_autocomplete.py`), and `label-count.js` already establishes the plain-global,
`window`-exposed idiom for a small shared page function. The rounding table is then a data
table in one test rather than fifteen form-driving round trips.

**Alternative considered**: adding Vitest or Jest. Rejected: a Node toolchain, a lockfile, and
a CI step, none of which this project has, for a function whose whole surface is two strings
in and one string out.

## What this feature deliberately does not do

- **It does not touch Quantity.** Stated in the spec's assumptions and repeated here because
  it is the first thing a reader will want to add: knowing the pack holds three does not tell
  the application that three arrived, and inferring it would silently change what a purchase
  claims about stock. The operator states quantity, as they do today.
- **It does not store the pack size.** FR-014. Issue #97 is explicit, and the moment a pack
  size is stored it needs a meaning on the receive screen, in the price history, and in the
  repeat-purchase path.
- **It does not detect the pack size from the listing.** Amazon's title says "3 Pack" often
  enough to be tempting and inconsistently enough to be wrong, and a wrong pack size produces
  a confidently wrong price. The operator can read.
