# Contract: Scan Classification and Resolution

**Feature**: [../spec.md](../spec.md) | **Research**: [../research.md](../research.md) §4, §5

Covers FR-014, FR-015, FR-016, FR-017, FR-018, FR-019 and Story 1 / Story 4 acceptance.

The scan path is split into two pieces with different dependencies, and keeping them apart is the
point of this contract:

| | `app/utils/scan_router.classify()` | `CatalogService.resolve_scan()` |
|---|---|---|
| Purity | **Pure** — stdlib only, no Flask, no config, no DB | Needs a session |
| Answers | *What kind of thing was scanned?* | *Which product is it, and what should happen?* |
| Testable | Unit suite, no app context | Unit suite with `test_storage` fixture |

---

## 1. `classify(scan: str) -> ScanClassification`

**Guarantee: never raises on any `str`.** Not on empty, not on 4 KB of control characters, not on
a lone surrogate, not on a header with garbage behind it. An unparseable scan is answered with
`FREE_TEXT` carrying the raw text — because SC-008 requires that a scan never dead-ends, and an
exception is a dead end.

The one reachable exception is `TypeError` when `scan` is not a `str`. That is a broken caller,
not a property of the scan, and classifying it as free text would bury the bug in a search result.

**Return shape** (frozen dataclass in `app/models.py`):

```text
ScanClassification:
    kind        : ScanKind          # INTERNAL | ECIA | GTIN | FREE_TEXT
    value       : str               # normalized payload; raw scan when FREE_TEXT
    ecia_fields : Mapping[str, str] # empty unless kind is ECIA
    raw         : str               # always the scan exactly as captured
```

**Precedence — five rules, first match wins, rule 5 always matches:**

| # | Rule | → `kind` | → `value` |
|---|---|---|---|
| 1 | Matches `^WIT[0-9A-HJKMNP-TV-Z]{10}$` after whitespace strip | `INTERNAL` | the code |
| 2 | ISO/IEC 15434 format-06 envelope carrying ≥1 recognized data identifier | `ECIA` | `1P` value if present, else `P` |
| 3 | Normalizes to a check-digit-valid GTIN (raw length 8/12/13/14) | `GTIN` | the 14-digit key |
| 4 | *(no structural rule — vendor ids have no distinguishing shape)* | — | — |
| 5 | Anything else | `FREE_TEXT` | the raw scan |

Rule 1 outranks rule 3 by design: a label this shop printed must never resolve to somebody else's
trade item.

**Rule 2 can recognize its own shape and still decline.** A valid format-06 header wrapping
nothing readable — an empty message, or records in no identifier grammar — does **not** classify
`ECIA`. It falls through to `FREE_TEXT` with the raw scan. Consequence worth relying on:
`kind is ECIA` implies `ecia_fields` is non-empty.

**Envelope edge cases that must not be read as data** (research §4):

- A character glued directly onto the format indicator → the indicator was never delimited → not
  an envelope.
- A half-delivered trailer (`<data> EOT` with no `RS`) → the `EOT` terminates the transmission
  and is not part of the value.
- A leading separator before the header → not an envelope.

**ECIA field extraction** — exactly these seven MH10.8.2 identifiers, values **uncoerced strings**:

`P` (customer part no.), `1P` (manufacturer part no.), `Q` (quantity), `K` (customer order no.),
`1K` (supplier order no.), `9D` / `10D` (date `YYWW`).

Any other legal identifier (`1T`, `4L`, `30P`, …) is ignored silently. No date parsing, no
quantity coercion, no content validation — FR-017 requires every value stay editable, and
rejecting a malformed date loses data the operator can read off the label with their own eyes.

---

## 2. `CatalogService.resolve_scan(classification) -> ScanResolution`

```text
ScanResolution:
    outcome        : 'product' | 'create' | 'search'
    product        : Product | None      # set iff outcome == 'product'
    prefill        : Mapping[str, str]   # for outcome == 'create'
    classification : ScanClassification  # passed through
```

**Resolution order:**

1. `INTERNAL` / `GTIN` — look up `product_identifiers` by normalized `value`.
   Hit → `outcome='product'`. Miss → `outcome='create'` with the identifier pre-attached in
   `prefill` (**FR-018**: never an error, never a dead end).
2. `ECIA` — look up by the `1P` manufacturer part number. Hit → `outcome='product'`. Miss →
   `outcome='create'` with **every** extracted field in `prefill`, all editable (FR-017,
   Story 4 scenario 2).
3. `FREE_TEXT` — first try a vendor-identifier lookup (this is the impure rule 4 from research
   §5: an ASIN has no distinguishing shape, so it can only be found by looking). Hit →
   `outcome='product'`. Miss → `outcome='search'` carrying the raw scan (Story 4 scenario 3:
   "the raw scan is surfaced for manual handling rather than failing silently").

**During receiving** (FR-019), a resolution of `outcome='product'` offers *add a purchase to this
product*, not *create a new product*. Same resolution, different call site.

---

## 3. HTTP surface

`POST /api/scan` — body `{"scan": "<raw text>"}` → `200` with the `ScanResolution` serialized.

Never returns `4xx` for an unrecognized scan; "unrecognized" is `outcome='search'`, which is a
successful answer. `4xx` is reserved for a malformed *request* (missing/non-string `scan`).

---

## 4. Capture transport

The keyboard-wedge scanner types its payload and terminates with Enter. Capture follows the
pattern already in `app/static/js/inventory-add.js`: buffer rapid keystrokes, flush on Enter or
an inter-key timeout.

Two properties this feature adds, both because the payloads here are richer than a JA ID:

- **Control characters must survive.** `GS` (`0x1d`), `RS` (`0x1e`), and `EOT` (`0x04`) carry the
  ECIA field structure and the operator confirmed the deployed scanner emits them. A capture that
  strips non-printing characters destroys rule 2 — this is the single most breakable link in the
  scan path and needs a direct e2e test.
- **Scanning is available wherever a scan makes sense**, not only on a dedicated page, so Story 1
  works from wherever the operator already is.
