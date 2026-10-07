# Implementation Plan: Free-Text Locations on the Product Move Page

**Branch**: `robot-army/issue-195-fix-for-189-product-locations-are-free` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/059-product-freeform-locations/spec.md`

## Summary

The shared scan machine (`MoveManager`, `app/static/js/move-manager.js`) classifies a scan as a
location only if it matches the item convention `^M[0-9]`, `^T-?[0-9]` or `Other`. Product
locations are free text, so the product page refuses every real product location. The fix is
in `ProductMoveManager` (`app/static/js/product-move.js`): override `isLocation(value)` so
that, while the machine is waiting for a location (`location` or `bulk_location`), any
non-empty value is one; in every other state the inherited pattern rule still applies. The
precedence in `classifyInput` (subject ID, then foreign ID, then location) is unchanged, so
product codes and JA labels are never taken as locations. The `M*, T*, or Other` wording moves
behind a `locationHint` getter that the product page overrides, and the page's instruction
example becomes a macro parameter.

## Technical Context

**Language/Version**: Python 3.13 (Flask, Jinja2); browser JavaScript (no build step)

**Primary Dependencies**: Existing only. No new dependencies.

**Storage**: N/A. There is no schema or server change, because `/api/products/batch-move`
already accepts any non-empty location.

**Testing**: The nox `e2e` session (Playwright). The JS has no unit harness, and the
behavior is in the browser, so e2e covers it. `waits.scan_on_move_page` asks the page's
`classifyInput` before typing, which picks up the state-aware classification without change.

**Target Platform**: LAN-only Linux server; desktop browser with a keyboard-wedge scanner

**Project Type**: Web application (server-rendered + page scripts)

**Performance Goals**: N/A

**Constraints**: The item Move page must be byte-for-byte unchanged in behavior and wording.

**Scale/Scope**: Two JS files, two templates plus the shared macro, one e2e test file, and the user manual.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ A one-method override in the existing subclass, plus one getter for the wording. There is no new abstraction, and no list of known locations is consulted. |
| **II. Layered Architecture** | ✅ The change is presentation only, and the server is untouched. |
| **III. Exact Numerics** | ✅ N/A. There are no measurements. |
| **IV. Test Discipline** | ✅ New e2e tests cover free-text locations on both entry paths, the still-refused cases and the hint wording. Waits go through `scan_on_move_page`/`expect`, so there are no fixed delays. The existing item and product move tests stay as regression cover. |
| **V. MariaDB Source of Truth** | ✅ No schema change. |
| **VI. Item Lifecycle Invariants** | ✅ The item page is untouched (FR-005). |
| **Threat model** | ✅ Free text was already accepted as a sub-location, and is now accepted as a location too, so no new validation is needed. |

**Post-design re-check**: ✅ Unchanged after Phase 1. There are no violations.

## Project Structure

### Documentation (this feature)

```text
specs/059-product-freeform-locations/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/move-manager.md
└── tasks.md
```

### Source Code (repository root)

```text
app/static/js/move-manager.js      # locationHint getter; four messages use it
app/static/js/product-move.js      # isLocation override; locationHint override
app/templates/move/_scan_move.html # location_example macro parameter
app/templates/inventory/move.html  # passes the item example (unchanged text)
app/templates/product/move.html    # passes a free-text example
tests/e2e/test_product_move.py     # new scenarios
tests/e2e/waits.py                 # docstring: classification is per-state on the product page
docs/user-manual.md                # Moving Products: locations are free text
```

**Structure Decision**: Existing files only.

## Complexity Tracking

No violations.
