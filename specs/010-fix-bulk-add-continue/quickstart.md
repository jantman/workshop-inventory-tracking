# Quickstart: Validating the Add & Continue Bulk Fix

How to see the defect, then prove it is gone. Everything here runs against the repository
virtualenv (Constitution, Development Workflow).

```bash
source venv/bin/activate
```

`nox` sessions pin Python 3.13; if the system Python is newer, put pyenv's 3.13 on `PATH` first.

## 1. Reproduce it by hand (before the fix)

```bash
python manage.py run      # or however the app is normally started locally
```

1. Open `/inventory/add` with the browser console visible.
2. Fill the required fields: JA ID (pre-filled), Type, Shape, Material, Location, and whatever
   dimensions the type/shape combination demands.
3. Set **Quantity to Create** to `3`.
4. Press **Add & Continue**.

What you should see today, and what tells you which interleaving you hit:

- The console logs `Submit: Submitting form with type: continue` **and**
  `Submit: Submitting form with type: add` — two runs of the same handler from one press. This
  line is the clearest single piece of evidence.
- Then either:
  - a red error toast (`Failed to create any items`) beside the green "3 Items Created
    Successfully" dialog — the JA-ID collision; or
  - no error at all, and `/inventory` now lists **six** new items — the silent doubling, which is
    the outcome that matters.
- Either way, dismissing the dialog leaves you on the same filled-in form. The "continue" never
  happens.

Compare against **Add** with the same quantity: one handler run, three items, no error.

## 2. Automated validation

```bash
nox -s tests      # unit suite; must stay green and unchanged
nox -s e2e        # allow a 15-minute tool timeout (Constitution IV)
```

Targeting just this feature's coverage while iterating:

```bash
nox -s e2e -- tests/e2e/test_bulk_creation.py
```

The full `e2e` run is not optional before merge. The add path is named in Constitution VI, so the
active-status and history suites are part of this change's regression surface, not adjacent
scenery. `nox -s e2e` selects `-m "e2e and not screenshot"`, so a run must leave the working tree
clean — if `git status` is dirty afterwards, something ran that should not have.

### The two assertions that carry the fix

| Requirement | How it is checked | Before | After |
|-------------|-------------------|--------|-------|
| FR-001 — one request per action | `page.on("request", ...)` counts `POST /inventory/add` | 2 | 1 |
| FR-002 — exactly N items | `len(InventoryService(live_server.storage).get_all_items())` delta | 3 or 6, nondeterministic | 3 |

Confirm the request-count test genuinely bites before trusting it: stash the fix, run that test
alone, and watch it fail with 2. A regression test that has never been seen red is not yet a
regression test (SC-005).

## 3. Manual acceptance walkthrough (after the fix)

Each step maps to a requirement so a failure names what broke.

| # | Action | Expected | Covers |
|---|--------|----------|--------|
| 1 | Quantity `6`, press **Add & Continue** | Console logs the handler once. Dialog: "6 Items Created Successfully". No error toast. | FR-001, FR-003 |
| 2 | Dismiss the dialog | Lands on a fresh `/inventory/add`; JA ID auto-populated to the next free ID; per-item fields cleared | FR-006 |
| 3 | Press **Carry Forward** | Success toast; type, shape, material, location, notes restored from the batch just created | FR-008 |
| 4 | Check `/inventory` | Exactly 6 new items, sequential JA IDs, no duplicates | FR-002, FR-004 |
| 5 | Quantity `3`, press **Add** (not continue) | 3 items, dialog appears; after dismissing, **still on the filled-in form** — no navigation | FR-007, FR-011 |
| 6 | Quantity `1`, press **Add & Continue** | Unchanged from today: item created, returned to an empty Add form | FR-011 |
| 7 | Quantity `1`, press **Add** | Unchanged from today: item created, redirected to the inventory list | FR-011 |
| 8 | Clear a required field, quantity `4`, press **Add & Continue** | Validation reported; **nothing created** — verify the item count did not move | FR-010 |
| 9 | Quantity `4`, press **Add & Continue** twice in quick succession | One batch of 4, not two. Buttons return to their normal labels and enabled state | FR-005, Edge Cases |
| 10 | Quantity `4`, press Enter in a text field | Behaves as **Add** (Enter's submitter is the first submit button), one submission | Edge Cases |

Step 5 is the one most easily lost: if **Add** starts navigating too, the two buttons have
collapsed into one and FR-007 is broken even though every count is right.

## 4. Before opening the PR

- `nox -s tests` and `nox -s e2e` both green; working tree clean after the e2e run.
- Screenshots **not** regenerated. The change is a `type` attribute, a hidden input, and event
  wiring — none of it renders. `.github/workflows/screenshots.yml` will still post its reminder
  comment on any PR touching `app/templates/**` or `app/static/js/**`; it blocks nothing and its
  own text says regeneration is not reproducible. Say so in the PR description rather than
  committing byte-different PNGs for zero visual change. (research.md D6.)
- `nox -s lint` is advisory and is red at baseline on pre-existing E501 failures. New lines should
  satisfy it; do not reformat surrounding code.
