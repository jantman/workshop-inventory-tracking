# Feature: API and Client Class

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Requirements

Our goal is to:

1. Add a ReST API endpoint for creating items, similar to the existing `POST /inventory/add` form handler endpoint (or update that endpoint to alternatively handle JSON POST). The endpoint should return the IDs of any items that were created, along with any errors. Do not duplicate code paths between the existing form handler and the new JSON handler; refactor as needed to ensure no duplication.
2. Add a standalone Python script at `app/api_client.py` whose only external dependency is the `requests` library, and which provides a Class that can be used to create items via the API and also to upload photos via the API (existing API for this, `POST /api/items/<ja_id>/photos`).
3. Add/update tests accordingly to verify full test coverage at least via unit tests and ideally also via e2e tests.

---

## Implementation Plan

Commit prefix: `API - {milestone}.{task}`

### Decisions (resolved)

1. **Endpoint URL:** new dedicated JSON endpoint `POST /api/inventory/items`. The form route is not overloaded.
2. **CSRF:** new endpoint is `@csrf.exempt`, matching the rest of `/api/*`.
3. **Authentication:** none. Same posture as existing `/api/*` endpoints (access controlled at the network layer).
4. **Status codes:** `200` (all created), `207 Multi-Status` (partial success), `400` (request-level validation error, nothing created), `500` (unexpected error).
5. **Bulk semantics:** mirror the form's `quantity_to_create` field. Same range (1–100), same sequential JA ID assignment. No heterogeneous-array bulk request.
6. **JSON field names:** accept the same form-style keys (incl. `vendor_part_number`) plus native booleans for `active` / `precision`. No alternate JSON-only key names.
7. **Client class scope:** `create_item(...)` and `upload_photo(...)` only. No list/search/edit/delete.

### Architecture overview

The form route at `inventory_add` already uses small helpers (`_create_single_item`, `_add_item_with_logging`, `_parse_item_from_form`), but the validation, bulk-loop, and JA-ID-allocation logic still live inline inside the route. We will lift those into a single reusable function so the form route and the new JSON route both call exactly the same code path.

New shared helper (in `app/main/routes.py`, near the existing `_create_single_item` helper):

```python
def _process_item_creation(input_data: dict) -> dict:
    """
    Run the full add-item pipeline (validation → parse → persist → audit log)
    for a single submission, including bulk creation when quantity_to_create > 1.

    input_data: form-style dict (str keys, str values for form callers; the
    JSON caller normalizes booleans/numbers to strings before calling).

    Returns:
        {
            'status': 'ok' | 'partial' | 'validation_error' | 'error',
            'created_ja_ids': [str, ...],
            'errors': [{'index': int, 'ja_id': str|None, 'message': str}, ...],
            'message': str | None,
        }
    """
```

Both callers translate that result into their own response format:

- Form route: flash + redirect for single (status `ok`), JSON for bulk (existing behavior preserved).
- JSON API route: JSON response with HTTP status derived from `status`.

A small input-normalization helper converts a JSON request body into the form-style dict the helper expects (booleans → `"on"`/`""`, numbers → `str`, key aliases handled). This keeps `_parse_item_from_form` unchanged.

### Milestone 1 — JSON API endpoint and shared helper

Goal: ship `POST /api/inventory/items` and refactor the form route to share its core path. All commits use prefix `API - 1.x`.

**Task 1.1 — Extract `_process_item_creation` shared helper.**
- Location: `app/main/routes.py`.
- Move the validation block (required fields, material taxonomy check, `quantity_to_create` range), JA-ID allocation, single/bulk dispatch, and audit-log calls out of `inventory_add` into the new helper.
- The helper takes a form-style dict and returns the structured result documented above.
- No behavior change for the form route — it continues to call this helper and translate the result into flash + redirect (single) or JSON (bulk).
- Unit tests: re-run existing `tests/unit/test_routes.py` add-item cases unchanged; they should still pass.

