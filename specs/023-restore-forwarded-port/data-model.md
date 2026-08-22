# Data Model: Restore the Browser's Port Behind a Reverse Proxy

**Feature**: `specs/023-restore-forwarded-port/` | **Date**: 2026-08-21

This feature persists nothing. No table, no column, no Alembic revision, no domain dataclass. What it
does have is a **transformation** — a request arrives having been rewritten by a proxy, is rewritten
again on the way in, and an address falls out the other end — and every requirement in the spec is an
assertion about a stage of that transformation. So that is what is modelled here.

The values in the tables below are observed, from the Phase 0 probe described in
[research.md](research.md). They are not predictions.

## The one entity: the request's idea of its own address

It has three stages and one derived output.

| Stage | What holds it | Who writes it | Why it matters |
|---|---|---|---|
| **Arrived** | `HTTP_HOST`, `wsgi.url_scheme` in the WSGI environ | the proxy, over the plain-HTTP hop | The port is *here* — this is the only place it survives today, and the only reason the defect is fixable at all |
| **Forwarded** | `HTTP_X_FORWARDED_{PROTO,HOST,PORT}` | the proxy | What the proxy *says* the browser did. Trusted for exactly one hop |
| **Believed** | `request.host`, `request.scheme` | Werkzeug, from the environ as the middleware left it | The value the referrer check compares against. **The defect lives here** |
| *derived* | `url_for(..., _external=True)` | Flask, from Believed | The bookmarklet's two addresses. The visible symptom |

Two rules govern the step from Forwarded to Believed, and Phase 0 established that they are enforced
at different layers — which is why one of the spec's edge cases needs code and another does not:

- **The port declaration overwrites the arrived host's port.** `ProxyFix` strips whatever port
  `HTTP_HOST` carries and appends the declared one. It does this *unconditionally* — including when
  the declared port is the scheme's default.
- **A standard port is then omitted, and an invalid host collapses to nothing.** `get_host` drops
  `:80` on `http` and `:443` on `https`, and returns the empty string if the composed host contains
  characters a host cannot contain.

The second rule cleans up after the first in one case and is catastrophic in another. That asymmetry
is the whole of the design.

## State table: every case the spec's Edge Cases name

Scheme is `https` unless noted. **Believed** is `request.host` — the value
`f"https://{request.host}/"` is built from, which the referrer check compares against what the
browser sent.

| Declared host | Declared port | Believed — today | Believed — with `x_port=1` | Bookmarklet addresses — with the fix | Spec reference |
|---|---|---|---|---|---|
| `titan.example.com` | *none* | `titan.example.com` | `titan.example.com` | no port | the live deployment; FR-006 |
| `titan.example.com` | `15603` | `titan.example.com` ❌ | `titan.example.com:15603` ✅ | both carry `:15603` | FR-001, FR-004, FR-005 |
| `titan.example.com` | `443` | `titan.example.com` | `titan.example.com` | no port | FR-003 — **no code needed** |
| `titan.example.com` | `80` *(http)* | `titan.example.com` | `titan.example.com` | no port | FR-003 |
| `titan.example.com:15603` | `15603` | `titan.example.com:15603` | `titan.example.com:15603` | both carry `:15603` | FR-007 — no doubling |
| `titan.example.com:15603` | *none* | `titan.example.com:15603` | `titan.example.com:15603` | both carry `:15603` | the rejected alternative, which does work |
| `titan.example.com` | `not-a-port` | `titan.example.com` | `''` ❌❌ **empty** | `https:///api/capture` | FR-007 — **guard required** |
| `titan.example.com` | *empty string* | `titan.example.com` | `titan.example.com` | no port | FR-007 — ignored, no guard needed |
| *none* | `15603` | `localhost` | `localhost:15603` | both carry `:15603` | — |
| *none* | *none* | `localhost` | `localhost` | no port | FR-006 — the e2e suite's case |

Read the two ❌ rows together: they are the entire feature. The second row is the defect being fixed.
The malformed-port row is the defect the fix would introduce if it shipped unguarded — note that it
is the only row where the "with the fix" column is *worse* than "today", and that it is silent.

## Validation rule introduced

Exactly one, and it applies to the Forwarded stage before `ProxyFix` reads it:

> A forwarded port declaration is honoured only if it consists solely of decimal digits. Anything
> else is discarded, and the arrived host stands.

An absent declaration and an empty one already behave this way without help — `ProxyFix` ignores a
falsy header value — so the rule adds nothing for them. It exists for the one observed input that
would otherwise collapse the host to the empty string.

No range check on the number. A port of `0` or `99999` is a misconfiguration that produces a visibly
wrong address the operator can read and correct, which is the behaviour they already get for a wrong
but well-formed hostname. Constraining it further would be Principle I's speculative generality.

## State transitions

None. There is no lifecycle here, nothing is persisted between requests, and no request affects the
next one. The transformation is recomputed per request from the headers of that request.
