# Quickstart: Validating Product Catalog & Purchase Tracking

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

How to run and verify this feature end to end. Scenarios map to the spec's user stories and
success criteria; details of shapes and payloads live in [data-model.md](./data-model.md) and
[contracts/](./contracts/) rather than being repeated here.

---

## Prerequisites

- Repository virtualenv at `venv/`. **Invoke its binaries by path** — `venv/bin/nox`,
  `venv/bin/python`. Do not `source venv/bin/activate`.
- Python 3.13 on PATH for nox to build its environments:
  ```bash
  PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
  ```
- MariaDB reachable per `.env` for migrations, integration, and e2e.
- A label printer configured in CUPS **only** if you intend to print for real. All automated
  tests short-circuit before `lp`.

---

## Setup

```bash
venv/bin/python manage.py db upgrade                  # apply b1a0c0d10001..b1a0c0d10005
venv/bin/python manage.py db downgrade 8213852b0b94   # exercise the downgrades
venv/bin/python manage.py db upgrade                  # and come back
```

Name the previous revision explicitly. `db downgrade -1` is the form you will reach for and it
does not work here — this Flask-Migrate CLI parses `-1` as an option and exits with
`Error: No such option '-1'` before Alembic sees it. This feature's five revisions sit on top of
`8213852b0b94`, so naming it walks the whole chain down in one command.

Exercising the downgrade is not optional: Constitution V requires each revision's `downgrade` to
have been run, and against **MariaDB** — SQLite will not catch an index/FK ordering fault, which
is a failure mode this repository has already hit once. This chain is the one most likely to
expose that: the six tables it creates are linked by foreign keys, so they only drop cleanly in
the right order.

Confirm it actually moved rather than trusting the exit code. `SHOW TABLES` should list
`products`, `purchases`, `product_identifiers`, `tags`, `product_tags` and `product_attachments`
after each upgrade and none of them in between.

---

## Running the suites

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests    # unit, SQLite, network blocked
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e      # Playwright — needs a 20-min timeout
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s coverage
```

Never run `pytest` directly (Constitution IV). `e2e` runs long enough to exceed a default
10-minute command timeout — set 20 minutes, or run it detached and poll.

**Screenshots.** This feature adds templates, CSS, and JS, so the documentation screenshots must
be regenerated and committed with the change or CI blocks the merge:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

---

## Scenario 1 — Identify a part in hand (Story 1, SC-001)

1. Create a product with a description and specifications at `/products/new`.
2. Print its label (`Sato 2x4`). With `DISABLE_LABEL_PRINTING` set, confirm the log records the
   composed label rather than printing.
3. Scan the printed code — or `POST /api/scan` with the internal code.

**Expected**: the product detail view, showing description, specifications, purchase history, and
location. No external network request is made at any point (SC-001).

## Scenario 2 — Unknown code never dead-ends (Story 1 scenario 3, SC-008, FR-018)

`POST /api/scan` with a valid but uncatalogued GTIN.

**Expected**: `200` with `outcome='create'` and the GTIN in `prefill` — an offer to create the
product with the identifier attached. **Not** a `404`, not an error page.

Then `POST /api/scan` with unparseable junk.

**Expected**: `200` with `outcome='search'` carrying the raw scan. Still not an error.

## Scenario 3 — Capture and label (Story 2, SC-003)

Record a received purchase, author a description, print. Then reprint from the product detail
view without re-entering anything.

**Expected**: the label carries description, provenance, and the code in **both** scannable and
human-readable form (FR-012). The reprint requires no data entry (SC-003).

## Scenario 4 — Order-time capture (Story 3, SC-002)

Click the bookmarklet on a vendor listing, or paste the URL at `/products/capture`.

**Expected**: an unreceived purchase exists with vendor, item identifier, listing title, order
date, and price. Capturing the same listing again creates nothing new. On receipt, the captured
details are already present and only description and specifications need authoring (SC-002).

## Scenario 5 — Distributor label (Story 4, SC-004)

Scan a DigiKey/Mouser 2D label — or `POST /api/scan` with a format-06 envelope.

**Expected**: manufacturer part number, quantity, and order references extracted into an editable
draft; no new label printed. Then scan an envelope with a corrupted body: the **raw scan** is
surfaced for manual handling, not a silent failure.

> This scenario depends on the wedge capture preserving `GS` (`0x1d`) and `RS` (`0x1e`). It is
> the most breakable link in the feature — a capture path that strips non-printing characters
> passes every other test and fails only here.

## Scenario 6 — Repeat purchase (Story 5, SC-005)

Record two purchases of one product at different prices and dates.

**Expected**: one chronological history under one product, most recent price visible, no
duplicate product created.

## Scenario 7 — Reorder view (Story 6, SC-006, SC-007)

Flag an untracked product low. Set a tracked product's quantity at or below its threshold. Leave
an outstanding order on one of them.

**Expected**: both appear at `/products/reorder`; the one with an outstanding order is marked as
on the way. Mark that order received — the tracked product's low status clears via the updated
quantity, and the **manually flagged** one clears because the receipt path clears the flag
explicitly (the FR-029 asymmetry in research §10; verify both halves).

Separately, confirm a product with `quantity = 0` and a product with `quantity = NULL` are
visibly different everywhere quantity is shown (SC-007).

## Scenario 8 — Classify and find (Story 7, SC-009)

Assign products to nested categories and cross-cutting tags.

**Expected**: filtering by a category returns it **and its sub-categories**; filtering by a tag
ignores category; searching matches description, specification, and identifier. A category typed
during product creation is created inline with no setup step.

## Scenario 9 — Touch and interruption (FR-035, FR-036, SC-010)

Compose a long description, kill the connection before submitting, reload.

**Expected**: the in-progress text is offered for restore.

Then drive Scenario 1 and Scenario 7 on a touch viewport with no keyboard.

**Expected**: every action completes — quantity adjust and stock-status set are reachable as
touch targets (SC-010).

---

## Pre-merge checklist

- [ ] `nox -s tests` green
- [ ] `nox -s e2e` green (20-minute timeout)
- [ ] Every new Alembic revision's `downgrade` exercised against MariaDB
- [ ] Screenshots regenerated and `screenshots_verify` passing
- [ ] Any new pytest marker registered in `pytest.ini` (`--strict-markers` is on)
- [ ] No `float` anywhere near a price — `Decimal` only
- [ ] `inventory_items` and JA-ID history untouched
- [ ] `POST /api/capture` is the only CSRF exemption **this feature adds**, and it
      carries a comment saying why. (`app/main/routes.py` already contains several,
      predating this work.) Every other new endpoint keeps CSRF on and the client
      sends the token via the `X-CSRFToken` header -- see `app/static/js/csrf.js`.
