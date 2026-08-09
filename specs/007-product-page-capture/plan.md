# Implementation Plan: Product Page Capture

**Branch**: `issues/57` | **Date**: 2026-08-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-product-page-capture/spec.md`

## Summary

The capture stops being a URL and a title and starts being the listing.

A script this application serves — `app/static/js/capture-agent.js` — is loaded into the vendor's page by a bookmarklet that is now a four-line loader. It reads the canonical listing for the item, pulls the gallery's full-resolution image addresses out of the page's own inline data, reads the price, the brand, the description and the product-information rows, and submits the lot as **one hidden JSON field on the form POST that already lands the bookmarklet on this app's confirmation page**. That last part is the whole transport design: the navigation is the one path proven to survive Amazon's `upgrade-insecure-requests` (issue #54), it is already CSRF-exempt, and it needs no CORS, no preflight and no new endpoint.

The payload then sits in a hidden field on the capture form and goes nowhere until the operator submits. That is what makes FR-014 and FR-015 cost nothing: an unconfirmed capture is a form, exactly as #58 left it, and a form that also carries fourteen image addresses is still a form. When `capture_order` raises `CaptureDecisionRequired`, the template re-emits the hidden field from `request.form` alongside every other value it already re-emits, so FR-016 costs nothing either.

On confirmation the write splits in two, because the two halves have entirely different failure characteristics. `CatalogService.capture_order` gains one parameter — the parsed listing — and does the fast, transactional half: product, purchase, merged specification rows, description row. The route then calls a new `app/services/listing_images.py`, which fetches each image from the vendor's CDN with `requests` and hands the bytes to `PhotoService`. That call is slow (roughly ten seconds for a full gallery) and partially failing by nature, which is exactly what FR-020 says it must be allowed to be; putting it inside the catalogue transaction would make one refused image roll back a purchase.

**One Alembic revision, and it is a column widening.** `b1a0c0d10009` takes `product_specifications.value` from `TEXT` to `MEDIUMTEXT`. Nearly everything this feature stores already has a home — specifications arrived with #71, attachments with feature 001, and `photos.sha256_hash` has existed, indexed and unused, since `8213852b0b94`, whose own backfill wrote `sha256_hash=None,  # Will be populated on future uploads` (FR-018's content dedupe is that promise being kept, not a schema change; the attachment cap FR-012 raises is a class constant). The exception is the captured description. `TEXT` holds 65,535 **bytes**, and FR-006 says a captured description is kept in full; rather than cap the agent and carry a bounded exception to a requirement, the column is widened to hold 16,777,215. See [research.md](./research.md#the-description-ceiling) for the version of this plan that capped instead, and why it lost.

**The one deferred decision resolves itself.** Issue #57 left "who owns the captured images, the product or the purchase" to this document. The spec's answer to clarification Q3 settled it before this document was written: FR-018 dedupes "against a given owner" and US5 scenarios 5–7 speak of what "the product already holds". Under purchase ownership every purchase is a fresh owner, so dedupe could never fire and a repeat buy would store the whole gallery again. The images belong to the product. The trade-offs are written out in full in [research.md](./research.md#who-owns-the-captured-images) rather than asserted here.

