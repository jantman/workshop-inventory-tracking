# Quickstart: Validating "Structured Specifications"

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

How to run and verify this feature end to end. Shapes and payloads live in [data-model.md](./data-model.md) and [contracts/](./contracts/) rather than being repeated here.

---

## Prerequisites

- Repository virtualenv at `venv/`. **Invoke its binaries by path** — `venv/bin/nox`, `venv/bin/python`.
- Python 3.13 on PATH for nox to build its environments (the system Python is newer):
  ```bash
  PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
  ```
- MariaDB reachable per `.env`. This feature's most important validation step needs a real MariaDB with real rows in it — SQLite will not do.

No label printer is needed. This feature prints nothing and changes nothing about what is printed.

---

## The migration round-trip

**Read this section before running anything.** This is the one step in the feature that destroys data if it is wrong, and it is the one step no automated test covers: `tests/conftest.py:51` and `tests/e2e/test_server.py:61` both build the schema with `Base.metadata.create_all`, so neither `nox -s tests` nor `nox -s e2e` ever executes an Alembic revision.

### Seed something worth losing

Against a database at revision `b1a0c0d10006`, before applying anything, create products covering the cases that break naive migrations:

| Product | `specifications` content |
|---|---|
| A | `12 V, 3 A` — the ordinary case |
| B | `Voltage: 12 V` + newline + `Current: 3 A` — contains a colon and a newline, which a splitter would be tempted by |
| C | `` (NULL) — must end with no rows, not an empty one |
| D | `   ` (whitespace only) — must also end with no rows |

Record A's and B's exact text somewhere you can diff against.

### Up, down, up

```bash
venv/bin/python manage.py db upgrade                  # apply b1a0c0d10007
venv/bin/python manage.py db downgrade b1a0c0d10006   # exercise the downgrade
venv/bin/python manage.py db upgrade                  # and come back
```

Name the previous revision explicitly. `db downgrade -1` is the form you will reach for and it does not work here — this Flask-Migrate CLI parses `-1` as an option and exits with `Error: No such option '-1'` before Alembic sees it.

### Check, do not trust the exit code

After the **first upgrade**:

- `SELECT * FROM product_specifications` — A and B have exactly one row each, `name = 'Specifications'`, `display_order = 0`. C and D have none.
- B's `value` is byte-identical to what you recorded, colon and newline intact, not split into two rows.
- `DESCRIBE products` no longer lists `specifications`.

After the **downgrade**:

- `DESCRIBE products` lists `specifications` again.
- A's and B's text is character-for-character what you started with (SC-002). This is the assertion that matters most.
- C and D are still NULL.
- `product_specifications` is gone.

After the **second upgrade**: the first set of checks again.

Then repeat the round-trip once more with a product edited into *several* named rows first, and confirm the downgrade produces a readable `name: value` block containing every name and value. That is FR-024's standard — no content lost — not byte-identity, which is only promised for untouched carry-across rows.

---

