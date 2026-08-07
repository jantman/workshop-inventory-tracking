<!--
Sync Impact Report
==================
Version change: 1.2.0 → 1.3.0
Bump rationale: Principle IV's waiting rule now binds every E2E test without exception for
pre-existing call sites. The tolerance for already-committed fixed waits, recorded in the
1.2.0 entry below, is retired because the set it covered has been cleared. The only
surviving exception is a condition that genuinely cannot be observed, justified in writing
at the call site. Existing guidance was materially expanded — a rule that bound new tests
now binds all of them — and none was inverted. MINOR under the versioning policy.

Modified principles:
  - IV. Test Discipline Through Nox        → waiting rule applies to all tests, not only
                                             new ones; sole exception is an unobservable
                                             condition justified at the call site

Migration path: `specs/003-e2e-remove-timed-waits/` did the work. Every fixed-duration wait
in `tests/e2e/` is either gone or carries a written justification naming the condition that
cannot be observed. No migration is outstanding.

Follow-up TODOs: none.

--- previous entry ---
Version change: 1.1.0 → 1.2.0
Bump rationale: Principle IV gained three rules — a corrected E2E timeout allowance, the
exclusion of screenshot generation from the E2E gate (a test run must leave the working
tree clean), and a prohibition on time-based waits in E2E tests. Existing guidance was
materially expanded and none was inverted. MINOR under the versioning policy.

Modified principles:
  - IV. Test Discipline Through Nox        → timeout 20min → 15min; screenshot exclusion;
                                             time-based waits prohibited

Migration path: `specs/002-e2e-test-performance/` did the work. `tests/e2e/` no longer uses
`networkidle`; the remaining `wait_for_timeout` call sites were listed as deferred in that
feature's plan, to be cleared by a follow-up — no *new* ones could be added meanwhile.
`specs/003-e2e-remove-timed-waits/` cleared them; see the 1.3.0 entry above.

--- previous entry ---
Version change: 1.0.0 → 1.1.0
Bump rationale: A new principle was added (Simplicity) and existing guidance was
materially rescoped to the project's actual operating context (single user, LAN-only).
No principle was removed, and no existing rule was inverted — the security guidance was
narrowed to a stated threat model rather than deleted. MINOR under the versioning policy.

Modified principles:
  - (new)                                   → I. Simplicity First (NON-NEGOTIABLE)
  - I. Layered Architecture Boundaries       → II. Layered Architecture Boundaries
  - II. Exact Numerics for Physical Measurements → III. Exact Numerics for Physical Measurements
  - III. Test Discipline Through Nox         → IV. Test Discipline Through Nox
  - IV. MariaDB Is the Source of Truth       → V. MariaDB Is the Source of Truth
  - V. Item Lifecycle and History Invariants → VI. Item Lifecycle and History Invariants

Added sections:
  - Operating Context and Threat Model (new; absorbs and rescopes the security guidance
    previously in "Technology and Security Constraints")

Removed sections:
  - Technology and Security Constraints (renamed to "Technology Constraints"; its security
    content moved to "Operating Context and Threat Model")

Follow-up TODOs: none
-->

# Workshop Inventory Tracking Constitution

## Core Principles

### I. Simplicity First (NON-NEGOTIABLE)

This is a single-user application for tracking materials and supplies in a hobby workshop.
It runs on a home network and is reachable only from the LAN. Every design decision MUST be
sized to that reality.

- **Build for the requirement in front of you.** Speculative generality is prohibited: no
  abstraction, hook, plugin point, or configuration knob added for a future that has not
  arrived. One implementation needs no interface.
- **No premature optimization.** Caching, batching, indexing beyond the obvious, async
  work, and background job machinery REQUIRE a measured, observed problem. "This might be
  slow with a lot of items" is not a measurement. The coverage gate is set to 1% and the
  unit suite runs in under a second — that is deliberate, not an oversight to correct.
- **No scale machinery.** Multi-tenancy, user accounts and roles, rate limiting,
  horizontal scaling, queues, and service decomposition are out of scope. The application
  has no login and does not need one.
- **Dependencies MUST earn their place.** Prefer the standard library and what is already
  in `requirements.txt` over a new package.
- **Prefer boring, obvious code.** Fewer moving parts beats clever. A reader who knows
  Python and Flask should be able to follow any file top to bottom.

When this principle conflicts with another, simplicity generally wins — with one exception:
it never licenses violating the data-integrity principles (III, V, VI). Losing or corrupting
inventory data is the one failure this project cannot absorb; everything else can be fixed
later, simply.

Rationale: the cost of over-engineering here is not paid by a team or a business — it is
paid by one person maintaining a workshop tool in their spare time. Complexity that would be
a reasonable investment in a production SaaS is pure loss in this context.

### II. Layered Architecture Boundaries

The application MUST preserve four distinct layers, and code MUST NOT collapse them:

- **Domain models** (`app/models.py`): `@dataclass` types and `Enum` definitions. All
  domain validation logic lives here.
