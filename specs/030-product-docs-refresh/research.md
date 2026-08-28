# Phase 0 Research: Product Documentation Refresh

**Feature**: 030-product-docs-refresh | **Date**: 2026-08-27

The spec's requirements are almost all of the form "the documentation must agree with what the application does". That makes the research phase unusually load-bearing: this file *is* the thing the documentation gets checked against, so every claim below carries the file and line it was read from. Where a claim could not be established from the code it is marked as such rather than smoothed over.

---

## 1. The configuration surface

**Decision**: seventeen environment variables change what a deployed or locally-run application does; five more belong to the test suite. Everything else currently in the deployment guide is read by nothing.

**Method**: `grep` for `os.environ`, `os.getenv`, `app.config[...]` and `config.get(...)` across `app/`, `config.py`, `manage.py`, `wsgi.py`, `app.py`, `noxfile.py`, `Dockerfile` and `.flaskenv`, then read each hit to establish its default and its consequence-when-unset.

**Two traps in that method**, both hit during this pass and both recorded in `quickstart.md` so the next person does not:

- **Indirection.** `CATEGORY_TAXONOMY_FILE` and `SPECIFICATION_KEYS_FILE` are read through module constants (`app/utils/catalog_taxonomy.py:60,62`), so a grep for the literal name inside `os.environ.get(...)` misses them.
- **`.flaskenv`.** It is committed, it is read by the `flask` CLI, and it carries four settings — including `FLASK_DEBUG=1`. A first pass that reads only its first line misses `FLASK_RUN_HOST` and `FLASK_RUN_PORT`.

### 1a. Variables that change a deployment

| Variable | Read at | Required | Default when unset | What unset means |
|----------|---------|----------|--------------------|------------------|
| `SQLALCHEMY_DATABASE_URI` | `config.py:11`, `manage.py:28,205,356,518` | **Yes** | none | No database connection. `manage.py config-check` reports it as an error (`config.py:99-101`). |
| `SECRET_KEY` | `config.py:8` | In practice yes | `dev-secret-key-change-in-production` | Sessions and CSRF tokens are signed with a key that is in the public repository. |
| `LOG_LEVEL` | `config.py:38`, applied at `app/logging_config.py:86` | No | `INFO` | INFO-level logging to stdout. |
| `FLASK_DEBUG` | `config.py:37`, and set to `1` by `.flaskenv:2` | No | `False` in `Config`, `True` in `TestConfig` | Debug off in a deployment. **Caveat**: `.flaskenv` is read by the `flask` CLI, so a source checkout run with `flask run` gets debug **on** unless the environment overrides it. Gunicorn never reads `.flaskenv`, and the file is not copied into the image (`Dockerfile:55-57`). |
| `CUPS_SERVER` | Not by application code — by the `lp` binary from `cups-client` (`Dockerfile:28-29`, invoked from `app/services/label_printer.py`) | No, but label printing needs it in the container | none (`lp` looks for a local cupsd) | Label printing fails in the container, because there is no local CUPS daemon in it. |
| `GOOGLE_SHEET_ID` | `config.py:23` | No | none | Google Sheets **export** is unavailable. Sheets is export-only and legacy (Constitution V); nothing else is affected. |
| `GOOGLE_CREDENTIALS_FILE` | `config.py:21` | No | `<repo>/credentials/credentials.json` | The default path is used. Note the name: the deployment guide currently calls this `GOOGLE_CREDENTIALS_PATH`, which is read by nothing. |
| `GOOGLE_TOKEN_FILE` | `config.py:22` | No | `<repo>/credentials/token.json` | As above; the guide's `GOOGLE_TOKEN_PATH` is not read. |
| `DIGIKEY_CLIENT_ID` | `config.py:29` | No | none | The two DigiKey screens still render, and say they are not configured (`app/product/routes.py:1143-1147,1158-1161`). Nothing else in the application changes. |
| `DIGIKEY_CLIENT_SECRET` | `config.py:30` | Required **if** the client id is set | none | DigiKey refuses the credentials; the screen says so (`app/services/digikey.py:209`). |
| `DIGIKEY_ACCOUNT_ID` | `config.py:31` | Required for the **order** endpoints | none | Order calls answer `400 Account ID must not be 0`. A 2-legged token identifies the application, not the customer, so this header is what names the account. Part lookup is unaffected. |
| `DIGIKEY_API_BASE` | `config.py:34` | No | `https://api.digikey.com` | The production API. Set to `https://sandbox-api.digikey.com` to work against the sandbox. |
| `CATEGORY_TAXONOMY_FILE` | `app/utils/catalog_taxonomy.py:333` | No | the shipped taxonomy | The branches from `docs/category-taxonomy.md` are offered. If set and unreadable, **the application refuses to start**. |
| `SPECIFICATION_KEYS_FILE` | `app/utils/catalog_taxonomy.py:374` | No | the shipped key list | As above, and independent of the taxonomy variable. |
| `FLASK_APP` | `.flaskenv:1`, read by the `flask` CLI | No | `wsgi.py`, set by the repository's own `.flaskenv` | Already correct. The deployment guide tells the reader to set it to `app.py`, which contradicts `.flaskenv`. |
| `FLASK_RUN_HOST` | `.flaskenv:3`, read by the `flask` CLI | No | `127.0.0.1` | `flask run` binds to loopback only — the reason a source checkout is not reachable from another machine on the LAN until this is changed. |
| `FLASK_RUN_PORT` | `.flaskenv:4`, read by the `flask` CLI | No | `5000` | `flask run` listens on 5000. |

