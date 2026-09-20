# Quickstart: Validating Build Version Suffix

**Feature**: 047-build-version-suffix

How to prove this works, in rising order of cost. All commands run from the repository
root with the project virtualenv.

---

## 1. Unit suite (sub-second, covers every branch)

```bash
venv/bin/nox -s tests
```

The resolution table in [data-model.md](./data-model.md) is covered case for case by
`tests/unit/test_version.py`, which monkeypatches `app.version._git` and the environment
rather than building fixture repositories. Expect the stamp case, the four working-copy
cases, the unrelated-tag case, and the three `git`-unavailable cases.

`tests/unit/test_basic.py` additionally asserts the same string reaches both surfaces —
`/health` and the footer — which is the claim of SC-004.

---

## 2. Working copy, by eye (seconds)

The suffix is real in a development checkout, so the fastest end-to-end check is to ask
Python directly:

```bash
venv/bin/python -c "from app.version import __version__, RELEASE_VERSION; print(RELEASE_VERSION, '->', __version__)"
```

On a normal feature branch with no edits, expect `0.1.1 -> 0.1.1-<short sha>`. Touch a
tracked file and re-run; expect `-dirty` to appear. Check the short SHA against
`git rev-parse --short=7 HEAD`.

To see the tagged case without cutting a release:

```bash
git tag v0.1.1-quickstart-probe   # NOT the release tag; see below
```

That tag will *not* match, because matching requires the tag to be `v0.1.1` or `0.1.1`
exactly — which is the behaviour to confirm. Drop it again with
`git tag -d v0.1.1-quickstart-probe`. Do not create a real `v0.1.1` tag locally: the
release workflow owns that name, and a stray local tag pushed by accident would
misrepresent a release.

---

## 3. Container, both paths (a few minutes)

Reproduce what each workflow does, locally.

**CI path** — stamped:

```bash
docker build --build-arg BUILD_SHA="$(git rev-parse HEAD)" -t wit-ci-probe .
docker run --rm wit-ci-probe python -c "from app.version import __version__; print(__version__)"
# expect: 0.1.1-<first 7 of that sha>
```

**Release path** — unstamped:

```bash
docker build -t wit-release-probe .
docker run --rm wit-release-probe python -c "from app.version import __version__; print(__version__)"
# expect: 0.1.1
```

This second run also exercises the "no stamp, no git" fallback (FR-007): the runtime
image contains neither `.git` nor a `git` binary, so it takes the same path an unpacked
archive would.

To see it through HTTP rather than the import, start the image the way the workflow's
smoke test does — no database is needed for `/health`:

```bash
docker run -d --name wit-probe -p 5000:5000 \
  -e SECRET_KEY=probe -e SQLALCHEMY_DATABASE_URI=mysql+pymysql://u:p@127.0.0.1/db \
  wit-ci-probe
curl -s http://127.0.0.1:5000/health
docker rm -f wit-probe
```

Clean up the probe images afterwards (`docker rmi wit-ci-probe wit-release-probe`).

---

## 4. In CI, after merge

The `docker-build` job publishes `ghcr.io/jantman/workshop-inventory-tracking:ci-<sha>`.
Pull one and check that the version it reports ends in the first seven characters of the
tag's own SHA — which is SC-001 and SC-002 together: two CI images of the same release
number are distinguishable, and the suffix locates the commit.

---

## What this feature does not require

- **No database work.** No Alembic revision, no schema change, nothing persisted.
- **No screenshot regeneration.** `app/templates/`, `app/static/css/` and
  `app/static/js/` are untouched; the footer template is unchanged, only the value
  flowing into it.
- **No E2E test.** The footer already has unit coverage asserting the rendered version,
  and the change is to a string's contents, not to any page behaviour, navigation or
  request flow. `nox -s e2e` must still pass, but gains no new test.
