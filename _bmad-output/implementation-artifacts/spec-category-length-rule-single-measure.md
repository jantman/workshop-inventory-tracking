---
title: "Measure the category path's 512-character limit once, on the normalized value (DW-37)"
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: '27f69f90b65c66b14e7a272cc445b8d579a9dcb2'
final_revision: '21e71d02f4e3d2f72d05d08ea7c156412ef2a658'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** The category field's 512-character limit is measured twice with different rules. `_validate_product_form` (`app/main/routes.py:885-888`, via `_PRODUCT_FIELD_LIMITS`) measures the string as SUBMITTED; `normalize_category_path` (`app/utils/category.py:142-145`) measures the NORMALIZED result and raises `InvalidCategoryPathError`, which `create_product`/`update_product` swallow into their `None`/`False` failure returns. Normalization usually shortens, but `'İ'.lower()` is two characters, so `'İ' * 300` is 300 raw (accepted by the route) and 600 normalized (refused by the util) — the operator gets a generic "An error occurred… Please try again" with no field-level message. Symmetrically, a 520-character path of slashes and spaces that normalizes to 300 is refused up front with a message about a limit it does not actually exceed. `maxlength="512"` on the three category inputs is a third measurement of the raw value, and it silently truncates.

**Approach:** Make the route consult the one implementation instead of restating a bound: drop `category_path` from `_PRODUCT_FIELD_LIMITS` and have `_validate_product_form` call `category_util.normalize_category_path` in a `try/except`, keying the util's own message on `category_path` — exactly the shape the `tags` field already uses (`routes.py:896-903`). The check is purely a pre-write test; the raw value still goes to the service, which stays the sole normalizer and writer (AD-4). Remove `maxlength` from the three category inputs, since a raw-value cap is the same double-measurement moved into the browser, and there it truncates silently.

## Boundaries & Constraints

**Always:**
- `app/utils/category.py` stays the ONLY implementation of the rule. The route consults it and renders its message verbatim; no length literal, no `512`, and no re-derived normalization appears in `app/main/routes.py` for this field.
- The error stays keyed `category_path`. `edit.html:25`'s `keyed_error_fields` list, its unkeyed fallback, `add.html:87`'s feedback block and `tests/unit/test_product_routes.py:2813` all depend on that key.
- Every rejection happens BEFORE any write, re-rendering the form (HTTP 200) with a field-level message — never a generic flash.
- Blank, whitespace-only, separator-only and absent values stay valid and still clear to NULL; that is `normalize_category_path`'s own contract, not a special case in the route.
- `_validate_product_form` is shared by `product_add` and `product_edit`; both routes must behave identically on this field.
- `MAX_CATEGORY_PATH_LENGTH` stays `512`, mirroring `products.category_path` VARCHAR(512) (`app/database.py:852`).

**Block If:**
- Making the route measure the normalized value would require changing `create_product`/`update_product`'s documented never-raise contract (they return `None`/`False`). It must not: the fix is a pre-write check in the route. If it turns out to be, HALT rather than redesigning the service's return contract.

