# Implementation Plan: Restore the Browser's Port Behind a Reverse Proxy

**Branch**: `issues/114` | **Date**: 2026-08-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/023-restore-forwarded-port/spec.md`

## Summary

A deployment behind a TLS proxy on a non-default port cannot save data. The proxy declares the
forwarded host without a port, the application believes that declaration and overwrites the host it
received — which did carry the port — and from then on it believes it lives at an address the
browser never used. Every secure form submission is refused by the referrer check, and the capture
bookmarklet hands out addresses on a port nothing listens on.

The remedy is to trust one hop of the forwarded **port** declaration alongside the scheme, host and
client address already trusted, and to say so in the proxy configuration the deployment guide hands
out. Phase 0 confirmed by observation that this is sufficient, that the default-port case needs no
code because Werkzeug already strips a standard port, and that one guard is genuinely required: an
unguarded change turns a malformed port declaration into an *empty* host, which is worse than
today's behaviour. See [research.md](research.md) for the probe and its five findings.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask, Werkzeug (`ProxyFix`, `sansio.utils.get_host`), Flask-WTF (the
referrer check). Nothing new is added.

**Storage**: Not touched. No schema change, no Alembic revision, no data written or read differently.

**Testing**: pytest via `nox -s tests`, using the existing `test_storage` → `app` → `client` fixture
chain in `tests/conftest.py`. No new pytest markers.

**Target Platform**: Linux, containerized, behind a TLS-terminating reverse proxy on the LAN.

**Project Type**: Flask web application, single project.

**Performance Goals**: None. The change is a per-request environ read that already happens for three
other headers.

**Constraints**: The no-proxy path and the default-port path must be byte-for-byte unchanged — the
end-to-end suite runs over plain HTTP on a default port and would not notice a regression there.

**Scale/Scope**: One line in the application factory, one small guard, one test file extended, two
documentation sections, one version bump.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 — see below.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | **Pass.** No new dependency, no abstraction, no configuration knob. The one item that could read as speculative — the malformed-port guard — is justified in Complexity Tracking against an observed regression rather than a hypothesis. Phase 0 *removed* planned work here: the default-port normalization I expected to write turned out to be dead code. |
| **II. Layered Architecture Boundaries** | **Pass.** The change is confined to the application factory in `app/__init__.py`, where the existing `ProxyFix` wrapping already lives. No route, service, storage or model is touched; no layer is crossed. |
| **III. Exact Numerics** | **N/A.** No physical measurement is involved. |
| **IV. Test Discipline Through Nox** | **Pass.** New tests extend `tests/unit/test_proxy_headers.py`, build through `tests/conftest.py`, and run under `nox -s tests`. No new marker, so `--strict-markers` is satisfied. No end-to-end test is added or changed, so nothing new can wait on a clock and the working tree stays clean. FR-008 and FR-009 must be **seen to fail** before the fix — the constitution's "write the test that would have caught the bug" stated as a procedure. |
| **V. MariaDB Is the Source of Truth** | **Pass.** No migration; nothing in the persistence path changes. |
| **VI. Item Lifecycle and History Invariants** | **N/A.** No item is created, moved, shortened or deactivated by this change. |

**Post-Phase-1 re-check**: unchanged. The Phase 1 artifacts introduced no new dependency, no new
module, and no new interface beyond documenting the header contract that already exists between the
proxy and the application.

## Project Structure

### Documentation (this feature)

```text
specs/023-restore-forwarded-port/
├── spec.md                      # /speckit-specify output
├── plan.md                      # This file
├── research.md                  # Phase 0 — the probe and its five findings
├── data-model.md                # Phase 1 — the environ→address transformation
├── quickstart.md                # Phase 1 — how to validate, automated and by hand
├── checklists/
│   └── requirements.md          # spec quality checklist
├── contracts/
│   └── proxy-headers.md         # Phase 1 — what the proxy must declare
└── tasks.md                     # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
└── __init__.py                  # create_app: the ProxyFix wrapping (line 32) and the guard

tests/
└── unit/
    └── test_proxy_headers.py    # extended: the non-default-port cases that do not exist today

docs/
├── deployment-guide.md          # "Serving Behind a TLS Reverse Proxy": the proxy config block
└── troubleshooting-guide.md     # "Common Nginx Issues": the new symptom, beside the missing-scheme one

pyproject.toml                   # PATCH version bump, without which no image is built
```

**Structure Decision**: Single Flask project, unchanged. This is a defect fix inside an existing
seam — the application factory already wraps the WSGI app to interpret forwarded headers, and this
feature adds one more thing for it to interpret. Nothing is created, moved, or introduced.

## Phase 0 — Outline & Research

Complete. [research.md](research.md) records five decisions, each observed rather than argued:

1. **`x_port=1` is the remedy** — confirmed to restore the port into `request.host` and into both
   bookmarklet addresses, and to make the refused POST accepted.
2. **No default-port normalization** — Werkzeug's `get_host` already omits a standard port, so the
   `:443` corruption that `ProxyFix`'s source predicts never reaches the application. Planned work
   deleted.
3. **A malformed port declaration must be rejected** — unguarded, it produces an *empty* host and
   addresses of the form `https:///api/capture`. This is the sole case the change would make worse
   than today, which is what justifies the guard.
4. **The tests assert the real comparison** — `same_origin` against `f"https://{request.host}/"`,
   because the write-path failure is a same-origin comparison and not a rendered address.
5. **A version bump is part of the fix** — no bump means no container image, which means the fix
   cannot be deployed and SC-001/SC-002 cannot be checked at all.

No `NEEDS CLARIFICATION` markers remain. The two open questions at spec time — which remedy, and
whether #113's blocked check belongs here — were both answered on 2026-08-21 and are recorded in the
spec's Assumptions and Out of Scope sections.

## Phase 1 — Design & Contracts

Complete.

- **[data-model.md](data-model.md)** — this feature persists nothing, so the "model" is the
  transformation the request environ undergoes and the address that falls out of it. It gives the
  observed value at each stage for every case the spec's Edge Cases name, which is what turns those
  edge cases into assertions.
- **[contracts/proxy-headers.md](contracts/proxy-headers.md)** — the contract between the reverse
  proxy and the application. It already existed, undocumented as a contract and stated only in prose;
  this feature adds a term to it, so it is written down as terms with an observed consequence for
  breaking each one.
- **[quickstart.md](quickstart.md)** — validation. The automated half, including the requirement to
  watch the new tests fail first; and the manual half against the real deployment, which is the only
  place SC-001, SC-002 and SC-007 can be settled.

## Complexity Tracking

One item is recorded here because a reviewer applying Principle I strictly would challenge it, and it
should be defended in writing rather than discovered later.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| A guard rejecting a non-numeric `X-Forwarded-Port` before `ProxyFix` reads it — input validation on a header from the one hop the application already trusts, which Principle I's threat model says needs no defending | It is not defence, it is regression control. Phase 0 observed that `x_port=1` **without** the guard turns a malformed declaration into an empty host and every built address into `https:///…`, where today the same input is merely ignored. The change would introduce a failure mode strictly worse than the defect it fixes, and one that is silent — no error, no log, just a site whose every link is malformed. Four lines. | *Accept it, since a proxy sends `$server_port` and that is always numeric*: true of the recommended configuration, false the moment a literal is typed, and the failure is total rather than degraded. *Log a warning instead of dropping*: the operator is not reading logs, and falling back to the arriving host is exactly the behaviour they have today. |
