---
title: 'ARIA combobox semantics for the shared field autocomplete'
type: 'feature'
created: '2026-07-27'
status: 'done'
baseline_revision: '25c8c009d1a2329d2c86b0dff9f83e8870cc5039'
final_revision: 'db5011eb03c2888c7919245f9c16599cf1d76b8f'
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/project-context.md']
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `app/static/js/field-autocomplete.js` renders its dropdown as a plain `<div>` of `<a class="dropdown-item">` elements — `grep -c 'aria-\|role="listbox"\|role="option"'` returns 0. A screen-reader user gets no announcement that suggestions appeared, no way to distinguish a real suggestion from Story 3.1's `+ Create "…"` entry (conveyed only by literal text plus `fw-semibold`), and no exposure of the arrow-key selection, which `highlight()` conveys with a CSS class alone (DW-40). The same 14 dropdown divs also repeat one identical `style="max-height: 200px; overflow-y: auto; z-index: 1000;"` inline attribute.

**Approach:** Give the component the WAI-ARIA 1.2 combobox pattern from inside the JS — `role="combobox"`/`aria-autocomplete`/`aria-expanded`/`aria-controls`/`aria-activedescendant` on the input, `role="listbox"` on the dropdown, `role="option"`/`aria-selected` on each entry, a polite live region announcing the result count, and a visually-hidden qualifier plus a `data-create` attribute on the create entry. Because the auto-init list drives every instance, one change covers all seven wired fields at once. Separately fold the duplicated inline style into one `.suggestions-menu` class in `app/static/css/main.css`.

## Boundaries & Constraints

