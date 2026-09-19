# Phase 0 Research: Packs Recorded as Units, and What a Pack Was Kept

Every decision below was settled by reading the code that already exists, not by choosing among
possibilities in the abstract. Where the answer was already implemented somewhere in the
repository, that is recorded rather than re-derived.

---

## R1 — Where the pack conversion belongs: on the line, not in the service

**Decision**: `AmazonOrderLine` gains the pack shape `McMasterOrderLine` already has — the stored
fields `packs`, `pack_size`, `pack_price`, and the derived properties `quantity`, `unit_price`,
`exact_unit_price`, `price_rounds`. The four properties are lifted into a shared `PackLine` mixin
in `app/models.py` and both line classes use it.

**Rationale**: `McMasterOrderLine` (`app/models.py:1607`) already does exactly this feature's
arithmetic, and everything downstream is written against the *result*:

- `_mcmaster_line_fields` and `_amazon_line_fields` both already call
  `service._mcmaster_quantity(line, decision)` and `service._mcmaster_unit_price(line, decision)`
  (`app/catalog_service.py:5035`, `:5175`) — Amazon reuses McMaster's helpers verbatim today.
- `ReviewedLine.has_change` (`app/models.py:2261`) compares `self.line.quantity` and
  `self.line.unit_price` against what is recorded. **Making these properties is what satisfies
  FR-010 without writing anything for it** — the comparison starts using converted values because
  that is what the line now reports.
- `ReviewedLine.price_rounds` and `unit_price_as_recorded` (`:2205`, `:2219`) likewise.
- `order_review.html` already renders a `price_rounds` warning and a pack column, gated on
  `vendor.review_columns`.

Doing the conversion in the service instead would leave `has_change` comparing raw values against
converted ones, which is the "Update it?" bug PR #116 already fixed once for sub-cent prices.

**Alternatives considered**:

- *Convert inside `_amazon_line_fields` only.* Rejected: `has_change`, `price_rounds` and the
  template all read the line directly and would each need their own conversion — four copies of
  one division, which is how this codebase got the duplicate-vendor defects in the first place.
- *No mixin, duplicate the four properties.* Rejected under the standard `order_vendors.py` sets:
  the variation is measured across two shipped implementations, so one copy is warranted.

---

## R2 — How the operator's pack size reaches the line

**Decision**: the review posts `pack_size[<form_key>]` per line. `_order_decisions`
(`app/product/routes.py:1536`) reads it alongside the fields it already reads. The service applies
it with `dataclasses.replace(line, pack_size=n)` before computing, because the line is frozen.