**Never:**
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md` — the orchestrator records resolution.
- Do not normalize on the route's WRITE path. `product_add`/`product_edit` keep passing the raw submitted string to the service; the route's call is a check whose return value is discarded.
- Do not touch `_SCAN_URL_ARG_LIMITS['category_path']` (`routes.py:2017`). That is an outbound cap on an editable pre-fill, where truncation is deliberate and documented.
- Do not change the other `_PRODUCT_FIELD_LIMITS` entries or their messages, do not add unstorable-text/NUL checks, and do not add a `ValidationError` path to `create_product`/`update_product`.
- Do not regenerate screenshots: the only template change is an attribute with no visual effect.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ordinary over-length | `category_path='a' * 513` | 200 re-render, `category_path` message `Category path is too long: 513 characters (max 512).` | Nothing written |
| Lowercasing LENGTHENS (the defect) | `'İ' * 300` — 300 raw, 600 normalized | 200 re-render, field message naming 600 characters | Nothing written; no generic flash |
| Normalization SHORTENS (the symmetric defect) | 520 chars of segments, spaces and repeated `/` normalizing to ≤512 | Accepted; the canonical path is stored | No error |
| Exactly at the limit | `'a' * 512` | Accepted and stored | No error |
| Blank / whitespace / `'/'` | `''`, `'   '`, `'/'` | Accepted; stored NULL | No error |
| Key absent from an edit POST | no `category_path` key | Stored value untouched | No error |
| Edit re-submitting a stored 512-char path | canonical 512-char value | Accepted; unchanged | No error |

</intent-contract>

## Code Map

- `app/main/routes.py:775-780` -- `_PRODUCT_FIELD_LIMITS`; `category_path` leaves it. `:853-904` `_validate_product_form` (raw loop at `:885-888`; the `tags` try/except at `:896-903` is the shape to mirror). `category_util` is already imported and already called by the category admin routes (`:2551`, `:2621`, `:2725`).
- `app/utils/category.py:67,96-146` -- `MAX_CATEGORY_PATH_LENGTH`, `normalize_category_path`, `InvalidCategoryPathError`; the length check at `:142-145` is on the normalized value.
- `app/mariadb_catalog_service.py:234`, `:333` -- the two writers; both normalize inside a blanket `except` that returns `None`/`False`. Unchanged — they become the backstop, no longer the operator-facing path.
- `app/templates/product/add.html:82` , `app/templates/product/edit.html:65`, `app/templates/product/category_rename.html:83` -- `maxlength="512"` on the raw input. `add.html:94-96` / `edit.html:77` carry the `tags` field's "No maxlength" comment to mirror.
- `tests/unit/test_product_routes.py:386-394` -- `test_overlong_category_still_rejected_by_the_existing_message` (asserts the old message; docstring is stale). `:2770-2781` `KEYED_FIELD_CASES` (`category_path` row at `:2775-2776`), read by `:2784` and by `:2813` `test_the_parametrized_names_are_the_templates_own_list`.
- `tests/unit/test_category.py:140-158` -- the util's limit tests; `test_length_is_measured_after_normalization` covers only the shrinking direction. No test anywhere uses `'İ'`.
- `docs/user-manual.md:748`, `:1237` -- quote the old message and assert the input "stops you typing past the limit — and silently shortens anything you paste".

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- remove the `category_path` entry from `_PRODUCT_FIELD_LIMITS` (leaving a comment saying where its rule now lives and why it cannot be a raw-length row), and add a `category_path` try/except around `category_util.normalize_category_path(form_data.get('category_path'))` in `_validate_product_form`, keyed `category_path` with `str(e)` as the message -- one measurement, taken on the value that is actually stored, in front of every write.
- [x] `app/templates/product/add.html`, `app/templates/product/edit.html`, `app/templates/product/category_rename.html` -- drop `maxlength="512"` from the category-path input in each, replacing it with a short comment on the `tags` field's pattern (the stored length is measured after normalization, so a raw cap would silently truncate a legal value; the server is the only enforcer) -- also closes the gap where `field-autocomplete.js:552` assigns `.value` programmatically, which browsers never clamp to `maxlength` anyway.
- [x] `tests/unit/test_product_routes.py` -- retitle and re-point the over-length test at the util's message, update the `KEYED_FIELD_CASES` `category_path` row to `Category path is too long: 600 characters (max 512).`, and add coverage for the I/O matrix: the `'İ' * 300` case on BOTH `/products/add` and `/products/edit/<id>` (200, field message, nothing written/changed), the shortening case (accepted, canonical value stored), the 512-char boundary, and an assertion that neither product form's category input carries a `maxlength` -- the İ case is the defect DW-37 records and nothing exercised it.
- [x] `tests/unit/test_category.py` -- add the lengthening-lowercase case to the util's own limit tests (`'İ' * 300` raises; a value whose raw length is over 512 but normalizes under it does not) -- pins the asymmetry that makes raw length the wrong thing to measure.
- [x] `docs/user-manual.md` -- update both passages: the quoted message, and the claim that the Category input stops you typing past the limit / silently shortens a paste (true of the other fields, no longer of this one).

**Acceptance Criteria:**
- Given a product form POST whose category normalizes longer than it was typed, when the value's normalized length exceeds 512, then the response is a 200 re-render carrying the message beside the Category field and no Product row is created or modified.
- Given a category path over 512 raw characters that normalizes to 512 or fewer, when the form is submitted, then the product saves and `products.category_path` holds the canonical value.
- Given `app/main/routes.py`, when it is searched for a category length literal, then the only remaining `512` for this field is the scan-URL cap at `_SCAN_URL_ARG_LIMITS`, and `_PRODUCT_FIELD_LIMITS` no longer mentions `category_path`.
- Given the rendered create and edit forms, when the category input is inspected, then it carries no `maxlength` attribute while `description`, `manufacturer` and `mpn` still carry theirs.
- Given the existing suite, when `nox -s tests` runs, then every other `characters or fewer` assertion (description, MPN, identifier, Purchase columns) is unchanged and green.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 0, low 6)
- defer: 3: (high 0, medium 1, low 2)
- reject: 8: (high 0, medium 0, low 8)
- addressed_findings:
  - `[low]` `[patch]` `docs/user-manual.md:686` still listed **Category** as a flat "512 characters" beside the three genuine raw-character limits, contradicting the passage this change rewrote sixty lines later. Now reads "counted on the *stored* path".
  - `[low]` `[patch]` `docs/user-manual.md:846` ("the only limit is 512 characters for the whole path") stated the bound without saying what it is measured on, in the very section that explains normalization. Now says it is counted after the tidying rather than on what is typed.
  - `[low]` `[patch]` `docs/user-manual.md:911` told the operator to type a rename destination "(up to 512 characters)" — a description of the `maxlength` this change removed from `category_rename.html`. Replaced with the rule that actually holds: nothing is cut off, and the server judges the stored path.
  - `[low]` `[patch]` The rename refusal list documented only the rewritten-descendant path-too-long case. The destination's own `Category path is too long: N characters (max 512).` is reachable by typing for the first time now that the input is uncapped, so it is listed.
  - `[low]` `[patch]` The third template this change touched had no coverage at all: nothing pinned that `#new_path` lost its cap, and nothing exercised what the removal makes reachable. Added three tests — the missing `maxlength`, a destination over 512 as typed that normalizes to fit (renamed), and one that lowercases longer (refused on the field, nothing written).
  - `[low]` `[patch]` `test_overlong_category_is_refused_with_the_utils_own_message` asserted the status and the message but not that nothing was written — on the plain over-length case, the one an operator actually meets. Now asserts the product count is zero.