**Always:**
- All ARIA wiring is applied by `field-autocomplete.js` itself (constructor/`attach()`/`render()`/`highlight()`/`hide()`), not by per-template attributes — the component owns its own semantics and no instance can be wired inconsistently.
- The listbox's accessible name is derived at runtime from the input's existing `<label for="…">`, falling back to the `field` name; no template needs an `aria-label`.
- The create entry stays one more `.dropdown-item` carrying `data-value`, so `onKeyDown`/`highlight`/`selectValue` keep working on it unchanged (Story 3.1's load-bearing design).
- The create entry's visible text stays exactly `+ Create "<canonical>"`; any added wording is appended in a `.visually-hidden` span so the accessible name still *contains* the visible text.
- `aria-expanded` tracks the dropdown's real visibility, including the `dismiss()` path; `aria-activedescendant` is present only while an entry is active and is removed on hide/re-render.
- The new CSS class carries exactly the three declarations the inline style did (`max-height: 200px; overflow-y: auto; z-index: 1000`) so rendering is pixel-identical.
- Every existing e2e selector keeps working: the dropdown id convention, `display: block/none` visibility, the `.dropdown-item` class, and `data-value`.

**Block If:**
- Applying `role="option"` to the existing `<a href="#">` entries turns out to break click or keyboard selection in Chromium (i.e. an existing e2e test in `test_field_autocomplete.py` / `test_category_autocomplete.py` / `test_product_tags.py` fails and the cause is the role, not the test).

**Never:**
- Do not reuse the existing `.autocomplete-dropdown` / `.autocomplete-item` rules in `main.css:511-535` — they are the legacy `main.js` widget's, use `max-height: 250px`, and carry `!important` that would collide with `.dropdown-menu`.
- Do not change `MaterialSelector` (`app/static/js/material-selector.js`), `inventory-add.js`, or the inline material script in `inventory/edit.html`; the two `#material-suggestions` divs get the shared class **only**, no ARIA.
- Do not change the fetch/debounce/dismiss/multi-value logic, the `/api/inventory/field-suggestions/<field>` endpoint, any service, or any Python route.
- Do not change any field's visible appearance, text, or keyboard behavior; no new dependency, no build step, no JS test framework.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Idle field | page loaded, input never focused | input has `role="combobox"`, `aria-autocomplete="list"`, `aria-controls="<id>-suggestions"`, `aria-expanded="false"`, no `aria-activedescendant` | No error expected |
| Suggestions render | server returns 3 matches | dropdown `role="listbox"` with an `aria-label` naming the field; 3 children `role="option"` `aria-selected="false"` with unique ids; input `aria-expanded="true"`; live region reads `3 suggestions available` | No error expected |
| Arrow-key selection | ArrowDown on an open 3-entry dropdown | first option `aria-selected="true"`, others `false`; input `aria-activedescendant` = that option's id; a second ArrowDown moves both | No error expected |
| Wrap-around | ArrowUp with `activeIndex === -1` | last option becomes active and is the one referenced by `aria-activedescendant` | No error expected |
| Create entry | `category_path` typed value the server echoes as novel | its option carries `data-create="true"` and a `.visually-hidden` qualifier; ordinary options carry neither; visible text still `+ Create "<canonical>"` | No error expected |
| Nothing matches | server returns `[]` and no create candidate | dropdown hidden, `aria-expanded="false"`, live region reads `No suggestions` | No error expected |
| Dismiss | Escape, blur, or outside click | `aria-expanded="false"`, `aria-activedescendant` removed, live region cleared | No error expected |
| Selection | click or Enter on an option | value written to the input, dropdown collapsed, combobox reports collapsed | No error expected |
| Fetch failure | endpoint 500s or `fetch` rejects | dropdown hidden and combobox collapsed, exactly as today | Existing `console.warn` + `hide()` unchanged |
| Missing label element | an input with no `<label for=…>` | listbox `aria-label` falls back to the humanized `field` name | Must not throw |

</intent-contract>

## Code Map

- `app/static/js/field-autocomplete.js` -- the whole component. Touch points: `attach()` (:133) input attributes; `buildItem()` (:277) option semantics; `render()` (:322) create entry (:357-364), show (:365); `hide()` (:416); `dismiss()` (:436); `highlight()` (:475). Auto-init list at :489-529 wires **seven** targets: `thread_size`, `purchase_location`, `vendor`, `location`, `sub_location`, `category_path` (create), `tags` (create + multi-value).
- `app/static/css/main.css` -- add `.suggestions-menu` near the existing `/* Auto-complete styling */` block (:511). `main.css` is linked after the Bootstrap CDN in `base.html:12`, so the class wins over `.dropdown-menu` defaults. Bootstrap 5.3.2 already supplies `.visually-hidden`.
- `app/templates/inventory/add.html` -- suggestion divs at :108 (material), :193, :246, :259, :291, :301.
- `app/templates/inventory/edit.html` -- :117 (material), :242, :297, :310, :343, :353.
- `app/templates/product/add.html` -- :86 (`category_path`), :102 (`tags`).
- `app/templates/product/edit.html` -- :50, :66. All 16 carry the identical inline style; all four templates load `field-autocomplete.js`.
- `tests/e2e/test_field_autocomplete.py`, `tests/e2e/test_category_autocomplete.py`, `tests/e2e/test_product_tags.py` -- 12 existing e2e tests keyed on `#<field>-suggestions`, `.dropdown-item`, visibility and text. Must stay green untouched.
- `tests/unit/test_product_routes.py:331,693` -- assert the rendered forms carry `id="category_path-suggestions"` / `id="tags-suggestions"` and the script tag. Must stay green untouched.
- `tests/e2e/pages/add_item_page.py` -- `AddItemPage` navigation helper used by the inventory-form e2e tests.

## Tasks & Acceptance

**Execution:**
- [x] `app/static/css/main.css` -- add a `.suggestions-menu` rule with the three declarations, commented as the shared replacement for the per-div inline style, placed beside the existing auto-complete block but deliberately *not* reusing `.autocomplete-dropdown`.
- [x] `app/templates/inventory/add.html`, `app/templates/inventory/edit.html`, `app/templates/product/add.html`, `app/templates/product/edit.html` -- on all 16 suggestion divs, append `suggestions-menu` to the class list and delete the `style="max-height: 200px; overflow-y: auto; z-index: 1000;"` attribute. Nothing else on those lines changes.
- [x] `app/static/js/field-autocomplete.js` -- apply the combobox pattern: input attributes in `attach()`; `role="listbox"` plus a label-derived `aria-label` on the dropdown; a `.visually-hidden` `role="status" aria-live="polite"` region created next to the dropdown; `role="option"`, unique `id`, `aria-selected="false"` and `tabindex="-1"` in `buildItem()`; `data-create="true"` plus a `.visually-hidden` qualifier on the create entry; `aria-expanded` + count announcement in `render()`/`hide()`; `aria-selected` + `aria-activedescendant` in `highlight()`. Update the module docstring to state that the component owns its ARIA wiring.
- [x] `tests/unit/test_autocomplete_markup.py` -- new file. Scan `app/templates/**` and assert (a) no template retains the `max-height: 200px; overflow-y: auto; z-index: 1000` inline style, (b) every `id="*-suggestions"` div carries `suggestions-menu`, (c) `main.css` defines `.suggestions-menu` with all three declarations, and (d) `GET /products/add` and `GET /inventory/add` render the class. This is the tripwire for a future field added with the old copy-pasted markup.
- [x] `tests/e2e/test_autocomplete_aria.py` -- new file covering the I/O matrix rows in a real browser: idle combobox attributes, listbox + option roles and unique ids on an open dropdown, ArrowDown/ArrowUp moving `aria-selected` and `aria-activedescendant` together, Escape collapsing and clearing both, the live-region count text, the create entry's `data-create` + hidden qualifier versus an ordinary option, and a sweep asserting all seven wired inputs report `role="combobox"` with an `aria-controls` that resolves to their own listbox. Reuse the seeding helper style of `tests/e2e/test_field_autocomplete.py` and the unique-prefix style of `tests/e2e/test_category_autocomplete.py`.

**Acceptance Criteria:**
- Given the Add Item and Add/Edit Product forms, when they load, then each of the seven autocomplete inputs is a `combobox` whose `aria-controls` resolves to its own `role="listbox"` dropdown — the fix reaches all fields, not just the create-enabled one.
- Given any open dropdown, when a screen reader inspects it, then the active entry is identifiable without CSS: exactly one option has `aria-selected="true"` and the input's `aria-activedescendant` names that option's id.
- Given the 12 pre-existing autocomplete e2e tests and the two markup unit tests in `test_product_routes.py`, when the suites run, then they pass with no edits to those files.
- Given the four templates, when the unit tripwire runs, then no suggestion div carries the old inline style and every one carries `suggestions-menu`.
- Given a rendered page before and after this change, when the dropdown is opened, then its geometry (max height, scrolling, stacking) is unchanged — the class replaces the inline style declaration-for-declaration.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass 2
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 0, medium 1, low 9)
- defer: 0
- reject: 14: (high 0, medium 0, low 14)
- addressed_findings:
  - `[medium]` `[patch]` `test_the_active_option_is_scrolled_into_view` was racy and would flake. `fill()` focuses first, and focus fires an immediate *unfiltered* fetch; the test seeds 13 distinct vendors against a limit of 10, so the unfiltered render also produces exactly 10 rows and satisfied `to_have_count(10)`. The debounced filtered fetch then landed *during* the ten `ArrowDown` presses, calling `replaceChildren()` and resetting `activeIndex` — failing the very scroll-into-view assertion pass 1 added. Now waits for the seeded vendors to be absent, which only the filtered render can satisfy (they sort ahead of `Scrolling Vendor` alphabetically, so the unfiltered top ten always contains them); once it is up the `requestSeq` guard makes a later render impossible.
  - `[low]` `[patch]` `test_the_material_dropdown_is_left_alone` asserted `#material-suggestions` carries no `role` at all — a tripwire aimed at the fix rather than at the regression, which would go red the day the deferred material-ARIA work lands. Narrowed to the actual scope claim: this component did not attach here, evidenced by the absence of the live region it always creates and of `aria-controls` on `#material`.
  - `[low]` `[patch]` The same test's docstring said `#material-suggestions` "belongs to MaterialSelector". It does not: `MaterialSelector` builds its own `.material-suggestions` container, while this div is filled by `inventory-add.js`'s `setupMaterialAutocomplete`/`showMaterialMatches` and by the inline script in `inventory/edit.html`. The docstring decides which file a future fixer opens, so it now names all three precisely.
  - `[low]` `[patch]` `_live_region`'s docstring justified the sibling placement partly by claiming an in-listbox region "changes the child counts the pre-existing e2e tests assert" — those tests count `.dropdown-item`, which a live region would not be, so the claim is false. This is the same fabricated-rationale defect pass 1 fixed in the production comment, left standing in the test. Reduced to the structural reason, which is sufficient alone.
  - `[low]` `[patch]` `SUGGESTION_DIV`'s id charset was `[A-Za-z0-9_]+`, so a hyphenated `id="part-number-suggestions"` could not match — invisible to all four markup assertions while the `>= 16` floor stayed green. That is precisely the drift the module exists to catch. Charset widened to allow `-`.
  - `[low]` `[patch]` `_assert_renders_the_class` searched the *whole rendered page* for the legacy inline style, contradicting the rationale the module argues one test earlier for scoping the same check to suggestion divs. An unrelated scrollable overlay on any of these four pages would have failed the suite with advice about suggestion dropdowns. Scoped to the matched div's own tag.
  - `[low]` `[patch]` `_rule()`'s comment claimed "`\B`-style delimiters" when the pattern has only a trailing guard. The one-sided guard is correct — the selector's own leading `.` is already a left boundary, and a lookbehind would wrongly reject the legitimate compound form `.dropdown-menu.suggestions-menu` — so the comment now says that instead of overstating the pattern.
  - `[low]` `[patch]` `test_main_css_defines_the_class_with_all_three_declarations` justified pinning `z-index` by claiming its loss "would put the dropdown behind the next form section". Untrue of this markup: Bootstrap's `.dropdown-menu`, which every one of these divs also carries, already sets the same 1000. The declaration stays for declaration-for-declaration parity; the docstring now gives that as the reason.
  - `[low]` `[patch]` `listboxLabel()` used `textContent` verbatim, so a label wrapped across lines or wrapping an icon would put newlines and indentation into the listbox's accessible name. Every label is single-line today, so this is hardening rather than a live defect, but the name is derived from arbitrary markup at runtime. Whitespace runs are now collapsed before the required-marker strip.
  - `[low]` `[patch]` The module docstring claimed "the item-form tests seed exactly three items and may therefore count rows", contradicted by the scroll test seeding thirteen. Reworded to the property that is actually true and actually load-bearing: each test knows what it seeded.

