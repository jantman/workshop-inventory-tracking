# Phase 0 Research: Restore the Browser's Port Behind a Reverse Proxy

**Feature**: `specs/023-restore-forwarded-port/` | **Date**: 2026-08-21

Everything below was **observed**, not reasoned about. A probe ran the real application through the
project's own `client` fixture, twice — once as the code stands, once with the proposed change — and
recorded, for ten header combinations, the value the referrer check compares against and the two
addresses baked into the capture bookmarklet. The probe was deleted after this document was written;
the assertions it justified become permanent tests in Phase 2.

The probing mattered. It killed one guard I had planned to write, and it found one regression I had
not planned for at all.

---

## Decision 1 — Trust one hop of the forwarded port declaration

**Decision**: Add `x_port=1` to the existing `ProxyFix` wrapping in `create_app`, and add the
matching `proxy_set_header` line to the deployment guide's copyable proxy configuration.

**Rationale**: Observed to work, end to end. With `X-Forwarded-Port: 15603` present:

| | address the app believes it serves | bookmarklet addresses | POST from a browser on `:15603` |
|---|---|---|---|
| **today** | `titan.example.com` | no port | **400 refused** |
| **with `x_port=1`** | `titan.example.com:15603` | both carry `:15603` | **accepted** |

That single row is FR-001, FR-004 and FR-005 at once, and it is the whole of the defect.

**Alternatives considered**: Both were the issue's own candidates, and the probe confirms both are
genuinely viable rather than straw men — which is why the choice was the owner's to make and was made
on 2026-08-21.

- *Proxy carries the port inside `X-Forwarded-Host`.* The probe's "port in host only" case works
  **today**, with no code change: `request.host` comes out `titan.example.com:15603` and the POST is
  accepted. Rejected because it fixes one deployment by reconfiguring it and leaves every other
  correctly-configured-looking deployment silently broken.
- *Stop trusting `X-Forwarded-Host`.* Would restore the port, since the `Host` header carries it
  untouched, but regresses the case `x_host=1` was added for in the first place.

---

## Decision 2 — Write no default-port normalization, because the framework already does it

**Decision**: Nothing. FR-003 needs no code.

**Rationale**: I expected this to be the hard part, and expected to have to write a normalization
step. Reading `ProxyFix.__call__` predicts trouble — its `x_port` branch rewrites `HTTP_HOST` to
`f"{host}:{x_port}"` **unconditionally**, with no check for whether the port is the default for the
scheme. On that reading, a deployment on 443 that declares `X-Forwarded-Port: 443` would end up
believing it lives at `titan.example.com:443`, whose referrer check would then refuse a browser that
sent `https://titan.example.com/…` — because `same_origin` compares parsed ports, and `443` is not
`None`. Adding the port declaration to the deployment guide would then have broken every
default-port deployment that followed it.

**The probe says that does not happen.** With `X-Forwarded-Port: 443` and `https`, the app believes
it serves `titan.example.com`, with no port, and a default-port browser is accepted. Same for `80`
over `http`. The mechanism is one layer further down than `ProxyFix`, in `werkzeug.sansio.utils.get_host`:

> The port is omitted if it matches the standard HTTP or HTTPS ports.

`ProxyFix` does write `:443` into `HTTP_HOST`; `get_host` takes it back out before anything the
application can see. So the corrupt-by-construction environ never reaches `request.host`, `url_for`,
or the referrer check.

This is the finding that most changes the shape of the work. Had I planned from the reading of
`ProxyFix` alone, this feature would have shipped a normalization helper that was pure dead weight —
exactly the speculative machinery Principle I prohibits, and it would have looked well-justified.

**Alternatives considered**: a normalization step after `ProxyFix`; instructing the deployment guide
to declare the port only when non-default. Both rejected as solving a problem that does not exist.

---

## Decision 3 — Reject a malformed port declaration before `ProxyFix` reads it

**Decision**: Drop `HTTP_X_FORWARDED_PORT` from the environ when its value is not a plain decimal
number, so `ProxyFix` falls back to the host it already has.

**Rationale**: This is the one case where the change makes things **strictly worse than today**, and
that is what takes it out of the realm of hypothetical hardening. Observed, with
`X-Forwarded-Port: not-a-port`:

