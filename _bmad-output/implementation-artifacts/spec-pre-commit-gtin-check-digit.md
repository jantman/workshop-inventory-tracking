---
title: 'Judge a GTIN check-digit failure before the product is written (DW-23)'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: 'eeadb36'
final_revision: '2b2e126'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** On `POST /products/add`, a value typed `GTIN` whose check digit does not validate is first judged inside `CatalogService.add_identifier`, which runs *after* `create_product` has committed and is deliberately non-fatal — so the POST returns a 302 with the product created, the identifier silently dropped, and only an advisory flash. Three of the four purely-checkable identifier faults (blank type, unknown type, over-long value) were already moved in front of the write; this is the fourth. The refusal message also says "Store it as GTIN_UNVALIDATED" without naming where that is done.

**Approach:** Add the missing pre-write check to `_validate_product_create_form` by *calling* the existing pure validator `app/utils/gtin.normalize_gtin` and catching `InvalidGtinError` — never re-deriving check-digit or 14-digit-padding math — so the form refuses exactly what `add_identifier` would refuse, as a field error on the card the operator is looking at. Separately reword the service's message to name a concrete action.

## Boundaries & Constraints

**Always:**
- Reuse `app/utils/gtin.py` for every GTIN judgment. No new check-digit arithmetic, no new length set, no new `zfill(14)` anywhere.
- The new rule lives in `_validate_product_create_form` (`app/main/routes.py`), beside its three siblings — NOT in the shared `_validate_product_form`, which `product_edit` also calls and which has no message slot for identifier fields.
- Gate the rule on a non-blank `identifier_value`: `add.html` renders the Scanned Identifier card and both `invalid-feedback` blocks only when `form_data.identifier_value` is set, so an error keyed there beside a blank value renders nowhere.
- Follow the file's first-writer-wins convention — do not overwrite an `identifier_value` error already recorded (the 255-char rule).
- Fire only when `identifier_type == IdentifierType.GTIN.value` (exact, case-sensitive), matching the one branch `add_identifier` normalizes.
- Keep the literal token `GTIN_UNVALIDATED` in the service's message; existing tests pin it.

**Block If:**
- The pre-write check cannot be made without duplicating normalization rules outside `app/utils/gtin.py`.

**Never:**
- Do not add a `GTIN_UNVALIDATED` escape hatch, checkbox, or auto-retype to the form — the Type `<select>` already lists it (see Design Notes) and any richer identifier management belongs with DW-9's surface.
- Do not change `app/utils/gtin.py`, the storage schema, `add_identifier`'s control flow, or what value gets persisted.
- Do not add identifier validation to `product_edit`.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid GTIN | `identifier_type=GTIN`, `identifier_value=012345678905` | 302 to detail; product created; identifier stored as `00012345678905` | No error expected |
| Bad check digit | `identifier_type=GTIN`, `identifier_value=012345678900` | 200 re-render of `add.html`; `identifier_value` field error quoting the pure module's message and naming `GTIN_UNVALIDATED`; **no product written** | Pre-write field error |
| Non-digit / wrong-length GTIN | `identifier_type=GTIN`, `identifier_value=ABC-123` or `12345` | 200 re-render; `identifier_value` field error; no product written | Pre-write field error |
| Quarantine path still open | `identifier_type=GTIN_UNVALIDATED`, `identifier_value=012345678900` | 302; product created; value stored exactly as entered | No error expected |
| Non-GTIN type unaffected | `identifier_type=MPN`, `identifier_value=012345678900` | 302; product created; identifier attached verbatim | No error expected |
| Blank value | `identifier_type=GTIN`, `identifier_value=` (empty) | 302; product created with no identifier; no identifier error | No error expected |
| Over-long GTIN value | `identifier_type=GTIN`, 256-char value | 200 re-render with the existing "255 characters or fewer" message only | First-writer-wins |
| Edit route untouched | `POST /products/<id>/edit` with `identifier_type=GTIN`, bad value | Edit succeeds; no identifier validation applied | No error expected |
| Direct service call | `add_identifier(pid, identifier_type='GTIN', value='012345678900')` | Raises `ValidationError` (not `InvalidGtinError`) whose message names an existing action and the `GTIN_UNVALIDATED` type | `ValidationError` |

</intent-contract>

## Code Map