**Notable rejections:** focus firing an unfiltered fetch so tab-through announces a count per field (already settled in pass 1 — it announces what visibly happens); whether AT re-announces an identical live-region string (engine-dependent, unfixable here); `insertAdjacentElement` returning null for a parentless dropdown (found via `getElementById`, so it is always in the document); a pre-existing element colliding with the `-status` id; `listboxLabel()` yielding "undefined suggestions" when `field` is omitted (the component is already inoperable without it — the fetch URL would be `/field-suggestions/undefined`); making the `>= 16` scan floor an exact count (it is a "the glob matched something" guard, and an exact count would fail every legitimate new field); `_rule()` seeing only the first matching rule (speculative `@media` override); adding a test that `main.css` is linked after the Bootstrap CDN; the full constructor not being idempotent (the live-region guard is defensive, not a claim of double-attach support); asserting native Tab order to prove `tabindex="-1"` (that tests the browser); the multi-value `tags` field having no ARIA-specific test beyond the wiring sweep (the fragment logic is pre-existing and covered by `test_product_tags.py`); no coverage of the documented silence on fetch failure; and the stale-stylesheet caching window (settled in pass 1).

### 2026-07-27 — Review pass 1
- intent_gap: 0
- bad_spec: 0
- patch: 20: (high 0, medium 3, low 17)
- defer: 2: (high 0, medium 1, low 1)
- reject: 8: (high 0, medium 0, low 8)
- addressed_findings:
  - `[medium]` `[patch]` The live region counted `dropdown.children.length`, which includes the `+ Create "…"` row — so on a brand-new category path, the one state the create affordance exists for, a screen-reader user was told "1 suggestion available" when nothing matched. Exactly the confusion the visible wording prevents, inverted. `announce()` now takes the create candidate as a separate argument and reads `No suggestions, plus an option to create "<canonical>"`; pinned in the create e2e test.
  - `[medium]` `[patch]` `highlight()` was rewritten to keep `aria-selected`/`aria-activedescendant` in step with the `active` class, but neither channel scrolled the active option into view. With a 200px cap and up to ten rows, arrow-keying past the fifth entry pushed the highlight below the fold — and ARIA requires `aria-activedescendant` to reference a visible option. Added `scrollIntoView({block: 'nearest'})` plus a ten-row e2e test asserting `to_be_in_viewport()`.
  - `[medium]` `[patch]` Ten of the sixteen suggestion divs live on the two *edit* templates, and nothing opened either one — AC #1 names the edit forms but every test used an add form. Added rendered-markup unit tests for `/products/edit/<id>` and `/inventory/edit/<ja_id>`, and an e2e test asserting the combobox wiring on both.
  - `[low]` `[patch]` `announce()`'s docstring justified announcing zero because "silence is indistinguishable from a request that never came back" — while all three fetch-failure paths route through `hide()`, which clears the region and produces exactly that silence. The behaviour is what the spec's matrix asks for ("exactly as today"); the docstring now says so instead of implying otherwise.
  - `[low]` `[patch]` The live region was created unconditionally with no id, so a second construction on the same input (the class is exported for programmatic use) left a stale duplicate asserting a count that no longer held. Now reused by id if present.
  - `[low]` `[patch]` The new CSS comment said the legacy `.autocomplete-dropdown` "caps at 250px" and a test pinned `max-height: 250px` as the load-bearing difference — but `main.js` overrides its own stylesheet with an inline `style.cssText` of 200px, so that value never takes effect. The real reason the rules cannot merge is the `!important` background/border/shadow set; comment and assertion both moved to that.
  - `[low]` `[patch]` The module docstring argued against "sixteen hand-written copies" of the ARIA attributes; only fourteen divs belong to this component, and the change explicitly denies the other two any ARIA. Corrected to fourteen.
  - `[low]` `[patch]` `SUGGESTION_DIV` applied `re.DOTALL` with a comment explaining it spans newlines — the pattern contains no `.`, so the flag was dead and the reason wrong. Removed, and the pattern widened to accept single-quoted ids, which it would otherwise have skipped silently.
  - `[low]` `[patch]` `test_no_template_carries_the_old_inline_style` scanned whole template files, so an unrelated scrollable overlay legitimately using those three declarations would fail with the advice "use class=suggestions-menu". Scoped to the suggestion divs the module already extracts.
  - `[low]` `[patch]` `_rule()` matched any rule whose selector merely *contains* the target, so `.suggestions-menu` would also match a future `.foo-suggestions-menu`. Bounded with a `(?![\w-])` guard.
  - `[low]` `[patch]` "Selection collapses the combobox" and "an outside click dismisses" are I/O-matrix rows with no coverage. Added assertions after the create-entry click, and a new `test_clicking_away_collapses_the_combobox`.
  - `[low]` `[patch]` The singular branch of the announcement (`1 suggestion available`) was unreachable in any test. Added a one-match case.
  - `[low]` `[patch]` `listboxLabel()`'s no-label fallback is unreachable through the app (every field has a `<label for=…>`) and was untested. Added an e2e test constructing the exported class over an unlabelled input.
  - `[low]` `[patch]` The local `_seed_items` copy justified itself by claiming an import would couple this module to "a sibling test module's lifetime", which is not how pytest imports work. The copy stays — the two seeders assert different rows, and promoting one to `conftest.py` would mean editing a file this change must leave untouched — but the comment now gives the real reason.
  - `[low]` `[patch]` Five assertions following an asynchronous action used non-retrying `get_attribute(...) is None`, in a suite run with `--reruns`. Replaced with `expect(...).not_to_have_attribute(name, ANY_VALUE)`.
  - `[low]` `[patch]` The hidden create qualifier used an em dash, in a string only screen readers consume; AT voicing of `—` varies by engine and punctuation verbosity. Changed to a comma.
  - `[low]` `[patch]` A production comment justified the live region's placement by naming a specific e2e assertion (`to_have_count()`), coupling the implementation's documentation to a test file. Rewritten to the structural reason (a listbox may only contain options).
  - `[low]` `[patch]` `test_the_material_dropdown_is_left_alone` read as approval of the material field's inaccessibility. Its docstring now states it is a scope boundary and points at the ledger entry.

