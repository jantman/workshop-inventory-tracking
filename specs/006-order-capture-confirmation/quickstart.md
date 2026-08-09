# Quickstart: Validating "Order Capture Confirmation"

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

How to run and verify this feature end to end. Shapes and payloads live in [data-model.md](./data-model.md) and [contracts/](./contracts/) rather than being repeated here.

---

## 1. Prerequisites

- Repository virtualenv at `venv/`. **Invoke its binaries by path** — `venv/bin/nox`, `venv/bin/python`.
- Python 3.13 on PATH for nox to build its environments (the system Python is newer):
  ```bash
  PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
  ```
- Docker, for the throwaway MariaDB in step 3. The e2e suite already pulls `mariadb:11.8`, so the image is probably cached.

No label printer is needed, and no vendor account. Every step below works against a listing URL you paste by hand.

---

## 2. Run the suites

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e     # 15-minute tool timeout
```

Then, because `app/templates/product/**` changes:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
git status --porcelain          # must be empty
```

The screenshot set covers inventory-item pages only — there is no capture or receive screenshot — so the expected result is **no diff**. If this produces a diff, something unrelated to this feature moved and it needs explaining before the PR.

---

## 3. Exercise the migration both ways

**Read this before running anything.** `b1a0c0d10008` is the only step in the feature that can lose data, and it is the only step no automated test covers: `tests/conftest.py:51` and `tests/e2e/test_server.py:62` both build the schema with `Base.metadata.create_all`, so neither `nox -s tests` nor `nox -s e2e` ever executes an Alembic revision.

**Run it against a disposable container, never against the database in `.env`.**

```bash
docker run --rm -d --name capture-migration-check \
  -e MARIADB_ROOT_PASSWORD=throwaway \
  -e MARIADB_DATABASE=workshop \
  -p 3399:3306 mariadb:11.8

export SQLALCHEMY_DATABASE_URI='mysql+pymysql://root:throwaway@127.0.0.1:3399/workshop'
venv/bin/python manage.py db upgrade b1a0c0d10007     # get to the parent revision
```

### Seed rows worth losing

At revision `b1a0c0d10007`, insert purchases covering the cases a careless backfill mangles:

| Purchase | `notes` before upgrade | Must end up as |
|---|---|---|
| A | `https://www.amazon.com/dp/B0ABCDEFGH/ref=sr_1_3` — a bare captured URL | `listing_url` set to that URL; `notes` **unchanged**, still holding it |
| B | `Arrived dented, vendor sent a replacement` — operator prose | `listing_url` NULL; notes untouched |
| C | `https://example.com/thing — arrived dented` — a URL *and* prose | `listing_url` NULL (`LIKE 'http%'` matches, so decide deliberately: the backfill copies the **whole** notes value, which is wrong here). **Verify what your implementation does with this row and make the revision match the table.** |
| D | `NULL` | `listing_url` NULL |

Row C is the one to think about. The backfill as specified copies the whole notes value, so C would get a `listing_url` with prose glued to it. Either tighten the predicate so C is skipped, or accept it and say so in the revision's docstring — but do not discover it in production.

### Up, down, up

```bash
venv/bin/python manage.py db upgrade                  # apply b1a0c0d10008
venv/bin/python manage.py db downgrade b1a0c0d10007   # exercise the downgrade
venv/bin/python manage.py db upgrade                  # and come back
```

Name the previous revision explicitly. `db downgrade -1` is the form you will reach for and it does not work here — this Flask-Migrate CLI parses `-1` as an option and exits with `Error: No such option '-1'` before Alembic sees it.

### Check, do not trust the exit code

After the **first upgrade**:

- `DESCRIBE purchases` lists `listing_url varchar(1000) YES`.
- A has `listing_url` set and `notes` **still holding the same URL** — the backfill copies, it does not move.
- B and D have `listing_url` NULL.
- Re-running `db upgrade` is a no-op (the revision is applied), and re-running the backfill statement by hand changes nothing, because of the `listing_url IS NULL` guard.

Then insert a row the way the *new* code does — `listing_url` set, `notes` empty — before downgrading.

After the **downgrade**:

- `DESCRIBE purchases` no longer lists `listing_url`.
- The row you just inserted has its URL in `notes`. This is the assertion that makes the round trip lossless.
- A's notes are unchanged. B's prose is unchanged — it must not have been overwritten by a NULL `listing_url`.

After the **second upgrade**: the first set of checks again.

```bash
docker rm -f capture-migration-check
unset SQLALCHEMY_DATABASE_URI
```

---

## 4. Manual validation, one section per user story

Start the app against your normal development database and open `/products/capture`.

### US1 — Author the description at capture

1. Paste `https://www.amazon.com/dp/B0ABCDEFGH/ref=sr_1_3`. Vendor fills as `Amazon`, item id as `B0ABCDEFGH`.
2. Set **Listing Title** to something long and shouty, and **Description** to `12V 3A PSU, 5.5mm barrel`.
3. Capture. You land on the receive screen.
4. Open the product: its description is your wording. Open the purchase: the listing title is the vendor's, unaltered (FR-004).
5. Repeat with the description left blank and confirm the listing title becomes the description (FR-003).
6. Paste 300 characters into the description and confirm the submission is **refused with the limit named**, not truncated (FR-006).

### US1 — the bookmarklet landing

The bookmarklet cannot be driven from CI, and it only reaches the app when this application is served over TLS, so this is the hand-check that matters:

1. From an `https` view of `/products/capture`, drag **Capture to Workshop** to the bookmarks bar.
2. On a vendor listing, click it. A new tab opens on **the capture form, pre-filled** — not on the receive screen.
3. Confirm no product and no purchase exists yet: check `/products`.
4. Close the tab without submitting. Check `/products` again — still nothing (FR-009).

Without TLS you can simulate the same request:

```bash
curl -i -X POST http://localhost:5000/api/capture \
  -d 'url=https://www.amazon.com/dp/B0ABCDEFGH' \
  -d 'listing_title=Blue Widget 10-Pack'
```

Expect `200` and an HTML body containing `id="description"` — not a `302` to a receive screen.

### US2 — Correct the description at receipt

1. Open an outstanding purchase's receive screen. The description is an **editable field**, pre-filled.
2. Change it, set a quantity, and press **Mark Received**. One submission: the product's description is updated and the purchase is received (FR-023).
3. Re-open the same receive screen. Change the description again and submit. It updates, and the received date does not move (FR-025). Confirm the already-received banner says so accurately.
4. Clear the description entirely and submit. Refused, with the reason named; the description and the received state are both unchanged (FR-024).

### US3 — Duplicates

1. Capture the same URL twice on the same day. The second submission comes back with `#duplicate-warning` naming the first purchase, and **nothing has been written**.
2. Follow the link to the existing purchase. Check `/products` — still one product, one purchase (FR-014).
3. Capture again, tick **"This is a separate order — record it anyway"**, submit. Now there are two purchases against one product (FR-012, FR-015).
4. Repeat with a URL that yields no item number — anything that is not `/dp/<ASIN>/`, e.g. `https://www.mcmaster.com/91290A115/`. The warning must still appear, matched on the address (FR-013).
5. Backdate one capture's order date by a day and confirm no warning (FR-016).

### US4 — A recycled item number

1. Create a product by hand with a `VENDOR` identifier of `B0ABCDEFGH` scoped to `Amazon`, manufacturer `Mean Well`, part number `RS-15-12`.
2. Capture `https://www.amazon.com/dp/B0ABCDEFGH` with **no** manufacturer or part number. `#identifier-warning` appears, naming the product and showing its part number, with no option pre-selected (FR-017).
3. Submit without choosing. It comes back and still writes nothing (FR-018).
4. Choose **"This is a different product"**. A second product is created; the first keeps its identifier and its purchase history untouched (FR-020).
5. Capture again, this time entering manufacturer `mean well` and part number ` RS-15-12 ` — deliberately different case and padding. It attaches **without asking** (FR-019); the fold is case- and whitespace-insensitive.
6. Capture again with the correct part number but no manufacturer. It **asks**: one value is not corroboration.

---

## 5. What the automated tests cover, and what they cannot

| Behaviour | `nox -s tests` | `nox -s e2e` | Manual |
|---|---|---|---|
| Duplicate detection on item id, on URL, and across days | ✅ | ✅ (US3) | |
| Acknowledged duplicate proceeds; stale acknowledgement re-raises | ✅ | | |
| Corroboration: both values, case-folded, Python-side | ✅ | ✅ (US4) | |
| `attach_to` new / existing / vanished | ✅ | ✅ (US4) | |
| Description at capture, fallback, over-length refusal | ✅ | ✅ (US1) | |
| Description at receipt, blank refusal, already-received case | ✅ | ✅ (US2) | |
| Nothing written when a decision is required | ✅ | ✅ | |
| `POST /api/capture` form body renders instead of writing | ✅ | ✅ | |
| 409 on the JSON path | ✅ | | |
| **Bookmarklet against a real vendor page** | | | ✅ only |
| **The Alembic round-trip** | | | ✅ only (step 3) |
| Collation behaviour of the SQL-side duplicate comparisons | | ✅ (MariaDB) | |

The two rows in bold are the ones with no automated coverage at all. The bookmarklet depends on the vendor's own content policy and on TLS, which CI has neither of; the migration is invisible to both suites because they build the schema with `create_all`.

---

## 6. Definition of done

- [ ] `nox -s tests` and `nox -s e2e` pass.
- [ ] `nox -s screenshots_headless` leaves `git status --porcelain` empty.
- [ ] The migration round-trip in step 3 has been run against a throwaway container, including the row-C decision, and the outcome matches the revision's docstring.
- [ ] `tests/unit/test_capture.py::TestIdempotency` has been **rewritten**, not deleted — the new class asserts the warn-and-let-the-operator-decide contract.
- [ ] `tests/unit/test_product_csrf.py` still passes unchanged: one `@csrf.exempt`, JSON capture still 201.
- [ ] Each of the four user stories has been walked by hand per step 4, including the bookmarklet landing over TLS.
- [ ] No `wait_for_timeout`, no `time.sleep`, no `networkidle` in the new e2e tests.
