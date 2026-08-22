# Implementation Plan: DigiKey Order Capture and Receiving

**Branch**: `issues/108` | **Date**: 2026-08-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/024-digikey-order-capture/spec.md`

## Summary

Make the **order** the unit of capture. One DigiKey sales order number, entered once, is read
back from DigiKey's Order Status API, reviewed line by line, and confirmed into one outstanding
purchase per line. Weeks later each bag's 2D label — which already parses, and already yields
the sales order number as ECIA `1K` and the DigiKey part number as `P` — resolves to the one
outstanding line it belongs to, and receiving is a scan and a confirmation.

The technical shape follows from one observation: **the catalog already has almost everything
it needs, and the missing piece is one column.** `app/utils/ecia.py` has read these labels since
the first release. `CatalogService` already maps `1K` to the name `supplier_order_reference`
(`app/catalog_service.py:1702`) — the value simply had nowhere to go and ended up in a note.
`app/exceptions.py` already defines an exception for each of the four failure states FR-038
distinguishes. `app/services/listing_images.py` already establishes the "fast transactional
write, slow network work afterwards" split that Story 3's datasheet and photo need. And
`app/static/js/scan-capture.js` navigates to whatever `url` the scan API returns without
inspecting the outcome, so a fourth outcome needs no JavaScript at all.

So the build is: a ~200-line HTTP client, one nullable indexed column, four dataclasses, a
review-then-write pair on `CatalogService`, five routes and three templates. **No new table, no
new pip dependency, no new exception class, no background work, no JavaScript.**

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.3 (app-factory), SQLAlchemy 2.0.51 (legacy `Query` API),
Alembic 1.18.5 via `manage.py db`, Jinja2 + Bootstrap 5.3.2, `requests` 2.33.1. **No new
package.** The `digikey-api` package on PyPI is rejected — it types prices as `float`
(Constitution III) and its released code targets v3 ([research §3](./research.md)).

**Storage**: MariaDB via PyMySQL. One new column, `purchases.supplier_order_reference`
(`String(200)`, nullable, indexed), shipped as one reversible Alembic revision. No new table —
a captured order is derived from its purchases ([research §6](./research.md)).

**External interface**: DigiKey Product Information V4 and Order Status, 2-legged OAuth
(`client_credentials`), 120 requests/minute and 1,000/day — orders of magnitude more than a
workshop that orders once a fortnight needs. Full contract in
[contracts/digikey-api.md](./contracts/digikey-api.md).

**Testing**: `nox -s tests` (network-blocked; DigiKey served from recorded JSON fixtures),
`nox -s e2e` (DigiKey played by a stdlib `ThreadingHTTPServer`, the pattern
`tests/e2e/test_product_page_capture.py` already uses for Amazon's image host),
`nox -s screenshots_headless` for the new templates.

**Target Platform**: Linux, single-user, LAN-only, served by gunicorn behind the project
Dockerfile.

**Project Type**: Server-rendered Flask web application.

**Performance Goals**: A capture is a request the operator waits a couple of seconds for. One
API call per capture (two if the order date needs the history endpoint), 10-second timeout,
no caching, no retries, no async. SC-004's ten-seconds-per-bag is dominated by the operator
picking up the next bag.

**Constraints**: Prices are `Decimal` end to end — the response body is parsed with
`json.loads(body, parse_float=Decimal)` and never with `response.json()`. A failed capture must
leave nothing partially recorded, which is why the whole order writes in one session.

**Scale/Scope**: An order of 20–40 lines. A few thousand purchases over the application's life.

**Unresolved**: none blocking. One assumption is *gated* rather than assumed —
[research §2](./research.md) — see Risks below.

## Constitution Check

*Evaluated before Phase 0 and re-evaluated after Phase 1. Both passes below.*

| Principle | Pre-design | Post-design |
|---|---|---|
| **I. Simplicity First** | Risk: an API integration invites a client library, a token store, a cache and a job runner | **PASS.** No new dependency; no new table; no new exception class; no cache, retry loop, queue or background job. Two config secrets plus a base URL. The one abstraction — a client returning dataclasses — exists because it is the seam that absorbs a v4 schema surprise, not for a second implementation |
| **II. Layered Architecture** | Risk: routes calling an HTTP client and the ORM in the same breath | **PASS.** `app/services/digikey.py` imports `requests`, the stdlib and `app.models` only — no Flask, no `app.database`. Writes go through `CatalogService`. Routes call the client, call a service, render. Same two-call shape `product_capture` already has |
| **III. Exact Numerics** | Risk: JSON `1.53` decodes to `float` by default, and every generated DigiKey client types prices as `float` | **PASS.** `json.loads(body, parse_float=Decimal)`; `response.json()` prohibited in this module; the `digikey-api` package rejected for exactly this; a unit assertion on `isinstance(..., Decimal)` is written first |
| **IV. Test Discipline** | Risk: unit tests run with the network blocked | **PASS.** The client is injected via `app.config['DIGIKEY_CLIENT']`, mirroring `STORAGE_BACKEND`. Fixtures are recorded from the real API in `T001`, redacted. E2E uses a loopback fake — which is why `DIGIKEY_API_BASE` is a present need, not a speculative knob. No new pytest marker. Waiting rules called out in [quickstart §3](./quickstart.md) |
| **V. MariaDB Source of Truth** | Risk: caching DigiKey's answer in a table | **PASS.** One reversible Alembic revision; the downgrade is exercised in [quickstart §1](./quickstart.md); the `create_all`-vs-Alembic drift trap the codebase already warns about is checked explicitly. Nothing from DigiKey is cached — the order is re-fetched at confirmation and the fetched order is the authority |
| **VI. Item Lifecycle Invariants** | N/A | **PASS.** No route, query or migration in this feature reads or writes `inventory_items`. This is the product catalog |
| **Threat model** | Risk: SSRF/allow-list reflexes around outbound HTTP | **PASS.** One hard-coded host from configuration, LAN-only app, one trusted operator. No allow-list, no sanitization layer. Secrets live in `.env` and are never committed. CSRF stays on for the new routes; unlike the Amazon bookmarklet they post from this application's own origin, so **no CSRF exemption is added** |
| **Error handling** | Risk: a new exception hierarchy for API failures | **PASS.** `ConfigurationError`, `AuthenticationError`, `ItemNotFoundError`, `TemporaryError` and `RateLimitError` all already exist and are already handled ([research §7](./research.md)) |

**One item needs justification** and is recorded in Complexity Tracking: the fourth
`ScanResolution` outcome amends a documented invariant.

## Project Structure

### Documentation (this feature)

```text
specs/024-digikey-order-capture/
├── plan.md                      # This file
├── spec.md
├── research.md                  # Phase 0
├── data-model.md                # Phase 1
├── quickstart.md                # Phase 1
├── contracts/                   # Phase 1
│   ├── routes.md                #   this application's new and changed routes
│   └── digikey-api.md           #   the outbound contract with DigiKey
├── checklists/requirements.md
└── tasks.md                     # /speckit-tasks — NOT created here
```

### Source code

```text
app/
├── models.py                    # + DigiKeyOrder, DigiKeyOrderLine, DigiKeyPart,
│                                #   OrderLineState, ReviewedLine, OrderCaptureReview;
│                                #   ScanResolution gains `purchases` and the 'receive' outcome
├── database.py                  # + Purchase.supplier_order_reference (column + to_dict)
├── catalog_service.py           # + review_digikey_order()  — read-only, writes nothing
│                                # + capture_digikey_order() — one _session() for the whole order
│                                # + find_order_lines(), find_receivable()
│                                # ~ resolve_scan(): the ECIA branch gains the order-line lookup,
│                                #   which must run BEFORE the existing 1P -> MPN lookup
├── services/
│   ├── digikey.py               # NEW. requests + stdlib + app.models. No Flask, no ORM
│   └── listing_images.py        # reused unchanged for the datasheet and photo (Story 3)
├── product/routes.py            # + 5 routes; ~ api_scan gains the 'receive' branch;
│                                #   ~ purchase_receive accepts ?quantity=
├── templates/product/
│   ├── digikey_order_entry.html # NEW
│   ├── digikey_order_review.html# NEW
│   └── digikey_order.html       # NEW — the captured order, derived
└── exceptions.py                # unchanged

