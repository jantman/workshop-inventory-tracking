# Phase 1 Data Model: API Routes Always Answer With JSON Errors

**Feature**: `specs/035-api-error-json` | **Date**: 2026-09-01

## Entities

**None.** This feature changes how a failure is *rendered*. It defines no entity, stores nothing,
reads nothing, and requires no Alembic revision. The spec's Key Entities section says the same.

The one structure worth pinning down is the error payload, which is **pre-existing and unchanged** —
it is recorded here so that "unchanged" is verifiable rather than asserted.

## The error payload (existing, unchanged)

Built by `ErrorHandler.handle_error` in `app/error_handlers.py` and serialized by `jsonify`. Two
shapes, depending on whether the exception is one of the project's own.

### For a `WorkshopInventoryError` subclass

`_handle_custom_error`, `app/error_handlers.py:76`

| Field | Type | Notes |
|---|---|---|
| `success` | boolean | Always `false` |
| `error_id` | integer | Millisecond timestamp; matches the `Error <id>:` line in the app log |
| `error_code` | string | From the exception's `code` |
| `error_type` | string | The exception class name, e.g. `ItemNotFoundError` |
| `message` | string | Human-readable, from the exception's `message` |
| `details` | object | From the exception's `details` |
| `recovery_suggestions` | array of string | Type-specific; empty list for types with no suggestions |

### For any other exception

`_handle_generic_error`, `app/error_handlers.py:120`

| Field | Type | Notes |
|---|---|---|
| `success` | boolean | Always `false` |
| `error_id` | integer | As above |
| `error_type` | string | The exception class name |
| `message` | string | `"An unexpected error occurred"` unless overridden |
| `context` | string | Where the failure happened, e.g. `"Item Lookup"` |
| `recovery_suggestions` | array of string | Generic |

### The app-level `404` handler

Does not call `handle_error`; it returns a fixed literal
(`app/error_handlers.py:346`): `success: false`, `error: "Resource not found"`,
`message: "The requested resource was not found"`. Left as-is.

## State transitions

None. Nothing in this feature has state.

## What actually changes

Not the payload — only **which requests receive it** instead of a `302`:

| Request | Before | After |
|---|---|---|
| `/api/…` failing, no body | `302` + flash | payload above, correct status |
| `/admin/api/…` failing, no body | `302` + flash | payload above, correct status |
| `/api/…` failing, JSON body | payload above | **unchanged** |
| page route failing, no body | `302` + flash | **unchanged** |
| page route failing, JSON body | payload above | **unchanged** |

The full status-code mapping is in [contracts/api-error-response.md](./contracts/api-error-response.md).