- `app/main/routes.py:927-984` -- `_validate_product_create_form`; the three sibling pre-write identifier checks live at :958-982. New rule goes here. `IdentifierType` already imported (:17); `gtin` is not.
- `app/main/routes.py:803` -- `_IDENTIFIER_VALUE_LIMIT = 255`, the sibling rule whose error shares the `identifier_value` key.
- `app/main/routes.py:1086-1095` -- `_identifier_type_choices()`; every `IdentifierType` except `INTERNAL`, so `GTIN_UNVALIDATED` is offered by the form.
- `app/main/routes.py:1145-1187` -- `_attach_scanned_identifier`, the post-commit non-fatal caller producing today's advisory flash.
- `app/main/routes.py:1247-1325` -- `product_add`: validate → `create_product` → follow-ups → flash.
- `app/utils/gtin.py:90-137` -- `normalize_gtin(value) -> str`, raising `InvalidGtinError` for non-str, non-digit, bad length, and bad check digit. Pure stdlib; the sole owner of the rule.
- `app/mariadb_catalog_service.py:1829-1842` -- `add_identifier`'s GTIN branch and the message to reword.
- `app/templates/product/add.html:125-155` -- the Scanned Identifier card; renders only when `identifier_value` is non-blank; `identifier_type` / `identifier_value` are the only error keys it can show.
- `tests/unit/test_product_routes.py:1478-1509` -- `TestScannedIdentifierOnCreate`, the sibling tests to match in style.
- `tests/unit/test_catalog_service.py:600-611` -- `test_gtin_bad_check_digit_rejected_offers_unvalidated`.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- import `gtin` from `app.utils` and add the GTIN check-digit rule to `_validate_product_create_form`, after the existing identifier checks: when `identifier_value` is non-blank, `identifier_type == IdentifierType.GTIN.value`, and `identifier_value` is not already in `errors`, call `gtin.normalize_gtin(identifier_value)` and on `gtin.InvalidGtinError` record `errors['identifier_value']` as the caught message plus a sentence naming the `GTIN_UNVALIDATED` type as the way to keep the value as scanned. Discard the normalized return value -- `add_identifier` still owns the write-time normalization. -- Moves the fourth purely-checkable fault in front of the commit, reusing the one owner of the rule.
- [x] `app/mariadb_catalog_service.py` -- reword the `ValidationError` raised on `gtin.InvalidGtinError` in `add_identifier` so it names an action that exists (adding the identifier with type `GTIN_UNVALIDATED`) instead of the bare "Store it as ..."; update the adjacent comment to record that the create form now refuses this before the write. -- The message is the operator's only recovery hint and must describe something reachable.
- [x] `tests/unit/test_product_routes.py` -- add tests to the `TestScannedIdentifierOnCreate` region covering every create-form row of the I/O matrix, in the house style (POST `/products/add` → assert 200 vs 302 → assert exact message bytes in `resp.data` → assert nothing/something written via `product_ids()` or `CatalogService(test_storage).search_products(...)`), plus the edit-route row. -- Pins the pre-write refusal and the four ways it must NOT fire.
- [x] `tests/unit/test_catalog_service.py` -- extend `test_gtin_bad_check_digit_rejected_offers_unvalidated` to pin the reworded message: still a `ValidationError`, still not an `InvalidGtinError`, still names `GTIN_UNVALIDATED`, and no longer says "Store it as". -- Stops the message regressing to naming a nonexistent action.