**Deferred — appended to the ledger as new entries only:**
- DW-122 (medium): `#material`, a *required* field on both item forms, still has no ARIA on its dropdown. Not a copy of this fix — MaterialSelector's dropdown is a navigable tree, so it needs its own pattern.
- DW-123 (low): declaring the input a `combobox` creates a WAI-ARIA expectation that ArrowDown reopens a dismissed list, which `onKeyDown` does not meet. Not a one-liner: `dismiss()` deliberately prevents the dropdown reappearing over the Save button.

**Notable rejections:** the create test being a "mega-test" (it is one comparison — create entry versus the same path once stored — and splitting it would double the page loads); extracting `_seed_items` to `conftest.py` (would require editing a file an AC pins as untouched); `data-create` having no non-test consumer (the ledger entry asks specifically for a non-visual marker); `role="status"` plus an explicit `aria-live="polite"` being redundant (belt-and-braces for older AT); the CSS deploy/caching window (no `SEND_FILE_MAX_AGE_DEFAULT` is set, so Flask revalidates); `sub_location`'s label differing in case between the add and edit forms (deriving the name from the visible label is the correct behaviour, and the two labels genuinely differ); focus firing an unfiltered fetch making tab-through announce a count each time (it announces what visibly happens); and `.visually-hidden` coming from the Bootstrap CDN (if that fails, the whole UI is unstyled).

