# Phase 0 Research: Label Print Count

**Feature**: [spec.md](./spec.md) | **Date**: 2026-08-11

The Technical Context carried no `NEEDS CLARIFICATION` markers — the one open scope question was
settled during `/speckit-specify`. What follows is the codebase research the design rests on, and
the six decisions it produced.

## What is already there

`app/services/label_printer.py:76` — `generate_and_print_label()` already accepts `num_copies: int = 1`:

```python
images: List[BytesIO] = [generator.file_obj] * num_copies if num_copies > 1 else [generator.file_obj]
printer.print_images(images)
```

Nothing has ever passed it a value. `print_label_for_ja_id(ja_id, label_type)` — the only caller —
does not take a count, so the parameter has sat at its default since it was written. The feature is
largely a matter of connecting a wire that is already run.

`LpPrinter.print_images(images, num_copies=1)` (in the `pt_p710bt_label_maker` package) writes each
image in the list to a temp PNG and passes all of them to a single `lp` invocation, and separately
supports `-n` for CUPS copies. So there are two routes to N labels, which is Decision 1.

## Decision 1 — N images in one `lp` job, not `lp -n N`

**Decision**: Keep the existing `[image] * N` list approach. Do not switch to
`print_images([image], num_copies=N)`.

**Rationale**: `lp -n N` delegates copy handling to the CUPS driver. This installation drives three
different Sato drivers (`sato2`, `sato3`, `SatoM48Pro2` — `LABEL_TYPES` in `label_printer.py:19`),
and whether each honors `-n` on a label stock is not something this repository can verify: there is
no printer in CI, and the test-mode short-circuit means no test ever reaches `print_images()`. N
explicit files depend on no driver feature — each file is a page, each page prints. The failure mode
of the rejected option is silent and only visible at the printer: you ask for 5 and get 1.

Reading `[generator.file_obj] * N` as a bug is tempting — it is the *same* `BytesIO` object N times,
and a repeated read of one stream would normally yield one payload and then nothing. It is not a bug
here: `print_images()` uses `i.getvalue()`, which returns the whole buffer regardless of stream
position. Verified by reading the installed package source.

**Alternatives considered**: `lp -n N` (fewer temp files, one page written instead of N — rejected
for the driver dependency above); calling `generate_and_print_label()` N times (N generator runs and
N `lp` jobs for identical output — strictly worse than both).

## Decision 2 — the count is a request parameter, not a client-side loop

**Decision**: `POST /api/labels/print` accepts `label_count`. The browser sends **one request per
item**, exactly as it does today, whatever the count.

**Rationale**: The alternative — the client posting the same request N times — multiplies the
request count by the label count, so a 12-item batch at 5 copies becomes 60 round trips and 60 `lp`
jobs where 12 would do. It also makes FR-009 unanswerable: with N independent requests per item,
"how many labels did this item actually produce" has N answers and the progress display has to
reconcile them. One request per item keeps the existing per-item success/failure reporting exactly
as it is, which is what FR-010 asks for.

