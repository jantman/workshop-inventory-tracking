# Feature: Autocomplete

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Requirements

On the Add Item and Edit Item forms, please make Thread Size, Purchase Location, Vendor, Location, and Sub-Location fields autocomplete based on current values in the database. These should also be exposed via API endpoints, documented in the "REST API" section of the user guide and queryable via methods on `app/api_client.py`. Add e2e and unit test coverage as applicable.

## Implementation Plan

### Design Decisions

1. **Source of suggestions**: Distinct values across **all** rows in `inventory_items` (active + history), not just active. Deactivated items still seed suggestions so users don't lose autocomplete recall when an item is deactivated/shortened.
2. **Endpoint shape**: A single backend route `GET /api/inventory/field-suggestions/<field>` with a whitelist of supported fields (`thread_size`, `purchase_location`, `vendor`, `location`, `sub_location`). Documented as one entry covering all five fields. Cleaner than five near-duplicate handlers and trivially extensible.
3. **Sub-location filtering**: `sub_location` requests accept an optional `?location=` query parameter that scopes suggestions to sub-locations recorded under that location. Bare sub-location values are ambiguous (e.g. "Top shelf"), so this is on by default in the frontend whenever Location is set.
4. **Materials are out of scope**: Material already has a dedicated taxonomy-backed selector and is not in the requirements list.
5. **Frontend approach**: A small generic `field-autocomplete.js` helper, modeled on the existing inline pattern in `inventory-add.js`. Reused for all five fields on both Add and Edit forms. Replaces only the bare text inputs; carry-forward and validation logic are unaffected.

### Endpoint contract

`GET /api/inventory/field-suggestions/<field>`

Query parameters:
- `q` (optional): case-insensitive substring filter. If absent, returns the most recently used values.
- `limit` (optional, default 10, clamped 1-50).
- `location` (optional, only meaningful when `field=sub_location`): scope suggestions to that location.

Response (200): `{"success": true, "field": "<field>", "suggestions": ["..."]}`.

Errors:
- 400 if `<field>` is not in the whitelist.
- 500 on unexpected backend failure.

Suggestions are returned in this priority order: exact match → starts-with matches → contains matches, with each tier alphabetized. (Matches the pattern used by `/api/materials/suggestions`.)

### Milestones

#### AC-1: Backend API and unit tests

- AC-1.1: Add `InventoryService.get_field_value_suggestions(field, query=None, limit=10, location=None)` returning sorted distinct strings from `inventory_items`. Whitelisted columns only. Filters out NULLs and empty strings.
- AC-1.2: Add Flask route `GET /api/inventory/field-suggestions/<field>` that calls the service method.
- AC-1.3: Unit tests for the service method (whitelist enforcement, empty/NULL filtering, query filtering, limit clamping, location scoping for sub_location).
- AC-1.4: Unit tests for the route (success, unknown field 400, query/limit/location parameters honored).
- AC-1.5: Run unit suite and confirm all green.

#### AC-2: Frontend autocomplete on Add and Edit forms

- AC-2.1: Add `app/static/js/field-autocomplete.js`: a small class that attaches to a text input, debounces input, fetches the endpoint, renders a dropdown of matches, and supports click-to-fill plus keyboard navigation.
- AC-2.2: Add a positioned dropdown container (`<div class="dropdown-menu position-absolute w-100">`) under each of the 5 target inputs on `add.html` and `edit.html`. Wrap each input in `position-relative` like the material field.
- AC-2.3: Initialize the autocomplete on DOM ready for both forms. For sub-location inputs, pass the current location element id so it sends `location=`.
- AC-2.4: Confirm carry-forward and existing form validation still work. Confirm the Material selector (which has its own selector component) is unchanged.

#### AC-3: Python API client and e2e tests

- AC-3.1: Add `WorkshopInventoryClient.get_field_suggestions(field, query=None, limit=10, location=None)` returning a `FieldSuggestionsResult` dataclass. Network errors propagate; HTTP errors land as `success=False`.
- AC-3.2: Unit tests for the new client method (success, 400 unknown-field handling, query/limit/location forwarding).
- AC-3.3: E2E test: hit the live endpoint via the client and verify suggestions are returned for seeded items.
- AC-3.4: E2E tests for the Add and Edit forms: type into each of the five fields, confirm dropdown appears, click an item, confirm the field is filled. Sub-location suggestions are scoped to the entered Location.

#### AC-4: Documentation and final validation

- AC-4.1: Add a `### GET /api/inventory/field-suggestions/<field>` section to the REST API portion of `docs/user-manual.md`, including the table of supported fields and example response. Add a Python-client usage example.
- AC-4.2: Update `README.md`, `docs/deployment-guide.md`, `docs/development-testing-guide.md`, `docs/troubleshooting-guide.md` only if they need to mention the new endpoint or behavior.
- AC-4.3: Run the full unit suite (`nox -s tests`) and the full e2e suite (`nox -s e2e`, 20-minute Bash timeout) — must run to completion without timeout, all tests green.
- AC-4.4: After the human verifies the feature, move this document into `complete/`, push, open a detailed PR.

### Success Criteria

1. All five target fields autocomplete on both Add and Edit forms.
2. Sub-location suggestions filter by the currently-entered Location.
3. The endpoint is reachable, documented, exercised by `api_client.py`, and covered by unit + e2e tests.
4. Full unit + e2e suites pass.

## Progress

- ✅ **AC-1: Backend API** — `GET /api/inventory/field-suggestions/<field>` with `InventoryService.get_field_value_suggestions()`. 21 new unit tests.
- ✅ **AC-2: Frontend autocomplete** — `app/static/js/field-autocomplete.js` wired to all five inputs on Add and Edit forms.
- ✅ **AC-3: API client + e2e** — `WorkshopInventoryClient.get_field_suggestions()` with `FieldSuggestionsResult`. 11 new client unit tests, 9 new e2e tests (2 API-level, 7 form-level).
- ✅ **AC-4: Documentation and final test pass** — REST API section in `docs/user-manual.md` documents the new endpoint and Python-client method; the form-features reference notes which fields autocomplete; `README.md` headline updated; `docs/development-testing-guide.md` updated for the expanded api-client public surface. Full unit suite green (340 tests). Full e2e suite green (297 passed, 1 skipped, 0 failed; ~17min runtime).