Rejected: that the `_SCAN_URL_ARG_LIMITS['category_path']` comment now contradicts the new one (both statements are true — one is a URL-budget cap on an outbound pre-fill, one is the validation rule — and no scan-built URL emits `category_path` at all); that products whose stored path already exceeds 512 become uneditable (the old raw check refused those identically, since a canonical path re-normalizes to its own length — no behavior changed); that rendering `str(e)` exposes developer-facing text (the mirrored `tags` precedent, and the value-bearing branch needs a non-string, unreachable through `request.form.to_dict()`); that `errors['category_path'] = str(e)` should carry the loop's `field not in errors` guard (the `tags` block it mirrors assigns unconditionally, and nothing else keys this field); that `_product_count` opening its own session is wasteful (it mirrors the existing helper in the tags class); that `_input_tag` assumes `description`/`manufacturer`/`mpn` stay `<input>` elements (true today, and the failure is loud); that the audit log can now record a megabyte of category text (already true of the uncapped tags and notes controls); and a `form-text` hint under the category input (a visible UI addition, deferred as DW-161 rather than patched into a change whose templates are otherwise attribute-only).

### 2026-07-27 — Review pass 2
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 0, low 4)
- defer: 2: (high 0, medium 0, low 2)
- reject: 12: (high 0, medium 0, low 12)
- addressed_findings:
  - `[low]` `[patch]` The new `docs/user-manual.md` rename bullet attributed `Category path is too long: N characters (max 512).` to the destination alone. `rename_category_path` raises the identical string with `field='old_path'` when the SOURCE is unstorable (`app/mariadb_catalog_service.py:738-741`), so an operator could be told to shorten a field they never typed in. The bullet now names both, says which reachable states produce the source form, and points at the red field as the discriminator.
  - `[low]` `[patch]` `test_category_at_the_limit_is_accepted` used `'a' * 512`, whose raw and normalized lengths are the same number — so it passes identically under the rule this change removed and proves nothing about WHICH length is measured. Added `test_the_512_cut_is_made_on_the_stored_length`: 256 and 257 `'İ'` land the stored length on 512 and 514 while the typed length stays near 256, far inside a raw-character rule. Only a rule reading the stored value separates them.
  - `[low]` `[patch]` The change added a third HTML-parsing helper to a file that already had one. `_input_tag` duplicated the module-level `_form_controls`, and `test_the_destination_input_is_not_capped` hand-rolled a byte-level `index`/`rindex` scan for the same question — one that silently assumed `id="new_path"` follows the `<input` it belongs to and that no `>` appears in an earlier attribute value. Both now call `_form_controls`; `_input_tag` is gone.
  - `[low]` `[patch]` `_PRODUCT_FIELD_LIMITS`'s summary line still read "Length limits mirroring the Product column definitions (app/database.py)" — a description of what the dict deliberately is no longer, with the five-line correction below it rather than in place of it. A maintainer adding the next bounded column reads the summary. It now says the dict holds the columns whose limit is on the value as submitted, and not every bounded column.

