# Quickstart: Validating Label Print Count

**Feature**: [spec.md](./spec.md) | **Date**: 2026-08-11

How to confirm the feature works. Contracts are in
[contracts/labels-print-api.md](./contracts/labels-print-api.md); the reasoning behind the choices is
in [research.md](./research.md). Neither is repeated here.

## Prerequisites

```bash
source venv/bin/activate      # required before anything that needs project deps
```

`nox` sessions pin Python 3.13. If the system Python is newer, put pyenv's 3.13 on `PATH` first or
the sessions will not find an interpreter.

**No printer is involved and none is required.** With `TESTING` or `DISABLE_LABEL_PRINTING` set, the
short-circuit at `app/services/label_printer.py:92` logs what it would have printed and returns.
Nothing in either suite reaches `LpPrinter.print_images()`, which drives real hardware.

## The suites

```bash
nox -s tests                  # unit; network blocked; well under a second
nox -s e2e                    # Playwright; ~8m15s warm
```

`nox -s e2e` outlasts the Bash tool's timeout cap — run it in the background and collect the result,
rather than in the foreground where it will be cut off. `nox -s lint` is red at baseline on
pre-existing E501s; it is not a gate for this change.

An e2e run must leave the working tree clean. If `git status` is dirty afterwards, a screenshot test
was selected — the session filters with `-m "e2e and not screenshot"` precisely to prevent that.

## What each layer proves

Splitting it this way matters because "three labels came out" is not observable from this repository.
The chain below is the closest honest substitute, and each link is where a regression would surface.

| Claim | Layer | Assertion |
|-------|-------|-----------|
| A count of N reaches the printer as N images | unit | `patch(...LpPrinter)`; `print_images` called once with a list of length N |
| The route validates and forwards the count | unit | `patch('app.services.label_printer.print_label_for_ja_id')`; assert call args |
| Out-of-range and non-integer counts are refused | unit | POST the bad value; expect 400 and the message from the contract |
| A dialog sends the count the user typed | e2e | Intercept `/api/labels/print` and read the request body |
| The user is told what happened | e2e | `expect()` on the alert or summary text |

The e2e request-interception pattern already exists — `test_label_printing_test_mode_verification`
in `tests/e2e/test_label_printing.py` registers a `page.on("request", ...)` handler before clicking.
Extend it to capture `request.post_data` rather than only counting calls.

## Manual walkthrough

Run the app against a real printer only if you want to see paper. Everything below can be checked
with the browser's network tab instead.

**Story 1 — single item.** Add Item → fill the required fields → **Print Label**. The dialog shows
**Number of labels** at `1`. Pick a label type, set it to `3`, print. Success message names three
labels. Reopen the dialog: the count is back at `1`, the label type is still remembered (that
persistence is unchanged).

**Story 2 — list bulk.** Inventory list → tick three items → Options → **Print Labels**. The dialog
shows **Labels per item** at `1`. Set it to `2`, pick a label type, **Print All Labels**. Progress
reads `Printing 1 of 3: JA…  (2 labels)`; the summary reads `Complete: 6 labels for 3 items, 0
failed`.

**Story 3 — after a bulk creation.** Add Item → set the form's **quantity** to 4 → submit. The print
dialog opens over the form. Two things to check, because both are new:

1. Its label type list offers the six real types (`Sato 1x2`, `Sato 1x2 Flag`, `Sato 2x4`, …) — not
   the three sizes it used to show. Before this feature every press of Print All returned 400.
2. Its **Labels per item** starts at `1`, *not* at the `4` that was just typed into the form. These
   are different numbers and the dialog must not conflate them.

Set it to `2`, print: `Complete: 8 labels for 4 items, 0 failed`.

**Boundaries.** In any of the three dialogs, enter `0`, `100`, `2.5`, or clear the field and press
print. Nothing is sent, the dialog stays open with the label type still selected, and the message
names the 1–99 range. Then `curl` past the browser to confirm the route does not depend on it:

```bash
curl -s -X POST localhost:5000/api/labels/print \
  -H 'Content-Type: application/json' \
  -d '{"ja_id":"JA123456","label_type":"Sato 1x2","label_count":500}'
# {"success": false, "error": "label_count must be between 1 and 99"}
```

## Regressions to watch

These are the existing behaviors most likely to break, and the suites that catch them.

- **Omitting `label_count` still prints one label.** `tests/unit/test_label_printer.py` posts two
  fields today and must keep passing untouched. Note that
  `test_print_label_endpoint_success` asserts `mock_print.assert_called_once_with('JA123456', 'Sato
  1x2')` positionally — that assertion has to be updated when the route starts passing a count, and
  updating it is correct, not a workaround.
- **Bulk creation itself is unaffected.** The FR-012 repair touches the dialog offered *after*
  creation, never creation. `tests/e2e/test_bulk_creation.py` must stay green in full;
  `test_bulk_label_printing_modal_content` in particular reads the modal's title and item list, which
  this feature does not change.
- **Label type persistence on the Add Item form.** `test_label_type_persistence_add_item_form`
  guards it. The count is deliberately *not* persisted; the label type still is.
- **The search page's bulk dialog is out of scope.** It remains a stub with no label types and no
  print action. Leaving it inert is the specified outcome, not an oversight.

## Waiting, for the new e2e tests

Per CLAUDE.md, wait on state and never on a duration. For this feature:

- The label-type selects populate from a `fetch`. `wait_for_select_populated(page, "<id>")` in
  `tests/e2e/waits.py` already exists — the post-bulk-Add dialog needs it now that its options come
  from the API rather than being hardcoded in the template.
- The bulk run's completion is rendered after every request settles, so the summary text is a
  complete signal — `expect(status).to_contain_text("Complete:")` is the whole wait.
- Do not read `text_content()` on the progress region before an `expect()` has established it. A
  negative assertion about a label count ("the request did not carry a count") would otherwise pass
  against a dialog that has not finished opening.
