# Research: Build Version Suffix

**Feature**: 047-build-version-suffix | **Date**: 2026-09-20

Five questions had to be answered before the design was determined. Each is recorded
with the decision, why, and what was rejected.

---

## R1 — How does a built image learn the commit it was built from?

**Decision**: a Docker build argument, persisted into the image as an environment
variable.

```dockerfile
ARG BUILD_SHA=""
ENV APP_BUILD_SHA=$BUILD_SHA
```

The CI job passes `build-args: BUILD_SHA=${{ steps.image.outputs.sha }}` to
`docker/build-push-action`. The application reads `APP_BUILD_SHA` from the environment.

**Rationale**:

- The runtime image has no `git` binary and no `.git` directory. `git` is installed in
  the *builder* stage only (it is there for a `pip install` from GitHub), and the runtime
  stage copies `/opt/venv` plus source files — never history. So an in-container answer
  must be baked in at build time; nothing can be derived at run time.
- `test.yml` already computes the right SHA and exposes it as `steps.image.outputs.sha`,
  precisely because `github.sha` on a `pull_request` event is GitHub's synthetic merge
  commit, which does not exist in the repository. The existing comment in that job says
  so. Reusing that output means the suffix names a commit that can actually be looked up,
  which is SC-002.
- An environment variable is readable with `os.environ.get` — no file format, no parser,
  no new file in the image. It is also visible in `docker inspect`, which is a free
  diagnostic.

**Alternatives rejected**:

- *Writing a generated `app/_build_info.py` at build time.* Needs a `RUN` layer that
  writes Python source, and puts a generated file on the import path. More moving parts
  for the same result.
- *Reading the OCI image labels the workflows already set.* `org.opencontainers.image.revision`
  is exactly the value wanted, but labels are image metadata: a process inside the
  container cannot read them without talking to a Docker socket. Non-starter.
- *`COPY .git` into the image and use `git` at run time.* Adds the whole history to the
  image, adds a `git` binary to the runtime stage, and does per-start subprocess work for
  information already known at build time.
- *Baking the finished version string in as `APP_VERSION`.* Moves the formatting rule
  ("release number, hyphen, seven characters") into the workflow YAML, splitting one rule
  across two languages and two files. The application should own the format; the build
  should supply only the fact.

---

## R2 — How does a release image report a bare version, given R1?

**Decision**: the release workflow simply does not pass `BUILD_SHA`. Absent (or empty)
`APP_BUILD_SHA`, with no usable history alongside it, yields the bare release number.

**Rationale**: the observable requirement is FR-003 — a release image reports
`0.1.1`. With `ARG BUILD_SHA=""` as the default, an unpassed argument produces an empty
environment variable, and empty is treated as absent. No second variable, no
`APP_BUILD_RELEASE=1`, no branching on build kind anywhere in the application.

This is a deliberate simplification of the spec as first written; FR-005 was revised to
match. Principle I is explicit that a configuration knob needs a requirement in front of
it, and a positive release marker has none: its only consumer would be code that
produces the same output as the absent-stamp path.

**Alternatives rejected**:

- *A second variable `APP_BUILD_RELEASE`.* Two stamps, one outcome. The release image
  would have to be wrong in two ways to misreport, which is not a benefit worth a knob.
- *Passing `BUILD_SHA=""` explicitly from the release workflow.* Identical behaviour to
  omitting it, but reads as though it were doing something.