### 1b. Variables that belong to the test suite only

`TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_USER`, `TEST_DB_PASSWORD`, `TEST_DB_NAME` (`config.py:52-56`), defaulting to `localhost`, `3307`, `inventory_test_user`, `test_password`, `workshop_inventory_test`. `CI` (`noxfile.py:55,164`) is set by GitHub Actions, not by a person. These belong to the development and testing guide, not to a deployment reference (spec FR-022).

### 1c. Named in the deployment guide, read by nothing

`FLASK_ENV` (removed from Flask in 2.3; this project pins Flask 3.1.3), `STORAGE_BACKEND` (an `app.config` key set inside `create_app` at `app/__init__.py:118`, never from the environment), `SQLALCHEMY_TRACK_MODIFICATIONS` (set to `False` in code at `config.py:12`), `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_TOKEN_PATH` (misspellings of the two real names), `APP_NAME`, `APP_VERSION` (the version comes from `pyproject.toml` via `app/version.py`), `CACHE_TTL`, `BATCH_SIZE` (read nowhere in the repository). Nine names, all of which an operator can set to anything with no effect.

**Rationale for the both-directions check**: the guide's failure is not that it is short. It is that a reader cannot tell which half of it is real, and the DigiKey omission means the half that matters most is the missing half.

**Alternatives considered**: a nox session or CI job that diffs the documented set against the read set, failing the build on drift. Rejected under Principle I — standing machinery for a problem observed once, in a project whose configuration surface changes about twice a year. The check lives in `quickstart.md` as two `grep` commands for whoever next has reason to run it.

---

## 2. The vendor capability matrix

**Decision**: three vendors, four distinct capabilities, and one of the three requires configuration. The full table is `contracts/vendor-capability-matrix.md`; this section records how each cell was established.

**Whole-order capture** — three vendors, registered in one registry (`app/services/order_vendors.py:169`, populated from `app/catalog_service.py`):

- **DigiKey** (`app/catalog_service.py:4024`): entered as a sales order number at *Products → Capture a DigiKey Order* (`app/product/routes.py:1134`), fetched from DigiKey's API. `carries_payload=False` — the order is re-fetched at confirmation, because the API is the authority.
- **McMaster-Carr** (`app/catalog_service.py:4056`): the bookmarklet on a McMaster order page (`app/static/js/capture-agent.js:113`, posting to `app/product/routes.py:1578`). `adopts_renames=True`, because McMaster's order "number" is the customer's own editable Purchase Order string.
- **Amazon** (`app/catalog_service.py:4152`): the bookmarklet on `/your-orders/order-details?orderID=...` (`app/static/js/capture-agent.js:110-112`, posting to `app/product/routes.py:1588`). `carries_payload=True` — the page cannot be re-read, so the read rides through confirmation.

**Single-item capture that reads the page** — two vendors:

- **Amazon**, via the general reader `extract()`, which is the fall-through branch for every page the agent does not otherwise recognize (`app/static/js/capture-agent.js:1720-1727`). It reads price, brand, description, the *About this item* bullets, every *Product information* row and every image the page's own data names.
- **McMaster-Carr**, via `mcmasterListing()` on a product-page path (`app/static/js/capture-agent.js:1692-1703`), read against the live document because McMaster renders client-side and a re-fetch returns an unrendered shell.