**Acceptance Criteria:**
- Given a POST to `/products/add` carrying `identifier_type=GTIN` and a value `gtin.normalize_gtin` rejects, when the request is handled, then no `Product` row exists afterwards and the response is a 200 re-render of the create form with the submitted values preserved.
- Given that same POST, when the page renders, then the message appears in the `identifier_value` `invalid-feedback` block on the Scanned Identifier card and names the `GTIN_UNVALIDATED` type.
- Given the codebase after the change, when GTIN validity or 14-digit normalization is computed anywhere, then it is a call into `app/utils/gtin.py` — `app/main/routes.py` contains no check-digit arithmetic, no `{8, 12, 13, 14}` length set, and no 14-padding.
- Given `nox -s tests` and `nox -s doctests`, when run, then both pass with no pre-existing test modified except the one message assertion named above.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 2, low 4)
- defer: 1: (high 0, medium 0, low 1)
- reject: 5
- addressed_findings:
  - `[medium]` `[patch]` `docs/user-manual.md` documented the exact behaviour this change removes — "the check digit is not tested until after the product has been created", "All three are checked before anything is written" (now four), and a troubleshooting row naming a failed check digit as a cause of the post-commit flash. Rewrote all three and added the new message to the troubleshooting table.
  - `[medium]` `[patch]` The route's message ("keep it exactly as scanned") both diverged from the service's reworded sentence and was false: `classify()` types a value `GTIN` only after its check digit validates, so a scan can never produce this error. Aligned the route to the service's wording ("keep the value exactly as entered, without check-digit validation").
  - `[low]` `[patch]` The route comment claimed the old bug cost a *scanned* identifier and ran to 29 lines for 8 lines of code. Corrected the claim (hand-typed/hand-edited only) and trimmed the restatement.
  - `[low]` `[patch]` The service comment justified keeping the raise with callers that do not exist ("imports, the API"). `add_identifier` has exactly one non-test caller; reworded to say why the raise is still the invariant.
  - `[low]` `[patch]` `test_every_way_the_util_refuses_a_gtin_is_refused_here` covered three of `normalize_gtin`'s four raise sites, skipping the deliberate non-ASCII-digit guard. Added an Arabic-Indic-digit case.
  - `[low]` `[patch]` Nothing asserted that the refused page actually offers the `GTIN_UNVALIDATED` option the message tells the operator to choose, and the class docstring miscounted its non-firing cases. Added both `<option>` assertions and fixed the docstring.

### 2026-07-27 — Follow-up review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 0, low 2)
- defer: 1: (high 0, medium 0, low 1)
- reject: 11
- addressed_findings:
  - `[low]` `[patch]` Three comments (route, service, `test_product_routes.py`) claimed the two messages are one sentence — "in the service's words, so the operator reads one sentence whichever side refuses them", "the route states it in the same words". They are not: the route says "Choose the GTIN_UNVALIDATED type to…" and the service "Add it with identifier type GTIN_UNVALIDATED to…". Only the recovery *clause* is shared. Reworded all three to claim exactly what is true (shared clause, differing verb, and why the verbs differ) and made the drift instruction concrete. The same edit corrected the route comment's reachability claim — a hand-edited *URL* is a third path, since `_scan_banner_args` passes `scan_value` through to `identifier_value` unjudged — and trimmed the block, which the previous pass reduced to 24 lines for 8 lines of code.
  - `[low]` `[patch]` `docs/user-manual.md:797` still framed the refusal post-hoc three lines above the new paragraph that says the opposite: "the message you get **back** names `GTIN_UNVALIDATED` as the way to **store it anyway**". Reworded to "check-digit validated before the product is created, and the refusal names `GTIN_UNVALIDATED` as the way to keep it anyway".

## Design Notes

**The ledger's "no surface lets them do" is partly inaccurate, and that changes the reword — not the fix.** `_identifier_type_choices()` returns every `IdentifierType` except `INTERNAL`, and `add.html:142-144` renders one `<option>` per choice, so `GTIN_UNVALIDATED` *is* selectable on the create form today. What does not exist is any surface to attach an identifier *after* the product is committed — which is exactly why the check must move in front of the write. So the message is reworded to name the action concretely rather than to stop naming `GTIN_UNVALIDATED`, and no new escape hatch is added: both messages point at the `<select>` that is already there.

**Catch `InvalidGtinError` wholesale, do not narrow to the check digit.** `normalize_gtin` refuses non-digits, wrong lengths, and bad check digits through one raise. Filtering to only the check-digit case would mean re-listing the other rules in the route — the third-copy problem every Epic 4 Never list rejects. Catching the whole exception makes the form refuse precisely the set `add_identifier` refuses, which is the property worth having.

