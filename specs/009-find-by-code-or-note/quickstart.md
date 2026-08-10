# Quickstart: validating Find By Any Code Or Note

**Feature**: `specs/009-find-by-code-or-note` | **Date**: 2026-08-09

How to prove the three changes work, and what each proof is actually worth. Details of behaviour live in [`contracts/scan-classification.md`](contracts/scan-classification.md) and [`contracts/search-and-addressing.md`](contracts/search-and-addressing.md); this is the run guide.

## Prerequisites

```bash
source venv/bin/activate
```

pyenv's Python 3.13 must be ahead of the system Python on `PATH` — the nox sessions pin 3.13 and the system Python is 3.14.

Run tests through `nox`, never `pytest` directly (Constitution IV).

## The commands

```bash
nox -s tests           # unit; under a second, network blocked
nox -s e2e             # give your tool a 15-minute timeout
nox -s screenshots_headless && nox -s screenshots_verify
git status --porcelain # MUST be empty after any test session
```

`nox -s lint` is red at baseline on this repo (pre-existing flake8 E501). It is advisory and not a gate; check that your new files are clean rather than that the session is green.

---

## Scenario 1 — a manufacturer's 2D barcode resolves (US1)

### The unit proof, which is the real one

Classification is a pure function, so the exhaustive matrix belongs in `nox -s tests`. Work the full input tables in `contracts/scan-classification.md`; the rows that matter most are the ones a plausible implementation gets wrong:

- **The extractor does not validate.** `decode_trade_item_number('0109506000134353')` returns `'09506000134353'` — a bad check digit, returned anyway — and `'0100000000000000'` returns fourteen zeros. If either returns `None`, extraction has started judging and `gtin.py` is no longer the single source of truth.
- **Those same two inputs classify as `FREE_TEXT`.** Extraction succeeded and validation refused, which is FR-006 working.
- **`'0109506000134352 RES 10K'` is `FREE_TEXT`.** The tail rule. Get this wrong and prose becomes a barcode.
- **`'\x1d10LOT42\x1d0109506000134352'` is `FREE_TEXT`.** Only a payload *opening* with the trade item number is read (FR-007).
- **Nothing else moved.** `'9506000134352'`, `'00012348'`, `'WIT…'`, `'[)>\x1e06\x1dP123\x1e\x04'`, `'B0ABC12345'`, `'M3 standoff'` all classify exactly as they do on `main` today (FR-008).

One more assertion belongs here, because it is the design expressed as behaviour:

- **Equivalence.** `classify('0109506000134352')` and `classify('9506000134352')` agree on `kind` and `value` and differ only in `raw`. That is FR-002 stated as a test.

The single-`normalize_and_validate`-call property from `contracts/scan-classification.md` is deliberately **not** a test. `tests/unit/test_gtin.py` and `tests/unit/test_ecia.py` are behaviour-only, with no source inspection anywhere in them, and a `inspect.getsource(...).count(...)` assertion would be the first of its kind in this suite. It is a code-review property; the equivalence test above is what protects the behaviour that property exists to protect.

### The e2e proof

One test, because the unit suite already covers the grammar and what e2e adds is that the wedge, the route and the service are wired together:

```
seed a product carrying GTIN 00012345678905
scan '0100012345678905' into #global-scan-input, terminated with Enter
expect(page.locator("#product-description")).to_have_text(...)
```

Reuse `test_wedge_scan.py`'s existing `scan()` helper — it types keystrokes and presses Enter rather than posting to the API, which is the point of that file. Seed with `live_server.add_test_products([...])`, not the Add Product form: the form costs about three seconds a product.

**Expected before the change**: this lands on the search page. That is the bug.

### By hand

Scan box in the header, on any page. Type `0100012345678905` and press Enter.

| You type | You should get |
|---|---|
| `0100012345678905` (catalogued) | that product's page |
| `0100012345678905` (not catalogued) | the create form, GTIN attached, type `GTIN` |
| `0100012345678353` (bad check digit) | a search carrying the raw text — **not** a product |
| `010001234567890517260101` | the same product; the trailing date is ignored |

