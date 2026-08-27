---

description: "Task list for 030-product-docs-refresh"
---

# Tasks: Product Documentation Refresh

**Input**: Design documents from `/specs/030-product-docs-refresh/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: No test tasks. Nothing behavioral changes, so there is no behavior to cover — the existing suites run once in the final phase as a regression check, unchanged and unmodified (plan.md, Constitution Check IV).

**Organization**: One phase per user story, in spec priority order. Each phase is one commit and is independently reviewable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: [US1] configuration, [US2] vendors, [US3] removals
- Every task names the file it touches

## Path Conventions

Documentation only: `README.md`, `.env.example`, `docs/*.md` at the repository root. No task touches `app/`, `tests/` or `migrations/` — that is checkable as SC-008 in T024.

**The two contracts are the source of every claim written below.** Do not re-derive facts from the documents being edited; they are what is wrong. `contracts/configuration-reference.md` is the authority for US1, `contracts/vendor-capability-matrix.md` for US2, and `research.md` carries the file:line each fact was read from.

---

## Phase 1: Setup

**Purpose**: Somewhere to put the work

- [X] T001 Create branch `030-product-docs-refresh` from `main` and confirm a clean working tree with `git status --short`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Confirm the Phase 0 ground truth still describes `HEAD` before anything is written from it. Both US1 and US2 are written entirely from facts captured on 2026-08-27; if a commit has landed since, they are re-derived before they are copied into prose, not after.

**⚠️ CRITICAL**: No user story work begins until T002 and T003 pass.

- [X] T002 Re-run the both-directions configuration comparison from `specs/030-product-docs-refresh/quickstart.md` §1 and confirm the read-set is exactly the seventeen deployment variables plus `HTTP_X_FORWARDED_PORT` and the five `TEST_DB_*`; if it differs, update `contracts/configuration-reference.md` and `research.md` §1 before proceeding
- [X] T003 [P] Re-confirm the vendor registry still holds exactly three vendors by checking `order_vendors.register(` call sites in `app/catalog_service.py` and the `pageKind` branches in `app/static/js/capture-agent.js`; if a fourth exists, update `contracts/vendor-capability-matrix.md` and `research.md` §2 before proceeding

**Checkpoint**: The contracts describe the application as it is today. Story work can begin.

---

## Phase 3: User Story 1 - Configure a deployment from the guide alone (Priority: P1) 🎯 MVP

**Goal**: An operator configures a working deployment, DigiKey included, from `docs/deployment-guide.md` alone — and every variable named in it does something.

**Independent test**: Run quickstart §1 and §2. The documented set and the read set match in both directions; the four questions in §2 are answerable from the guide without opening `config.py`.

- [X] T004 [US1] Replace the environment-variable block in `docs/deployment-guide.md` (the "1. Environment Variables" subsection, currently lines 174-205) with the full reference from `contracts/configuration-reference.md`: all seventeen variables, each stating what it does, required-or-optional, its default, and what is absent or fails when unset (FR-018, FR-020). Delete `FLASK_ENV`, `STORAGE_BACKEND`, `SQLALCHEMY_TRACK_MODIFICATIONS`, `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_TOKEN_PATH`, `APP_NAME`, `APP_VERSION`, `CACHE_TTL` and `BATCH_SIZE` outright (FR-019)
- [X] T005 [US1] Add a DigiKey subsection to the Configuration section of `docs/deployment-guide.md` carrying the four setup steps from `contracts/configuration-reference.md` — Production App, the Product Information and Order Status subscriptions (never Ordering), the `https://localhost` callback, and where the account number comes from — plus what is absent when the variables are unset: both DigiKey screens render and say they are not configured, and nothing else changes (FR-021). Placeholders only, never a credential value
- [X] T006 [US1] Reconcile the Docker `inventory.env` example in `docs/deployment-guide.md` (lines 64-78) with the new reference: add the DigiKey four and the taxonomy pair, keep `CUPS_SERVER`, and state that the image contains no `.env` and reads none (FR-023)
- [X] T007 [US1] State in the from-source part of `docs/deployment-guide.md` that values come from `.env` at the repository root, and that the committed `.flaskenv` already supplies `FLASK_APP=wsgi.py`, `FLASK_DEBUG=1`, `FLASK_RUN_HOST` and `FLASK_RUN_PORT` for `flask run` — so a source checkout runs with debug **on** — while gunicorn reads none of it and the file is not copied into the image (FR-023, research.md §1a)
- [X] T008 [US1] Correct the `FLASK_APP=app.py` line in `docs/deployment-guide.md` to match the repository's own `.flaskenv` value `wsgi.py`, or drop it as already-set (contracts/configuration-reference.md, "The set that must be removed")
- [X] T009 [US1] Move the `TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_USER`, `TEST_DB_PASSWORD` and `TEST_DB_NAME` settings with their defaults into `docs/development-testing-guide.md`, and ensure they appear nowhere in `docs/deployment-guide.md` as deployment settings (FR-022)
- [X] T010 [US1] Replace `export FLASK_APP=app.py` and `export FLASK_ENV=development` in `docs/development-testing-guide.md` (lines 422-424) — `.flaskenv` already sets `FLASK_APP=wsgi.py`, and `FLASK_ENV` has had no effect since Flask 2.3 while this project pins 3.1.3 (plan.md, Deviations)
- [X] T011 [P] [US1] Update `.env.example` to cover the same set the from-source deployment documents — it is currently missing `SQLALCHEMY_DATABASE_URI` entirely — or state in it which variables it deliberately omits (FR-024)
- [X] T012 [US1] Update the Table of Contents in `docs/deployment-guide.md` (lines 3-40) for any subsection added or renamed by T004-T009
- [X] T013 [US1] Confirm `DISABLE_LABEL_PRINTING` appears nowhere in `docs/deployment-guide.md` or `.env.example` as an environment variable; it is honored in code and set from no environment (FR-026, research.md §5)
- [X] T014 [US1] Run the quickstart §1 checks and the §2 reading, and fix what they surface (SC-001, SC-002, SC-003)
- [X] T015 [US1] Commit the configuration work with a message naming what was removed as unread and what was added for DigiKey

**Checkpoint**: US1 is deliverable on its own. A deployment configured from the guide now gets DigiKey, and no setting in the guide is inert.

---

## Phase 4: User Story 2 - Find out which vendors are supported, and for what (Priority: P2)

**Goal**: One place in the manual, and one line in the README, answer "which vendors, and for what" without reading three long sections.

**Independent test**: Run quickstart §3. Answer "which vendors can I capture an order from, and does any of them need setting up?" from the README plus one manual section, in under a minute.

- [X] T016 [US2] Add a *Which Vendors Are Supported* section to `docs/user-manual.md`, immediately before *Capturing an Order When You Place It* (line 1017), carrying the matrix from `contracts/vendor-capability-matrix.md`: the four capabilities kept distinct — whole order, one item with the page read, one item from the address alone, detail backfill — against Amazon, DigiKey, McMaster-Carr and everything else (FR-009, FR-010, FR-011, FR-012)
- [X] T017 [US2] In that section, state what an unrecognized site yields: the address can still be pasted, the vendor name is derived from the host, and the closed list Amazon/DigiKey/Mouser/eBay/McMaster-Carr/AliExpress gives a tidier name than the bare host — while Mouser, eBay and AliExpress get **only** a name and no reading of any kind (FR-013)
- [X] T018 [US2] In that section, state that DigiKey is the only vendor needing configuration, that without it both DigiKey screens say so and everything else works, and link to the DigiKey subsection T005 added to `docs/deployment-guide.md` (FR-014)
- [X] T019 [US2] Insert the new section into the numbered Table of Contents of `docs/user-manual.md` (lines 5-45), renumbering the entries after it, and add the missing *Amazon Orders* sub-entry alongside *DigiKey Orders* and *McMaster-Carr Orders* — the body has had that section since feature 029 and the contents never listed it
- [X] T020 [P] [US2] Rewrite the Product Catalog bullet in `README.md` (line 17) to name the vendors for all three capture capabilities and for backfill, and link to the manual section rather than repeating the matrix (FR-015)
- [X] T021 [P] [US2] Verify `docs/troubleshooting-guide.md` makes no vendor or capture claim — `grep -in 'digikey\|mcmaster\|amazon\|capture' docs/troubleshooting-guide.md` currently returns nothing for the vendors — and correct anything it does say against `contracts/vendor-capability-matrix.md` (FR-017). No claim, no edit
- [X] T022 [US2] Check every vendor claim written in T016-T021 against the code paths cited in `research.md` §2, not against any pre-existing document (FR-016, SC-005), and confirm the vendor names are spelled `Amazon`, `DigiKey`, `McMaster-Carr` throughout — never `Digi-Key`
- [X] T023 [US2] Run the quickstart §3 checks, then commit the vendor work

**Checkpoint**: US1 and US2 are both deliverable. The vendor question is answerable in one place, and it points at a configuration section that already exists.

---

## Phase 5: User Story 3 - Trust that everything in docs/ describes the application as it is (Priority: P3)

**Goal**: Every file under `docs/` describes the application, its deployment, its development, or a design it still implements.

**Independent test**: Run quickstart §4. The three targets are gone, and nothing outside `specs/` references them.

- [X] T024 [US3] Carry the one piece of reasoning that survives its document into `docs/user-manual.md`'s *Printing Product Labels* section (line 1469): the printed code is a conventional barcode by choice — the goal is a code that cannot be mistaken for a vendor's or a distributor's, which either form meets — and the label carries no ownership or return-to-owner line (FR-007, research.md §4). This is the only carry-over; every other section of the removed document is built, superseded, or recorded in `specs/`
- [X] T025 [US3] `git rm docs/product-functionality-gap.md` (FR-001)
- [X] T026 [P] [US3] `git rm docs/spec-product-catalog.md` — the input `specs/001-product-catalog/spec.md` was written from and duplicates (FR-003)
- [X] T027 [P] [US3] `git rm -r docs/features/` — all 28 files: the instructional `README.md` for a workflow Spec Kit replaced, `TEMPLATE.md`, and 26 completed feature documents under `complete/` (FR-004)
- [X] T028 [US3] Run the quickstart §4 link audit and confirm no tracked file outside `specs/` references any removed path; leave every reference under `specs/` alone, dangling and correct as a frozen record (FR-005, FR-006, SC-007)
- [X] T029 [US3] Commit the removals and the T024 carry-over as one commit containing nothing else, so it reverts on its own (FR-008)

**Checkpoint**: All three stories delivered.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 [P] Confirm American spelling across everything written: `grep -ric "catalogue" README.md docs/ app/ tests/` returns zero for every file (`CLAUDE.md`)
- [X] T031 [P] Confirm nothing outside documentation moved: `git diff --name-only main...` shows no path under `app/`, `tests/` or `migrations/`, and nothing under `specs/` outside `specs/030-product-docs-refresh/` (SC-008)
- [X] T032 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` as a regression check (SC-009)
- [X] T033 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` **detached** and poll — about 13m 45s warm, which outlasts a 10-minute agent bash cap — then confirm `git status` is still clean, since an e2e run must leave the working tree untouched (SC-009, Constitution IV)
- [X] T034 Read the three commits as a reviewer would: `git log --oneline main..HEAD` shows configuration, vendors, removals, and the removals commit contains deletions plus the T024 sentence and nothing else
- [X] T035 Push `030-product-docs-refresh` to origin and open the pull request against `main`, naming issue #124 and listing the nine unread variables removed, the vendor summary added, and the 28 files deleted (FR-027)

---

## Dependencies & Execution Order

**Phase order**: Setup (T001) → Foundational (T002-T003) → US1 (T004-T015) → US2 (T016-T023) → US3 (T024-T029) → Polish (T030-T035).

**Story dependencies**:

- **US1 → US2**: one real edge. T018 links to the DigiKey subsection T005 creates; writing the link first means writing a link to a section that does not exist yet.
- **US2 → US3**: not a dependency, an ordering convenience. T024 and T019 both edit `docs/user-manual.md`; doing the manual's structural work (T016-T019) before the one-sentence carry-over avoids editing the same file from two directions.
- **US3 stands alone.** Its three removals depend on nothing and could be done first; they are last because they are the cheapest to review and the easiest to revert, and holding them there keeps the two rewrites out of a diff full of deletions.

**Within US1**: T004 comes first — the reference table is what T005-T008 and T012 hang off. T009, T010 and T011 touch different files and can go any time after T004.

**Within US2**: T016 comes first; T017 and T018 extend the section it creates. T020 and T021 touch different files entirely.

**Within US3**: T024 before T025, because the reasoning must land somewhere before its document is deleted (FR-007).

## Parallel Opportunities

Genuinely independent, by file:

- **Foundational**: T003 runs alongside T002.
- **US1**: T011 (`.env.example`) is independent of every deployment-guide task. T009 and T010 both touch `docs/development-testing-guide.md`, so they run together but not in parallel with each other.
- **US2**: T020 (`README.md`) and T021 (`docs/troubleshooting-guide.md`) are independent of the manual work and of each other.
- **US3**: T026 and T027 are separate paths; T025 is separate again. All three are one `git rm` invocation in practice.
- **Polish**: T030 and T031 are independent greps.

The parallelism here is small and honest — this is a documentation feature, and four of its six files are edited by one story each.

## Implementation Strategy

**MVP is US1 alone.** It is the only story whose absence produces a broken deployment: an operator following today's guide gets an application with no DigiKey capture and four settings that do nothing. Ship T001-T015 and that is fixed, whether or not the other two ever land.

**Then US2**, which costs a reader time rather than correctness, and **then US3**, which costs nothing at all — it removes confusion, not defects.

Each phase is one commit and one reviewable increment. If the work is interrupted after any checkpoint, what is committed is coherent on its own.
