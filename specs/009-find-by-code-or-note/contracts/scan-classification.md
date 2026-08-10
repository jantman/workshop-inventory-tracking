# Contract: scan classification

One new pure function, and one new rule in an existing one. No type changes anywhere: `ScanKind`, `ScanClassification`, `ScanResolution`, `CatalogService.resolve_scan` and `POST /api/scan` are all read-only for this feature.

---

## `app/utils/gs1.py` — new module

Pure: standard library only. No Flask, no database, no config — the same contract `gtin.py`, `ecia.py` and `internal_id.py` carry.

```python
_TRADE_ITEM_AI = '01'
_TRADE_ITEM_LENGTH = 14

def decode_trade_item_number(raw: str) -> Optional[str]
```

Returns the 14 digits carried by a GS1 element string opening with application identifier `01`, **verbatim and unjudged**, or `None`.

**Never raises. On anything.** Including a non-`str`, which returns `None` rather than a `TypeError` — unlike `scan_router.classify`, where a non-`str` is a broken caller worth surfacing. Here the function is a shape test that a caller uses in a boolean position; a raise would be noise.

### Recognition, in order

1. Non-`str` → `None`.
2. `raw.strip()`.
3. Remove at most one AIM symbology identifier: `]` + one ASCII letter + one ASCII digit.
4. Remove at most one leading FNC1 (`\x1d`). **Not redundant with step 2's strip** — `'\x1d'.isspace()` is `True`, so a bare leading GS is already gone, but a GS that followed an AIM identifier is interior at the time `strip()` runs and survives it.
5. Require the remainder to open with `01` followed by exactly 14 **ASCII** digits. (`str.isdigit()` accepts Arabic-Indic digits; `gtin.py` already has `_ASCII_DIGITS` for this reason.)
6. Require what follows to be **end of input, or another element string** — AI `01` is predefined-length, so the next element string abuts the field or is separated from it. Concretely: consume at most one FNC1, then require at least **two** ASCII digits, because every AI is 2–4 digits.

   **Corrected in review (PR #82).** This step first read "end of input, a GS, or an ASCII digit", which admitted three families of free text as trade item numbers — `EL + '1 RES 10K'`, `EL + GS + 'RES 10K'`, and `EL + GS + GS + '10LOT42'` — each resolving to a real product's key. `_MIN_AI_LENGTH = 2` is the operative constant; the separator is a delimiter and not an exemption; exactly one separator is consumed, asymmetric with the leading side where `strip()` absorbs any number.
7. Return the 14 digits.

### It does not validate — and that is the contract

| Call | Returns | Why |
|---|---|---|
| `decode_trade_item_number('0109506000134352')` | `'09506000134352'` | valid, extracted |
| `decode_trade_item_number('0109506000134353')` | `'09506000134353'` | **bad check digit, still returned** — validity is `gtin.py`'s alone |
| `decode_trade_item_number('0100000000000000')` | `'00000000000000'` | **the no-read value, still returned** — refused downstream |

A test asserting these three rows is the one that pins the seam. If extraction ever starts judging, `gtin.py` stops being the single source of truth for what a trade item number is.

### Full input matrix

`EL = '0109506000134352'` throughout.

| Input | Returns |
|---|---|
| `EL` | `'09506000134352'` |
| `'\x1d' + EL` | `'09506000134352'` |
| `']d1' + EL`, `']C1' + EL`, `']d2' + EL` | `'09506000134352'` |
| `']C1\x1d' + EL` | `'09506000134352'` |
| `' ' + EL + ' '`, `EL + '\r\n'`, `EL + '\x1d'`, `EL + '\x1e'` | `'09506000134352'` |
| `EL + '17260101'`, `EL + '10LOT42'` | `'09506000134352'` — abutted element string |
| `EL + '\x1d10LOT42'` | `'09506000134352'` — GS-separated |
| `'01' + '00000000012348'` | `'00000000012348'` |
| `EL + 'ABC'`, `EL + ' RES 10K'` | `None` — tail is not an element string |
| `EL + '1ABC'`, `EL + '1 RES 10K'`, `EL + '1'` | `None` — one digit is not an AI |
| `EL + '\x1dRES 10K'` | `None` — a separator delimits an element string, it does not excuse one |
| `EL + '\x1d\x1d10LOT42'` | `None` — one separator is consumed; the second opens the tail |
| `EL + '\x04'` | `None` — EOT is not whitespace, not a GS, not a digit |
| `'010950600013435'` (13 digits), `'01' + '0'*14 + 'X'` | `None` |
| `'01' + 14 Arabic-Indic digits` | `None` |
| `'\x1d21SN0001'`, `'\x1d17260101'`, `'\x1d00123456789012345675'` | `None` — a different AI |
| `'\x1d10LOT42\x1d' + EL` | `None` — AI 01 not in first position (FR-007) |
| `''`, `'01'`, `'\x1d'`, `']d2'` | `None` |
| `None`, `123`, `b'01…'`, 4096 control characters | `None`, no raise |

---

## `app/utils/scan_router.py` — one rule inserted

`classify(scan: str) -> ScanClassification`. Signature, return type and raising behaviour all unchanged: still `TypeError` on a non-`str`, still never raises on any `str`, still returns `raw` verbatim.

**Precedence becomes five rules**, first match wins, the last always matches:

| # | Rule | Delegates to |
|---|---|---|
| 1 | this shop's own printed code | `internal_id.is_internal_id` |
| 2 | ISO/IEC 15434 format-06 envelope carrying a recognized field | `ecia.parse` |
| 3 | **GS1 element string opening with AI `01`** → its digits become what rule 4 judges | **`gs1.decode_trade_item_number`** |
| 4 | a check-digit-valid trade item number → `GTIN` | `gtin.normalize_and_validate` |
| 5 | anything else → `FREE_TEXT` | — |

### Rules 3 and 4 are one arm

```python
trade_item = gs1.decode_trade_item_number(scan)
gtin_key = gtin.normalize_and_validate(scan if trade_item is None else trade_item)
if gtin_key is not None:
    return ScanClassification(kind=ScanKind.GTIN, value=gtin_key, raw=scan)
```

**Exactly one `normalize_and_validate` call and exactly one `kind=GTIN` construction in the module.** This is a reviewable property, not a style preference: it is what makes "a structured scan is indistinguishable from a bare one" (FR-002) true by construction, and what gives FR-006 to the feature for free.

`scan_router.py` must contain **no `'01'` literal, no AI table and no digit arithmetic** — the element-string grammar lives in `gs1.py`, exactly as rule 1's grammar lives in `internal_id.py`.

### Why no existing scan can move (FR-008)

A rule-3 match needs ≥16 characters; `gtin.ACCEPTED_LENGTHS` is `(8, 12, 13, 14)`. Disjoint sets, so rule 3 cannot capture a bare GTIN. Rules 1 and 2 run first, so it cannot capture an internal code or an envelope. The only inputs whose classification changes are element strings that are free text today.

This argument belongs in a comment at the call site — it is the reason the new rule is safe, and it is not obvious from reading the code.

### Classification results

| Scan | Before | After |
|---|---|---|
| `'0109506000134352'` | `FREE_TEXT`, value = the whole string | `GTIN`, value `'09506000134352'` |
| `']d2' + EL`, `'\x1d' + EL`, `EL + '10LOT42'` | `FREE_TEXT` | `GTIN`, value `'09506000134352'` |
| `'0109506000134353'` (bad check digit) | `FREE_TEXT` | `FREE_TEXT` — unchanged |
| `'0100000000000000'` | `FREE_TEXT` | `FREE_TEXT` — unchanged |
| `'0109506000134352 RES 10K'` | `FREE_TEXT` | `FREE_TEXT` — unchanged |
| `'9506000134352'`, `'WIT…'`, `'[)>\x1e06…'`, `'B0ABC12345'`, `'M3 standoff'` | as today | **identical** |

---

## Downstream, unchanged

`CatalogService.resolve_scan` receives `ScanKind.GTIN` and looks up `IdentifierType.GTIN` on `classification.value` — the same lookup, on the same key, as for a bare barcode. So:

- a catalogued number → `outcome='product'`, the product page;
- an uncatalogued valid number → `outcome='create'`, prefilled with the GTIN (FR-001 scenario 2);
- a refused number → `outcome='search'` carrying `raw` (FR-006).

`POST /api/scan` and `app/static/js/scan-capture.js` are not modified.
