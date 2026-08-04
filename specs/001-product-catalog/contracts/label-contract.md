# Contract: Label Composition and Printing

**Feature**: [../spec.md](../spec.md) | **Research**: [../research.md](../research.md) §1, §2

Covers FR-011, FR-012, FR-013, FR-037 and Story 2 acceptance.

---

## 1. The constraint being honoured

The spec fences off *"new printer control language, driver, or printing path… native printer
command languages such as SBPL are explicitly out of scope; the existing raster-image printing
path is used."*

The existing raster path, read from the codebase, is:

```text
PNG bytes (BytesIO)  →  LpPrinter(lp_options).print_images([...])  →  temp .png  →  `lp` + options
```

This contract changes **what PNG is composed** and nothing else. `lp_options`, the `LABEL_TYPES`
dictionary, `LpPrinter`, and the `lp` invocation are all untouched.

**Why composition is necessary at all**: `BarcodeLabelGenerator(value=…, show_text=True)` draws
the barcode and, as text, `self.value` — the barcode's own content. There is no parameter for a
caption or a second line. FR-011 requires description **and** provenance **and** code on one
label, so it cannot be met by calling the existing generator.

---

## 2. `compose_product_label(...) -> BytesIO`

**Inputs**: the product's `description`, the provenance line, the internal code, and the
`LABEL_TYPES` entry for the chosen stock (`lp_width_px`, `fixed_len_px`, `maxlen_inches`,
`lp_dpi`, `flag_mode`).

**Output**: a PNG `BytesIO` sized exactly as the existing generator's output for that stock, so
`LpPrinter` receives what it already expects.

**Layout, top to bottom:**

| Band | Content | Rules |
|---|---|---|
| Description | `products.description` | Wrapped to the label width, font shrunk to fit; truncated with an ellipsis only when it cannot fit at the minimum legible size. |
| Provenance | Vendor + order date + price of the most recent purchase | Single line; omitted entirely when the product has no purchases (a hand-entered product is still labelable — FR-001). |
| Code | Code128 symbol **and** the code as text | Both, always — this is FR-012, not a display option. |

**FR-012 is a durability requirement, not a formatting preference.** The spec's environmental
assumptions state that direct-thermal labels degrade in a workshop, and the mitigation is *"dual
scannable/human-readable encoding and on-demand reprinting"*. The human-readable code is what
makes a label with a scuffed barcode still usable, so it is never suppressed to gain space —
the description gets truncated first.

---

## 3. Label stocks (FR-037)

All six existing entries in `LABEL_TYPES` are offered: `Sato 1x2`, `Sato 1x2 Flag`, `Sato 2x4`,
`Sato 2x4 Flag`, `Sato 4x6`, `Sato 4x6 Flag`. None is reserved, and **no new stock is defined** —
`LABEL_TYPES` stays the single source of truth, as the original label-printing feature required.

On the narrowest stock (`Sato 1x2`, 2.0 in) the description band will often truncate. That is the
expected trade-off and the reason the operator picks the stock per print.

---

## 4. Reprint (FR-013)

Reprinting composes from the stored record. There is **no cached label image and no stored
rendering** — the record is the source of truth, so a reprint after an edited description
correctly reflects the edit.

Consequence: a reprint is byte-identical to the original *only while the record is unchanged*.
Story 2 scenario 3 ("the label is reproduced without re-entering any information") is about not
re-entering data, and that holds unconditionally.

---

## 5. HTTP surface

- `GET /api/labels/types` — **already exists**; reused unchanged.
- `POST /api/products/<id>/label` — body `{"label_type": "<key from LABEL_TYPES>"}`.
  Invalid key → `400` listing the valid keys, matching the existing endpoint's behaviour.

---

## 6. Testing

The existing test seam is preserved and is non-negotiable: `generate_and_print_label()`
short-circuits when `current_app.config['TESTING']` or `DISABLE_LABEL_PRINTING` is set, logging
the arguments it would have used. **No test may ever reach `LpPrinter.print_images()`** — it
drives real hardware.

- **Unit**: composition is asserted directly — output dimensions match the stock, the description
  text is present, the code is present in both forms, a long description truncates rather than
  overflowing, a product with no purchases composes without a provenance band.
- **E2E**: the print request reaches the short-circuit with the expected label type and product,
  and the reprint path produces the same request without re-entry.