It also keeps FR-007 (all of one item's copies produced consecutively) true by construction rather
than by discipline — one item's copies are one `lp` job, so nothing can interleave.

**Alternatives considered**: a client loop (rejected as above); a new bulk endpoint taking a list of
JA IDs (rejected — it would replace the working per-item progress reporting on two dialogs to solve
a problem nobody has, and Principle I bars the speculative generality).

## Decision 3 — validate on the server, and gate on the server; the input attributes are affordance only

**Decision**: `min`/`max`/`step` go on the `<input type="number">` for the spinner and the mobile
keypad, but the enforced gate is (a) the shared JS helper before the request is sent, and (b) the
route's own validation. Browser constraint validation is not relied on.

**Rationale**: Every print button in these dialogs is `type="button"` with a click handler — one of
them (`label-printing-modal.js:130`) sits next to a `<form>`, three do not. Constraint validation
fires on form submission, which never happens, so `min`/`max` alone would let `500` through to the
request. And per CLAUDE.md, a browser validation bubble is invisible to an e2e test: the assertion
that the user was told something has to land on a DOM element. The helper writes into each dialog's
existing alert region, which is both visible and assertable.

Server-side validation is not defense against an attacker — Principle I and the project's threat
model rule that out. It is there because the route is the one place all four dialogs pass through,
so it is where "1 to 99, whole numbers" is actually true rather than repeated.

**Alternatives considered**: trusting `min`/`max` (rejected: never fires); clamping out-of-range
values silently (rejected: the spec's edge case requires the user be told the maximum, not have
their 500 quietly become 99).

## Decision 4 — one shared helper, and why that survives Principle I

**Decision**: `app/static/js/label-count.js`, a plain script exposing `window.readLabelCount(inputId)`
returning `{ok: true, value}` or `{ok: false, error}`.

**Rationale**: Principle I prohibits abstraction for a single implementation. There are four, and
SC-007 makes their agreement a requirement: the same bounds and the same error text on all four
surfaces. The alternative is the same six lines pasted four times, which is precisely how the
post-bulk-Add dialog ended up posting a `label_size` nobody else posts. A plain global script rather
than an ES module because the call sites are mixed: `inventory-list.js` is loaded with
`type="module"` (`list.html:259`) while `inventory-add.js` and `label-printing-modal.js` are plain
scripts. A global is readable from all three; a module export is not, without converting files this
feature has no other reason to touch.

**Alternatives considered**: an ES module under `app/static/js/components/` (matches the
`item-actions.js` precedent but forces `inventory-add.js` to become a module or use dynamic import —
churn for no gain); duplicating the check (rejected as above).

## Decision 5 — the bulk completion summary is reworded at every count

**Decision**: `Complete: {labels} labels for {items} items, {failed} failed`, unconditionally.
Today's string is `Complete: {n} printed, {n} failed`.

**Rationale**: This resolves a genuine conflict inside the spec. FR-008 requires the bulk summary to
report both how many items were covered and how many labels that amounted to, with no exemption for
a count of 1. The Edge Cases bullet "a label count of 1 must be indistinguishable from today" would,
read literally, forbid changing that string. The bullet's stated concerns are an extra confirmation,
an extra delay, and a reworded result message — the first two are about friction, and the resolution
taken here is that friction is what the bullet protects: nothing is added to the count-1 path, no
press, no wait. A clearer summary is not friction, and at count 1 the new wording ("3 labels for 3
items") is strictly more useful for reconciling against the stack in hand, which is what SC-005
measures.

The two places where the bullet is honored literally are the ones where a user would notice a
change for no reason: the single-item success alert keeps today's exact string at count 1, and the
bulk progress line keeps today's exact string at count 1 with a suffix appended only above 1.

**Alternatives considered**: conditional summary wording (today's string at 1, the new one above 1 —
rejected: two strings to maintain and two branches to test, so that a user never sees an improvement);
leaving the summary alone (rejected: violates FR-008 outright at every count).

## Decision 6 — partial failure inside one item's copies is reported as a whole-item failure

**Decision**: If `lp` fails for an item, that item's entire label count is reported as not produced,
even if some copies physically emerged before the failure.

**Rationale**: One item's N copies are one `lp` invocation with one exit code (Decision 1). Partial
progress inside that job is not observable from the application — CUPS does not report it back
through `subprocess.run`. FR-009 constrains the direction of the error: the report MUST NOT claim
*more* labels than were produced. Reporting 0 for an item that produced 2 of 5 under-claims, which
the requirement permits; the reverse would not be. The user is standing at the printer and can see
what came out, so the summary's job is to be safe rather than precise here.

**Alternatives considered**: parsing CUPS job state to recover partial progress (rejected — a polling
loop against a job queue is exactly the scale machinery Principle I prohibits, for a hobby printer
that jams roughly never).

## Naming

The spec reserves "quantity" for the Add Item form's item count and uses **label count** for this
feature. Applied to the code: `label_count` in the request body, the route, and
`print_label_for_ja_id()`, and the existing `num_copies` parameter of `generate_and_print_label()` is
**renamed** to `label_count` to match. That rename is free — `grep` finds `num_copies` on five lines,
all inside `label_printer.py`, and no test references it.

`app/services/product_label.py` keeps its own `num_copies`. Product labels are out of scope, that
file is otherwise untouched by this feature, and renaming a parameter there would be churn in a file
nobody is reading for this change.

## Test seam

No test may reach `LpPrinter.print_images()` — it drives hardware. The existing short-circuit
(`label_printer.py:92`) catches `TESTING` and `DISABLE_LABEL_PRINTING` and logs what it would have
printed, including the count. So the observable boundaries are:

| Claim | Where it is verified | How |
|-------|---------------------|-----|
| The dialog sends the count the user typed | e2e | Intercept `/api/labels/print` and read the request body — precedent: `test_label_printing_test_mode_verification` |
| The route validates and forwards the count | unit | `patch('app.services.label_printer.print_label_for_ja_id')`, assert the call args |
| The service turns a count of N into N images | unit | `patch(...LpPrinter)`, assert `print_images` received a list of length N |
| The user was told what happened | e2e | `expect()` on the alert / summary text |

"Three labels physically emerged" is not verifiable in this repository and is not claimed by any
test. The chain above is the closest honest substitute, and it is where a regression would actually
appear.
