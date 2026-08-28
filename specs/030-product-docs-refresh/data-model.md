# Phase 1 Data Model: Product Documentation Refresh

**Feature**: 030-product-docs-refresh | **Date**: 2026-08-27

There is no database in this feature. The "entities" are the three kinds of fact the documentation is being rebuilt from — each one a row shape that both the source (`research.md`) and the destination (the documents) are written against, so that a reviewer can put them side by side. The populated instances live in `contracts/`.

---

## Configuration setting

One environment variable, as the deployment guide must present it.

| Field | Meaning | Rule |
|-------|---------|------|
| `name` | The variable name, exactly as spelled in the environment | MUST appear verbatim in at least one file under `app/`, `config.py`, `manage.py`, `.flaskenv` or `Dockerfile` (spec FR-019). A name that appears in no such file MUST NOT be documented. |
| `consumer` | What reads it: the application, an invoked tool, or the test suite | A test-suite consumer MUST be documented in the development and testing guide, never as a deployment setting (FR-022). A tool consumer (`CUPS_SERVER`) is still documented (FR-018) — the test is whether setting it changes the deployment, not whether Python reads it. |
| `required` | `yes`, `no`, or a stated condition | A conditional requirement states its condition (`DIGIKEY_CLIENT_SECRET` is required only when a client id is set). |
| `default` | The value used when unset | MUST be the literal default from the code, not a recommendation. Where the default differs between production and test configuration, both are given. |
| `when_unset` | What is absent, degraded, or fails | MUST be a consequence the operator can observe, not a restatement of the default (FR-020). "The DigiKey screens say they are not configured" — not "DigiKey is disabled". |
| `scope` | `docker`, `source`, or `both` | Drives which worked example the variable appears in (FR-023). |

**Not an entity**: a value that lives in `app.config` but is never populated from the environment. `DISABLE_LABEL_PRINTING` is the case in hand, and FR-026 forbids presenting it as a variable.

---

## Vendor capability

One vendor against one capability, as the user manual's summary must present it.

| Field | Meaning | Rule |
|-------|---------|------|
| `vendor` | The vendor name the catalog files purchases under | MUST be the name the application itself uses — `Amazon`, `DigiKey`, `McMaster-Carr` — because those strings are compared inside the application and a documented variant would mislead an operator reading a purchase record. |
| `whole_order` | How a whole order is captured, or "not supported" | States the mechanism: bookmarklet on the vendor's own order page, or an order number typed in. |
| `page_read` | Whether single-item capture reads the vendor's page | `yes` only where a reader exists for that vendor's markup. Everything else is `address only` (FR-011). |
| `address_only` | What a pasted address yields | Every vendor and every site has this row filled; it is the universal fall-back (FR-013). |
| `backfill` | Whether the application fills catalog detail from the vendor | `yes` only for DigiKey, in both of its places — the part-lookup screen and gap-filling on a matched order line (FR-012). |
| `configuration` | What must be set before it works | `none` for Amazon and McMaster-Carr; the DigiKey variables for DigiKey, with a link to the deployment guide (FR-014). |

**Two states that must stay distinct** (research.md §2):

1. **A reader exists** — the capture brings back price, specifications and images.
2. **A name is derived** — the host maps to a tidy vendor name and nothing else is read. Mouser, eBay and AliExpress are only ever this. The summary MUST NOT present state 2 as "supported" without the qualifier.

---

## Documentation file

One file under `docs/`, as spec FR-002 classifies it.

| Field | Meaning | Rule |
|-------|---------|------|
| `path` | Repository-relative path | — |
| `status` | `current-behavior`, `deployment-or-development`, `implemented-design`, or `vestigial` | A file matching none of the first three is `vestigial` and is removed. |
| `basis` | The evidence for the status | For `implemented-design`, names the code that still implements it. For `vestigial`, names what superseded it. |
| `inbound_links` | Tracked files outside `specs/` that reference it | MUST be empty before a `vestigial` file is removed, or repaired in the same commit (FR-005). |
| `unique_reasoning` | Reasoning it records that applies and is recorded nowhere else | MUST be carried into a surviving document before removal (FR-007). Populated for exactly one file; see `research.md` §4. |

**`specs/**` is not in scope for this entity.** It is a frozen record and its inbound links are left dangling by design (FR-006).
