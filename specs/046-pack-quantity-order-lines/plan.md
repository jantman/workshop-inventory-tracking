# Implementation Plan: Packs Recorded as Units, and What a Pack Was Kept

**Branch**: `speckit/046-pack-quantity-order-lines` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/046-pack-quantity-order-lines/spec.md`

## Summary

An Amazon order line states packs and a price per pack, and the catalog records both as if they
were items. This makes every capture path agree on one rule — **quantity is items, price is per
item** — and stops discarding the pack that made the conversion necessary.

The approach is almost entirely *reuse of shapes that already exist*, which is why a five-story
feature stays small:

- `AmazonOrderLine` gains the pack shape `McMasterOrderLine` already has (`packs`, `pack_size`,
  `pack_price`, with `quantity`, `unit_price` and `price_rounds` as derived properties). The four
  properties are identical in both, so they move to one shared mixin rather than being written
  twice — the variation is measured across two shipped implementations, which is the bar
  `app/services/order_vendors.py` sets for an abstraction here.
- The pack size the operator states rides the form as `pack_size[<form_key>]`, read in the one
  place per-line decisions are already read (`_order_decisions`), and applied by
  `dataclasses.replace` on the frozen line before the existing `line_fields` runs. Nothing
  downstream of `line.quantity` changes — `has_change`, `price_rounds` and the review template
  all keep working, which is what makes FR-010 fall out instead of needing its own code.
- The pack size is **suggested from the line's own title in Python**, not by the capture agent.
  Amazon's order page already carries the full title (`Pack of 100`, `100 Pcs`, `5-Pack`), so the
  suggestion needs no listing read, no agent change, and is covered by the sub-second unit suite.
- The single-listing confirmation page gains a **Packs** input beside its existing pack fields,
  and its Quantity becomes derived the same way its Unit Price already is.
  `window.unitPriceFromPack` in `pack-unit-price.js` is exact `BigInt` arithmetic and is reused as
  is, on both pages.
- Two nullable columns on `purchases` — `pack_size`, `pack_price` — written by all three capture
  paths, read by the order page. One Alembic revision on head `d0817b3ea45c`.

The one genuinely new mechanism is **override detection** (research R3): the server recomputes
what it rendered and treats a quantity or price that still equals it as "not overridden", so a
pack size entered with JavaScript disabled still converts. Without it the feature silently
records the wrong number for a no-JS operator, which is the data-corruption class Principle I
explicitly does not license.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app factory), SQLAlchemy 2.0.x (legacy `Query` style),
Alembic, Jinja2 + Bootstrap 5.3.2, plain-global browser JavaScript (no build step)

**Storage**: MariaDB via PyMySQL; SQLite through the same `Storage` ABC for unit tests

**Testing**: `nox -s tests` (unit, network-blocked, sub-second), `nox -s e2e` (Playwright,
`-m "e2e and not screenshot"`, ~20 min warm — run detached)

**Target Platform**: Single-user Flask app on a home LAN

**Project Type**: Server-rendered web application

**Performance Goals**: None new. The title parse is a regex over a string already in memory; no
request gains I/O. Feature 044's order capture already takes 8–15 s per line for image retrieval
and this adds nothing to it.

**Constraints**: `Decimal` end to end for every price (Constitution III) — the browser half uses
the existing `BigInt` helper, never `parseFloat`; the schema change ships as one reversible
Alembic revision that matches the ORM model exactly, because the unit suite builds its schema
with `create_all` and never runs Alembic (Constitution V).

**Scale/Scope**: 2 new columns, 1 migration, ~5 templates, 2 JS files, 4 service seams. No new
route, no new endpoint, no new dependency.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 design — see bottom of this section.*

| Principle | Assessment |
|-----------|------------|
| **I. Simplicity First** | **Passes, with one item to justify.** No new abstraction beyond the shared pack mixin, which covers two shipped implementations (McMaster, Amazon) plus the listing page's fields, not a speculative third. No new route, dependency, config knob, or service. The pack suggestion is a regex in `app/models.py`, not an agent change. **The justified item** is the two new columns: storing the pack reverses a rule three code sites currently assert. It is the author's explicit decision C, it is recorded in Complexity Tracking below, and it buys a verifiable reconciliation (SC-007) that cannot be recomputed after rounding — `$0.13 × 100` is `$13.00`, not the `$13.23` that was charged. That is the measurement that makes the column earn its place. |
| **II. Layered Architecture Boundaries** | **Passes.** Domain arithmetic in `app/models.py` (dataclasses), the columns in `app/database.py`, the decision plumbing in `app/catalog_service.py`, form reading in `app/product/routes.py`. No ORM query moves into a route, and `_order_decisions` stays the single place a per-line form field is read. |
| **III. Exact Numerics** | **The principle most at risk here, and the one the design is shaped around.** Every division is `Decimal` through the existing `price_to_cents`, on the server. The browser half reuses `window.unitPriceFromPack`, which parses digit strings to `BigInt` and formats back by string assembly — no `parseFloat`, no `toFixed`. A pack price crossing JSON stays a string, as `ListingCapture.price` already does. `pack_price` is `Numeric(10, 2)`, matching `unit_price`. |
| **IV. Test Discipline** | **Passes.** Unit tests for the title parse, the pack arithmetic, override detection and the three `line_fields`; E2E for the two pages. Every E2E wait is on an observable state — the derived quantity's value — never a duration. Template and JS changes to `app/templates/**` and `app/static/js/**` trigger the screenshot gate (`nox -s screenshots`), which must be regenerated and committed. |
| **V. MariaDB Is the Source of Truth** | **Applies directly.** One Alembic revision on head `d0817b3ea45c`, with an exercised `downgrade` dropping both columns. The ORM model and the revision must agree exactly or the drift passes `nox -s tests` (SQLite `create_all`) and fails on MariaDB. No backfill: FR-032 requires existing rows are untouched, and both columns are nullable so the upgrade rewrites nothing. |
| **VI. Item Lifecycle** | **Not engaged.** This feature touches products and purchases; it does not touch `InventoryItem`, JA IDs, shortening or active-row history. |
| **Operating context** | No auth, no new input-sanitization layer. Pack-size validation exists because a bad pack size corrupts the inventory, not because input is hostile. |

### Post-Phase-1 re-check

Re-evaluated after `data-model.md` and the contracts were written. No gate moved. Two things the
design deliberately did **not** do, both of which would have failed Principle I:

- **No `packs` column.** Packs ordered is `quantity / pack_size` in every case the operator did
  not override, and the order page says so rather than storing a third number.
- **No pack fields on `Product`.** A pack is a property of one purchase — the same screw is
  bought loose once and in a bag of 100 the next time (spec, *Key Entities*).

## Project Structure

### Documentation (this feature)

```text
specs/046-pack-quantity-order-lines/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── pack-conversion.md      # The arithmetic and override rules, both pages
│   └── purchase-pack-fields.md # What the two columns mean and who writes them
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── models.py                        # PackLine mixin; AmazonOrderLine gains the pack shape;
│                                    #   pack_size_from_title(); ListingCapture.quantity_from_pack
├── database.py                      # Purchase.pack_size, Purchase.pack_price
├── catalog_service.py               # _pack_size_for_line(), override detection,
│                                    #   _amazon_line_fields / _mcmaster_line_fields retention,
│                                    #   capture_order(packs=, pack_size=, pack_price=),
│                                    #   _apply_order_change writes pack fields
├── product/routes.py                # _order_decisions reads pack_size[<key>];
│                                    #   product_capture forwards the pack fields
├── templates/product/
│   ├── order_review.html            # pack-size column for Amazon; conversion marking
│   ├── capture.html                 # Packs input; corrected help text
│   ├── order.html                   # both views on a captured order's lines
│   └── receive.html                 # pack context where a purchase carries one
└── static/js/
    ├── pack-unit-price.js           # also derives #quantity from #packs x #pack_size
    └── order-line-pack.js           # new: the same derivation per review row

migrations/versions/
└── <rev>_add_purchases_pack_size_and_pack_price.py   # down_revision = 'd0817b3ea45c'

tests/
├── unit/
│   ├── test_pack_conversion.py      # new: title parse, arithmetic, override detection
│   ├── test_amazon_capture.py       # Amazon line_fields with a pack
│   ├── test_mcmaster_capture.py     # McMaster now retains its pack
│   └── test_capture.py              # listing capture: derived quantity, stored pack
└── e2e/
    ├── test_amazon_order.py         # pack size on the review, end to end
    └── test_product_page_capture.py # the listing page's derived quantity

docs/user-manual.md                  # FR-035 to FR-038
```

**Structure Decision**: No new structure. Every change lands in a file that already owns that
concern — the four-layer split in Principle II is already where this feature's pieces belong, and
the one new file (`order-line-pack.js`) exists only because `pack-unit-price.js` binds to single
`id`s and the review has one row per line.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| **Two new `purchases` columns**, reversing the standing rule that pack values are not stored (asserted in `order_review.html`, `capture.html`, `ListingCapture` and the user manual) | The author's decision C. A captured order must reconcile against the vendor's invoice (SC-007), and a pack size may now be a *guess* read from a title (US3) that has to be auditable after the fact | **Recomputing the pack price from the stored unit price is arithmetically impossible**: `$13.23 ÷ 100` stores `$0.13`, and `$0.13 × 100` is `$13.00`. The $0.23 is destroyed by the rounding the feature deliberately performs. Nothing short of storing it recovers the invoice line |
| **A shared pack mixin** in `app/models.py` rather than the same four properties on two dataclasses | Two shipped implementations already, both of which must stay in step — divergence between the McMaster and DigiKey copies is the documented reason `order_vendors.py` exists | Duplicating the arithmetic is what produced the defects PR #123 fixed twice. One copy is ~25 lines against two copies of ~25 lines that must never drift |
| **Override detection** (research R3) — comparing a submitted value against the value the server rendered | A pack size entered with JavaScript disabled otherwise records a silently wrong quantity. Principle I never licenses a data-integrity failure | Hidden `derived_*` fields per line: more form state, and a stale hidden field is a corruption of the same kind. Trusting the JS alone: fails silently. Making the derived values read-only: contradicts FR-007 and diverges from the McMaster review |
