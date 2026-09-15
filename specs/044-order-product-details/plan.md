# Implementation Plan: Capture Product Details for Products an Order Created

**Branch**: `robot-army/issue-156-amazon-order-capture-workflow-bug` | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/044-order-product-details/spec.md`

## Summary

A product an Amazon order capture creates holds only a title and an ASIN. The one route to its
details, capturing its listing, records a second purchase on every answer. This plan adds a third
outcome to a listing capture, **details only**, and builds the guided order process on top of it.

The approach in one line: **one read-only lookup on the bookmarklet landing, one write method that
fills blanks and replaces only what the operator ticks, and a loop in the capture agent that reads
each order line's listing.**

Findings from the code keep it smaller than thirty-two requirements suggest:

1. **The landing page already knows everything the choice needs.** `api_capture` has the vendor,
   the ASIN and the listing before the operator submits anything, so one read-only lookup can show
   the choice up front. No new bookmarklet, no mode flag, and today's request is unchanged when the
   new `intent` field is absent. research.md §3.
2. **The collapsed message needs no JavaScript.** Its "separate purchase" option carries the two
   answers `capture_order` already understands as hidden fields, so the purchase path asks nothing
   more. research.md §3.
3. **One write method serves both callers.** `apply_listing_details` fills blanks and replaces only
   named fields. The order path calls it with nothing named, which *is* FR-027's "fill blanks,
   overwrite nothing". research.md §4.
4. **Order-line details are written after the order commits,** the way the single-listing capture
   already splits its write. `capture_order_lines` changes only to report which product each line
   landed on. This makes FR-030 free: re-running the bookmarklet on yesterday's order repairs its
   products in one click. research.md §6.
5. **The agent already fetches `/dp/<ASIN>` same-origin** (`canonicalDocument`). Auto-fetch is that
   fetch and `extract()` in a sequential loop, with a guard against sign-in and robot-check pages.
   research.md §5.
6. **"Details captured" is derived from specification rows.** No schema change, and no backfill
   guess. research.md §2.

**Two operational limits bite if forgotten.** Both are measured, not speculative, and both are a
single setting:

- **Werkzeug's 500 KB form-field cap.** The order payload now carries a listing per line.
  research.md §7.
- **Gunicorn's 30 s worker timeout.** An order confirmation now stores a gallery per line.
  research.md §8.

**Order of work** follows the dependencies:

1. **US1** (details-only) is the foundation. **US2** (the collapsed message) is its presentation.
   These two ship the fix for the reported defect.
2. **US3** (checklist) needs only the derived status.
3. **US4** (auto-fetch) needs US1's write method and US3's fallback.

## Technical Context

**Language/Version**:
- Python 3.13 on the server, and Jinja2 templates.
- **Browser JavaScript changes in `app/static/js/capture-agent.js` only.** It gains the order
  listing loop and the progress element. `capture.html` needs no new script: the choice is plain
  radios and checkboxes.

**Primary Dependencies**: Flask 3.1.3, Werkzeug 3.1.8, SQLAlchemy, Jinja2 and `requests` (already
used by `listing_images`). **No new dependency.**

**Storage**: MariaDB, with SQLite under unit test through the same interface. **No schema change
and no Alembic revision.** data-model.md.

**Testing**:
- pytest through `nox` (`tests`, `e2e`), with Playwright for e2e. **No new pytest marker.**
- New files: `tests/unit/test_order_product_details.py` and
  `tests/e2e/test_order_product_details.py`, plus one fixture,
  `tests/e2e/fixtures/amazon_robot_check.html`.
- Deliberate edits to existing tests are listed in research.md §11.

**Target Platform**: The Flask app in a gunicorn container on the LAN, with no login and a single
operator. The capture agent runs in the operator's browser on amazon.com.

**Project Type**: Server-rendered Flask web application. No SPA and no build step.

**Performance Goals**:
- **Reading listings:** sequential, about 1–2 s each in the operator's browser (SC-007 allows 5 s).
- **Confirmation:** an order confirmation stores each line's gallery, at 8–15 s per gallery, which
  is the existing single-capture figure.
- **No concurrency and no background work** (Constitution I). The request timeout is raised
  instead (research.md §8).

**Constraints**:
- Nothing is written before the operator confirms.
- An order's purchases write all-or-nothing, unchanged.
- A details-only capture never touches a purchase, quantity or stock.
- No listing value replaces a held one without a tick.
- Existing tests outside research.md §11 pass unedited.

**Scale/Scope**:
- One operator, typically orders of 1–10 lines.
- **Production files changed:**
  - `app/catalog_service.py`: three methods, plus `line_products`
  - `app/models.py`: two new dataclasses, and new fields on `AmazonOrderLine` and
    `OrderCaptureResult`
  - `app/product/routes.py`: the landing, the capture POST, the order confirmation, the order
    page and the product page
  - `app/static/js/capture-agent.js`
  - `config.py`: one setting
  - `Dockerfile`: one flag
- **Templates:** `capture.html`, `order_review.html`, `order.html`, `detail.html`.
- **Documentation:** `docs/user-manual.md` (Amazon Orders) and `docs/deployment-guide.md` (the
  timeout).

## Constitution Check

*GATE: passed before Phase 0 and re-checked after Phase 1 design. No violations, so Complexity
Tracking is omitted.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | **Pass.** No new abstraction, route, table, background job or dependency. The choice is one form field (`intent`) and reuses the existing `acknowledged_duplicate_of`/`attach_to` answers rather than new ones. One write method serves both callers. The details status is derived rather than stored. Listings are read sequentially, with no concurrency. The two operational settings (§7, §8) are raised because this feature creates a measured need (payload size, and 8–15 s × lines), not a speculative one. A rejected alternative, background image retrieval, is recorded in research.md §8. |
| **II. Layered Architecture Boundaries** | **Pass.** All logic lives in `CatalogService`: `find_listing_match`, `apply_listing_details`, `products_missing_details`. Routes forward form fields and call services. The order-listing loop in the confirm route calls two service functions per line and holds no query. `ListingMatch` and `ListingDetailsResult` are frozen dataclasses in `app/models.py`, so no ORM row crosses a closed session into a template. |
| **III. Exact Numerics** | **Pass.** No arithmetic on money or measurements is introduced. The listing's price is not written by details-only, and on the purchase path it stays a string until `_validate_price`, unchanged. |
| **IV. Test Discipline Through Nox** | **Pass.** Everything runs through `nox`. The SC-001 regression test is written red first (quickstart §1). No new marker. New e2e waits name elements (quickstart §3), and the one negative assertion is guarded. Screenshot tests stay out of `e2e`, and changed pages' screenshots are regenerated and verified. |
| **V. MariaDB Is the Source of Truth** | **Pass.** No schema change, so there is no migration to reverse. Writes go through existing service sessions. The order's own transaction is unchanged. |
| **VI. Item Lifecycle and History Invariants** | **Not applicable, and checked rather than assumed.** Only `products`, `product_specifications`, `product_identifiers`, `product_attachments` and (unchanged) `purchases` are touched. No JA ID, active-row, shortening or parent-child path is reached. The neighboring purchase invariants are honored: a details-only capture writes no purchase and moves no count (FR-002, data-model.md). |

**Operating Context and Threat Model:** the `/api/capture` CSRF exemption is unchanged, and the
details path goes through `product_capture`, which carries a token. No new exemption, no
sanitization layer and no URL allow-list for listing images (`listing_images.py` already states
why).

**Post-design re-check:** unchanged. Phase 1 added two frozen dataclasses and three service methods.
Its only operational changes (§7, §8) are single settings with written justification, not
machinery.

## Project Structure

### Documentation (this feature)

```text
specs/044-order-product-details/
├── plan.md                              # This file
├── research.md                          # Phase 0: twelve findings from the code
├── data-model.md                        # Phase 1: derived status, in-memory types, invariants
├── quickstart.md                        # Phase 1: how to prove it, red first
├── contracts/
│   ├── details-only-capture.md          # Phase 1: confirmation page fields, service methods
│   └── order-payload.md                 # Phase 1: agent payload, review, confirm, order page
├── spec.md
├── checklists/requirements.md
└── tasks.md                             # /speckit-tasks; NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── catalog_service.py        # find_listing_match, apply_listing_details, products_missing_details;
│                             #   capture_order_lines reports line_products
├── models.py                 # ListingMatch, ListingDetailsResult; ListingCapture.from_data;
│                             #   AmazonOrderLine.listing/listing_problem; OrderCaptureResult fields
├── product/routes.py         # api_capture landing + product_capture intent=details;
│                             #   _confirm_page_order applies listings; order_detail + product_detail status
├── static/js/capture-agent.js  # amazon-order branch: sequential listing reads + progress element
└── templates/product/
    ├── capture.html          # match block, collapsed message, show-and-choose
    ├── order_review.html     # per-line listing summary, rewritten note
    ├── order.html            # details column + progress alert (Amazon)
    └── detail.html           # missing-details notice
config.py                     # MAX_FORM_MEMORY_SIZE
Dockerfile                    # gunicorn --timeout 600
docs/user-manual.md           # Amazon Orders: the guided process
docs/deployment-guide.md      # proxy read timeout
tests/
├── unit/test_order_product_details.py
├── unit/test_cross_path_duplicates.py      # collapsed-message assertions (research.md §11)
├── e2e/test_order_product_details.py
├── e2e/test_amazon_order.py                # route /dp/<ASIN> or assert not-read (§11)
└── e2e/fixtures/amazon_robot_check.html
```

**Structure Decision**: this is the existing single Flask project. Every file above already exists
except the two new test modules and one fixture. No new package, blueprint or `app/` module.