- **ORM models** (`app/database.py`): SQLAlchemy `Base` and `InventoryItem`. Conversion
  between dataclasses and ORM rows happens explicitly at the storage boundary.
- **Storage** (`app/storage.py`, `app/mariadb_storage.py`): every persistence path goes
  through the `Storage` ABC and returns a `StorageResult(success, data, error,
  affected_rows)`. Callers MUST check `result.success`; storage MUST NOT raise across
  that boundary.
- **Services** (`app/*_service.py`, `app/services/`): all business logic. Routes in the
  `main` and `admin` blueprints MUST stay thin — no raw SQL and no ORM queries in routes.

The Flask app MUST be constructed via `create_app(config_class, storage_backend=None)`,
and route code MUST read the backend from `app.config['STORAGE_BACKEND']` rather than
instantiating storage inline.

This is the one structural investment the project keeps, because it already exists and it
earns its keep: unit tests run against SQLite through the same interface production uses
against MariaDB. Per Principle I, do not extend the layering further — new abstraction
layers, repositories, or DTO tiers are not warranted.

Rationale: the existing seam is what makes the test suite fast and the business logic
testable. A single leak — one ORM query in a route — breaks that property.

### III. Exact Numerics for Physical Measurements

All dimensions, lengths, and other physical quantities MUST use `decimal.Decimal` with
`ROUND_HALF_UP` normalization. Introducing `float` arithmetic for any measured quantity
is prohibited, including in parsing, display formatting, comparison, and search filters.

Rationale: this is a machinist's inventory. Fractional-inch notation and stock lengths
must round-trip exactly; binary floating point silently corrupts them.

### IV. Test Discipline Through Nox

- Tests MUST be run through `nox` sessions (`tests`, `e2e`, `coverage`, `lint`), never
  by invoking `pytest` directly.
- The `e2e` session MUST be given at least a 15-minute timeout by whatever tool or agent
  runs it; it installs Playwright browsers and retries with `--reruns=3`. The suite itself
  runs in well under 10 minutes on a warm environment — the margin is for a cold start.
- `--strict-markers` is enabled. Any new pytest marker MUST be registered in `pytest.ini`
  before use.
- The `e2e` session MUST NOT run screenshot-generation tests (`-m "e2e and not
  screenshot"`). Those tests write into `docs/images/screenshots/`, so including them made
  the test suite modify tracked files. **Running a test session MUST leave the working tree
  clean.**
- E2E tests MUST wait on observable application state, never on elapsed time.
  `page.wait_for_timeout(...)`, `time.sleep(...)` and `wait_for_load_state("networkidle")`
  are prohibited in `tests/e2e/`. This binds every test, not only new ones; no call site is
  exempt for having been written first. The sole exception is a condition that genuinely
  cannot be observed, and it MAY be taken only with a written justification at the call
  site naming that condition. How to find the condition to wait on is practice, not
  governance: it lives in `CLAUDE.md`.
- Unit tests run with the network blocked (`--blockage`). Unit tests MUST mock all HTTP
  and external API calls.
- Unit tests MUST build fixtures through `tests/conftest.py` (`test_storage` → `app` →
  `client`) rather than constructing an app or storage by hand.
- Changes that alter behavior MUST land with tests covering that behavior, and
  `nox -s tests` and `nox -s e2e` MUST pass before a change is merged.

Test *coverage* is deliberately not a target — there is no percentage to chase. Write the
test that would have caught the bug, and stop.

Rationale: the nox sessions encode environment setup (Python 3.13, Playwright, container
config) that bare `pytest` does not. Divergent invocation produces results that do not
predict CI. The waiting rule is not style: fixed delays were over half of every E2E test
body and cost 12 minutes a run, and a delay that is long enough today is a flake tomorrow.

### V. MariaDB Is the Source of Truth

- MariaDB (via PyMySQL) is the sole primary datastore. Google Sheets integration is
  **export-only and legacy**; no feature may treat it as live storage.
- Every schema change MUST ship as an Alembic revision applied through
  `python manage.py db ...`. Hand-editing the database, or calling `create_all` outside
  of test fixtures, is prohibited.
- Migrations MUST be reversible: each revision MUST provide a `downgrade` that has been
  exercised, with operation ordering valid on MariaDB (indexes and foreign keys dropped
  in dependency-safe order).

Rationale: a single authoritative store with versioned, reversible migrations is what
makes an upgrade recoverable when it goes wrong on a Saturday afternoon.

### VI. Item Lifecycle and History Invariants

Inventory items carry identity and history semantics that MUST be preserved by any change
touching add, move, shorten, edit, or search paths:

- JA-ID identifiers follow the `JA######` format and identify an item across its history.
- Shortening produces multi-row history: exactly one row per JA ID is active, and prior
  rows are retained as inactive history.
- Parent-child relationships between items MUST remain consistent after any mutation.
- Queries that present "current inventory" MUST filter to active rows.

Any change to these paths MUST be covered by the dedicated E2E tests for active-status and
history behavior.

Rationale: history is the audit trail for physical stock. A lost or duplicated active row
makes the inventory unreliable in ways the user cannot detect from the UI.