---

## Scenario 2 — notes are searched (US2)

### Unit

Add to `TestTextSearch` in `tests/unit/test_product_search.py`, alongside the existing `test_matches_a_description` and friends:

- a phrase held only in `notes` finds the product;
- a product with no notes is not returned for it;
- a term matching product A by description and product B by notes returns **both, once each** — this is the assertion that proves sameness and non-duplication together, and it is the one worth writing;
- a notes match still obeys a category / tag / stock / spec filter applied alongside it (FR-013).

**Do not write a case-insensitivity test.** SQLite and MariaDB agree about `LIKE` folding, so such a test passes whether the code says `like` or `ilike` and proves nothing about which. FR-012 is guaranteed by using the identical construct as the sibling clauses, not by a test.

### E2E

Covered adequately by the unit suite plus one check that the screen's copy names notes. If you add an e2e case, seed with `add_test_products` and establish the results region with `expect(...)` before any `count()` — a negative assertion against a table that has not rendered passes trivially.

### By hand

Products → All Products. Search for a phrase you know is only in one product's notes. Read the search box's placeholder: it must name notes, and it must agree with `docs/user-manual.md:749`.

---

## Scenario 3 — the printed code is an address (US3)

### Unit

`tests/unit/test_routes.py` or a sibling, using the `client` fixture:

- `GET /products/<code>` for a real code → **302** to `/products/<id>`;
- the same code lowercased → **302** to the same place;
- a well-formed code no product carries → **404**;
- a segment that is not a code → **404**.

**And the shadowing test, which is not optional.** Enumerate `/products`, `/products/new`, `/products/capture`, `/products/reorder`, `/products/categories`, `/products/tags` and assert each still resolves to its own endpoint. Werkzeug's rule ordering makes this true, but it fails silently and far from its cause if it is ever not.

### E2E

```
product = live_server.add_test_products([{'description': 'LM358 op-amp'}])[0]
page.goto(f"{base_url}/products/{product.internal_code}")
expect(page.locator("#product-description")).to_have_text('LM358 op-amp')
```

`add_test_products` returns Product objects whose `identifiers` are eager-loaded, so `product.internal_code` is readable off the detached instance.

### By hand

Print or view a product's label, read the `WIT…` code, and type `/products/WIT…` into the address bar. You should land on that product, with the address bar showing the record-number URL.

---

## Regression: what must not have moved

This feature's largest risk is not that the new behaviour is wrong but that existing behaviour changed. Before calling it done:

- `nox -s tests` and `nox -s e2e` green, with **no previously passing test newly failing** — particularly `tests/unit/test_scan_router.py`, `tests/unit/test_gtin.py`, `tests/unit/test_ecia.py`, `tests/unit/test_scan_resolution.py`, `tests/e2e/test_wedge_scan.py` and `tests/e2e/test_ecia_scan.py`.
- `git status --porcelain` empty after every session, including the e2e one.
- `nox -s screenshots_verify` passes and `docs/images/screenshots/` is unchanged. One template is edited, but no screenshot covers the product catalogue — a diff there means something unintended happened.
- No Alembic revision was created. If you wrote one, the design was misunderstood: this feature stores nothing new.

## Writing the e2e tests

`CLAUDE.md` is normative here and worth re-reading before you add any wait. In short: wait on state, never on a duration; `page.wait_for_timeout` and `time.sleep` are prohibited; never `wait_for_load_state("networkidle")`; and never call `count()`, `text_content()`, `is_visible()` or `get_attribute()` against a JS-rendered region you have not first established with `expect(...)`.

All three of this feature's e2e paths are full page loads rather than fetch-driven updates, so the cheapest correct wait — `expect(locator)` on something the new page renders — is the right one throughout. None of them needs a helper in `tests/e2e/waits.py`.