## Running the suites

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests   # unit, SQLite, network blocked
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e     # Playwright — 15-minute tool timeout
```

Never invoke `pytest` directly (Constitution IV). The `e2e` session needs a 15-minute timeout set on the tool running it, not on the command line; it runs in about 8m 15s warm, and the margin is for a cold start that pulls the MariaDB image and installs browsers.

**Screenshots are mandatory for this change.** It touches `app/templates/product/**` and `app/static/js/**`, so:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

Commit the regenerated images with the change. CI blocks merge on stale screenshots. `nox -s e2e` deliberately excludes screenshot tests, so an e2e run must leave the working tree clean.

---

## Manual validation

```bash
venv/bin/python app.py
```

### US1 — Record specifications as named values

1. Add a product. The Specifications card is a row of **Name** / **Value** inputs with an **Add specification** button, not a textarea.
2. Record `Voltage` / `12 V`, `Output current` / `3 A`, `Connector` / `barrel 5.5 mm`. Save.
3. On the product page, expect three labelled fields in the order entered — not a paragraph, and not alphabetized.
4. Edit it. Each specification is an editable pair. Change one, remove one, add one, save. Expect exactly what you left.
5. Open a product created before the migration. Expect one specification named `Specifications` carrying its original paragraph, in full.
6. Add a product with no specifications. Expect no Specifications card at all — an ordinary state, not an error.

**The refusals** — each should leave the form as you left it, with a message naming the offender:

| Try | Expect |
|---|---|
| `Voltage` / `12 V` and `voltage` / `5 V` on one product | Refused: duplicate name. Case is not what distinguishes two specifications. |
| A name with an empty value | Refused, naming the name. |
| A value with an empty name | Refused, naming the value. |
| An entirely blank row alongside good ones | Saved, blank row ignored — **not** an error (FR-009). |

Also worth trying once: `Volt` and `Vôlt` on one product. These are **different** names and both must save. The database would disagree if a unique constraint had been added, which is why there isn't one.

### US2 — Find every product with a given specification

1. Seed three products: one with `Voltage` / `12 V`, one with `Voltage` / `5 V`, and one whose *description* says "12 V input" but which records no voltage specification.
2. On the catalogue list, filter `spec_name = Voltage`, `spec_value = 12 V`. Expect exactly the first. The third must not appear — that is SC-001, and it is the whole point of the feature.
3. Filter on `Voltage` with no value. Expect the first two.
4. Filter `voltage` in lower case. Expect the same results (FR-015). This is the case the unit suite cannot prove.
5. Filter `12` as the value. Expect the `12 V` product — matching is contained, not exact (FR-014).
6. Combine with a category or tag filter. Expect both to narrow together.
7. Filter a name nobody records. Expect an empty list, not an error.
8. From a product page, click a specification. Expect the catalogue filtered to that name and value (FR-018).
9. Search the free-text box for a word that appears only in a specification value. Expect the product (FR-017) — nothing findable before this change may stop being findable.

### US3 — Suggestions

1. With `Voltage` recorded somewhere, start typing `Vol` in a specification name on another product. Expect `Voltage` offered.
2. Accept it, then focus the value. Expect the values already recorded under `Voltage` offered.
3. Change that row's name to `Connector`. Expect the value suggestions to change with it — they are per row, not one shared list.
4. Type a name and a value nobody has used. Expect both accepted (FR-021, SC-007). A datalist cannot restrict entry, which is why one is used.
5. Record `voltage` in lower case on one product and `Voltage` on another. Expect **one** suggestion, not two (FR-019). Another case the unit suite cannot prove.
6. On the catalogue filter, expect the same name suggestions.

### Draft persistence — the regression to watch

1. Start adding a product. Fill the description and three specification rows. Do **not** save.
2. Navigate away and return to the Add Product form.
3. Click **Restore it**. Expect all three specification rows back, with their names and values, in order.

This is an existing feature (FR-035), and the field it was tested against is the one this change removes. If restore comes back with only the last row, `product-form.js` did not learn about repeated names.

---

## What the automated tests cover

| Story | Unit | E2E |
|---|---|---|
| US1 — record and display | `test_catalog_service.py` (create, replace-on-update, each refusal, blank-row drop, ordering), `test_product_model.py` (`to_dict` shape) | `test_product_specifications.py`, updated `test_product_crud.py` |
| US2 — filtering | `test_product_search.py` (name-only, name+value, contained match, value-without-name ignored, combination with other filters, free text over specs) | `test_product_specifications.py` |
| US3 — suggestions | `test_catalog_service.py` (`list_specification_names`, `list_specification_values`, prefix narrowing) | `test_product_specifications.py` |
| Draft persistence | — | rewritten `test_draft_persistence.py` |
| The migration | **none** | **none** — the manual round-trip above is the only coverage |

**Two requirements are invisible to `nox -s tests`; the third turned out to be the other way round.** Each was confirmed by making the implementation deliberately case-sensitive and watching which suite went red:

| Requirement | Guarded by | Confirmed |
|---|---|---|
| FR-004, duplicate names | e2e — `test_a_refusal_re_renders_...[entries0]` | yes |
| FR-019, suggestion dedup | e2e — `test_one_name_recorded_in_two_cases_yields_one_suggestion` | yes |
| FR-015, name filter | **unit** — `TestSpecificationFilter.test_the_name_filter_is_case_insensitive` | yes; the e2e test stayed green |

FR-015's guard belongs to the unit suite because `utf8mb4_uca1400_ai_ci` folds case inside the comparison operator, so on MariaDB `name == 'voltage'` already matches `Voltage` and dropping `func.lower` is unobservable there. SQLite is the backend that disagrees, so SQLite is where the test has to live. See [research.md](./research.md#what-the-tests-can-and-cannot-prove).

The discipline itself is commit `091e918`'s, established after the same collation gap deleted a tag and every one of its associations: confirm the test fails without the fix rather than assuming it would.

**A note for whoever writes the e2e tests.** The add and edit flows are form posts that navigate, so `expect()` on the resulting page is the whole wait. The datalists are the render-implies-completion case (CLAUDE.md pattern C): options are appended only after the fetch resolves, so `expect(datalist.locator('option')).to_have_count(n)` is a complete signal. Adding a row is synchronous DOM work — `expect(rows).to_have_count(n)` covers it. Do **not** assert "this product is absent from the filtered list" with `count()` against a table nothing has established first; establish it with a positive `expect()` on a product that *should* be there, then assert the absence.

Seed with `live_server.add_test_products([...])`, which already exists in `tests/e2e/test_server.py:192` and takes `create_product` kwargs — so it accepts the new `specifications` list with no change. Drive the form only in the tests where the form is the subject: US1's round-trip, the refusals, and draft persistence.

---

## Definition of done

- `nox -s tests` and `nox -s e2e` green.
- `nox -s screenshots_headless` run and its output committed; `nox -s screenshots_verify` green.
- **The migration round-trip performed against MariaDB with real rows**, including the colon-and-newline paragraph, and the character-for-character check made rather than assumed.
- The three collation-sensitive e2e tests confirmed to fail against a case-sensitive implementation.
- The working tree is clean after a test run.
