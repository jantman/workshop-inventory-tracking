# Contract: DigiKey Order Listing

**Requirements**: FR-018 – FR-022 | **Research**: research.md §5, §6

**This contract is provisional in one respect only** — the query parameter names and response
field names below are DigiKey's, and are published inside a Swagger file that could not be read as
text. They are closed by one live call before any code is written, and the result is recorded in
`verification.md`. The path, the auth, the error mapping and the screen are not provisional.

## Client (`app/services/digikey.py`)

```python
def list_orders(self, days: int = 365) -> list[DigiKeyOrderSummary]:
```

| Aspect | Contract |
|---|---|
| Path | `GET {base}/orderstatus/v4/orders` — the documented v3→v4 rename of `/History`, under the prefix `get_order` already calls |
| Date range | The endpoint's own start/end parameters, computed from `days` back to today. **Exact names from `verification.md`.** |
| Paging | One page. DigiKey's paging parameters are used to *ask* for one; no paging UI is built without a measured need (Constitution I) |
| Auth | `_get`, unchanged — bearer token plus `X-DIGIKEY-Account-ID` |
| Parsing | Through `_get`, which uses `json.loads(body, parse_float=Decimal)`. **No `.json()` in this module**, per its docstring |
| Not configured | `ConfigurationError`, via the existing `account id must not be 0` mapping — free, and exactly what FR-021 asks for |
| Other failures | `AuthenticationError`, `RateLimitError`, `TemporaryError`, mapped by the existing `_raise_for_status`. **No new exception type.** |
| Empty account | An empty list, not an error. "No orders" is an answer. |
| Retries / cache | None, matching the rest of the module |

`DigiKeyOrderSummary.from_payload` returns `None` for an entry it cannot parse, so one bad row does
not lose the listing.

## Screen (`GET /products/digikey/orders`)

No new route and no new template — the listing renders on the screen that already answers "capture
a DigiKey order" (research.md §6).

| State | What renders |
|---|---|
| Configured, orders returned | A table above the existing form: sales order number, date, DigiKey's reference, status. Each row is a submit posting `sales_order_number` to this same route, reaching the review that already exists (FR-019, FR-020) |
| Configured, no orders | A plain "no orders in the last year" line. The form still works |
| Not configured | `_digikey_problem.html` with `not_configured`, as today. The listing is simply absent (FR-021) |
| Listing failed | The error's message beside a form **that still works** (FR-022). A failure to enumerate never removes the ability to capture by number |

The `POST` half of this route is unchanged.

## Fallback if the live call fails

Per research.md §5 and the spec's Assumptions: FR-018 – FR-022 are dropped, the operator reads
sales order numbers off DigiKey's own order-history page in the browser, and the manual chapter says
so. **A 3-legged OAuth flow is not the fallback** — it means a browser redirect, an HTTPS callback
and a refresh token on disk, which is a login system for an application whose constitution says it
has none.
