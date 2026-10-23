# Data Model: JA IDs in the Header Scan Box

No persisted data changes. Two in-memory types in `app/models.py` gain a member each.

## ScanKind (Enum)

| Member | New? | Produced by |
|---|---|---|
| `JA_ID` | yes | `classify()` rule 0 |
| `INTERNAL`, `ECIA`, `GTIN`, `FREE_TEXT` | no | `classify()` |
| `VENDOR` | no | `resolve_scan()` |

For `JA_ID`, `ScanClassification.value` is the uppercase JA ID with whitespace stripped;
`raw` is the scan as captured; `ecia_fields` is empty.

## ScanResolution.outcome

| Outcome | New? | Set for | Other fields |
|---|---|---|---|
| `'item'` | yes | `kind is JA_ID` | `product` None, `prefill` empty, `purchases` empty |
| `'product'`, `'create'`, `'search'`, `'receive'` | no | unchanged | unchanged |
