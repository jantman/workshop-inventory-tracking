# Implementation Plan: Capture McMaster Variant Product Pages

**Branch**: `robot-army/issue-184-mcmaster-page-capturing-bug` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/056-mcmaster-variant-urls/spec.md`

## Summary

`MCMASTER_PRODUCT_PATTERN` in `extension/capture-agent.js` accepts `/<part>/` only, so
`/3408A521-3408A523/` — where McMaster puts the owner after a variant is chosen — falls to
`'other'`, `readableKind()` returns null and the service worker refuses the page.

Two changes to application code, one on each side of the machine boundary the two copies
of this rule already straddle:

1. **The agent** (`extension/capture-agent.js`): the pattern gains an optional
   `-<part>` second group (FR-001, FR-005). A new `mcmasterPartNumber(doc, loc)` picks the
   part number: the page's `[class*="_productDetailPartNumber_"]` text when it is one of the
   address's part numbers, otherwise the address's first (FR-002). For a single-part
   address that rule can only ever answer the address's one part number, so FR-003 holds
   by construction rather than by a branch.
2. **The server** (`app/product/routes.py`, `_mcmaster_part_from_url`): the same optional
   second group; the first part number is returned (FR-004). There is no page on this side
   to consult.

## Technical Context

**Language/Version**: Python 3.13; plain browser JavaScript (the MV3 extension, no build)

**Primary Dependencies**: existing only; nothing added

**Storage**: none touched. No schema change, no migration.

**Testing**: pytest via `nox -s tests` (unit) and `nox -s e2e` (Playwright, extension loaded)

**Target Platform**: Linux server, LAN-only; Chrome with the capture extension

**Project Type**: web-service plus browser extension

**Performance Goals**: N/A — one extra `querySelector` per McMaster product capture.

**Constraints**: every existing capture path unchanged (SC-002).

**Scale/Scope**: ~20 lines of application code; tests in three existing modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Simplicity First | Pass. A widened regex on each side and one small function choosing between numbers the address already names. No per-variant model, no configuration. The deliberate agent/server duplication is kept, not merged — the existing docstrings explain why. |
| II. Layered Architecture | Pass. The server change is inside the existing route helper; no layer crossed. |
| III. Exact Numerics | N/A — no measurements. |
| IV. Test Discipline Through Nox | Pass. Unit tests for the server helper; e2e tests for the agent's reader and for the extension's refusal path, which is the reported symptom. Tests wait on state (pattern C: `capture()` settles only after the read). |
| V. MariaDB Source of Truth | N/A — nothing stored differently; the part number lands in the existing field. |
| VI. Item Lifecycle / History | N/A. |
| Threat model | N/A — no new input surface; the address is already read. |

**Post-design re-check**: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/056-mcmaster-variant-urls/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

No `contracts/`: the payload, routes and forms are unchanged — only which addresses reach
them.

### Source Code (repository root)

```text
extension/capture-agent.js            # pattern + mcmasterPartNumber()
app/product/routes.py                 # _mcmaster_part_from_url pattern
tests/unit/test_mcmaster_routes.py    # variant and malformed-variant addresses
tests/e2e/test_mcmaster_product.py    # reader on variant addresses: part number, drawing
tests/e2e/test_capture_extension.py   # the extension no longer refuses a variant page
```

**Structure Decision**: existing layout; nothing new at the structure level.

## Complexity Tracking

No violations to justify.
