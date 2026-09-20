# Data Model: Build Version Suffix

**Feature**: 047-build-version-suffix | **Date**: 2026-09-20

No database entity changes. No Alembic revision. Nothing is persisted. The "model" here
is the small set of values that combine into the reported version string, all of them
resolved once at process start.

## Values

| Value | Source | Type | Example |
|---|---|---|---|
| `RELEASE_VERSION` | `[project].version` in `pyproject.toml` | `str` | `0.1.1` |
| build stamp | `APP_BUILD_SHA` environment variable | `str` (may be empty/absent) | `6d15bde4d4cda7c8ec7a0e277cf926ad2bf7881c` |
| current commit | `git rev-parse --short=7 HEAD` | `str` or `None` | `6d15bde` |
| tags at HEAD | `git tag --points-at HEAD` | list of `str` (possibly empty) or `None` | `["v0.1.1"]` |
| tracked-file edits | `git status --porcelain --untracked-files=no` | `str` (empty means clean) or `None` | `" M app/version.py"` |
| `__version__` | derived from the above | `str` | `0.1.1-6d15bde-dirty` |

`None` from a `git` value means the question could not be answered — not a repository,
`git` not installed, `git` failed, or `git` timed out. All four are the same outcome.

## Reported version grammar

```text
version   := RELEASE_VERSION [ "-" short-sha ] [ "-dirty" ]
short-sha := 7 characters of a commit identifier
```

The footer prepends a literal `v` for display. That `v` is in the template today and
stays there; it is not part of the string (FR-001).

## Resolution order

```text
1. APP_BUILD_SHA is set and non-empty
      -> RELEASE_VERSION + "-" + first 7 characters
      -> DONE. Git is never consulted.

2. Otherwise, ask git:
      commit  = rev-parse --short=7 HEAD
      tags    = tag --points-at HEAD
      dirty   = status --porcelain --untracked-files=no  (non-empty output)

   a. commit is None (any git failure)
         -> RELEASE_VERSION
   b. tags contains "v<RELEASE_VERSION>" or "<RELEASE_VERSION>"
         -> RELEASE_VERSION            + ("-dirty" if dirty)
   c. otherwise
         -> RELEASE_VERSION + "-" + commit + ("-dirty" if dirty)
```

Step 1 taking precedence over step 2 is required by the spec's edge cases: a container
started from inside a working copy must report what it was built from, not what happens
to be on disk around it.

Step 2a returning the bare number — rather than falling through to a dirty check — is
deliberate. If `git` cannot be reached at all, "dirty" is not knowable either, and
reporting `0.1.1` is the honest answer.

## Worked cases

| Situation | `APP_BUILD_SHA` | commit | tags | dirty | Reported |
|---|---|---|---|---|---|
| CI image, PR head `6d15bde4…` | `6d15bde4d4cd…` | — | — | — | `0.1.1-6d15bde` |
| Release image | absent | `None` | `None` | `None` | `0.1.1` |
| Working copy on release tag | absent | `6d15bde` | `["v0.1.1"]` | no | `0.1.1` |
| Working copy on release tag, edited | absent | `6d15bde` | `["v0.1.1"]` | yes | `0.1.1-dirty` |
| Working copy, untagged | absent | `abc1234` | `[]` | no | `0.1.1-abc1234` |
| Working copy, untagged, edited | absent | `abc1234` | `[]` | yes | `0.1.1-abc1234-dirty` |
| Working copy on an unrelated tag | absent | `abc1234` | `["nightly"]` | no | `0.1.1-abc1234` |
| Unpacked archive, no `.git` | absent | `None` | `None` | `None` | `0.1.1` |
| `git` not installed | absent | `None` | `None` | `None` | `0.1.1` |
| `git` hangs past the timeout | absent | `None` | `None` | `None` | `0.1.1` |
| `APP_BUILD_SHA` set to whitespace | `"   "` | falls through to git | | | per git rows above |

## Lifecycle

Computed once, at import of `app.version`, which happens once per worker process. There
is no invalidation and no refresh: an image's provenance cannot change while it runs, and
a working copy's can, but reporting the state at start is what "what am I running?"
means. This satisfies FR-009 and SC-006 with no caching machinery — module-level
evaluation *is* the cache.