## Design Notes

Why the semantics live in JS rather than the templates: the component already refuses to attach unless both `#<inputId>` and `#<inputId>-suggestions` exist (`:522-526`), so the JS is the only place that knows an instance is live. Attributes written from `attach()` cannot drift between the 14 template sites, and a future field needs no ARIA markup at all.

Shape of the option and the create entry:

```js
// buildItem()
a.id = `${this.dropdownId}-option-${index}`;
a.setAttribute('role', 'option');
a.setAttribute('aria-selected', 'false');
a.setAttribute('tabindex', '-1');   // focus stays in the input, per the pattern

// render(), create entry only
a.textContent = `+ Create "${candidate}"`;   // visible text unchanged
a.classList.add('fw-semibold');
a.dataset.create = 'true';
const note = document.createElement('span');
note.className = 'visually-hidden';
note.textContent = ' — new entry, not yet in the list';
a.appendChild(note);
```

The qualifier is a hidden *suffix* rather than an `aria-label` so the accessible name still contains the visible text (WCAG 2.5.3, label-in-name) — voice-control users can still say "Create". It also keeps `to_contain_text('+ Create "…")` passing in `test_category_autocomplete.py:68`.

`tabindex="-1"` is a real fix, not decoration: today each entry is an `<a href="#">`, so Tab from the input walks *into* the suggestion list instead of moving to the next form control.