**Single-item capture from the address alone** — *any* page. The paste-a-URL form at `app/product/routes.py:468` derives the vendor from the host through a closed table (`app/product/routes.py:869-876`): Amazon, DigiKey, Mouser, eBay, McMaster-Carr, AliExpress. Any other host becomes the vendor name verbatim. An ASIN is pulled from an Amazon path and a part number from a McMaster path (`app/product/routes.py:894,929`); nothing else is derived.

**Detail backfill** — **DigiKey only**, and in two places: *Products → Capture a DigiKey Part* (`app/product/routes.py:1644`) fills a whole product — manufacturer, both part numbers, description, datasheet, photograph, category and parametric specifications; and `enrich_product` (`app/catalog_service.py:4048`) writes the same detail onto a product an order line *matched*, filling gaps only, so a value the operator has already set always wins.

**Configuration** — DigiKey alone needs any (§1a). Amazon and McMaster-Carr need nothing beyond the bookmarklet, because the operator's own browser does the reading.

### The distinction that must not be blurred

Mouser, eBay and AliExpress appear in the host table and nowhere else. Being on it buys them a tidier vendor *name* than the bare host, and nothing else: no reader is written for their markup, so the bookmarklet falls through to the general reader on their pages exactly as it does on a site that is not listed at all (`app/static/js/capture-agent.js:1720-1727`). The paste-a-URL path reads no page for anybody.

**The claim to avoid is "no reading of any kind"** -- an earlier draft of the manual said exactly that, and it is wrong: the general reader does run. What is true is that nothing was written *for them*. Calling them "supported vendors" is wrong in the other direction. Spec FR-013 exists for this sentence, and the contract table gives them their own row group.

**Alternatives considered for where the summary lives**: a new `docs/vendor-support.md`. Rejected — a reader asking "can I capture this?" is already in the user manual, and a fifth document to keep in step with the code is the cost. It goes at the head of the catalog part of the manual, before the per-vendor sections it summarizes.

---

## 3. Document disposition and link audit

**Every file directly under `docs/`, against spec FR-002's criterion:**

