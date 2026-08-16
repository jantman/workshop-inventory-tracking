# Quickstart: Clean Captured Description

How to run this feature's checks, what each one proves, and the manual pass that has to happen against the real listings because nothing automated can reach them.

## Prerequisites

- The repository virtualenv at `venv/`. Invoke its binaries by path — `venv/bin/nox` — rather than activating it.
- `python3.13` on `PATH` for nox's environment creation:
  ```bash
  PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
  ```
- Docker, for the MariaDB testcontainer the e2e session uses.
- For the manual pass: Chrome with the capture bookmarklet installed, an Amazon session, and the application running on the LAN over TLS.

## Automated checks

### Unit suite — a regression gate only

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

No Python changes ship with this feature, so this proves only that none crept in. Sub-second; run it freely. Never invoke `pytest` directly (Principle IV).

### E2E suite — where the feature is actually proved

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e
```

**Give this at least a 15-minute timeout, and prefer running it detached** — it outlasts a 10-minute shell cap on a cold start. It installs Playwright browsers and pulls the MariaDB image the first time.

Afterwards, `git status` must be clean. If `docs/images/screenshots/` shows changes, screenshot tests leaked into the run; revert them (`git checkout -- docs/images/screenshots/`) and check the `-m "e2e and not screenshot"` selector.

To iterate on just this feature's tests while developing, the whole capture file is:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- tests/e2e/test_product_page_capture.py
```

## What the automated tests prove

Everything runs against `tests/e2e/fixtures/amazon_listing_aplus.html`, enriched to carry the whole test table in `contracts/text-extraction.md`. The technique is the one `test_the_rich_description_is_kept_and_its_furniture_is_not` already uses: drive one capture, then read and parse the payload the confirmation form is holding.

```python
payload = json.loads(landed.locator("input[name='listing']").input_value())
assert payload["description_text"] == EXPECTED
```

One capture, sixteen assertions. Do not write one capture per case — each is a full browser flow, and the suite's 8m 13s is a budget worth protecting.

| Requirement | Where it is proved |
|---|---|
| FR-001, FR-002 — no stylesheet or script text | Test table rows 1–3, 13 |
| FR-003 — the live page is not mutated | Property of `contentClone`; asserted by capturing twice from the same tab and getting identical payloads |
| FR-004 — an all-markup block reads as no description | Row 11, its own fixture |
| FR-005 to FR-008 — line structure and whitespace | Rows 4–10 |
| FR-009 — names single-line, values not | Rows 14, 15 |
| FR-010 — nothing truncated | Row 12 against the plain fixture, character for character |
| **FR-011 — displayed with its breaks** | **Already covered.** `tests/e2e/test_product_specifications.py::test_a_migrated_paragraph_is_shown_whole` asserts a multi-line value through `inner_text()`, which respects the `white-space: pre-wrap` on `product/detail.html:106`. |
| **FR-012 — editable without losing breaks** | **Already covered.** `test_editing_a_product_does_not_reflow_a_migrated_paragraph` saves an unrelated field and asserts the paragraph survives, which is what the textarea at `product/_form_fields.html:59` is for. |
| FR-013, FR-014 — nothing else changes | Row 16, plus the existing image assertions in the rich-description test |
| FR-015 — no capture fails | Every test in the file; a throw in the agent means no form is submitted and no page lands |

FR-011 and FR-012 needing no new code is the plan's finding, not an assumption — but add one assertion tying a *captured* description to the rendered breaks, so the two halves are joined by a test rather than by this paragraph.

### Waiting rules for the new tests

Read `CLAUDE.md`'s "Writing e2e tests" before adding any. The two that bite here:

- **`input_value()` is a snapshot.** It does not wait. Establish the landed page with an `expect(...)` first — `expect(landed.locator("#summary-description")).to_contain_text("kept in full")` is the natural one, and it is already in the existing test.
- **A negative assertion against a JS-rendered region passes trivially before it loads.** `assert "function" not in value` is fine against a parsed payload string, but `expect(specifications).not_to_contain_text("function")` against `#product-specifications` needs the region established first.

No `wait_for_timeout`, no `time.sleep`, no `networkidle`. The constitution binds every call site, not only new ones.

## Verifying against the real listings

This cannot be automated. The application cannot re-fetch an Amazon listing from the LAN — a machine on the LAN meets a bot wall, which is why capture reads the page in the operator's own browser in the first place.

### The step that is easy to get wrong

`CatalogService.merge_specifications` is **already-present-wins**. Re-capturing `B0DMNXC4CD` onto its existing product will keep the contaminated `Description` and you will conclude the fix does not work.

That rule is correct and this feature does not change it. So, for each of the three A+ listings, **first** open the product, edit it, remove the `Description` specification row, and save. **Then** re-capture.

### The pass

| Listing | Expect | Criterion |
|---|---|---|
| `B0DMNXC4CD` | `Description` has no `{`…`;` stylesheet run and no `function`/`var` source; reads as paragraphs; visibly shorter than before | SC-001, SC-002 |
| `B09GM8FB3X` | the same, **and** the `Customer Reviews` row is a rating and a count | SC-001, SC-002, SC-005 |
| `B0FX4PDW6M` | the same | SC-001, SC-002 |
| `B0CKXJLP4B` | `Description` still captured whole, unchanged | SC-003 |
| `B01N4OSKWE` | the same | SC-003 |
| `B099F4X4Q9` | the same | SC-003 |

For all six, before confirming, check the confirmation page's "what the listing yielded" summary: the image count, the product-information row count, the vendor, item identifier, title, brand and price must all match what the same listing produced before (SC-006). The three A+ listings' character counts should drop sharply — #80 §1b recorded 21,415 and 28,767 — while the plain three should not move at all.

**The failure this pass is looking for is not "still contaminated".** It is "shorter because prose went missing". Read one of the A+ descriptions against the listing on screen and confirm the copy is all there.

### Optional: looking at the real markup

The issue offers this and the plan treats it as fixture fidelity, not a prerequisite. With the owner present, drive their Chrome to the three A+ listings and look at how a real A+ block is actually built — where the stylesheets sit relative to the copy, whether the prose is in paragraphs or table cells, how deep the nesting runs.

Anything learned goes back into `tests/e2e/fixtures/amazon_listing_aplus.html` as markup shaped like the real thing, with a note in the fixture's header comment saying why it is there. That file's existing comment — the table of six images and which two are content — is the model.

## Screenshots

The Screenshot Reminder workflow fires on any PR touching `app/static/js/**`, which this one does. It is informational (issue #77) and leaves the judgment to the author.

The judgment: `capture-agent.js` runs inside the *vendor's* page and appears in no documentation screenshot, so no regeneration is warranted — **provided no template changed**. The plan says none should, because `detail.html` and `_form_fields.html` already satisfy FR-011 and FR-012. If that turns out to be wrong and a template does change:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
git add docs/images/screenshots/
```

## Done when

- [ ] `nox -s tests` green.
- [ ] `nox -s e2e` green, and `git status` clean afterwards.
- [ ] Every row of the test table in `contracts/text-extraction.md` has an assertion.
- [ ] The six listings re-captured by hand, against the table above.
- [ ] No Alembic revision, no new dependency, no Python change in the diff.
