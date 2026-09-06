# Contract: the Stock card's count controls

**Feature**: 039-typed-quantity-entry

The product detail page is the UI contract here — the element ids are what the E2E tests bind to,
and several of them are already load-bearing for tests written for earlier features. This records
what exists, what is added, and what must not move.

## Existing elements — unchanged

`app/templates/product/detail.html`, inside `#stock-card`.

| Id | What it is | Depended on by |
|---|---|---|
| `#stock-card` | The card. Carries `data-product-id`. | `product-stock.js` bootstrap |
| `#stock-alerts` | Where refusals are written. | `showAlert()` |
| `#quantity-value` | The rendered count: a number, a "None on hand" badge, or "Not tracked". | `test_stock_age.py`, `test_touch_readiness.py`, `test_reorder_view.py` |
| `#quantity-age` | "counted <age>". Present only when counted. | `test_stock_age.py` |
| `#quantity-decrement` | `data-step="-1"`. Disabled when not counted. | `test_touch_readiness.py` |
| `#quantity-increment` | `data-step="1"`. Disabled when not counted. | `test_touch_readiness.py`, `test_reorder_view.py` |
| `#start-tracking-btn` | Present only when **not** counted. | `test_touch_readiness.py:70,138`, `test_reorder_view.py:193` |
| `#stop-tracking-btn` | Present only when counted. | `test_reorder_view.py:201` |
| `.stock-status-btn` | The low/out/clear flags. | `test_touch_readiness.py` |

**Both stepper buttons keep their present size, position and behavior.** `#start-tracking-btn`
keeps its id, its label, and its behavior when the new input is untouched: pressing it starts the
count at zero.

## New elements

| Id | Present when | What it is |
|---|---|---|
| `#quantity-input` | always | The typed count. Numeric, non-negative, whole. Pre-filled with the current count when the product is counted; empty otherwise. Disabled when not counted **only** in the sense that it feeds `#start-tracking-btn` rather than a Set button — it is never inert. |
| `#quantity-set-btn` | only when the product **is** counted | Commits the typed count. |
| `#received-total` | only when the product is **not** counted **and** the received sum is greater than zero | States the total quantity received for this product. |

### `#quantity-input`

- `type="text"` with `inputmode="numeric"` and `pattern="[0-9]*"` — **not** `type="number"`. The
  attributes configure the on-screen keypad; **they are not the validation** (see
  `contracts/quantity-commit.md`). A number input would report `value` as `''` for content it
  considers invalid, collapsing "abc" and an untouched field into one case — and those are the two
  FR-006 and FR-007 refuse with different messages (`research.md` §7a).
- When the product is counted, its value is the current count, so committing an unchanged field is
  a re-verification (FR-003) rather than an accident.
- When the product is not counted, it is empty and labelled as a starting count. Empty means zero
  (FR-004).

### `#quantity-set-btn`

- At least 44px tall, like every other control on this card.
- Absent — not merely disabled — when the product is not counted, because in that state
  `#start-tracking-btn` is the commit control and two commit buttons would be ambiguous (FR-011).

### `#received-total`

- Text. Not a control, not a link, and not a button that fills anything in.
- Absent entirely when the product is counted, or when the sum is zero, or when there are no
  received purchases. There is no "0 received" rendering.

## Layout obligations

- Every control on the card remains at least 44px tall on a touch viewport, including
  `#quantity-set-btn`. `tests/e2e/test_touch_readiness.py::test_the_stock_controls_are_large_enough_to_hit`
  is extended with the new selector rather than a new test being written.
- The card must not introduce horizontal scrolling on a phone viewport;
  `test_touch_readiness.py::test_the_page_does_not_scroll_sideways_on_a_phone` already guards this
  and must keep passing.
