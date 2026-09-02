# Quickstart: Verifying API Routes Answer With JSON Errors

**Feature**: `specs/035-api-error-json` | **Date**: 2026-09-01

How to see the defect, and how to confirm it is gone. Every command assumes the repository
virtualenv is used **by path** — do not `source venv/bin/activate`.

## Prerequisites

```bash
cd /home/jantman/GIT/workshop-inventory-tracking
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"   # nox needs python3.13 on PATH
```

## 1. Reproduce, and re-verify after the fix

One script covers every case in the contract. It destroys nothing — every id it names does not
exist. It builds storage the way `tests/conftest.py` does (SQLite behind `MariaDBStorage`), because
the routes resolve a real backend before they can raise; `create_app(TestConfig)` with no backend
fails on engine creation instead of reaching the handler.

```bash
cat > /tmp/api_error_repro.py <<'PY'
"""Issue #132: an /api/ route answers a bodyless request with an HTML redirect."""
import tempfile
from sqlalchemy import create_engine
from app import create_app
from app.database import Base
from app.mariadb_storage import MariaDBStorage
from tests.test_config import TestConfig

db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
db.close()
uri = f"sqlite:///{db.name}?check_same_thread=false"
Base.metadata.create_all(create_engine(uri))
storage = MariaDBStorage(database_url=uri)
storage.connect()

client = create_app(TestConfig, storage_backend=storage).test_client()

CASES = [
    ("GET  /api/products/999999", "get", "/api/products/999999", {}),
    ("GET  /api/products/999999 +ct", "get", "/api/products/999999",
     {"Content-Type": "application/json"}),
    ("DEL  /api/attachments/999999", "delete", "/api/attachments/999999", {}),
    ("DEL  /api/products/1/identifiers/999999", "delete",
     "/api/products/1/identifiers/999999", {}),
    ("GET  /api/no-such-route", "get", "/api/no-such-route", {}),
    ("GET  /products/999999 (page)", "get", "/products/999999", {}),
]

for label, method, path, headers in CASES:
    r = getattr(client, method)(path, headers=headers)
    where = r.headers.get("Location") or r.content_type
    print(f"{label:42} -> {r.status_code} {where}")
PY
PYTHONPATH=. venv/bin/python /tmp/api_error_repro.py 2>&1 | grep -v '"timestamp"' | tail -8
```

**Before the fix** (measured on `main` at `2e6d63a`, 2026-09-01):

```
GET  /api/products/999999                  -> 302 /inventory
GET  /api/products/999999 +ct              -> 404 application/json
DEL  /api/attachments/999999               -> 302 /inventory
DEL  /api/products/1/identifiers/999999    -> 302 /inventory
GET  /api/no-such-route                    -> 302 /index
GET  /products/999999 (page)               -> 302 /inventory
```

Lines 1, 3, 4 and 5 are the defect. Line 2 is the same request as line 1 plus a `Content-Type`
header and **no body**, and it gets the correct answer — which is the mechanism in one comparison:
the format follows what the caller *declared*, not what the route is.

Two things here are wider than issue #132 records, and both are in scope under FR-001:

* The bug is not specific to `DELETE`. `GET /api/products/<id>` for a missing product redirects too;
  any bodyless request does.
* An unrouted `/api/` path redirects to `/index` rather than returning a JSON 404.

**After the fix**, the first five lines must all read `404 application/json` with no `Location`, and
**line 6 must be unchanged** — a `404` on the page route is a regression against FR-004.

## 2. Run the tests

```bash
venv/bin/nox -s tests
```

Unit suite, under a second. The new file is `tests/unit/test_api_error_format.py`.

```bash
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

**Run e2e detached and poll.** It takes about 13m 45s warm, which does not fit inside a 10-minute
agent bash timeout — a foreground run reports a false timeout on a passing suite. Budget 20 minutes
cold.

To run only the attachments file while iterating:

```bash
nohup venv/bin/nox -s e2e -- tests/e2e/test_product_attachments.py > /tmp/e2e.log 2>&1 &
```

An e2e run must leave the working tree clean — check `git status` afterwards.

## 3. The manual two-tab check (issue #132's inherited item)

Issue #132 carries a verification checkbox moved over from #80. The e2e test covers it, but the
issue asks for it by hand as well:

1. Start the app and open one product's detail page in **two** browser tabs, with at least three
   attachments on it.
2. In tab A, delete one attachment with its own trash button.
3. In tab B — still showing the stale grid — tick that attachment plus two others and press
   **Delete Selected**.

**Expect**: no error, the grid empties, the page reloads.

**Expect it for the right reason.** Open DevTools → Network in tab B before pressing. There must be
**three** `DELETE` requests and **nothing** to `/inventory`. The stale one must show `404`. A `302`
followed by a request to `/inventory` means the fix is not in effect — and note that the follow-up
appears as `DELETE /inventory` answered `405`, not as a page load: `fetch` preserves the method
across a 302 for everything but a `POST`. That 405 is why the unfixed build shows *"1 attachment
could not be removed"* here rather than silently succeeding.

Also press the per-tile trash button on a stale tile in tab B: it must reload the page, **not** show
*"Could not remove that attachment"*.

## Success criteria mapping

| Criterion | Verified by |
|---|---|
| SC-001 | Step 1, lines 1-5; `tests/unit/test_api_error_format.py` |
| SC-002 | The predicate test over the path matrix, plus the per-route tests |
| SC-003 | Step 3's network panel; the e2e test's recorded request list |
| SC-004 | The existing partial-failure e2e tests, which now exercise a real failure path |
| SC-005 | Step 1, line 6; `nox -s tests` and `nox -s e2e` green |