Shape (rationale in the file's own comment style, not this literal text):

```python
if identifier_value and identifier_type == IdentifierType.GTIN.value \
        and 'identifier_value' not in errors:
    try:
        gtin.normalize_gtin(identifier_value)
    except gtin.InvalidGtinError as e:
        errors['identifier_value'] = (
            f'{e} Choose the {IdentifierType.GTIN_UNVALIDATED.value} type to '
            f'keep the value exactly as entered, without check-digit '
            f'validation.')
```

**The two messages say the same sentence on purpose.** The route cannot derive its text from the service's `ValidationError` without calling the write path it is trying to get in front of, so the wording is duplicated by hand and pinned by an assertion on each side. Keep them identical when either changes.

Canonical fixture values already used across the suite: invalid `'012345678900'`; valid twin `'012345678905'` → `'00012345678905'`.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass, including the new route tests
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (`app/utils/gtin.py` untouched, but confirms it)
- `grep -n "zfill\|% 10\|check_digit" app/main/routes.py` -- expected: no matches (no third copy of the rule)

## Auto Run Result

Status: done

**Implemented change (DW-23).** A value typed `GTIN` whose check digit — or length, or character set — `app/utils/gtin.py` refuses is now judged by the create form *before* `create_product` commits, joining the three sibling identifier faults already moved there. Previously it was first judged inside `add_identifier`, which runs after the commit and is deliberately non-fatal, so the POST returned 302 with the product created and the identifier silently dropped behind an advisory flash. The judgement is a call into the existing pure validator — no check-digit arithmetic, length set, or 14-padding was re-derived anywhere. The service's recovery message was reworded from "Store it as GTIN_UNVALIDATED" (a storage outcome naming no control) to naming the identifier type the create form's `<select>` already offers; the route offers the same recovery clause verbatim, differing only in its verb because there the type is still a `<select>` to change.

**Files changed:**
- `app/main/routes.py` — imports `app.utils.gtin`; new pre-write GTIN rule at the end of `_validate_product_create_form`, gated on a non-blank value, the exact case-sensitive `GTIN` type, and first-writer-wins on `identifier_value`.
- `app/mariadb_catalog_service.py` — `add_identifier`'s `InvalidGtinError` branch: message reworded, comment records that the form now refuses this first and why the raise remains the invariant.
- `tests/unit/test_product_routes.py` — new `TestGtinCheckDigitRefusedBeforeTheWrite` (9 tests): the refusal and its rendering, all four of `normalize_gtin`'s raise sites, and the six ways the rule must not fire (valid GTIN, `GTIN_UNVALIDATED`, `MPN`, blank value, over-long value, the edit route).
- `tests/unit/test_catalog_service.py` — the one sanctioned edit: `test_gtin_bad_check_digit_rejected_offers_unvalidated` now pins the reworded message.
- `docs/user-manual.md` — the Scanned Identifier section and Troubleshooting table described the post-commit behaviour this change removes; corrected, and the new message documented.

**Review findings across both passes:** 8 patches applied (2 medium, 6 low), 2 items deferred, 16 rejected. No intent gaps, no spec repairs, no loopbacks. The follow-up pass added no behavioural change: both of its patches were comment and prose accuracy fixes.

**Deferred:**
- `DW-175` (this pass) — a whitespace-only `identifier_value` strips to empty, so none of the four pre-write rules fire and `_attach_scanned_identifier` attaches nothing: the product is created with the identifier silently gone and no message anywhere, because `add.html` renders the card on the *unstripped* truthy value. Pre-existing and shared by all four sibling rules.
- The first pass recorded the same finding here rather than in the ledger, its invocation having forbidden ledger edits; this invocation permitted new entries, so it is now `DW-175`. No existing ledger entry was modified.

**Verification:**
- `nox -s tests` — 2851 passed, 427 deselected.
- `nox -s doctests` — 21 passed.
- `grep -n "zfill\|% 10\|check_digit" app/main/routes.py` — no matches; the no-re-derivation criterion holds.

**Residual risks:**
- The Design Notes above say "The two messages say the same sentence on purpose … Keep them identical when either changes", while the code shape they prescribe two paragraphs earlier gives the route a different opening verb. The shipped code follows the prescribed shape and the comments now describe the real invariant (a shared recovery clause, one wording per side, each pinned by its own assertion), but that Design Note sentence overstates it. Not amended here: editing the spec outside a `bad_spec` loopback is not sanctioned by this workflow.
- The route's and the service's recovery clauses are duplicated by hand (the route cannot derive text from the write path it precedes). Each side is pinned by an assertion, so a one-sided edit fails a test, but no assertion compares the two.
- The `docs/user-manual.md` prose is not covered by any test and entered the change during review.
- No e2e coverage was added: the refused state is reachable only by hand-typing, hand-editing the type, or hand-editing the pre-fill URL, never from a scan, so it is outside the scan-routing e2e suite's remit.
