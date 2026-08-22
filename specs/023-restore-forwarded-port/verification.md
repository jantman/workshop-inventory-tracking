# Live Verification Against the Deployment

**Feature**: `specs/023-restore-forwarded-port/` | **Date**: 2026-08-22

Run against `https://titan.jasonantman.com:15603/` on the image
`ghcr.io/jantman/workshop-inventory-tracking:ci-1534b60ed5a7760e994b36be7e3e53c60a23a93f`,
built by PR #115's CI, with the proxy reconfigured to send `X-Forwarded-Port`.

Note the deployment is on a CI image rather than a release: the `ci-` tag is built on every
PR, which made it possible to verify **before** merging rather than after. The task list
assumed the reverse. The release image (`:0.1.1`, `:latest`) is still what should be pinned
once #115 merges.

Connecting requires `curl -k`: the site presents a certificate from an internal CA. That
affects nothing here — the scheme is still `https`, so `request.is_secure` is true and the
referrer check runs, which is the whole point.

## SC-003 / T025 — the port survives into both bookmarklet addresses ✅

```
agent    : https://titan.jasonantman.com:15603/static/js/capture-agent.js?v=
endpoint : https://titan.jasonantman.com:15603/api/capture
```

The `bookmarklet-http-warning` box is absent, so `X-Forwarded-Proto` is still being honoured
too — this feature did not disturb issue #89's fix.

## SC-001 / T026 — a CSRF-protected form is accepted ✅

Verified **without writing anything**, by posting to `/products/categories/rename` with an
empty payload. That handler validates inside the transaction and a raise rolls it back, so
the request reaches the handler, proves the referrer check passed, and leaves the tree
exactly as it was.

| | Referrer sent | Result |
|---|---|---|
| **A** | `https://titan.jasonantman.com:15603/products/categories` | **HTTP 302** — handler reached |
| **B** | `https://titan.jasonantman.com/products/categories` (no port) | **HTTP 400** — `The referrer does not match the host` |

**B is the case that makes A mean something.** Without it, A is equally consistent with
`WTF_CSRF_SSL_STRICT` being switched off, in which case the referrer check would never run
and A would pass on a still-broken deployment. B shows the check is live and that the port
is what it compares — it is the defect reproduced deliberately, from the other side.

Nothing was written: A's redirect lands on the categories page showing the `required`
validation error, which is the rollback path, and the page is intact afterwards.

## SC-002 / T027 — the bookmarklet ⚠️ partially verified

The load step is confirmed: the agent script at the bookmarklet's own address answers
`HTTP 200`, `text/javascript`, 45,950 bytes. That is the step this feature broke — the
address was unreachable, so the script never loaded and clicking did nothing.

What is **not** verified here is the end-to-end journey: dragging the bookmarklet, clicking
it on a live Amazon listing, and landing on the confirmation page. It needs a signed-in
browser, and completing it performs a real capture that writes a product. #80 §1a check A1
is the existing form of it.

## Out of scope, still

022 SC-010 / #80 §1b B4 — confirming a capture and measuring a stored file to show every
gallery image is a full-resolution original — belongs to #113. SC-001 above unblocks it. It
is not done, and this record does not close it.