| File | Status | Basis |
|------|--------|-------|
| `category-taxonomy.md` | Keep | Documents the shipped taxonomy; linked from the deployment guide and the manual. |
| `deployment-guide.md` | Keep, edit | Current deployment reference. |
| `development-testing-guide.md` | Keep, one-line edit | Current development reference. |
| `materials-taxonomy-design.md` | Keep | Describes the three-level `MaterialTaxonomy` design the application still implements (`app/database.py`, used at `app/mariadb_materials_admin_service.py:61-68`). Old (last touched 2025-09-28) but not wrong. |
| `troubleshooting-guide.md` | Keep, unchanged | Current diagnostic reference. Expected to need a vendor correction; it makes no vendor claim, so it did not. |
| `user-manual.md` | Keep, edit | Current behavior reference. |
| `product-functionality-gap.md` | **Remove** | A list of what an abandoned branch planned; over half of it is now struck through as built, and the largest remaining item — capture not reading the price — was closed with issue #56. |
| `spec-product-catalog.md` | **Remove** | The input document `specs/001-product-catalog/spec.md` was written from and duplicates (that spec's own header cites it). |
| `features/` (28 files) | **Remove** | `README.md` instructs an agent to follow a per-feature workflow Spec Kit replaced; `complete/` is 26 finished feature documents, last touched 2026-07-18. |

**Link audit** — searched every tracked `.md`, `.py`, `.yml`, `.yaml`, `.html`, `.toml` and `.txt` outside `venv/` and `.git/` for the three removal targets:

- References from **`specs/**`**: twelve, across features 001, 004, 005, 006, 008, 009 and 011. Left alone — `specs/` is frozen (spec FR-006), and a frozen record naming a document that has since been deleted is still an accurate record of what was true when it was written.
- References from **inside the removal set to itself**: six, all within `docs/features/`. They leave with it.
- References from **anywhere else**: **none.** Not from `README.md`, not from any surviving guide, not from `CLAUDE.md`, `.github/`, or `tests/`.

So the removal is a `git rm` and no repair work (spec FR-005 costs nothing here).

**Images**: `docs/product-functionality-gap.md` and the `docs/features/` set name two image paths that no surviving document names — `docs/images/screenshots/user-manual/inventory_list.png` and `docs/images/steel_rod_sample.jpg`. **Neither file exists**; both are already-dead links inside documents that are being deleted. No image work at all. Separately, `tests/e2e/screenshot_config.yaml`'s `used_in` entries name only `README.md`, `docs/deployment-guide.md`, `docs/development-testing-guide.md` and `docs/user-manual.md`, so the removals leave it accurate — and nothing validates `used_in` anyway (`nox -s screenshots_verify` checks PNG validity, color mode and file size only, `noxfile.py:189-215`).

---

## 4. Reasoning that exists only in a removal candidate (FR-007)

Each section of `docs/product-functionality-gap.md`, checked for whether its reasoning still applies and whether it is recorded elsewhere:

| Section | Still applies? | Recorded elsewhere? | Action |
|---------|----------------|---------------------|--------|
| Order capture — description at capture, editable at receipt, duplicates, recycled item numbers | No, all built (feature 006) | `specs/006-*`, user manual | Goes with the file |
| Order capture — the price isn't captured | **No.** Closed: the bookmarklet reads price (features 007, 028, 029), and issue #56 is closed | `specs/007-*`, user manual | Goes with the file |
| Reordering and stock — flag age, receiving and counts | No, built (feature 008) | `specs/008-*`, user manual | Goes with the file |
| Grouping products that are the same thing | Yes — still not built | Stated in the document itself as "a deliberate decision recorded in the current spec", i.e. `specs/001-product-catalog/spec.md` | Goes with the file |
| Organising the catalog — renames, shared vocabulary, structured specifications | No, all built (features 004, 005); the manual documents renames at `docs/user-manual.md:1625` and the shared vocabulary in its *Locations and Vendors: One Shared Vocabulary* section | `specs/004-*`, `specs/005-*`, user manual | Goes with the file |
| Finding things — 2D barcodes, notes search, code-as-address | No, built (feature 009) | `specs/009-*`, user manual | Goes with the file |
| Labels — no "if found, return to" line; the printed code is a conventional barcode rather than a 2D symbol | **Yes**, both are still true of the label as printed | **No.** The manual's label section (`docs/user-manual.md:1469-1492`) says what a label carries, never why it does not carry these | **Carry over**: one sentence in the manual's label section recording that the barcode is a deliberate choice — the functional goal is a code that cannot be mistaken for a vendor's, which either form meets — and that ownership text is not printed |
| "Where the current application is ahead" | Partly — but it is a comparison against a branch that no longer exists | The behaviors themselves are documented in the manual | Goes with the file |

`docs/spec-product-catalog.md` needs no carry-over: `specs/001-product-catalog/spec.md` was written from it and preserves its content.

`docs/features/` needs no carry-over: each document describes a feature that shipped, and the shipped behavior is in the manual. The workflow instructions in its `README.md` are the thing being retired, not preserved.

---

## 5. Found while verifying, deliberately not fixed

Both are application-code observations. This feature touches no code, and neither is a documentation defect — they are recorded so the next person does not have to re-derive them.

1. **`validate_config()` is defined on `TestConfig`, not `Config`** (`config.py:95`), yet it reads `Config.SQLALCHEMY_DATABASE_URI` and `Config.GOOGLE_*`. It works — `manage.py:506` calls it and gets the production values — but it reads as a mistake and would surprise anyone editing it.
2. **`DISABLE_LABEL_PRINTING` is honored but unreachable from the environment.** It is read at `app/services/label_printer.py:92` and `app/services/product_label.py:348`, and nothing anywhere sets it from `os.environ` — only `TESTING` does the same job in the test fixtures. Documenting it as an environment variable would create exactly the class of falsehood this feature removes, so it is documented as an in-code test seam or not at all (spec FR-026).

---

## 6. What the guide's two configuration examples must reconcile to

The Docker section (`docs/deployment-guide.md:58-78`) and the from-source section (`:172-205`) currently disagree with each other as well as with the code: the Docker example alone names `CUPS_SERVER` and the correct `GOOGLE_*_FILE` names; the from-source example alone names `STORAGE_BACKEND`, `APP_NAME` and the rest of the invented set. Neither names DigiKey.

**Decision**: one reference table (`contracts/configuration-reference.md`) is the source, and each section carries a short worked example drawn from it, differing only in what genuinely differs — the container is configured with `--env-file` and reads no `.env` (there is none in the image, `Dockerfile:55-57` — only `config.py`, `manage.py`, `wsgi.py`, `app/` and `migrations/` are copied in), while a from-source deployment gets its values from `.env` at the repository root via `load_dotenv` (`config.py:5`). `.env.example` then matches the from-source example (spec FR-024).