The live region is created by the component next to the dropdown (`insertAdjacentElement('afterend', …)`), not inside it — putting it inside would add a non-`.dropdown-item` child and change `to_have_count()` assertions in the existing tests.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the new `tests/unit/test_autocomplete_markup.py`.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: green, including `tests/e2e/test_autocomplete_aria.py` and the 12 pre-existing autocomplete tests. Needs a 20-minute harness timeout; run detached and poll.
- `grep -rn 'max-height: 200px; overflow-y: auto; z-index: 1000' app/templates` -- expected: no output.
- `grep -c 'aria-\|role="listbox"\|role="option"' app/static/js/field-autocomplete.js` -- expected: non-zero (was 0).

**Manual checks (if no CLI):**
- After the e2e session, `git status` on `docs/screenshots/**` — the run rewrites them; revert any churn, since this change is visually identical by construction.

## Auto Run Result

Status: done

**Summary.** DW-40, resolved for every field the shared component drives. `app/static/js/field-autocomplete.js` writes the full WAI-ARIA 1.2 combobox pattern itself — `role="combobox"`/`aria-autocomplete`/`aria-controls`/`aria-expanded` on the input, `role="listbox"` with a label-derived accessible name on the dropdown, `role="option"`/`aria-selected`/unique id/`tabindex="-1"` per entry, `aria-activedescendant` tracking the arrow-key selection, and a polite live region announcing the result count. Story 3.1's `+ Create "…"` row, previously distinguishable only by font weight, carries `data-create="true"` plus a visually-hidden qualifier appended as a *suffix* so the accessible name still contains the visible text. Because the wiring lives in the auto-init path rather than in markup, one change reaches all seven fields (`thread_size`, `purchase_location`, `vendor`, `location`, `sub_location`, `category_path`, `tags`) across four templates. The sixteen copy-pasted `style="max-height: 200px; …"` attributes are now one `.suggestions-menu` rule.

