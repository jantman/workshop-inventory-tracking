# Contract: Label Printing Interfaces

**Feature**: [../spec.md](../spec.md) | **Date**: 2026-08-11

Three contracts change. The HTTP endpoint is the one all four dialogs share, so it is where the
label count is actually enforced; the service signature and the browser helper are the seams either
side of it.

---

## 1. `POST /api/labels/print`

Defined at `app/main/routes.py:1774`. One request prints one item's labels.

### Request

```json
{
  "ja_id": "JA123456",
  "label_type": "Sato 1x2",
  "label_count": 3
}
```

| Field | Type | Required | Default | Change |
|-------|------|----------|---------|--------|
| `ja_id` | string | yes | — | unchanged |
| `label_type` | string | yes | — | unchanged |
| `label_count` | integer | **no** | `1` | **new** |

`label_count` is optional and defaults to `1`. A request that omits it behaves exactly as it does
today — this is what lets the four dialogs be converted one at a time without a flag day, and what
keeps the existing unit tests valid (FR-010).

### Success — `200`

```json
{
  "success": true,
  "message": "3 labels printed successfully for JA123456",
  "ja_id": "JA123456",
  "label_type": "Sato 1x2",
  "label_count": 3
}
```

`label_count` is echoed so a caller can confirm what was acted on rather than what it believed it
sent. At a count of `1` the message keeps today's exact wording — `Label printed successfully for
JA123456` — per the Edge Cases bullet on indistinguishability.

### Failure — `400`

Existing validation is unchanged and runs first: missing `ja_id`, missing `label_type`, malformed JA
ID, unknown label type. The new rules run after those.

```json
{ "success": false, "error": "label_count must be between 1 and 99" }
```

| Condition | Error |
|-----------|-------|
| not a whole number — `2.5`, `"3"`, `null`, `[]`, `true` | `label_count must be a whole number` |
| out of range — `0`, negative, `100`+ | `label_count must be between 1 and 99` |

`true` must be rejected explicitly: `isinstance(True, int)` is `True` in Python, so a plain int check
would accept a boolean and print one label for it.

**No partial success.** An item's copies are one `lp` job with one exit code, so a failure is
reported for the whole request (`500`, existing behavior) and the caller counts `0` labels for that
item. See Decision 6 in [../research.md](../research.md).

### Compatibility

| Caller | Before | After |
|--------|--------|-------|
| Single-item dialog (Add, Edit) | `{ja_id, label_type}` → 1 label | `{ja_id, label_type, label_count}` |
| List bulk dialog | `{ja_id, label_type}` per item → 1 label each | `+ label_count` per item |
| Post-bulk-Add dialog | `{ja_id, label_size}` → **400 every time** | `{ja_id, label_type, label_count}` |
| Existing unit tests posting two fields | 1 label | unchanged — still 1 label |

The third row is FR-012: that dialog has never satisfied this contract. It sends a `label_size` the
endpoint has no field for, and omits the `label_type` the endpoint requires.

---

## 2. `app/services/label_printer.py`

```python
def print_label_for_ja_id(ja_id: str, label_type: str, label_count: int = 1) -> None: ...

def generate_and_print_label(
    barcode_value: str,
    lp_options: str,
    maxlen_inches: float,
    lp_width_px: int,
    fixed_len_px: int,
    flag_mode: bool = False,
    lp_dpi: int = 305,
    label_count: int = 1,          # renamed from num_copies
) -> None: ...
```

- `print_label_for_ja_id` gains a defaulted third parameter and forwards it.
- `generate_and_print_label`'s `num_copies` is **renamed** to `label_count` so the feature uses one
  word end to end. Its body is otherwise unchanged: it already builds `[image] * n` and hands the
  list to one `LpPrinter.print_images()` call. The rename touches five lines, all within this file,
  and no test refers to the old name.
- The test-mode short-circuit at `label_printer.py:92` already logs the count. It stays first in the
  function — **no test may reach `LpPrinter.print_images()`.**
- `app/services/product_label.py` keeps its own `num_copies`. Product labels are out of scope.

**Behavioral contract**: a call with `label_count=n` results in exactly one `print_images()` call
receiving a list of `n` images. That is the unit-testable statement of "n labels".

---

## 3. `window.readLabelCount(inputId)` — `app/static/js/label-count.js` (new)

The single owner of the bounds and the error wording across all four dialogs, which is what SC-007
requires.

```js
window.readLabelCount('list-bulk-label-count')
// -> { ok: true,  value: 3 }
// -> { ok: false, error: 'Label count must be a whole number between 1 and 99' }
```

| Input value | Result |
|-------------|--------|
| `"1"` … `"99"` | `{ok: true, value: <int>}` |
| `""`, `"0"`, `"-2"`, `"100"`, `"2.5"`, `"abc"` | `{ok: false, error: ...}` |
| element not found | `{ok: true, value: 1}` — a dialog that has no count input yet still prints one label |

A plain global rather than an ES module: `inventory-list.js` is loaded with `type="module"` while
`inventory-add.js` and `label-printing-modal.js` are plain scripts, and a global is readable from
all three without converting files this feature has no other reason to touch.

Callers render `error` into their existing alert region and do not send the request. They must not
rely on browser constraint validation — every print button is `type="button"`, so it never fires,
and a validation bubble is not observable from an e2e test.

### Markup contract

Each dialog carries the same input, differing only in `id` and label text:

```html
<input type="number" class="form-control" id="{prefix}-label-count"
       min="1" max="99" step="1" value="1">
```

| Dialog | Input id | Label text |
|--------|----------|-----------|
| Single-item (Add, Edit) | `label-count` | Number of labels |
| List bulk | `list-bulk-label-count` | Labels per item |
| Post-bulk-Add | `bulk-label-count` | Labels per item |

`min`/`max`/`step` are affordance — the spinner and the mobile numeric keypad. The gate is the
helper. The two bulk dialogs say **"Labels per item"** rather than "Quantity" because the user has
just typed an item quantity into the form behind them (FR-014, SC-008).

**Reset**: `value="1"` in the markup covers the first open. Each dialog must additionally set the
input back to `1` when it is shown, because a Bootstrap modal is reused rather than recreated
(FR-002).

### Also on the post-bulk-Add dialog (FR-012)

`add.html`'s `<select id="bulk-label-size">` with its three invented sizes is replaced by
`<select id="bulk-label-type">`, populated from `GET /api/labels/types` like the other three dialogs,
with the same `Select label type...` placeholder and the same "Print All" disabled-until-selected
behavior the list dialog has.
