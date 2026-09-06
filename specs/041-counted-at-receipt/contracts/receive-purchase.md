# Contract: Receiving a Purchase, With and Without the Count Assertion

**Feature**: `specs/041-counted-at-receipt` | **Date**: 2026-09-06

Two interfaces change, both additively, and neither breaks an existing caller.

---

## 1. Service: `CatalogService.receive_purchase`

**File**: `app/catalog_service.py`

### Signature

```python
def receive_purchase(
    self,
    purchase_id: int,
    received_date: Optional[datetime] = None,
    quantity: Optional[int] = None,
    unit_price: Optional[str] = None,
    notes: Optional[str] = None,
    description: Optional[str] = None,
    counted: bool = False,          # NEW
) -> Purchase:
```

`counted` is appended last with a `False` default. **This is a compatible extension**: every
existing call site — one route and roughly two dozen unit tests — keeps its exact current
behaviour without being edited, which is what makes those tests a regression net for spec Story
2 rather than a set of files to update.

### Parameter

| Name | Type | Default | Meaning |
|---|---|---|---|
| `counted` | `bool` | `False` | The operator asserts they have counted what is on the shelf, and that the count this receipt arrives at is that number. |

`counted` asserts an *act*, not a value. It carries no number, and the method does not ask for
one.

### Behaviour

Unchanged in every respect except one conditional write:

```
if counted and product is not None and product.quantity is not None:
    product.quantity_updated_at = utc_now()
```

Three properties of that condition are contractual:

1. **`utc_now()`, not the receipt's `received_date`.** The count age is a recorded instant and
   the received date is a day the operator may have backdated on this very form. Spec FR-008;
   `app/utils/clock.py` is the authority.
2. **Guarded by `product.quantity is not None`.** Receiving never begins tracking a count, and
   an untracked product gains no age (spec FR-006, echoing 008 FR-009).
3. **Not guarded by `purchase.quantity`, and not guarded by `already_received`.** The increment
   requires both; this write requires neither. The operator either looked at the shelf or did
   not, and a delivery with no recorded quantity, or a purchase already marked received, does
   not change that (spec FR-010, and the no-quantity edge case).

Everything else holds exactly as before: the received date is set only on a first receipt, the
count increment happens only on a first receipt and only when the purchase has a quantity, the
description amendment applies on every submission, the manual flag and its date are cleared on a
first receipt, and validation of quantity, price and description happens before the session
opens so a refusal writes nothing.

### Contract tests

| # | Given | When | Then |
|---|---|---|---|
| C1 | tracked count `4`, age 100 days old; outstanding purchase for 100 | `receive_purchase(id, counted=True)` | `quantity == 104` and `quantity_updated_at` is within seconds of now |
| C2 | same | `receive_purchase(id)` | `quantity == 104` and `quantity_updated_at` is the seeded 100-day-old value, unchanged |
| C3 | count not tracked (`quantity is None`) | `receive_purchase(id, counted=True)` | `quantity is None` and `quantity_updated_at is None` |
| C4 | tracked count `4`, age old; purchase with `quantity is None` | `receive_purchase(id, counted=True)` | `quantity == 4` and `quantity_updated_at` is now |
| C5 | tracked count, already received | `receive_purchase(id, counted=True)` | `received_date` unchanged, `quantity` unchanged, `quantity_updated_at` is now |
| C6 | tracked count `0`, age old | `receive_purchase(id, counted=True)` with a receipt for 10 | `quantity == 10` and `quantity_updated_at` is now |
| C7 | tracked count, manual flag `low` set | `receive_purchase(id, counted=True)` | flag and `stock_status_updated_at` both cleared, exactly as with `counted=False` |
| C8 | tracked count, age old | `receive_purchase(id, counted=True, unit_price='not a price')` | `ValidationError`; count, age and received date all unchanged |

---

## 2. Form: `POST /products/purchases/<purchase_id>/receive`

**File**: `app/product/routes.py` (`product.purchase_receive`),
`app/templates/product/receive.html`

### Request

One new optional field on a form that is otherwise unchanged:

| Field | Type | Present when | Parsed as |
|---|---|---|---|
| `counted` | checkbox | the operator ticked it | `request.form.get('counted') == 'on'` |

An unchecked HTML checkbox posts nothing, so absence is the default and no hidden companion
field is used. The parse matches `identifier_override` in the same file.

Existing fields — `csrf_token`, `description`, `received_date`, `quantity`, `unit_price`,
`notes` — are unchanged in name, meaning and handling.

### Response

Unchanged. Success flashes `Received.` and redirects to the product detail page; a
`ValidationError` flashes the message and re-renders `product/receive.html` with
`form_data=request.form`.

### Rendered control

```html
<div class="form-check">
  <input class="form-check-input" type="checkbox" id="counted" name="counted"
         {% if form_data and form_data.get('counted') %}checked{% endif %}>
  <label class="form-check-label" for="counted">…</label>
</div>
```

Contractual properties of the rendering:

| # | Condition | Required rendering |
|---|---|---|
| R1 | `product.quantity is none` | the control is **absent** (spec FR-007) |
| R2 | `product.quantity` is `0` | the control is **present** — zero is a counted number, not an absence (spec Story 3 scenario 2) |
| R3 | GET, any tracked product | present and **not** checked (spec FR-002) |
| R4 | POST refused after the operator ticked it | present and **checked** (spec FR-009) |
| R5 | POST refused after the operator left it | present and **not** checked |

The label states the operator's claim — that they counted what is on the shelf — and not a
system action about a date (spec FR-012). The element id `counted` is what the E2E test selects
on.

### Already-received banner

`#already-received` currently reads: "…Submitting again leaves that date alone, and does not
touch the stock count a second time — but the description, quantity, price and notes below are
still applied." The count assertion joins that second list, because it does apply on a second
submission (spec FR-010) and the banner is the only place that tells the operator what does.
