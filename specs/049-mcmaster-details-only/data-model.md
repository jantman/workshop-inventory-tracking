# Data Model: McMaster Details-Only Capture

No schema change. One existing entity changes in what is written to it.

## ProductIdentifier (existing)

| Field | Note |
|---|---|
| `id_type` | `VENDOR` and `DISTRIBUTOR` are the vendor-scoped kinds (`VENDOR_SCOPED_TYPES`). |
| `value` | The item number — an ASIN, a McMaster or DigiKey part number. |
| `vendor` | Required for vendor-scoped kinds; every lookup filters on it. |

### What each capture path writes for a vendor's item number

| Path | Amazon | McMaster-Carr | DigiKey |
|---|---|---|---|
| Order capture | `VENDOR` | `DISTRIBUTOR` | `DISTRIBUTOR` |
| Single-listing capture (`capture_order`) — before | `VENDOR` | `VENDOR` | `VENDOR` |
| Single-listing capture — **after** | `VENDOR` | **`DISTRIBUTOR`** | `VENDOR` |

### Lookup rule (after)

"Which product does item number *N* from vendor *V* name?" — the first product carrying *N*
as a `VENDOR`, else a `DISTRIBUTOR`, identifier scoped to *V*; otherwise none. Used by both
`find_listing_match` and `capture_order`.