config.py                        # + DIGIKEY_CLIENT_ID / _SECRET / _API_BASE, beside GOOGLE_*
migrations/versions/<rev>_*.py   # NEW. add_column + create_index; reversible

tests/
├── fixtures/digikey/            # NEW. salesorder.json, productdetails.json — recorded, redacted
├── unit/
│   ├── test_digikey_client.py   # NEW
│   ├── test_digikey_capture.py  # NEW
│   └── test_scan_resolution.py  # ~ the 'receive' outcome
└── e2e/
    ├── test_digikey_order.py    # NEW — capture, re-capture, exclude, the order screen
    └── test_digikey_receive.py  # NEW — scan a bag, receive, scan again
```

**Structure Decision**: No new blueprint and no new service module beyond the HTTP client.
The catalog's routes already live in the `product` blueprint, and the transactional write must
live on `CatalogService` because that is the only place a single session spanning all of an
order's lines is available without inventing a session-passing convention the codebase does not
have ([research §9](./research.md)). A separate `app/digikey_service.py` was considered and
rejected for that reason.

## Sequencing

The stories are independently deliverable and this is the order to build them, matching the
spec's priorities:

| Stage | Delivers | Depends on |
|---|---|---|
| **0** | `T001` — verify the API against a real order; record and redact fixtures | Nothing. **Run first** |
| **1** | The column + migration, the client, the dataclasses | Stage 0's fixtures |
| **2** | **US1** — capture an order (entry, review, confirm, order screen) | Stage 1 |
| **3** | **US2** — receive by scanning (the fourth outcome, the quantity prefill) | Stage 2 |
| **4** | **US3** — capture a single part (part lookup, specifications, datasheet, photo) | Stage 1 |
| **5** | **US4** — the four failure messages, and the not-configured path on every entry point | Stages 2–4 |

Stage 2 is a shippable MVP on its own: orders are recorded, the reorder list stops suggesting
what is already on the way, and parts are cataloged before they arrive. Stage 4 does not depend
on Stages 2–3 and could be built in parallel.

## Risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** | **The largest.** Order Status may refuse a non-business account, or 2-legged OAuth may not see this account's orders. DigiKey's FAQ requires a Credit account "before API orders can be *placed*" — scoped to the Ordering API, but untested for Order Status | `T001` verifies against the live API **before any code is written**. Two documented outcomes: fall back to 3-legged (one extra module, no other change), or **stop and report** — if this account cannot read its own orders, US1 is not buildable as specified and that is the user's call, not something to route around by scraping |
| R2 | v4 response field names may differ from the v3 record | The mapping lives in one module behind dataclasses. Fixtures are recorded from the real API, and the mapping is written from the file rather than from memory |
| R3 | The sales-order response may carry no order date | Two fallbacks, neither structural: the orders-history endpoint, then today's date — which is what `capture_order` already defaults to |
| R4 | A scanner wedge that swallows `GS` separators breaks label parsing | Pre-existing and already documented in the user manual. This feature is the first that fails *visibly* without it, which is an improvement on failing silently |
| R5 | A DigiKey product URL may not yield a resolvable part number | Read the MPN from the path; anything unresolvable is FR-032 — say so, offer the ordinary form, never guess |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| A fourth `ScanResolution` outcome (`'receive'`), amending a docstring that says "Three outcomes and no fourth" | FR-019 requires a scanned bag to land on the receipt for a specific order line, which is neither "here is the product" nor "here is a blank draft" | Encoding it as `outcome='product'` plus a hint makes one outcome mean two things, and every existing caller would have to learn the hint. The cited requirements (001 FR-018, SC-008) say *nothing dead-ends*, which a fourth answer does not weaken — the free-text rule still always matches. The docstring and the 001 cross-references are corrected as part of the work rather than left contradicting the code |
| `DIGIKEY_API_BASE` is configurable | The E2E suite points it at a loopback fake, and development points it at DigiKey's sandbox | A hard-coded host makes the feature untestable without the network, which Constitution IV prohibits. This is a present need, not a knob for a future that has not arrived |

---

**Phase 0 output**: [research.md](./research.md) — 13 sections, every unknown resolved or gated.

**Phase 1 output**: [data-model.md](./data-model.md),
[contracts/routes.md](./contracts/routes.md),
[contracts/digikey-api.md](./contracts/digikey-api.md), [quickstart.md](./quickstart.md).

**Next**: `/speckit-tasks`.