Deliberately **not** built: any server-side draft or session storage for an unconfirmed capture; a background job or queue for image retrieval; a browser extension; any CORS configuration; a JavaScript test runner; an Alembic revision; a second blob store; and any attempt to make the extractor vendor-neutral. Each is argued in [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.13. The extractor is plain ES2017 browser JavaScript in one file, no build step, matching the twenty-two scripts already in `app/static/js/`.

**Primary Dependencies**: Flask 3.1.x, SQLAlchemy 2.0.x (legacy `Query` API, matching `catalog_service.py` and `photo_service.py`), Jinja2 + Bootstrap 5.3.2, Pillow (already used for every attachment). **`requests` is added to `requirements.txt`** — it is not a new dependency, it is an undeclared one: it is installed today as a transitive of `google-api-python-client` and already imported by `app/api_client.py:20`. Pinning what we import is a correction, not an addition. No new package is introduced.

**Storage**: MariaDB via PyMySQL. Writes `products`, `product_specifications`, `purchases`, `product_identifiers`, `product_attachments` and `photos`. One schema change: `product_specifications.value` `TEXT` → `MEDIUMTEXT` on revision `b1a0c0d10009`, moving head from `b1a0c0d10008`. The only previously-unwritten column now written is `photos.sha256_hash`, which exists and is indexed.

**Testing**: `nox -s tests` (pytest against SQLite through the `Storage` seam, network blocked by `--blockage`, so every `requests.get` is mocked) and `nox -s e2e` (Playwright against a MariaDB testcontainer, 15-minute tool timeout), plus a **manual Alembic round-trip** — neither suite runs migrations (`tests/conftest.py` and `tests/e2e/test_server.py` both build the schema with `Base.metadata.create_all`), and the widening is MariaDB-only, so SQLite could not exercise it even if they did. Two further pieces of test infrastructure do not exist yet, both described in [quickstart.md](./quickstart.md): a fixture listing page fulfilled through Playwright's `page.route` so the extractor can be exercised without reaching Amazon, and a stdlib `http.server` thread serving `tests/e2e/fixtures/images/` so the application fetches real bytes over real HTTP from an origin the test controls.

**Target Platform**: Single Flask app on a home LAN behind TLS, driven from Chrome on Linux.

**Project Type**: Web application, single deployable. No new top-level directory.

**Performance Goals**: None measured, and none set. One number is predicted rather than required, so that it can be checked: a fourteen-image capture is expected to hold the confirmation POST for **8–15 seconds**, dominated by Pillow generating a thumbnail and a medium rendition per image rather than by the network. This is recorded so that "the capture feels slow" becomes a comparison rather than an impression. Under Principle I it is not optimized in advance — see [research.md](./research.md#why-image-retrieval-is-synchronous).

**Constraints**: Prices cross a JSON boundary, and JSON numbers are IEEE doubles. The payload carries `price` as a **string**, and it stays a string until `_validate_price` turns it into a `Decimal` — Principle III has no exception for "it was only in transit". After `b1a0c0d10009` a specification value is bounded at 16,777,215 bytes, against a largest observed description of 28,767 characters, so the agent imposes no cap of its own and FR-006 holds unconditionally.

**Scale/Scope**: One operator, no concurrency. Roughly: 1 Alembic revision (schema only, both directions), 2 new files (`app/static/js/capture-agent.js`, `app/services/listing_images.py`), 2 new dataclasses, 1 new service method on `CatalogService`, 2 changed methods and 1 new constant on `PhotoService`, 1 changed column type, 2 changed routes, 2 changed templates, 1 changed JS file, 1 line added to `requirements.txt`.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 design — see below.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | The transport reuses the existing form-POST navigation and the existing `/api/capture` endpoint; the payload rides in a hidden field on a form that already round-trips its values, so the "leave no trace" and "survive a decision" requirements cost zero new machinery. No drafts table, no session store, no queue, no extension, no CORS layer, no build step. The one genuinely new abstraction is `app/services/listing_images.py`, and it exists because retrieval is slow and partially-failing while the catalogue write is neither — not because a layer looked tidy. **PASS** |
| **II. Layered Architecture Boundaries** | `ListingCapture` and `ImageCaptureResult` are `@dataclass` types in `app/models.py`, and `ListingCapture.from_json` is where the payload's validation lives — domain validation in the domain layer. Specification merging is a `CatalogService` method. Attachment storage stays behind `PhotoService`. The routes parse a form field, call two service methods, catch the exceptions they already catch, and render. No ORM query and no raw SQL enters a route. **PASS** |
| **III. Exact Numerics** | The extracted price is a string in the payload, a string in the form field, and a `Decimal` the moment `_validate_price` sees it. No `float` exists anywhere on the path, and no arithmetic is performed on a price. The image size filter compares pixel integers, which are counts, not measurements. **PASS** |
| **IV. Test Discipline Through Nox** | Unit tests cover the merge rules, the payload parsing, the hash dedupe, the cap, and every failure branch of the fetcher with `requests.get` mocked (the suite blocks the network, so an unmocked call fails loudly rather than reaching out). E2E covers the six stories against MariaDB, with the vendor page fulfilled locally and the image host served locally. Every wait is on an element: the confirmation flow is a full-page form navigation, and the thumbnail grid and paste upload are `expect(...)` on rendered nodes — pattern C from `CLAUDE.md`, where the node cannot predate the completed work. No new pytest marker. **PASS** |
| **V. MariaDB Is the Source of Truth** | One revision, `b1a0c0d10009`, on the current head `b1a0c0d10008`: `product_specifications.value` `TEXT` → `MEDIUMTEXT`. It carries no data — a widening needs no backfill, because every existing value already fits. The `downgrade` narrows back, and **refuses rather than truncates**: it counts rows over 65,535 bytes first and raises naming them, because Principle I never licenses losing data. That guard also protects the older `b1a0c0d10007` downgrade, which folds specification rows back into `products.specifications TEXT` and would otherwise meet a value that cannot fit. Every other value this feature writes goes to a column that already exists — [data-model.md](./data-model.md#one-migration-and-one-column-that-was-waiting) traces each one, including `photos.sha256_hash` at `8213852b0b94:46`. **Neither test suite runs Alembic**, and the widening is MariaDB-only besides, so the round-trip in [quickstart.md](./quickstart.md#exercise-the-migration-both-ways) is a required step against a disposable container, not a suggestion. Google Sheets is untouched. **PASS — with an obligation recorded** |
| **VI. Item Lifecycle and History Invariants** | `inventory_items` is neither read nor written. No add, move, shorten, edit or search path for inventory items is touched. **N/A** |
| **Operating Context / Threat Model** | The CSRF exemption count stays at one — `api_capture` is already exempt and gains no sibling — so the assertion at `tests/unit/test_product_csrf.py:188` — which counts `@csrf.exempt` in the blueprint's source and requires exactly one — still holds. The application now makes outbound HTTP requests to a vendor CDN on the operator's instruction, which is new behaviour and is bounded rather than hardened: a fixed per-request timeout, a byte ceiling that is the existing 20 MB attachment limit, and the existing MIME allow-list. **No URL sanitization layer, no host allow-list, no SSRF defence** — the operator is the only user, the URLs come from a page they are looking at, and Principle I plus the stated threat model prohibit building a wall against an attacker who does not exist. This is a deliberate reading and is argued rather than assumed in [research.md](./research.md#what-we-are-not-defending-against). **PASS** |
| **Technology Constraints** | Server-rendered Jinja + Bootstrap. The extractor is one plain script file served from `static/`, no framework and no bundler. New Python carries type hints and raises the project's own exceptions. SQLAlchemy stays on the legacy `Query` API to match both files it touches. `app/api_client.py` is not touched, so its `__all__` contract is unaffected. **PASS** |
| **Development Workflow** | Feature branch `issues/57`, merged via PR. `app/templates/product/**` and `app/static/js/**` both change, so `nox -s screenshots_headless` runs and its output is committed; per the note recorded in feature 006's plan, that diff carries no signal and the informational workflow does not block. **PASS** |

No violations. The Complexity Tracking table is therefore omitted.

### Why the extractor is a served script and not an extension

This is the choice issue #57 spent the most evidence on, and it reverses an earlier assumption, so it is restated here with what actually settled it.

The case for a Chrome extension rested on a prediction: that Amazon's CSP would block a `<script src>` from this application, forcing the whole extractor to live inline inside a `javascript:` string. Tested against a real listing, injecting a foreign-origin script raised no `securitypolicyviolation` and there is no CSP `<meta>` element on the page — Amazon does not restrict `script-src` on listing pages. The prediction was wrong, and with it the only real argument for a second codebase.

What remains is a comparison the constitution answers on its own. An extension is a separate project with a manifest, a build, an install, an update mechanism and a review surface, maintained by one person in their spare time, to run the same two hundred lines. A served script is `app/static/js/capture-agent.js` — an ordinary file in this repository, edited in this repository, tested from this repository's test suite, and picked up on the next click because the loader cache-busts. FR-024 is satisfied by the transport rather than by a mechanism.

The extension remains the fallback if the cross-origin POST ever becomes awkward, and it is worth noting *why* that is unlikely: the POST is a form navigation, not a `fetch`. It is not subject to CORS at all, so there is no preflight to be refused and no header for Amazon to influence.

### Why `capture_order` grows a parameter instead of a sibling

`capture_order` already resolves-or-creates the product, and the merge in FR-010 needs exactly that resolution: the rows go onto whichever product the capture landed on, which is not known until the duplicate and recycled-identifier questions have been settled. A separate `apply_listing(product_id, listing)` called by the route would work, but it would put the FR-011 invariant — a capture never removes what the operator typed — in the route's hands, one call site at a time, which is the same failure shape feature 006 rejected when it made `CaptureDecisionRequired` a raise rather than a return.

Image retrieval is the opposite case and gets the opposite answer. It cannot be inside the transaction: it is seconds of network I/O whose expected outcome includes partial failure, and FR-020 requires the capture to have succeeded before the first image is even attempted. So the split is not stylistic. The line is drawn where the failure semantics change.

### Post-design re-check (after Phase 1)

Re-read after [data-model.md](./data-model.md) and the contracts were written. Five points:

- **The schema change is one widening and nothing else.** Every other value this feature writes was traced to an existing column, including one that has never been written. `photos.sha256_hash` simply stops being null on new rows; old rows keep a null hash, which means a pre-existing hand-uploaded copy of a captured image will not be recognized as a duplicate. That is accepted and stated in [data-model.md](./data-model.md#existing-photos-keep-a-null-hash) rather than papered over with a backfill nobody asked for. Still **PASS** under Principle V.
- **FR-006 now holds without an exception, and that is why the migration exists.** An earlier draft of this plan capped the agent at 60,000 characters to stay inside `TEXT`, and recorded the cap as a bounded exception to a requirement that says "kept in full". Widening the column removes the exception instead of documenting it: at 16,777,215 bytes against a largest observed description of 28,767 characters, there is no realistic listing the agent has to truncate. The trade — one reversible DDL migration against a permanent asterisk on a requirement — is argued in [research.md](./research.md#the-description-ceiling). The agent now imposes no cap at all, and `truncated_description` is gone from the payload.
- **The size filter runs entirely in the browser**, so the payload carries one flat image list and the server never learns which image came from the gallery and which from the description. That is what lets FR-019's "gallery images are not subject to this rule" be true without the server holding a distinction it would otherwise have to be trusted with. It also means a bug in the filter is a bug in one file with one test surface.
- **Within-capture and across-capture dedupe are the same mechanism.** A gallery image reused in the description block hashes identically to the copy already stored a moment earlier in the same run, so FR-018's two clauses need one implementation. A cheap URL-level pass runs first purely to avoid fetching the same address twice; correctness is the hash.
- **The extractor has no unit-test surface in this repository and will not get one.** Adding a JavaScript test runner is a new dependency and a new machine to maintain for one file. It is covered end to end instead, against a fixture page fulfilled by `page.route`, which tests the thing that actually breaks — the extraction — rather than the functions it is made of. The residual risk is real and named in [research.md](./research.md#the-risk-that-is-not-mitigated): the fixture is a snapshot, and a snapshot cannot fail when Amazon changes. FR-007's graceful degradation is what bounds the damage.

## Project Structure

### Documentation (this feature)

```text
specs/007-product-page-capture/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — decisions, and the alternatives that lost
├── data-model.md        # Phase 1 output — every value written, and the column it lands in
├── quickstart.md        # Phase 1 output — how to run and validate it, including by hand
├── contracts/
│   ├── capture-payload.md      # The JSON the extractor posts — the one cross-boundary contract
│   ├── catalog-service.md      # Changed and new CatalogService / PhotoService surface
│   └── http-routes.md          # Changed HTTP surface
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
migrations/versions/
└── b1a0c0d10009_widen_specification_value.py   # NEW — TEXT -> MEDIUMTEXT, both directions

app/
├── models.py                       # + ListingCapture, + ImageCaptureResult
├── database.py                     # ProductSpecification.value gains the mysql variant
├── catalog_service.py              # capture_order gains `listing`; + merge_specifications
├── photo_service.py                # cap 25 -> 100; sha256_hash populated;
│                                   #   + upload_product_attachment_if_new
├── services/
│   └── listing_images.py           # NEW — fetch from the CDN, filter, dedupe, store
├── product/
│   └── routes.py                   # product_capture, api_capture, _capture_bookmarklet
├── static/js/
│   ├── capture-agent.js            # NEW — the extractor, loaded into the vendor's page
│   └── product-attachments.js      # + paste-to-attach
└── templates/product/
    ├── capture.html                # + hidden listing field, + "what will be written" panel
    └── detail.html                 # attachments become a thumbnail grid

tests/
├── unit/
│   ├── test_capture.py             # + listing merge, description row, FR-011 invariant
│   ├── test_listing_images.py      # NEW — fetcher branches, all with requests mocked
│   └── test_product_attachments.py # + hash dedupe, + the raised cap
└── e2e/
    ├── fixtures/
    │   └── amazon_listing.html     # NEW — a snapshot page for page.route to fulfil
    ├── test_product_page_capture.py # NEW — stories 1-5
    └── test_product_attachments.py  # + paste, + the grid   (story 6)

requirements.txt                    # + requests (already imported, never declared)
```

**Structure Decision**: The existing layout, unchanged. The one new package-level file goes in `app/services/` because the constitution puts shared services there and this one is called by a route and calls `PhotoService`. The extractor goes in `app/static/js/` alongside the eighteen scripts already there, because that is what makes it an ordinary reviewable file in this repository — which is the entire argument for choosing it over an extension.

## Phase 0 / Phase 1 outputs

- [research.md](./research.md) — the transport, the owner decision, synchronous retrieval, the collation and ceiling questions, and what is deliberately not defended against.
- [data-model.md](./data-model.md) — every value written and the column it lands in; why there is nothing to migrate.
- [contracts/capture-payload.md](./contracts/capture-payload.md) — the JSON contract between the extractor and the application.
- [contracts/catalog-service.md](./contracts/catalog-service.md) — changed and new service surface.
- [contracts/http-routes.md](./contracts/http-routes.md) — changed HTTP surface.
- [quickstart.md](./quickstart.md) — how to run it, how to validate it, and the two manual checks no suite can perform.