**Consequence accepted**: an image built by hand (`docker build .` with no argument) is
indistinguishable from a release image — both report the bare number. The spec's edge
cases already require exactly that ("no build stamp and no history ⇒ bare release
number"), and this project builds images in two places only, both of them workflows.

---

## R3 — Where does the working-copy (non-Docker) answer come from?

**Decision**: three `git` invocations through `subprocess.run`, each wrapped so that any
failure means "no answer", run once at import of `app/version.py`.

| Question | Command |
|---|---|
| What commit? | `git rev-parse --short=7 HEAD` |
| Are we on the release tag? | `git tag --points-at HEAD` |
| Are tracked files edited? | `git status --porcelain --untracked-files=no` |

**Rationale**:

- `--untracked-files=no` is load-bearing. Working in this repository leaves untracked
  scratch files constantly — `test-debug-output/`, `.pytest_cache/`, a scratch script.
  Plain `--porcelain` reports those as `??` and every developer run would say `-dirty`,
  which makes the marker noise instead of signal. The spec says "edits to **tracked**
  files" for this reason.
- `git tag --points-at HEAD` lists tags and exits 0 when there are none, so "on a tag"
  is a string test rather than an exception. `git describe --exact-match` exits non-zero
  in the ordinary untagged case, which would mean treating a normal exit code as normal —
  workable, but the listing form has no error path to get right.
- The tag is matched against the declared release number in both the `v`-prefixed and
  bare spellings. The release workflow creates `v<version>`; accepting the bare spelling
  as well costs one `or`.

**Alternatives rejected**:

- *Depending on `versionfinder`* (named in the issue). It is unmaintained, its last
  release predates Python 3.13, it pulls in `GitPython` and `pip` internals, and it
  answers a much larger question (which pip/git/egg source an *installed package* came
  from) than the one being asked. Principle I: "Dependencies MUST earn their place" and
  "prefer the standard library". Three `subprocess.run` calls are the standard-library
  answer, and about thirty lines.
- *`setuptools_scm` / `dunamai`.* Both assume a build step that produces a distribution.
  This application is not built or installed as a package — `pyproject.toml` says so in
  its own comment — so there is no build step to hook.
- *Shelling out to `git describe --dirty --always --tags`.* One command instead of three,
  but the output format is a blend (`v0.1.1-14-gabc1234-dirty`) that has to be parsed
  back apart into the shape the spec asks for, and its `-dirty` includes untracked files
  with no way to turn that off. Parsing a string that was assembled from facts is worse
  than asking for the facts.

---

## R4 — Is the working-copy path "a significant additional complication"?

**Decision**: no. It is in scope and ships alongside the container path.

**Rationale**: the issue makes Story 2 conditional and the spec requires the call to be
recorded here. The honest measure of the complication is: one private helper of roughly
thirty lines, one `subprocess` import, no new dependency, no new configuration, no change
to any caller, and no runtime cost beyond three subprocess calls at process start. It
shares the whole of its output path with the container case. The condition for dropping
it is not met.

The one real risk it introduces — a `git` invocation hanging and taking application
startup with it — is bounded by passing `timeout=5` and catching `TimeoutExpired`
alongside the other failures.

---

## R5 — What shape keeps this testable without a fixture repository?

**Decision**: isolate the subprocess call in one private helper, `_git(args)`, returning
stripped stdout or `None`. Everything above it is pure string logic. Unit tests
monkeypatch `_git`.

**Rationale**: the eight situations SC-005 enumerates (on tag / off tag × clean / dirty,
plus not-a-repository, `git` missing, `git` hanging, and stamp-present) all reduce to
"what did `_git` return". Monkeypatching one function covers all eight in the sub-second
unit suite with no temporary repositories, no `git init`, and no filesystem work.

Building real fixture repositories would cost seconds per test for coverage that is
strictly worse — a fixture repository cannot easily be made to represent "`git` is not
installed" or "`git` hangs".

**Consequence for module shape**: `app/version.py` currently computes `__version__` as a
module-level side effect. It keeps doing that, but the computation moves into functions
that tests can call directly with the environment and `_git` under their control, so no
test needs to re-import the module or manipulate `sys.modules`.

---

## Cross-cutting: what does *not* change

- `pyproject.toml` remains the single source of truth for the release number (FR-010).
- `app/__init__.py`, `app/main/routes.py` and `app/templates/base.html` are untouched.
  They consume `app.version.__version__`, and that name keeps meaning "the version to
  report" — it simply now has more to report. This is what makes FR-001 (one string,
  footer and health agree) true by construction rather than by two call sites being kept
  in step.
- No template, CSS or JS file changes, so the constitution's screenshot-regeneration gate
  is not triggered.
