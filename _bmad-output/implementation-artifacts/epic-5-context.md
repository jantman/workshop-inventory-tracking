# Epic 5 Context: Stock Tracking & Reorder Signals

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic makes stock tracking opt-in and honest, then turns it into one actionable reorder list. Quantity and location are tracked only for the handful of items where a stockout has real cost, with an unambiguous distinction between "not tracked" and "none on hand" and with the age of the operator's last count surfaced rather than silently corrected. On top of that, it establishes the stored-vs-derived split that the rest of the system depends on: the `stock_status` column holds only the operator's manual assertion, while Effective Low, On Order, and Recently Received are computed at read and never persisted — so the stored value and the reorder signal can never contradict each other. It closes with a single reorder view that unifies manually-flagged and threshold-derived low stock and marks in-flight orders so the operator does not double-order.

## Stories

- Story 5.1: Tri-state quantity and location
- Story 5.2: Reorder threshold and derived Effective Low
- Story 5.3: Manual stock status
- Story 5.4: Derived On Order and Recently Received
- Story 5.5: Receipt clears manual low
- Story 5.6: Unified reorder view

## Requirements & Constraints

- Quantity On Hand is a nullable integer with three semantically distinct states: `NULL` = not tracked, `0` = tracked with none on hand, `N` = tracked with N. All three must render as visibly distinct literal text (e.g. an untracked marker vs "In stock: 0" vs "In stock: N") — a reader must never be able to confuse "untracked" with "none". New Products default to `NULL`; tracking is opt-in per Product.
- Quantity is modified **only** by manual operator assertion. Receiving a Purchase never writes quantity or its verification timestamp. Each manual assertion sets a verification timestamp, and the **age** of that timestamp is displayed alongside any tracked quantity — staleness is surfaced, not corrected.
- Reorder Threshold is an optional integer per Product. Location and sub-location are optional and must draw from the **existing** location autocomplete vocabulary and endpoint rather than introducing parallel fields; the shared suggestion source query is extended (not forked) so Product locations feed back into it bidirectionally.
- Stored Stock Status is one of `unknown` (default) / `ok` / `low` / `out` and holds **only** manual assertions — derivation never writes it. Manual flagging must work on Products with no tracked quantity at all, and setting it records a timestamp whose age is displayed.
- Effective Low is true when stored status is `low`/`out` **OR** (quantity is tracked AND a threshold is set AND quantity ≤ threshold). A `NULL` threshold makes the threshold branch false. Evaluating it must never write the stored status.
- On Order is derived from the existence of any unreceived Purchase; Recently Received is derived from a Purchase received within the last N days, where N is a named configuration value. Neither is ever persisted.
- Setting a Purchase's received date clears **only** a manual `low`/`out` back to `ok`, scoped to the purchased Product. It must not touch quantity, must not write any other Product's status, and must not override the derived Effective-Low signal — a tracked Product still at/below threshold stays Effective Low after receipt (no flip-flop).
- The reorder view is a single list containing every Effective-Low Product, whether manually flagged or threshold-derived, with On-Order ones visibly marked.
- The system must remain fully usable for identification with quantity tracking entirely unused. Broad quantity coverage is an explicit non-goal — inaccurate counts are worse than absent ones.
- The UI must work responsively from 360 px upward on the existing Bootstrap 5.3.2 codebase.

## Technical Decisions

- **Stored-manual, derived-at-read (AD-6).** This is the governing invariant for the whole epic. Only `stock_status` / `stock_status_at` (and the manually-asserted quantity fields) are columns. Effective Low, On Order, and Recently Received are computed in the catalog service at read time. Do not add derived columns, caches, or triggers.
- **Single-sourced Effective-Low predicate.** The predicate must be expressed exactly once, as a single SQLAlchemy hybrid expression / service method usable both in Python and in a SQL `WHERE` clause — Epic 8's stock-status search facet reuses this same expression. A second hand-written copy anywhere (template, route, query) is a defect.
- **Layering (AD-1, AD-2).** All queries and mutations go through `mariadb_catalog_service.py`; no ORM or SQL in routes. Routes build the standard `{success, …}` envelope and choose the HTTP status; JSON errors use the fixed `{success: false, error: {code, message, field?}}` shape and JSON routes are `@csrf.exempt`. Every mutation logs an audit operation. Per-method session lifecycle is `try / except-log / finally: session.close()`.
- **Columns already exist.** The Product/Purchase entity migrations from Epic 1 already carry `quantity_on_hand`, `quantity_verified_at`, `reorder_threshold`, `stock_status`, `stock_status_at`, `location`, `sub_location`, and the nullable `received_date`. This epic should generally need no new schema; if one proves necessary it is an Alembic migration via `manage.py db`, chained from the current HEAD, with metal-stock tables untouched.
- **Config, not literals.** The Recently-Received window N is a named application config value, not an inline constant.
- **Signals are group-aware by definition but per-Product for now.** Write the derived-signal logic so the group-sibling extension in Epic 10 is a widening of the query, not a rewrite; do not build group behavior here (no groups exist yet).
- **New JSON endpoints need client parity (AD-13).** Any programmatic endpoint added for quantity/status changes gets a matching method plus a frozen result dataclass in `app/api_client.py`.
- **Conventions.** Money uses `decimal.Decimal` with `ROUND_HALF_UP`, never `float`. Status values are single-sourced as an enum in `app/models.py` and bridged onto the ORM class with `@hybrid_property`.

## UX & Interaction Patterns

- There is no separate UX design contract; the UI is the existing responsive Bootstrap 5.3.2 codebase.
- The three quantity states are a *rendering* contract, not just a data one — the untracked marker, zero, and N must be independently recognizable at a glance.
- Verification age and status age are displayed next to their values so the operator can judge how much to trust them.
- Manual status flagging must be reachable for a Product that tracks no quantity — flagging something low is never gated on committing to counting it.
- The reorder view is a single pass: one list, On-Order clearly distinguished from actionable, so nothing gets double-ordered.

## Cross-Story Dependencies

- Depends on Epic 1 for the Product and Purchase entities, the purchase received-date write path that Story 5.5 hooks, and the product detail/edit forms these fields appear on.
- Story 5.1 (tri-state quantity) and 5.3 (manual status) supply the inputs to 5.2's Effective-Low predicate; 5.2 and 5.4's signals are prerequisites for 5.6's reorder view.
- Story 5.5 depends on 5.3's manual status and on the derived Effective Low from 5.2 to prove the no-flip-flop behavior.
- Epic 8 reuses the Effective-Low predicate for its stock-status search facet — build it as a shared service/hybrid expression, not a reorder-view helper.
- Epic 9's self-sufficient scan-result view surfaces location, Stock Status, and the Effective-Low/On-Order indicators and offers inline quantity + status changes, so expose those mutations as reusable service methods.
- Epic 10 extends On Order and Recently Received across Equivalent Product Group siblings and collapses the Story 5.6 reorder view to one line per group; group suppression must remain purely derived, never a sibling stored-status write.
