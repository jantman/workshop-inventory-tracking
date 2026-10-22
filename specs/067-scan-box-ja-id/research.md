# Research: JA IDs in the Header Scan Box

## 1. Where JA ID recognition lives

- **Decision**: A new classifier rule in `app/utils/scan_router.classify()`, delegating its
  grammar to a new sibling `app/utils/ja_id.py`, producing a new `ScanKind.JA_ID`.
- **Rationale**: `classify()` owns precedence and delegates every grammar to a sibling parser
  (its module docstring says so). A JA ID has a distinguishing shape, so it is structural and
  belongs in the classifier, not in resolution.
- **Alternatives**: Client-side branch in `scan-capture.js` that navigates without calling the
  server — rejected: splits scan routing across two languages and bypasses the one place that
  decides what a scan is. Resolving JA IDs inside the FREE_TEXT branch — rejected: it is not
  free text, and the kind would lie.

## 2. Precedence

- **Decision**: Rule 0, before the internal-code rule.
- **Rationale**: Disjoint from every other rule (`WIT…`, `[)>` envelopes, all-digit GTINs and
  GS1 strings), so order does not change any existing result. Putting it first states plainly
  that this is the one rule that does not lead to the catalog, and avoids renumbering rules that
  other comments cite by number. It also beats the free-text vendor-id lookup, which is correct:
  a JA ID is ours and must never resolve to a vendor's product.

## 3. Accepted form

- **Decision**: `^JA[0-9]{6}$` after `strip()`, case-insensitive; value normalized to uppercase.
- **Rationale**: Matches the database check constraint `^JA[0-9]{6}$`. Uppercasing carries over
  the old box's behavior. Anything else (`JA12345`, trailing text) stays on its current path.

## 4. Existence check

- **Decision**: None in resolution. Outcome `'item'` always; the route sends the operator to
  `/inventory/edit/<JA ID>`.
- **Rationale**: That is exactly what the old box did. `inventory_edit` already flashes
  "Item JA… not found." and redirects to the inventory list for a missing item, and uses
  `get_canonical_item` so inactive-only items open (FR-003, FR-004). A lookup would duplicate
  that and add a `CatalogService` → inventory dependency for nothing.
- **Alternatives**: Fall through to search when the item is missing — rejected by FR-003.

## 5. Consumers of "every resolution ends at a product"

Checked every user of `classify`/`resolve_scan`/`ScanResolution.outcome`:

- `app/product/routes.py::api_scan` — the only consumer; gains an `'item'` branch.
- `ScanResolution.product` stays `None` for `'item'` (it is "set iff outcome == 'product'"), and
  `to_dict()` already handles `None`.
- `scan-capture.js` navigates to `data.url` for any outcome — no code change, comment only.
- `app/api_client.py` has no scan call.
- Docstrings in `ScanKind`, `ScanResolution`, `resolve_scan`, `api_scan` enumerate outcomes and
  are updated.
- `specs/001-product-catalog/contracts/scan-contract.md` is frozen; this feature's
  `contracts/scan-contract.md` records the delta.

## 6. Header layout

- **Decision**: Keep the scan box's width and placeholder; update its `title` to mention JA IDs.
- **Rationale**: An 8-character JA ID fits in the existing box; no layout work needed.
