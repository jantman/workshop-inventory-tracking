# Quickstart: Verifying the Documentation Refresh

**Feature**: 030-product-docs-refresh | **Date**: 2026-08-27

How to check this feature is done. Everything here is run by hand from the repository root — none of it becomes a nox session or a CI job (Principle I). Each check names the success criterion it discharges.

## Prerequisites

- The repository, on branch `030-product-docs-refresh`.
- `venv/` for the test runs, invoked by path (`venv/bin/nox`), with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"` so nox can build its 3.13 environment.
- No application changes: every check below assumes `app/` is untouched.

---

## 1. Configuration, checked in both directions (SC-002, SC-003)

The two lists must be identical once the guide is rewritten.

```bash
# What the guide documents
grep -oE '^[A-Z][A-Z0-9_]{2,}=' docs/deployment-guide.md | tr -d '=' | sort -u

# What the application, its CLI and its container actually read
{ grep -rhoE "environ(\.get\(|\[)['\"][A-Z0-9_]+" app/ config.py manage.py \
    | grep -oE '[A-Z0-9_]+$'
  grep -oE '^[A-Z_]+' .flaskenv
  echo CUPS_SERVER               # read by `lp`, not by Python (Dockerfile:28)
  echo CATEGORY_TAXONOMY_FILE    # read through a constant, see below
  echo SPECIFICATION_KEYS_FILE
} | sort -u
```

**Two things the second command cannot see on its own**, both hit while writing `research.md`:

- **Indirection.** `CATEGORY_TAXONOMY_FILE` and `SPECIFICATION_KEYS_FILE` are read via module constants (`app/utils/catalog_taxonomy.py:60,62`), so they are appended by hand above. Any future variable read through a constant needs the same treatment — grep for `_ENV = '` to find them.
- **`.flaskenv`.** Committed, read by the `flask` CLI, and it carries four settings including `FLASK_DEBUG=1`. Reading only its first line loses `FLASK_RUN_HOST` and `FLASK_RUN_PORT`.

Expected differences after the rewrite: **none**, except that `HTTP_X_FORWARDED_PORT` (a request header, not a setting) and the `TEST_DB_*` family (documented in the development guide instead) appear only on the right.

Then confirm the nine invented names are gone (SC-003):

```bash
grep -nE 'FLASK_ENV|STORAGE_BACKEND|SQLALCHEMY_TRACK_MODIFICATIONS|GOOGLE_CREDENTIALS_PATH|GOOGLE_TOKEN_PATH|APP_NAME|APP_VERSION|CACHE_TTL|BATCH_SIZE' \
  docs/deployment-guide.md docs/development-testing-guide.md .env.example
# expect: no output
```

And that the DigiKey four are present (SC-001):

```bash
grep -c 'DIGIKEY_CLIENT_ID\|DIGIKEY_CLIENT_SECRET\|DIGIKEY_ACCOUNT_ID\|DIGIKEY_API_BASE' docs/deployment-guide.md
# expect: 4 or more
```

## 2. The configuration is usable, not just present (SC-001)

Not a grep — a reading. Take the deployment guide alone and answer, without opening `config.py` or `.env.example`:

1. What must I set for the application to start at all?
2. What do I set to get DigiKey order capture, and where do those values come from?
3. What do I lose by setting nothing optional?
4. Why does my label printing not work in the container?

Every answer must be in the guide. Cross-check each against `contracts/configuration-reference.md`.

## 3. The vendor matrix (SC-004, SC-005)

```bash
# The summary exists and names all three vendors in one place
grep -n 'Amazon' docs/user-manual.md | head
grep -n 'McMaster-Carr\|DigiKey' README.md
```

Then read the summary against `contracts/vendor-capability-matrix.md` cell by cell. The three that are easiest to get wrong, and that a reviewer should check explicitly:

- Mouser, eBay and AliExpress yield a vendor **name** and nothing else — they are not "supported vendors" without that qualifier.
- DigiKey's backfill happens in **two** places: the part-lookup screen, and gap-filling on a product an order line matched.
- Amazon and McMaster-Carr order capture is the **bookmarklet on the vendor's own order page**; DigiKey's is an **order number typed in**.

Vendor names spelled as the application spells them:

```bash
grep -n 'Digi-Key' README.md docs/*.md   # expect: no output
```

## 4. Removals and links (SC-006, SC-007)

```bash
# The three targets are gone
ls docs/product-functionality-gap.md docs/spec-product-catalog.md docs/features 2>&1
# expect: three "No such file or directory"

# Nothing outside specs/ references them
grep -rn 'product-functionality-gap\|spec-product-catalog\|docs/features\|features/complete' \
  --include='*.md' --include='*.py' --include='*.yml' --include='*.yaml' \
  --include='*.html' --include='*.toml' --include='*.txt' \
  . --exclude-dir=venv --exclude-dir=.git | grep -v '^./specs/'
# expect: no output
```

References remaining under `specs/` are correct and must not be repaired (FR-006).

## 5. Nothing else moved (SC-008)

```bash
git diff --name-only main... | grep -E '^(app|tests|migrations)/'
# expect: no output

git diff --name-only main... | grep '^specs/' | grep -v '^specs/030-product-docs-refresh/'
# expect: no output
```

## 6. Spelling (repository rule)

```bash
grep -ric 'catalogue' README.md docs/ app/ tests/
# expect: every count 0
```

## 7. The suites still pass (SC-009)

Unchanged, unmodified, run once as a regression check:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e
```

`e2e` takes about 13m 45s warm and outlasts a 10-minute agent bash cap: run it detached and poll. It must also leave the working tree clean — `git status` after the run is part of the check.

## 8. The commit shape (FR-008)

```bash
git log --oneline main..HEAD
```

Three commits: removals first, then configuration, then vendors. The first must contain deletions and the carry-over sentence only, so it can be reverted alone.
