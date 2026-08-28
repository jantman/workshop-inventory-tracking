# Feature Specification: Product Documentation Refresh

**Feature Branch**: `030-product-docs-refresh`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "issue #124 on this repo" — *Product documentation updates*: identify and remove vestigial documents in `docs/` (such as `product-functionality-gap.md`); update the user manual, `README.md` and other relevant documents to name the vendors supported for product capture and backfill; update the deployment guide with all required and optional configuration and environment variables.

## Overview

The application's prose has fallen behind its code in three separate ways, and each one costs the operator something different.

`docs/` still carries documents written for work that has since been done, abandoned, or superseded by a frozen specification — a reader cannot tell which of the nine documents describe the application as it is and which describe a road not taken.

Vendor support has grown one feature at a time — Amazon, DigiKey and McMaster-Carr, each arriving separately for orders, for single listings, or for filling in what the catalog already holds. The per-vendor sections of the user manual are thorough, but nowhere states in one place **which vendors are supported and what each one actually gives you**, so the answer to "can I capture this?" is only reachable by reading three long sections.

The deployment guide's environment-variable reference is worse than incomplete: it lists variables the application has never read (`APP_NAME`, `CACHE_TTL`, `BATCH_SIZE`, `GOOGLE_CREDENTIALS_PATH`), and omits every variable that turns DigiKey on. An operator following it configures a deployment that silently lacks the DigiKey screens, and sets four settings that do nothing.

This feature is documentation only. No application behavior changes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure a deployment from the guide alone (Priority: P1)

An operator deploying the application — into Docker or onto a host — reads the deployment guide and configures every setting the application actually honors, without opening `config.py` or `.env.example` to find out what is real. Where a variable is optional, the guide says what the application does when it is unset. Where a variable is required, the guide says so and says what fails without it. Nothing in the guide names a setting the application does not read.

**Why this priority**: This is the only failure of the three that produces a broken deployment. Following the current guide yields an application whose DigiKey order capture and part lookup are silently absent, because the three variables that enable them appear nowhere in it, and yields four settings that look configured and are inert.

**Independent Test**: Take the deployment guide's configuration section and the set of variables the application reads, and compare them in both directions. Every variable the application reads appears in the guide; every variable in the guide is one the application reads. Ship this alone and the deployment problem is fixed regardless of the other two stories.

**Acceptance Scenarios**:

1. **Given** an operator who wants DigiKey order capture and part lookup, **When** they read the deployment guide's configuration section, **Then** they find the DigiKey credentials, the account number, and the API base address, each with what it is for, where to obtain it, and what happens when it is omitted.
2. **Given** an operator reading the deployment guide, **When** they look for a variable named in it, **Then** the application reads that variable — the guide names no setting that has no effect.
3. **Given** an operator who sets nothing optional, **When** they start the application, **Then** the guide has told them in advance which features are consequently absent and which still work.
4. **Given** a deployment that fails to start because a taxonomy override file cannot be read, **When** the operator consults the documentation, **Then** the refusal-to-start behavior and the file format are described where the variable is documented.

---

### User Story 2 - Find out which vendors are supported, and for what (Priority: P2)

Someone looking at the project — the operator months later, or a reader of the README — wants to know which vendors this application can capture from and what "capture" means for each: a whole order, a single listing, or filling in detail the catalog is missing. They get that answer in one place, in a form that distinguishes the three capabilities, and learns which vendor requires configuration before it works at all.

**Why this priority**: The information exists but is spread across three long manual sections; the reader who has not already read them cannot tell whether their vendor is supported. It costs the operator time rather than correctness, which puts it behind the configuration story.

**Independent Test**: Ask the question "which vendors can I capture an order from, and does any of them need setting up?" and answer it from the README and one place in the user manual, without reading the per-vendor sections.

**Acceptance Scenarios**:

1. **Given** a reader on the README, **When** they read the product catalog feature description, **Then** it names the vendors supported for whole-order capture, for single-item capture, and for automatic detail backfill, and points at the manual for the detail.
2. **Given** a reader in the user manual, **When** they reach the product catalog part of it, **Then** one place names every supported vendor against what each supports, before the per-vendor sections go into detail.
3. **Given** a reader whose vendor is not one of the named ones, **When** they read that place, **Then** they learn what still works for an unrecognized vendor — that a listing address can be pasted for anything at all, and how the vendor name is derived from it.
4. **Given** a reader considering DigiKey, **When** they read that place, **Then** they learn that DigiKey alone requires configured credentials and are pointed at the deployment guide for them.

---

### User Story 3 - Trust that everything in docs/ describes the application as it is (Priority: P3)

A reader opening any document under `docs/` is reading either a current description of the application or a document whose purpose is plainly stated as historical. Documents that describe plans never built, or that duplicate a frozen specification, are gone.

**Why this priority**: Nothing is broken by their presence; they cost a reader confidence and time. Removing them is also the cheapest of the three to get wrong — a document that turns out to be the only record of a decision cannot be recovered from prose.