**Rationale**: `_order_decisions` is already the single place a per-line form field is read, and
its docstring states the rule this follows — *"`quantity` and `unit_price` are read for every
vendor, and ignored by the ones that do not offer the edit … an absent field costs nothing and
there is no branch here."* A pack size is one more such field. `form_key` (not the item id) is
mandatory: an order can carry the same ASIN twice, and keying by item id gave two lines one shared
control (PR #116 review) — FR-004 is that same rule.

`dataclasses.replace` on a frozen line is how the pack size reaches every reader at once. Note
`AmazonOrderLine` excludes `listing` and `listing_problem` from comparison/hashing because the line
may be put in a set; `replace` preserves that.

**Alternatives considered**: mutating the line (it is frozen, deliberately); passing the pack size
alongside the line through every call (threads one argument through five signatures for nothing).

---

## R3 — Making the conversion survive a browser with JavaScript disabled

**The problem.** The review's `quantity[<key>]` and `unit_price[<key>]` inputs mean *what gets
recorded*, and `_mcmaster_quantity` prefers a submitted value over the line's computed one
(`app/catalog_service.py:2155`). With JavaScript, changing the pack size rewrites those inputs and
everything agrees. Without it, the operator sets a pack size of 100, the quantity input still holds
the rendered `1`, the submitted `1` wins, and **the purchase records one item at the pack price —
silently, with no error and nothing on screen that looks wrong.** That is the exact failure this
feature exists to fix, reintroduced through the back door.

**Decision**: the server detects an override by recomputing what it rendered.

```
rendered_pack     = suggested pack size for this line   (pure function of the payload — R4)
rendered_quantity = line.packs x rendered_pack
rendered_price    = price_to_cents(line.pack_price / rendered_pack)

submitted_pack    = decision['pack_size'], or rendered_pack when the field is absent

quantity = submitted_quantity if submitted_quantity != rendered_quantity
           else line.packs x submitted_pack
```

and the same shape for the price. The rule in words: **a value the operator did not change follows
the pack size; a value they changed wins.**

**Rationale**:

- It is deterministic and needs no hidden form state. `rendered_pack` is a pure function of the
  payload, and the payload rides the form in `#order-payload` for every payload-carrying vendor —
  so the server can reconstruct precisely what it drew.
- It gives the *same* answer with JavaScript as without. With JS the submitted quantity is already
  `packs x submitted_pack`; if that differs from `rendered_quantity` the first branch returns it,
  and if it does not the second branch computes the identical number.
- The residual false negative — the operator changes the pack size and separately types the
  rendered value back by hand — resolves to the converted number, and US2's conversion marking
  shows plainly what was recorded. No data is lost either way.

**Alternatives considered**:

- *Hidden `derived_quantity[<key>]` fields.* Same effect, more form state, and a stale hidden
  field corrupts in the same way it is meant to prevent.
- *Trust the JavaScript.* Rejected: silent wrong data.
- *Make the derived values read-only.* Contradicts FR-007 and diverges from the McMaster review,
  where they are editable for a stated reason — the operator can see the box and the page, and
  this application can only see the page.
- *Re-frame the inputs as "packs" and "price per pack" for Amazon.* Clean in isolation, but it
  gives `quantity[<key>]` a different meaning per vendor, which is the divergence
  `app/services/order_vendors.py` exists to prevent.

---

## R4 — Where a suggested pack size comes from

**Decision**: parse it in Python from the line's own **title**, in `app/models.py`, as a pure
function. No change to `capture-agent.js`.

**Rationale**: Amazon's order-details page already carries the full product title on every line —
`AmazonOrderLine.title` — and that is where Amazon states pack counts. It follows that:

- **The suggestion works even when the listing was not read.** Feature 044's per-line listing fetch
  is sequential, one HTTP request per ASIN, and reports a problem for anything it cannot read
  (`capture-agent.js:readListing`). A suggestion that depended on it would be absent exactly when
  the capture was already degraded.
- **It is covered by the sub-second unit suite** rather than only by E2E, because it is a string
  function over a dataclass field.
- **The fallible half stays dumb.** The agent's job is reading a vendor's markup, which is not a
  contract; a regex over a title it already sends is not the agent's problem.

Where a line *did* get its listing read and `ListingCapture.pack_size` is set (FR-018 — McMaster's
reader already populates this at `capture-agent.js:1546`), that structured value wins over the
title parse. The order of preference is: operator's entry → listing's structured `pack_size` →
title parse → 1.

**The forms to recognise**, with a worked reason for the guard on each:

| Form | Example | Note |
|------|---------|------|
| `Pack of N` / `Packs of N` | `(Pack of 100)` | McMaster's reader already handles this shape |
| `N Pack` / `N-Pack` / `N Pk` | `5-Pack`, `10 Pack` | |
| `N Pcs` / `N pieces` / `N pc` / `N ct` / `N count` | `100 Pcs` | |
| `Set of N` / `Box of N` / `Bag of N` | `Set of 10` | |

**What must not be read** (FR-022, and the reason US3 is ranked below US2): a title is full of
numbers that are not pack counts. The parse only fires on a digit run **adjacent to one of the
words above**, never on a bare number — so `M3 x 12mm`, `12V`, `1/4-20`, `2-Pack of 50mm bolts`
(reads 2, correctly) and a part number embedded in the title do not produce a suggestion. A parse
that finds two different counts produces **none**, because there is no basis for picking one.

**Alternatives considered**:

- *Read it in the capture agent.* Rejected for the three reasons above; also an agent change means
  the operator must re-drag the bookmarklet, and `docs/user-manual.md` warns that a stale
  bookmarklet is already a support issue.
- *No suggestion at all.* That was option A at clarification and the author chose C.
- *Suggest from the listing only.* FR-018 keeps it, but as the narrower of two sources, not the
  only one.

---

## R5 — Which columns to add, and why not three

**Decision**: `purchases.pack_size` (`Integer`, nullable) and `purchases.pack_price`
(`Numeric(10, 2)`, nullable). No `packs` column.

**Rationale**: what reconciliation needs is the vendor's line — *N packs of S at $P*.

- `S` is `pack_size`. Not derivable from anything stored.
- `$P` is `pack_price`. **Not recoverable by arithmetic**: the feature rounds `$13.23 ÷ 100` to the
  stored `$0.13`, and `$0.13 × 100` is `$13.00`. The $0.23 is gone. This is the measurement that
  justifies the column against Principle I.
- `N` is `quantity / pack_size`, exact whenever the operator did not override the quantity. The
  order page renders it when it divides evenly and omits it when it does not, rather than storing
  a third number for a case that is already visible.

`Numeric(10, 2)` matches `unit_price` exactly, including the comment at `app/database.py` about
MariaDB rounding silently on write — `pack_price` goes through `_validate_price` for the same
reason.

**Alternatives considered**: a `packs` column (derivable); a single JSON `pack` column (opaque to
SQL and against the surrounding style); pack fields on `Product` (a pack is a property of one
purchase — the same screw is bought loose once and in a bag of 100 the next time).

---

## R6 — Which capture paths write the columns

**Decision**: all three, at the seam each already uses.

| Path | Seam | What it writes |
|------|------|----------------|
| Amazon order | `_amazon_line_fields` (`catalog_service.py:5163`) | the pack size in force for that line, and the line's stated per-listing price as `pack_price` — both only when the pack size exceeds 1 |
| McMaster order | `_mcmaster_line_fields` (`:5022`) | `line.pack_size` and `line.pack_price` straight off the line — the page already read them and they are currently thrown away |
| Single listing | `capture_order` (`:1317`) | the confirmation form's `pack_size` and `pack_price`, which the route currently drops on the floor |
| DigiKey order | — | nothing. FR-040: its quantities come from a service already in items |

`_apply_order_change` (`catalog_service.py:3069`) must write them too. It brings an
already-recorded purchase into line with what the order now says, and a re-capture that updated the
quantity but left a stale pack size would produce exactly the contradiction FR-033 forbids.

**A pack size of 1 stores NULL, never 1** (FR-031). "No pack was stated" and "a pack of one was
stated" must not be the same row, or every purchase in the catalog starts claiming to be a pack.

---

## R7 — What a stored pack means when the operator overrides, or edits later

**The tension.** FR-033 says a stored pack must never contradict the purchase's own quantity and
price. But the receive screen (`purchase_receive`, `app/product/routes.py:1100`) deliberately lets
the operator amend quantity and price on arrival — *"what arrived is allowed to differ from what
was ordered"* — and FR-007 lets them override the derived values at capture. Either makes
`quantity = packs × pack_size` stop holding.

**Decision**: `pack_size` and `pack_price` record **what the vendor charged**, not the arithmetic
that produced the row. They are never recomputed from, or reconciled against, the purchase's
quantity and price, and amending a purchase leaves them alone.

**Rationale**: the two are answering different questions, and the difference is information rather
than an inconsistency. *"I ordered a pack of 100 at $13.23 and 90 arrived"* is a true and useful
row; forcing consistency would either destroy the invoice record or refuse a legitimate receipt.
Everything the feature promises still holds — FR-029's restatement of the vendor's line is exactly
what these two fields are, and SC-007's reconciliation works because it reads the vendor's numbers,
not the catalog's.

**This is an interpretation of FR-033, and it should be read before implementation.** The
requirement as written suggests keeping the two in step or clearing the pack values; both were
rejected here. If the author intends the stricter reading, the place to change it is this decision,
before any code. What FR-033 does still bind is naming: the order page must label the pack fields
as the vendor's line and never as a derivation of the catalog's row — see
`contracts/purchase-pack-fields.md`.

**Alternatives considered**:

- *Clear the pack values on any later edit.* Loses the invoice record precisely when the row is
  most worth explaining.
- *Recompute `pack_price` from the new quantity.* Invents a price the vendor never charged.
- *Refuse an edit that breaks the arithmetic.* Blocks a legitimate short delivery.

---

## R8 — The browser half, on both pages

**Decision**: reuse `window.unitPriceFromPack` from `app/static/js/pack-unit-price.js` unchanged.
Extend that file to also derive `#quantity` on the capture page, and add
`app/static/js/order-line-pack.js` doing the same per row on the review.

**Rationale**: `pack-unit-price.js` is already exactly the right arithmetic — it parses digit
strings into `BigInt`, divides as integers, and assembles the decimal string back by hand,
specifically so that Principle III holds for a value merely passing through. Writing a second
price division in JavaScript would be the mistake that file exists to prevent. The quantity
derivation is `packs × pack_size`, integers, which needs no helper.

**Two behaviours are carried over verbatim from that file**, both of which are load-bearing and
are re-stated here so they are not lost in a rewrite:

- **Write the field only when the operator has typed in a pack field, never on load.** A re-render
  after a refused submission may be carrying a value the operator typed over the derived one, and
  writing on load discards it without a trace. The server supplies the initial derived value
  instead (`ListingCapture.unit_price_from_pack` does this today; `quantity_from_pack` joins it).
- **Nothing listens on the derived field itself.** An operator typing in Quantity or Unit Price is
  overruling the derivation, and a derivation that recomputed over the top of that would be
  useless.

A separate file for the review because `pack-unit-price.js` binds to single `id`s and the review
has one row per line; it is inert on every page lacking its hooks, the same way the existing file
is.

---

## R9 — Migration mechanics

**Decision**: one revision, `down_revision = 'd0817b3ea45c'` (the current head,
`add_purchases_vendor_order_id`), adding both columns as nullable, with a `downgrade` that drops
both. No data migration.

**Rationale**: Constitution V requires a reversible revision with MariaDB-valid ordering; two
nullable column adds and two drops have no dependency order to get wrong. Nullable is not a
convenience — FR-032 requires existing rows to be untouched, and FR-031 requires "no pack stated"
to remain distinguishable from a pack of 1.

**The trap to avoid**, already documented on `supplier_order_reference` in `app/database.py`: the
unit suite builds its schema with `create_all` and never runs Alembic, so a column that differs
between the ORM model and the revision passes `nox -s tests` and fails on the real database. The
two must be written to match — `Integer` and `Numeric(10, 2)`, both `nullable=True`, neither
indexed (nothing queries by them).

---

## R10 — Documentation, and the code comments that assert the old rule

**Decision**: correct all four sites, not only the manual.

FR-035 to FR-038 name `docs/user-manual.md`. Three code sites assert the same now-false rule and
will mislead the next reader if left:

| Site | What it says today |
|------|--------------------|
| `app/models.py`, `ListingCapture.pack_price` / `pack_size` | *"**Neither is recorded anywhere** … There is no pack size in the schema and this is not the beginning of one"* |
| `app/templates/product/capture.html` | *"**Neither pack field is recorded anywhere.** … There is no pack size in the schema and this is not the beginning of one"* |
| `app/templates/product/order_review.html`, the McMaster packs column | *"Not editable, and not stored: what is recorded is units and a unit price"* |

The manual's passages: `docs/user-manual.md:1228` *"When it is sold as a pack"* (the *"Neither pack
field is stored"* sentence, FR-035, and the Quantity description, FR-037), `:1643` and `:1808`
(McMaster now keeps the pack, FR-038), plus a new passage for the Amazon review's pack size
including that a suggested one is a guess the operator is answerable for (FR-036).

**One passage needs no rewrite and should be checked rather than edited**: the manual already says
*"Units in the Pack is not Quantity … Quantity is how many units the order brings in"*, which is
what the capture page will do **after** US4 and does not do now. That sentence becomes true.

`specs/` is a frozen record and is not edited — including
`specs/029-whole-order-capture/research.md` §5, whose finding this feature reverses. The reversal
is stated in this feature's spec Background instead.