| | address the app believes it serves | bookmarklet addresses |
|---|---|---|
| **today** | `titan.example.com` — degraded but usable | `https://titan.example.com/…` |
| **with `x_port=1`, unguarded** | `''` — **empty** | `https:///api/capture` — **corrupt** |

Every address the application builds loses its host entirely, and every secure POST is refused. The
mechanism is again `get_host`, whose contract is explicit:

> If the host header is not available … or it has invalid characters, the empty string is returned.

`ProxyFix` composes `titan.example.com:not-a-port`, `get_host` finds characters that cannot be in a
host, and returns `''`. There is no error, no log line, and no clue: the operator sees a site whose
every link is malformed.

This satisfies FR-007, but FR-007 is not the reason to do it. The reason is that a change whose
purpose is to fix a broken deployment must not introduce a new way to break one. A guard that
prevents a regression the probe actually produced is not speculative generality — it is the change
being finished. Note the asymmetry with Decision 2: the same requirement covers both, one needs no
code because the framework handles it and one needs four lines because the framework does not, and
only the probe distinguishes them.

**Alternatives considered**:

- *Accept it; a proxy sends `$server_port`, which is always numeric.* True of the configuration the
  deployment guide will recommend, and false the moment someone types a literal. Rejected because the
  failure is total and silent rather than partial and visible.
- *Validate and log a warning instead of dropping.* Rejected: the operator is not reading logs, and
  falling back to the host that arrived is the behaviour they already have today.

---

## Decision 4 — Where the new tests go, and what they assert

**Decision**: Extend `tests/unit/test_proxy_headers.py`, the file whose gap allowed this. Assert the
bookmarklet's two addresses for FR-008, and for FR-009 assert `flask_wtf.csrf.same_origin` against
`f"https://{request.host}/"` — the exact expression the referrer check builds — with `request.host`
captured from inside a request through the existing `client` fixture.

**Rationale**: FR-009 has to cover the *write* path, and the write path's failure is a same-origin
comparison, not a rendered address. Asserting the addresses alone would have missed nothing here
only by luck: the probe shows one case (`X-Forwarded-Port: 443`) where the addresses are right and
`request.host` still carries information the addresses do not. Asserting the real comparison function
against the real expression is the difference between testing the defect and testing near it.

**Alternatives considered**: a full CSRF-enabled `POST` with a scraped token and a forged `Referer`.
It is the most faithful possible test and it is what a reader would reach for first. Rejected: it
needs `WTF_CSRF_ENABLED` flipped on for one test, a token scraped from a rendered form, and a forged
referrer — three pieces of scaffolding whose own correctness would be load-bearing, to reach a
comparison that can be asserted directly in one line. Recorded here so the next reader knows it was
weighed rather than missed.

---

## Decision 5 — The fix is not deployable without a version bump

**Decision**: Bump `version` in `pyproject.toml` to `0.1.1` as part of this feature.

**Rationale**: This is a delivery blocker that has nothing to do with the code, and it is easy to
finish the work without noticing it. The release workflow builds and pushes a container image **only
when the version is higher than the latest GitHub release**; on an unchanged version, an ordinary
merge to `main` deliberately does nothing. The version has not moved since SemVer was adopted.

So a merged fix with no bump produces no image, and the deployment stays broken. SC-001 and SC-002
can only be checked against the deployed build, which means they cannot be checked at all until an
image exists. The deployment guide's own rule makes this a **PATCH** — "bug fixes and documentation"
— and this feature is exactly both.

**Alternatives considered**: leaving the bump to a separate release step. Rejected because it strands
this feature's own acceptance criteria behind an action nobody has been assigned.

---

## What remains unobserved

Everything above was established against the test client. Three things can only be confirmed against
the real deployment behind the real proxy, and the spec already says so:

- that the proxy in front of `titan.jasonantman.com:15603` does send `X-Forwarded-Port` once
  configured (SC-007),
- that a real form submission is accepted (SC-001),
- that a freshly dragged bookmarklet loads its agent on a vendor listing (SC-002).

No amount of further probing moves these. They are a manual verification task in Phase 2.