**Independent Test**: Each surviving file under `docs/` can be named as describing current behavior, current configuration, or a design the application still implements. Every removed file can be named as superseded or as describing work that was never built.

**Acceptance Scenarios**:

1. **Given** `docs/product-functionality-gap.md`, which lists what an abandoned branch planned and the application does not do, **When** the documentation set is reviewed, **Then** it is removed.
2. **Given** a document that duplicates a frozen specification under `specs/`, **When** the documentation set is reviewed, **Then** it is removed and the frozen copy remains the record.
3. **Given** a surviving document that links to a removed one, **When** the removal is made, **Then** the link is removed or repointed, so no surviving document links to a file that no longer exists.
4. **Given** a frozen record under `specs/` that links to a removed document, **When** the removal is made, **Then** `specs/` is left untouched — it records what was true when it was written.

---

### Edge Cases

- **A knob that is readable in code but not settable from the environment.** `DISABLE_LABEL_PRINTING` is read from the application's configuration but is never populated from an environment variable. Documenting it as one would be a new false entry of exactly the kind this feature removes. It is documented as what it is, or not at all.
- **A variable consumed by something other than the application.** `CUPS_SERVER` is read by the CUPS client the container invokes, not by application code. It must still be documented, because an operator has to set it — the test is "does setting it change what the deployment does", not "does `config.py` read it".
- **A variable that only exists for the test suite.** The `TEST_DB_*` family configures the test database. It belongs with the development and testing guidance, not in a production deployment reference.
- **Test and development-only guidance in the deployment guide.** Where a variable is only meaningful when running the suite, the guide says so rather than presenting it as a deployment setting.
- **A vendor named in the URL table but with no reader of its own.** An address at Mouser, eBay or AliExpress yields a recognized vendor *name* and nothing more — no page reading, no order capture. Naming those vendors as "supported" without that distinction would over-promise.
- **A document that is the only record of a decision.** Where a removal candidate contains reasoning that is recorded nowhere else, the reasoning is preserved — carried into a surviving document — or the document stays.
- **Screenshots referenced by a removed document.** An image referenced only by a removed document is left in place unless it is referenced nowhere else; images are cheap and a wrongly deleted one is regenerated by a screenshot run, not by hand.

## Requirements *(mandatory)*

### Functional Requirements

#### Removing vestigial documents

- **FR-001**: `docs/product-functionality-gap.md` MUST be removed.
- **FR-002**: Every remaining file directly under `docs/` MUST be assessed against a stated criterion: it describes the application as it currently behaves, describes how to deploy, develop or troubleshoot it, or describes a design the application still implements. A file meeting none of these MUST be removed.
- **FR-003**: `docs/spec-product-catalog.md` MUST be removed. It is the input document that `specs/001-product-catalog/spec.md` was written from and duplicates; that frozen spec is the record.
- **FR-004**: `docs/features/` MUST be removed in its entirety — the instructional README describing a development workflow Spec Kit has replaced, `TEMPLATE.md`, and all twenty-six completed feature documents under `complete/`. The history stays in git; nothing outside that directory links into it.
- **FR-005**: No surviving document under `docs/`, and no other tracked file outside `specs/`, may link to or reference a removed document by path after this feature.
- **FR-006**: `specs/**` MUST NOT be edited by this feature, including where it references a removed document. It is the frozen record of what was specified at the time.
- **FR-007**: Reasoning that exists only in a removed document and still applies to the application MUST be carried into a surviving document before the removal.
- **FR-008**: The removals MUST be committed separately from the documentation rewrites, so that a removal can be reviewed and reverted on its own.

#### Naming the supported vendors

- **FR-009**: One place in the user manual MUST name every supported vendor against what it supports, distinguishing at least: whole-order capture, single-item capture that reads the vendor's page, single-item capture from the address alone, and automatic backfill of catalog detail.
- **FR-010**: That place MUST state, for whole-order capture, that Amazon and McMaster-Carr are captured from their own order pages by the bookmarklet and DigiKey is captured by entering an order number.
- **FR-011**: That place MUST state which vendors' pages are read for a single item — the vendors for which capture brings back price, specifications and images rather than a title — and that any other page yields what its address gives.
- **FR-012**: That place MUST state that DigiKey supplies part detail the other vendors do not: manufacturer, category, datasheet and parametric specifications, both when cataloging a single part and when filling gaps on a product an order line matched.
- **FR-013**: That place MUST state what happens for a vendor with no reader of its own: the address can still be pasted, the vendor name is derived from the site, and a set of named sites derive a tidier name than the bare host.
- **FR-014**: That place MUST state that DigiKey is the only vendor requiring configuration, name what is absent without it, and link to the deployment guide.
- **FR-015**: `README.md` MUST name the supported vendors for order capture, single-item capture and backfill in its product catalog description, and link to the place in the user manual described by FR-009.
- **FR-016**: Every vendor capability claimed by FR-009 through FR-015 MUST be verified against the application's behavior as built, not against a prior document.
- **FR-017**: Documents made inaccurate by a vendor claim elsewhere — the troubleshooting guide's diagnosis of capture problems in particular — MUST be brought into agreement with FR-009's list.

