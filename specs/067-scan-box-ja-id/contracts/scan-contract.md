# Contract delta: Scan Classification and Resolution

Amends [`specs/001-product-catalog/contracts/scan-contract.md`](../../001-product-catalog/contracts/scan-contract.md)
(frozen) and the outcomes added since (feature 024 `receive`). Only the changes are listed.

## classify()

New rule, evaluated **before** rule 1:

| # | Rule | → `kind` | → `value` |
|---|---|---|---|
| 0 | Matches `^JA[0-9]{6}$` case-insensitively after whitespace strip | `JA_ID` | the JA ID, uppercased and stripped |

Disjoint from rules 1–6, so no previously classified scan changes kind. The never-raises
guarantee is unchanged.

## resolve_scan()

| `kind` | → `outcome` | Lookup |
|---|---|---|
| `JA_ID` | `'item'` | none |

`'item'` is the first outcome that does not concern the product catalog. `product` is `None`.

## POST /api/scan

| `outcome` | `url` |
|---|---|
| `'item'` | `/inventory/edit/<JA ID>` |

Still 200 for every well-formed request. A JA ID with no matching item is answered by the edit
page itself ("Item … not found." and a redirect to the inventory list), not by the API.

## Removed

The header's `#ja-id-lookup` input and its client-side handler. `#global-scan-input` is the only
header code-entry box.