## Operating Context and Threat Model

The application is deployed on a home LAN, used by one trusted person, and is not exposed
to the Internet. The threat model follows from that and MUST NOT be inflated:

- **In scope:** not losing data, not corrupting item history, and not committing secrets to
  the repository. `.env`, `credentials.json`, and `token.json` stay untracked, and
  credentials are never hardcoded.
- **Out of scope:** anonymous attackers, hostile input from untrusted users, brute-force
  and enumeration defenses, rate limiting, session hardening, CSP tuning, and dependency
  CVE triage as a merge gate. The `security.yml` workflow is informational; it does not
  block work.
- **No authentication layer.** The app intentionally has no login, users, roles, or
  permissions. `app/auth.py` is Google OAuth for the Sheets *export* only, not application
  access control. Adding an auth system REQUIRES a change to this constitution.
- **Validation serves correctness, not defense.** Validate input because bad data breaks
  the inventory, not because the input might be malicious. Sanitization layers added
  against injection by an imagined attacker are prohibited.
- **CSRF protection stays enabled** because it is already wired up and costs nothing to
  keep; tests disable it via `WTF_CSRF_ENABLED = False`. This is not an invitation to add
  further hardening.

## Technology Constraints

- **Runtime:** Python 3.13, Flask 3.1.x with the app-factory pattern, SQLAlchemy 2.0.x,
  Alembic, Jinja2 + Bootstrap 5.3.2 server-rendered UI. Server-rendered HTML is the UI
  strategy; introducing a frontend framework or build step REQUIRES amending this document.
- **SQLAlchemy style:** the codebase predominantly uses the legacy `Query` API. New code
  MUST match the surrounding file's style; working `session.query(...)` code MUST NOT be
  refactored to `select()` gratuitously. Raw SQL passed to `.execute()` MUST be wrapped in
  `sqlalchemy.text(...)`.
- **Typing:** public functions and methods MUST carry type hints, consistent with the
  existing codebase.
- **Error handling:** use the project's custom exceptions (`app/exceptions.py`) and the
  centralized handlers installed by `create_error_handlers(app)` rather than ad-hoc error
  responses. Do not add new error-handling machinery on top of them.
- **Standalone API client:** `app/api_client.py` MUST depend only on the standard library
  plus `requests`. It MUST NOT import from the rest of the `app` package. Its `__all__`
  surface is a contract — additive changes are permitted; renames and removals are
  breaking changes requiring a stated migration note.

## Development Workflow and Quality Gates

- **Branching:** non-trivial code changes MUST be developed on a feature branch and merged
  via pull request. Documentation-only and planning artifacts may go directly to `main`.
- **CI gates:** `test.yml` (unit tests, coverage, E2E) MUST be green before merge. A red
  gate is never waived by re-running until it passes; the underlying flakiness or failure
  MUST be fixed.
- **Screenshots:** changes to `app/templates/**`, `app/static/css/**`, or
  `app/static/js/**` REQUIRE regenerating documentation screenshots
  (`nox -s screenshots` or `screenshots_headless`) and committing them alongside the UI
  change. Screenshots MUST pass `nox -s screenshots_verify`: valid PNG, RGB/RGBA, under
  500KB. CI blocks merge on stale screenshots.
- **Style:** `nox -s lint` (flake8, black, isort) is advisory and not part of the default
  session set. New code SHOULD satisfy it, but mass reformatting of existing files is
  prohibited because it destroys review signal.
- **Module placement:** routes in blueprint packages (`app/main`, `app/admin`), services as
  `*_service.py`, shared services in `app/services/`, helpers in `app/utils/`. Modules and
  functions use `snake_case`; classes use `PascalCase`; test files are `test_*.py`.
- **Local commands:** project commands MUST be run against the repository virtualenv
  (`venv/`).

## Governance

This constitution supersedes conflicting practice, habit, or convenience. Where it and
another project document disagree, this document wins and the other document MUST be
corrected.

**Amendment procedure.** Amendments are proposed as a change to this file, accompanied by
a Sync Impact Report at the top recording the version change, modified principles, and
added or removed sections. An amendment that invalidates existing code MUST state the
migration path for that code.

**Versioning policy.** This document is versioned semantically:

- **MAJOR** — a principle is removed or redefined in a backward-incompatible way.
- **MINOR** — a principle or section is added, or existing guidance is materially expanded.
- **PATCH** — clarification, wording, or typo fixes with no change in meaning.

**Compliance review.** Every pull request is reviewed against these principles. The review
question is not only "is this correct?" but "is this the simplest thing that works?"
Unjustified complexity is grounds for rejection, and a reviewer may reject a change purely
for being larger than the problem. A change that violates a principle MUST either be
revised or carry an explicit, written justification in the pull request explaining why the
exception is warranted and what bounds it. Agent-driven work additionally follows the
operational rules in `CLAUDE.md` and `_bmad-output/project-context.md`; those files are
subordinate to this constitution and MUST be updated when it changes.

**Version**: 1.3.0 | **Ratified**: 2026-08-01 | **Last Amended**: 2026-08-06