#### Documenting configuration

- **FR-018**: The deployment guide MUST document every environment variable that changes what a deployed application does, including those consumed by a subprocess or client library rather than by application code.
- **FR-019**: The deployment guide MUST NOT name any variable that the application, its startup command, or a tool it invokes does not read.
- **FR-020**: Each documented variable MUST state whether it is required or optional, what it does, its default when unset, and what is absent or fails when it is not set.
- **FR-021**: The DigiKey variables — client id, client secret, account number and API base address — MUST be documented in the deployment guide, including how to obtain them, which API subscriptions are needed, and that leaving them unset disables the DigiKey screens and nothing else.
- **FR-022**: Variables that are meaningful only when running the test suite MUST be documented as such, and MUST NOT appear as deployment settings.
- **FR-023**: The Docker configuration example and the from-source configuration example MUST agree with each other and with the full reference, differing only where the deployment method genuinely differs.
- **FR-024**: `.env.example` MUST cover the same variables the deployment guide documents for a from-source deployment, or state where it deliberately does not.
- **FR-025**: The configuration documentation MUST be verified against the application's actual reads, in both directions: nothing documented that is not read, nothing read that is not documented.
- **FR-026**: Where a settable value exists in the application's configuration but cannot be set from the environment, the documentation MUST NOT present it as an environment variable.

#### Delivery

- **FR-027**: The work MUST be done on a branch cut for this issue and delivered as a pull request against `main`, per this repository's convention for changes to tracked files.

### Key Entities

- **Vendor capability**: What one vendor supports — whole-order capture, page-reading single-item capture, address-only capture, and detail backfill — and whether it requires configuration. The unit the user manual's summary and the README are written from.
- **Configuration setting**: One environment variable, its consumer (application, test suite, or invoked tool), whether it is required, its default, and the consequence of leaving it unset. The unit the deployment guide's reference is written from.
- **Documentation file**: One file under `docs/`, and its status — current description, deployment or development guidance, implemented design, or vestigial.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can configure a deployment, including DigiKey order capture, using only the deployment guide, without opening application source or `.env.example`.
- **SC-002**: Comparing the deployment guide's configuration reference against the settings the application actually reads yields zero entries on either side that are missing from the other.
- **SC-003**: Zero variables documented in the deployment guide have no effect on a deployment.
- **SC-004**: A reader can answer "which vendors are supported, and for what" from a single place in the user manual, in under one minute, without reading the per-vendor sections.
- **SC-005**: Every vendor capability claim in `README.md`, the user manual summary and the troubleshooting guide agrees with what the application does — a reviewer checking each claim against the built behavior finds no disagreement.
- **SC-006**: Every file remaining under `docs/` can be placed in one of the categories in FR-002 by a reader who knows the application.
- **SC-007**: No surviving tracked file outside `specs/` links to a removed document; a link check over the documentation set finds no dangling reference.
- **SC-008**: `git diff` for this feature touches no file under `app/`, `tests/` or `migrations/`, and no file under `specs/` other than this feature's own directory.
- **SC-009**: The existing test suites pass unchanged, because nothing they exercise has changed.

## Assumptions

- **This feature changes documentation only.** No application behavior, configuration handling, or vendor support changes. Where documentation and code disagree, the documentation is what gets corrected — a disagreement that looks like a code defect is reported, not fixed here.
- **`specs/` is frozen** by the repository's own rule and is not edited, not even to repair a reference to a document this feature removes. Dangling references from `specs/` to removed documents are an accepted and intended outcome.
- **`docs/materials-taxonomy-design.md` stays.** It describes the three-level material taxonomy the application still implements, so it satisfies FR-002 despite its age.
- **`docs/category-taxonomy.md`, `docs/deployment-guide.md`, `docs/development-testing-guide.md`, `docs/troubleshooting-guide.md` and `docs/user-manual.md` stay**, and are updated rather than removed.
- **The vendor set as built** is Amazon, DigiKey and McMaster-Carr for order capture; Amazon and McMaster-Carr for page-reading single-item capture; DigiKey for API-driven part lookup and detail backfill; and a recognized-name list covering Amazon, DigiKey, Mouser, eBay, McMaster-Carr and AliExpress for address-derived capture, with the bare site name for anything else. FR-016 requires this to be re-verified against the code during implementation rather than taken from this spec.
- **American spelling** ("catalog", never "catalogue") applies to every file this feature writes, per the repository rule.
- **Screenshots are not regenerated** by this feature. Where a screenshot is stale, that is noted rather than fixed, because a screenshot run churns unrelated images.
- **Nothing outside `docs/features/` links into it.** Checked: the only references to that directory are from other files inside it, so FR-005 costs nothing for this removal. The references to the surviving guides *from* those files disappear with them.
- **No new documents are created** unless the vendor summary (FR-009) reads better as its own file than as a section of the user manual; the default is a section of the existing manual.
