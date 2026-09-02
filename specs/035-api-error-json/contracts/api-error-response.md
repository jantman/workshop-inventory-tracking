# Contract: Error Responses From API Routes

**Feature**: `specs/035-api-error-json` | **Date**: 2026-09-01

## Scope

Every route whose **path** begins with `/api/` or `/admin/api/`. Currently 49 + 2 routes across the
`main`, `product` and `admin` blueprints. The contract is stated over the path prefix rather than a
route list so that a route added later is covered without being enumerated.

## The rule

> A failing request to an API route is answered with a JSON body and the status code for the
> failure. It is never answered with a redirect, and never with HTML.

This holds regardless of the request's method, `Content-Type`, `Accept` header, or whether it
carried a body.

## Status codes

| Condition | Status | Rendered by |
|---|---|---|
| `ValidationError` | `400` | `handle_validation_error` |
| `AuthenticationError` | `401` | `handle_auth_error` |
| `ItemNotFoundError` | `404` | `handle_item_not_found` |
| No route matches the path | `404` | app-level `handle_not_found` |
| `StorageError` | `500` | `handle_storage_error` |
| `ConfigurationError` | `500` | `handle_config_error` |
| Any unhandled exception | `500` | app-level `handle_internal_error`, or `main`'s blueprint `500` handler |

Routes that build their own responses — `_upload_attachment`'s `400`/`500`, `api_add_identifier`'s
`400`/`409` — are already JSON and are outside this contract; it governs only what the centralized
handlers produce.

## Response body

`Content-Type: application/json`, with the payload documented in
[../data-model.md](../data-model.md). `success` is `false` in every case. The shape is unchanged
from what a JSON-bodied caller receives today, so a caller that works now keeps working.

## Success responses are not in scope

`DELETE /api/attachments/<id>` still answers `204` with an empty body on success;
`GET /api/products/<id>` still answers `200` with its product. Nothing about a successful response
changes.

## Client obligations

A caller distinguishes outcomes by **status code**, never by whether a body parses:

- `2xx` — the operation happened.
- `404` on a `DELETE` — the resource is already absent. For a delete, that *is* the requested state;
  the attachments grid counts it as removed.
- Any other non-`2xx` — a failure. Report it to the user. Do not refresh as though it had succeeded.

`fetch` follows redirects by default, so a redirect never reaches the caller as a redirect. It
arrives as whatever the *other* resource answered — an opaque `200` from an unrelated page for a
`GET`, or a `405` for a `DELETE`, since the method is preserved across a 302 and page routes are
`GET`-only. Neither is distinguishable from the outcome the caller asked about. That is the defect
this contract exists to prevent, and it is why the rule is stated as "never a redirect" rather than
"a JSON body when convenient".

## Routes outside the prefix

Unchanged, and deliberately so. A page route answers a browser with a flash message and a redirect,
and answers a caller that sent a JSON body with JSON. Adding a page route to this contract is a
behaviour change requiring its own spec.

## Verification

- `GET /api/products/999999` → `404`, `application/json`, `success: false`, no `Location` header.
- `DELETE /api/attachments/999999` → same.
- `DELETE /api/products/<id>/identifiers/999999` → same.
- `GET /api/no-such-route` → `404`, `application/json`.
- `GET /products/999999` → `302` to the inventory list (the page-route half of the contract).
