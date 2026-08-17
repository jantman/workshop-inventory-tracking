# Contracts: Unit Price From a Multi-Pack

Two surfaces, both internal to the application: the capture form's fields, and the one
JavaScript function that holds the arithmetic. No HTTP API is added or changed by this feature.

## The capture form (`POST /products/capture`)

Unchanged in what it accepts and what it records. Two new fields ride along and are ignored.

| Field | Direction | Consumed by `product_capture`? | Notes |
|-------|-----------|-------------------------------|-------|
| `pack_price` | submitted, re-emitted | **No** | Present so the derivation survives a re-render (FR-012). Never passed to `capture_order`. |
| `pack_size` | submitted, re-emitted | **No** | As above. |
| `unit_price` | submitted, recorded | Yes, as today | The derived-or-overridden value. Same string → `_validate_price` → `Decimal` path as today. |

The re-emission is not new code: `product_capture` already renders with
`form_data=request.form` on the `CaptureDecisionRequired` and `ValidationError` paths, and with
`form_data=request.args` on first load, so any field the template reads out of `form_data`
survives a question. The contract to preserve is therefore a *template* contract — both fields
must read their value from `form_data` — and a route contract of omission: neither field may
ever be forwarded to `capture_order`.

## `unitPriceFromPack(paid, packSize)`

Defined in `app/static/js/pack-unit-price.js`, exposed as `window.unitPriceFromPack`. Pure: no
DOM access, no side effects. The exposure is deliberate — it is how the rounding table is
tested (`page.evaluate`), following `window.readLabelCount` in `label-count.js`.

### Signature

```text
unitPriceFromPack(paid: string, packSize: string)
  → {ok: true,  value: string, exact: boolean}
  | {ok: false, error: string, field: 'pack_price' | 'pack_size'}
```

`value` is always a decimal string, never a number. `exact` is `true` when
`value × packSize === paid` with no remainder discarded.

### Rules

1. **Trim both.** An empty `paid` is `ok: false` on `pack_price`; there is nothing to divide.
2. **`paid` must match `^\d+(\.\d+)?$`.** Anything else — a currency symbol, a thousands
   separator, a sign, a second point — is `ok: false` on `pack_price`. This is the same
   strictness `_validate_price` applies server-side, deliberately: a value it would reject must
   not be turned into a unit price here.
3. **`packSize` empty, or `1`** → `{ok: true, value: paid, exact: true}`. The amount paid is
   returned **verbatim**, unparsed and unrounded, so a single-unit capture is byte-identical to
   today's (FR-010, FR-015).
4. **`packSize` must otherwise match `^\d+$` and exceed zero.** `0`, `-1`, `2.5`, `three` are
   each `ok: false` on `pack_size`.
5. **Otherwise divide, half-up, at two decimal places.** With `s` the count of fractional
   digits in `paid` and `N` its digits as a `BigInt`:

   ```text
   A = N * 100n
   B = BigInt(packSize) * 10n ** BigInt(s)
   q = A / B
   r = A % B
   if (2n * r >= B) q = q + 1n
   value = `${q / 100n}.${String(q % 100n).padStart(2, '0')}`
   exact = (r === 0n)
   ```

   Integers throughout. No `Number`, no `parseFloat`, no `toFixed` — Principle III holds by
   construction rather than by care.

6. **Both operands are non-negative** by rules 2 and 4, so half-up and half-away-from-zero are
   the same rule and no sign handling exists.

### The table this must satisfy

| `paid` | `packSize` | `value` | `exact` |
|--------|-----------|---------|---------|
| `29.97` | `3` | `9.99` | `true` |
| `17.99` | `3` | `6.00` | `false` |
| `0.01` | `3` | `0.00` | `false` |
| `10.00` | `4` | `2.50` | `true` |
| `17.995` | `2` | `9.00` | `false` |
| `1249.50` | `1` | `1249.50` | `true` |
| `1249.50` | *(empty)* | `1249.50` | `true` |
| `9` | `2` | `4.50` | `true` |

Rejections: `1,249.50` / `$5` / `` (empty) / `5.` → `pack_price`; `0` / `-1` / `2.5` /
`three` → `pack_size`.

## DOM contract on `/products/capture`

| Id | Kind | Role |
|----|------|------|
| `#pack_price` | text input, `inputmode="decimal"` | The amount paid. Prefilled from `listing.price`. |
| `#pack_size` | number input, `min="1"`, `step="1"` | Units in the pack. Defaults to `1`. |
| `#unit_price` | text input (existing) | Written on recompute; freely editable; recorded. |
| `#unit-price-inexact` | inline text, hidden by default | Shown when `exact` is `false` (FR-008), hidden when `true` (FR-009). |
| `#unit-price-error` | inline text, hidden by default | Shown when `ok` is `false`, naming the unusable field (FR-011). |

Behavioral contract: `input` on `#pack_price` or `#pack_size` recomputes, writes `#unit_price`
on success, and leaves it untouched on failure. `input` on `#unit_price` triggers nothing — an
override is an override. On page load the two notes are evaluated and `#unit_price` is not
written.
