# Contracts: Build Version Suffix

**Feature**: 047-build-version-suffix

Three surfaces are contracts here: one Python module surface, one HTTP response, and one
build-time input. None of them changes shape; two of them change what they can contain.

---

## 1. `app/version.py` module surface

```python
RELEASE_VERSION: str   # NEW. "0.1.1" -- the declared release number, always bare SemVer.
__version__: str       # EXISTING NAME, WIDENED VALUE. The version to report.
```

**`__version__` before**: always `MAJOR.MINOR.PATCH`.

**`__version__` after**: `MAJOR.MINOR.PATCH` optionally followed by `-<7 chars>` and
optionally followed by `-dirty`. Matches:

```text
^\d+\.\d+\.\d+(-[0-9a-f]{7})?(-dirty)?$
```

**Why `RELEASE_VERSION` is added**: exactly one existing consumer needs the bare number —
the unit test asserting the project version is SemVer. Without a name for the bare
number that test would have to re-read `pyproject.toml` itself, duplicating the one piece
of logic this module exists to own. It is not a general-purpose accessor and has no other
caller.

**Importers that do not change**: `app/__init__.py` (`from app.version import __version__`,
re-exported and injected into templates as `app_version`) and `app/main/routes.py`
(`from app import ... __version__`). Both keep working unmodified, which is the point.

**Private helpers** (`_` prefix, not a public surface, but named because the unit tests
reach for one of them):

```python
def _git(*args: str) -> str | None
    # Runs `git <args>` in the repository root. Returns stripped stdout on success,
    # None on ANY failure: non-zero exit, git missing, not a repository, timeout.
    # Never raises.

def _version_suffix(release_version: str) -> str
    # "" | "-abc1234" | "-dirty" | "-abc1234-dirty"
```

---

## 2. `GET /health`

Response shape is unchanged. Status stays `200`. Only the `version` value widens.

```json
{
  "status": "healthy",
  "service": "workshop-inventory-tracking",
  "version": "0.1.1-6d15bde"
}
```

**Guarantee**: `version` here is byte-identical to the string the footer renders after
its literal `v` prefix. They are the same object, read from the same module attribute
(FR-001, SC-004).

**Consumers to be aware of**: the Dockerfile `HEALTHCHECK` fetches this endpoint and the
`docker-build` job's smoke test curls it. Neither parses `version`, so neither breaks.

---

## 3. Docker build argument

```dockerfile
ARG BUILD_SHA=""
ENV APP_BUILD_SHA=$BUILD_SHA
```

| | Passes `BUILD_SHA`? | Value | Image reports |
|---|---|---|---|
| `test.yml` → `docker-build` | yes | `${{ steps.image.outputs.sha }}` — PR head SHA, or push SHA | `0.1.1-<7 chars>` |
| `release.yml` → `release` | no | argument unset, `ENV` empty | `0.1.1` |
| `docker build .` by hand | no | argument unset, `ENV` empty | `0.1.1` |

**Accepted input**: any commit identifier of at least seven characters. The application
truncates; the workflow passes the full forty. Whitespace-only is treated as unset.

**The build argument must be declared in the runtime stage**, not the builder stage.
`ARG` is scoped to the stage it appears in, and it is the runtime stage that needs to
carry the `ENV` forward.

**Cache note**: `ENV APP_BUILD_SHA=$BUILD_SHA` is placed immediately before the
`HEALTHCHECK`/`CMD` at the end of the runtime stage, after every `COPY`. A value that
changes on every commit invalidates its layer and all layers below it, so it belongs
below the expensive ones.

---

## 4. What is explicitly *not* a contract

- The exact `git` commands used, or the number of them.
- The `APP_BUILD_SHA` name as a *user-facing* setting. It is set by the image build. It
  is not documented as a deployment configuration variable and is not in
  `config.py`; setting it by hand at `docker run` time is neither supported nor
  prevented.