Rejected: that `_SCAN_URL_ARG_LIMITS['category_path']` is a surviving raw-length rule for the same column (raised again by both reviewers; the spec's Never list forbids touching it, it is an outbound URL-budget cap on an editable pre-fill where truncation is documented and deliberate, and the previous pass rejected it on the same grounds); that a non-string `category_path` would render the util's `{value!r}` type-fault message (rejected last pass — unreachable through `request.form.to_dict()`); that `_product_count` reaches past the service API and leaks its `CatalogService` (rejected last pass — it mirrors the existing helper in the tags class); a NUL/unpaired-surrogate check on the category path (the spec's Never list forbids adding one, and it is already on the ledger as DW-160); that the emptying suggestion dropdown leaves the operator without a reason (already on the ledger as DW-161); that the field message's grammar should match the other three fields' "must be N characters or fewer" shape (the spec requires the util's message verbatim, and a route-owned sentence is what put two rules in the tree); that no test pins the route's normalization against the service's (both are the same pure function on the same string, and the tests compare the stored value against a literal); that `assert b'An error occurred' not in resp.data` fails to discriminate between the route's two flashes (the positive message assertion and the zero product count carry the test); that the same "No maxlength" Jinja comment in three templates has drifted (the wording is reflowed to each template's indentation, not divergent); that a pasted category can now exceed `MAX_REQUEST_BODY_BYTES` and yield a 413 instead of a field message (1 MiB, already true of the uncapped tags and notes controls, and named in Design Notes).

## Design Notes

The route consults the util rather than the service for the same reason `tags` does: `create_product` returns `Optional[int]` and never raises, so the only way to get a field-level message in front of the write is a pure check on the form. Mirror it exactly:

```python
try:
    category_util.normalize_category_path(form_data.get('category_path'))
except category_util.InvalidCategoryPathError as e:
    errors['category_path'] = str(e)
```