**Task 1.2 — Add JSON input normalizer.**
- New helper `_normalize_json_item_payload(json_body: dict) -> dict` in `app/main/routes.py`.
- Accepts native JSON types and emits the form-style string dict the shared helper expects.
- Booleans for `active` / `precision` map to `"on"` / `""` (matching `_parse_item_from_form`'s existing checkbox semantics).
- Numbers are coerced to strings via `str(...)` so dimension parsing stays unchanged.
- Reject non-dict bodies and unknown top-level keys explicitly with a 400.

**Task 1.3 — Add `POST /api/inventory/items` route.**
- Endpoint: `POST /api/inventory/items`, accepts `application/json`.
- `@csrf.exempt` decorator (consistent with other `/api/*` POSTs).
- Body parsing with `request.get_json(silent=True)`; on `None`/non-dict return 400 with `{success: false, error: "Request body must be a JSON object"}`.
- Calls `_normalize_json_item_payload` then `_process_item_creation`.
- Response shape (always JSON):
  ```json
  {
    "success": true,
    "created_ja_ids": ["JA000123", "JA000124"],
    "errors": []
  }
  ```
  - HTTP `200` when `status == 'ok'`.
  - HTTP `207` when `status == 'partial'` (some items created, some failed; both `created_ja_ids` and `errors` populated; `success: false`).
  - HTTP `400` when `status == 'validation_error'` (nothing created).
  - HTTP `500` when `status == 'error'` (unexpected backend failure; nothing created).
- Audit logging is delegated to the shared helper (already in place).

**Task 1.4 — Refactor `inventory_add` to consume the helper.**
- Replace inline validation/bulk logic in the form POST branch with a single call to `_process_item_creation(form_data)`.
- Translate the result into the existing form responses (single → flash + redirect; bulk → JSON, preserving the current 200/500 behavior so e2e tests don't regress).
- Verify against existing e2e bulk-creation and add-item tests.

**Task 1.5 — Unit tests for the new endpoint and helper.**
- New file `tests/unit/test_api_items.py` (or extend `test_routes.py` — I'll extend to keep test layout consistent with existing convention).
- Cases:
  - Single-item creation success → 200, `created_ja_ids` of length 1, no errors, item persisted (verified via storage).
  - Bulk creation success (`quantity_to_create=3`) → 200, three sequential JA IDs returned.
  - Missing required fields → 400 with field list in error message.
  - Invalid material → 400.
  - `quantity_to_create` out of range (0, 101) → 400.
  - Non-JSON / non-dict body → 400.
  - Native boolean handling (`active: true`, `precision: false`) → item persists with correct flags.
  - Numeric dimensions in JSON (`length: 12.5`) → parsed correctly.
  - Threading fields → persist on item.
  - Partial-failure simulation (mock storage to fail mid-loop) → 207 with `created_ja_ids` and `errors`.
- Existing form-route unit tests must still pass unchanged (regression guard for the refactor).

**Task 1.6 — Documentation.**
- Add an "REST API" section to `docs/user-manual.md` (or a new `docs/api-reference.md` linked from the manual — I'll inline in user-manual.md unless you prefer otherwise) describing the request/response of `POST /api/inventory/items`.
- Note `@csrf.exempt` and current lack of authentication in `docs/deployment-guide.md`'s security section.
- Update `README.md` feature list to mention the API.

**End of Milestone 1:** run `nox -s tests` and `nox -s e2e` (20-min bash timeout). All must pass. Commit per `docs/features/README.md` rules. Pause for human approval before Milestone 2.

### Milestone 2 — Standalone Python client and tests

Goal: ship `app/api_client.py` with a `WorkshopInventoryClient` class plus tests. All commits use prefix `API - 2.x`.

**Task 2.1 — Implement `app/api_client.py`.**
- Single file. Imports: stdlib only plus `requests` (no Flask, no SQLAlchemy, no models — must run from a clean venv with only `requests`).
- Public surface:
  ```python
  class WorkshopInventoryClient:
      def __init__(self, base_url: str, *, timeout: float = 30.0, session: requests.Session | None = None): ...
      def create_item(self, item: dict) -> CreateItemResult: ...
      def upload_photo(self, ja_id: str, *, file_path: str | None = None,
                       file_data: bytes | None = None, filename: str | None = None,
                       content_type: str | None = None) -> UploadPhotoResult: ...
  ```
- `CreateItemResult` and `UploadPhotoResult` are stdlib `@dataclass(frozen=True)` value objects exposing the parsed JSON (`success`, `created_ja_ids`, `errors`, `http_status`, `raw`). Keeping them frozen dataclasses avoids any third-party dependency.
- Errors:
  - Network/transport failures raise `requests.RequestException` (let it bubble).
  - HTTP 4xx/5xx return a `*Result` with `success=False` populated from the response body when JSON-parseable; if the body is not JSON, populate `errors` with a synthetic `{message: <text>}` entry.
- Provide a minimal `if __name__ == "__main__":` block — a one-line argparse-driven CLI that creates a single item from a JSON file and prints the result. This makes the module independently runnable for ad-hoc use, and does not add a dependency.
- Type hints throughout. Docstrings on public methods only (one short line each).

**Task 2.2 — Unit tests for the client.**
- New file `tests/unit/test_api_client.py`.
- Use `responses` (already in `requirements-test.txt` if available — I'll verify; if not, fall back to `unittest.mock.patch` on `requests.Session.request`) to mock HTTP without standing up a server.
- Cases:
  - `create_item` happy path → returns parsed `CreateItemResult` with `created_ja_ids` populated.
  - `create_item` with bulk → returns multiple IDs.
  - `create_item` with validation error (mock 400) → `success=False`, `http_status=400`, errors populated.
  - `create_item` with partial-success 207 → both `created_ja_ids` and `errors` populated.
  - `create_item` raises `RequestException` on connection failure (mock raise) — verify it propagates.
  - `upload_photo` from `file_path` → multipart request body shape verified.
  - `upload_photo` from `file_data` + `filename` → multipart request body shape verified.
  - `upload_photo` 4xx → `success=False`.
- The client must work with no Flask/test config available; tests instantiate the client directly with a fake base URL.

**Task 2.3 — E2E test exercising the client against the live test server.**
- New file `tests/e2e/test_api_client.py`.
- Marked `@pytest.mark.e2e`. No browser needed; uses the existing `live_server` fixture and the new client.
- Cases:
  - Create a single item via the client; then verify presence by hitting `GET /api/items/<ja_id>` (existing endpoint) or by checking `/inventory` page.
  - Bulk-create 3 items; verify all three returned IDs exist.
  - Upload a photo (PIL-generated test image, same pattern as `tests/e2e/test_photo_upload.py`) for the created item; verify via `GET /api/items/<ja_id>/photos`.
- These tests don't open Playwright — they run in the same e2e session because they need the live Flask server.

**Task 2.4 — Documentation.**
- Add a "Python API client" subsection to `docs/user-manual.md` (or to the API reference added in 1.6) with a usage example.
- `docs/development-testing-guide.md`: note that the client is dependency-light and can be vendored / copied into other projects.

**End of Milestone 2 (= end of Feature):** run `nox -s tests` and `nox -s e2e` (20-min bash timeout). All must pass. Update progress section below. Commit. After human verification of the feature, the feature doc is moved into `complete/` and a PR is opened per the process in `docs/features/README.md`.

### Files touched

- `app/main/routes.py` — extract shared helper, add new JSON route, refactor form route.
- `app/api_client.py` — new file.
- `tests/unit/test_routes.py` (or new `test_api_items.py`) — new tests.
- `tests/unit/test_api_client.py` — new file.
- `tests/e2e/test_api_client.py` — new file.
- `docs/user-manual.md` — API + client documentation.
- `docs/deployment-guide.md` — note CSRF/auth posture for the new endpoint.
- `README.md` — feature mention.

### Out of scope

- Authentication/authorization on `/api/*` endpoints (current behavior preserved; called out as a question above).
- API endpoints for read/edit/delete operations (only "create item" + existing photo upload are in scope).
- A full OpenAPI / Swagger spec (can be added later if desired).
- Packaging `api_client.py` as a separate distributable Python package.

---

## Progress

_Not started — awaiting plan approval._