This was a second, independent review pass over the completed change (pass 1's `followup_review_recommended: true`). It found no intent gap and no spec defect, and made no production behavior change beyond one hardening fix; its substantive result was removing a latent flake from the new e2e suite and correcting a cluster of test comments that asserted things about the codebase which are not true.

**Files changed:**
- `app/static/js/field-autocomplete.js` — `attachAria()`, `listboxLabel()`, `announce()`; option semantics in `buildItem()`; create-entry marker and hidden qualifier, expanded state and count announcement in `render()`; collapse in `hide()`; `aria-selected` + `aria-activedescendant` + `scrollIntoView` in `highlight()`. Pass 2 added whitespace collapsing to the runtime-derived listbox name.
- `app/static/css/main.css` — new `.suggestions-menu` rule, kept deliberately separate from the legacy `.autocomplete-dropdown`.
- `app/templates/inventory/add.html`, `inventory/edit.html`, `product/add.html`, `product/edit.html` — all 16 suggestion divs: class in, inline style out.
- `tests/unit/test_autocomplete_markup.py` (new, 10 tests) — template/CSS tripwire plus rendered-page checks on all four forms, add and edit. Pass 2 closed a hyphenated-id blind spot in the scanner and scoped the rendered-page style check to the dropdown's own tag.
- `tests/e2e/test_autocomplete_aria.py` (new, 16 tests) — the accessibility-tree contract in a real browser. Pass 2 de-flaked the scroll-into-view test and narrowed the material scope-boundary assertion.
- `_bmad-output/implementation-artifacts/deferred-work.md` — three entries added by pass 1 (DW-122, DW-123, DW-124); pass 2 added none and touched none.

**Review findings breakdown (pass 2):** 10 patched (1 medium, 9 low), 0 deferred, 14 rejected. No intent gap and no spec defect, so no loopback; `review_loop_iteration` stays 0.

The one medium was a genuine test defect: `test_the_active_option_is_scrolled_into_view` could pass on the wrong render. Playwright's `fill()` focuses before typing, focus fires an immediate unfiltered fetch, and 13 seeded vendors against a limit of 10 meant that render also produced exactly the 10 rows the test waited for — leaving the debounced filtered fetch to land mid-arrow-keying and reset `activeIndex`. Four of the low patches were comments stating things that are false of this repo (that `#material-suggestions` belongs to `MaterialSelector`; that the pre-existing e2e tests count dropdown children; that dropping `z-index` would restack the dropdown; that the item-form tests all seed three items) — the same class of defect pass 1 corrected elsewhere, and the reason this pass was worth running.

**Verification:**
- `nox -s tests` — **2620 passed**, 405 deselected, 18 pre-existing warnings, 25s. Unchanged from pass 1.
- `nox -s e2e` — **385 passed, 1 skipped, 0 failed**, 21m34s. All 16 ARIA tests pass, and all 12 pre-existing autocomplete e2e tests (`test_field_autocomplete.py`, `test_category_autocomplete.py`, `test_product_tags.py`) pass unedited. `test_move_items_sub_location.py::test_batch_move_mixed_sub_locations`, which failed in pass 1's run and was confirmed flaky and unrelated (recorded as DW-124), passed here — so this run is fully green with no known-failure carve-out.
- `grep -rn 'max-height: 200px; overflow-y: auto; z-index: 1000' app/templates` → no output. `grep -c 'aria-\|role="listbox"\|role="option"' app/static/js/field-autocomplete.js` → 24 (was 0).
- Screenshot churn from the e2e run reverted (`docs/images/screenshots/**`); `test-debug-output/` removed. Working tree carries only the intended files.

**Residual risks:**
- `#material` — a required field on both item forms — still has no ARIA on its dropdown (DW-122). Its markup is driven by `inventory-add.js` and an inline script in `inventory/edit.html`, with `MaterialSelector` a third widget again; the scope-boundary test now asserts only that *this* component did not attach there, so it will not obstruct that work.
- Declaring the input a `combobox` advertises an ArrowDown-reopens-the-list affordance that `onKeyDown` does not implement (DW-123); adding it has to be reconciled with `dismiss()`, which exists to stop a stale fetch reopening the dropdown over the Save button.
- The listbox's accessible name is derived from the visible `<label>`, so it is only as good as the label — `sub_location` reads "Sub-Location" on the add form and "Sub-location" on the edit form.
- The multi-value `tags` field is covered by the wiring sweep but by no ARIA-specific interaction test; its announced count is computed after the same `slice(0, limit)` the single-value fields use, and its fragment logic is pre-existing and covered by `test_product_tags.py`.
- The hidden qualifier and the live region rely on Bootstrap's `.visually-hidden` from the CDN. If that fails to load the qualifier text renders visibly — though so does the rest of the UI.
- Geometry now comes from `main.css` rather than an inline attribute. No `SEND_FILE_MAX_AGE_DEFAULT` is configured, so Flask revalidates and the window is narrow, but a client holding a pre-change stylesheet would briefly get an uncapped dropdown.