The return value is discarded — the service still normalizes and writes, so "every stored path is canonical" keeps exactly one owner. Calling the pure util from a route is not the re-derivation AD-4 forbids; the category admin routes already do it in three places.

The util's message names the MEASURED length (`600 characters`), which will not match what the operator typed in the İ case. That is the point: it is the only honest way to say why a 300-character entry was refused, and a message hard-coded in the route is what put two rules in the tree to begin with.

Removing `maxlength` follows this project's stated stance on operator input (`_prefill_form_data`: nothing is silently shortened behind the operator's back). Bodies stay bounded server-side by `MAX_REQUEST_BODY_BYTES` (1 MiB, `config.py:143`).

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the new İ and shortening cases.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: green; `app/utils/category.py`'s examples are unchanged.
- `grep -n "category_path" app/main/routes.py | grep 512` -- expected: only the `_SCAN_URL_ARG_LIMITS` line.
- `grep -n "maxlength" app/templates/product/*.html` -- expected: no hit on any category-path input; description/manufacturer/mpn/receipt fields unchanged.

**Manual checks (if no CLI):**
- `nox -s e2e` is not run (~20 minutes; no JS and no server behavior an e2e test asserts has changed). Confirm by inspection that the template diffs are the attribute removal plus a comment.

## Auto Run Result

Status: `done` (follow-up review pass on an already-implemented change; no production behavior changed in this pass)

**Implemented change (unchanged from the first run):** the category path's 512-character limit is now measured once, on the normalized value, by `app/utils/category.py`. `_validate_product_form` calls `normalize_category_path` purely and renders the util's own message keyed `category_path`, so the `'İ' * 300` case (300 typed, 600 stored) is refused with a field-level message before any write instead of failing inside the never-raising service as a generic flash — and the symmetric case (over 512 as typed, under it once normalized) is now accepted. `maxlength="512"` is gone from all three category inputs, since a raw cap is the same second rule moved into the browser, where it truncates silently.

**Files changed in this review pass:**
- `app/main/routes.py` — reworded the `_PRODUCT_FIELD_LIMITS` summary line, which still claimed to mirror the Product columns while deliberately omitting one.
- `docs/user-manual.md` — the rename refusal bullet now names both fields the too-long message can be keyed to, not just the destination.
- `tests/unit/test_product_routes.py` — added `test_the_512_cut_is_made_on_the_stored_length` (256/257 `'İ'`, pinning the accept/reject cut on the stored length while the typed length stays far inside a raw rule); dropped the redundant `_input_tag` helper and pointed both `maxlength` assertions at the module-level `_form_controls`.

**Review findings breakdown:** 4 patched (all low), 2 deferred (both low, DW-163 and DW-164), 12 rejected. No intent gaps, no spec defects, no loopback. See `## Review Triage Log` → *2026-07-27 — Review pass 2* for the rejection rationale, including the two findings both reviewers re-raised that the previous pass and the spec's Never list had already settled.

**Verification:**
- `nox -s tests` — green, 2764 passed / 427 deselected.
- `nox -s doctests` — green, 21 passed.
- `grep -n "category_path" app/main/routes.py | grep 512` — only `_SCAN_URL_ARG_LIMITS`.
- `grep -n "maxlength" app/templates/product/*.html` — no hit on any category-path input; `description`/`manufacturer`/`mpn` and the Purchase fields unchanged.
- `nox -s e2e` not run, per the Verification section: the template diffs remain attribute-removal-plus-comment and this pass touched no template.

**Residual risks:** DW-163 records that the `maxlength="255"` caps this change deliberately keeps count UTF-16 code units rather than code points, so the argument that removed the category cap does not fully generalize yet; DW-164 records a pre-existing manual sentence, carried through the rewritten paragraph, that explains the 255-character messages as arriving from a scan pre-fill that cannot in fact produce them. Both are documentation/UI-level and neither affects the rule this story unified.

