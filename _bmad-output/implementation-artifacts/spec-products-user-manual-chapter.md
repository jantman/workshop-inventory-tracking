---
title: 'Products and Catalog chapter for the user manual (DW-41)'
type: 'chore'
created: '2026-07-27'
status: 'done'
baseline_revision: 'a6339ea3bfab238d20db5b50a0d47281ae1c1307'
final_revision: '06d0ba254ec960d74e772b9952f657f2bd4c57f0'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `docs/user-manual.md` has no Products/Catalog chapter, so every operator-facing catalog behavior shipped by Story 1.3 and extended by Epics 3 and 4 — category canonicalization, the `+ Create "…"` affordance, tags, scan routing, the First Receipt block — is documented only inside the REST API reference, where an operator will not look.

**Approach:** Author a new `## Products and Catalog` chapter in `docs/user-manual.md` covering the shipped product pages, category/tag behavior, scan outcomes and purchases; wire it into the Table of Contents and the Main Navigation list; and cross-link it from the REST API section that currently carries the catalog facts.

## Boundaries & Constraints

**Always:** Document only behavior verified in the shipped code (routes in `app/main/routes.py`, templates under `app/templates/product/`, `app/utils/category.py`, `app/utils/tag.py`, `app/utils/scan_router.py`, `app/mariadb_catalog_service.py`). Quote on-screen labels, button text, help text and flash messages verbatim from the templates/routes. Match the manual's existing voice, heading depth (`##` chapter, `###` section, `####` sub-section) and Markdown conventions. State the operator-visible transformation for canonicalization with a concrete example (`Electronics/Power/` → `electronics/power`). Explicitly mark `/products/search` as a stub and name its shipped limits (50-row cap, oldest-first selection, no total, no paging, contiguous substring matching only) per DW-8.

**Block If:** The chapter would need to describe behavior that cannot be confirmed from the code (do not extrapolate from planning docs). A required product screenshot is missing — there are none under `docs/images/screenshots/user-manual/`, so the chapter ships text-only rather than referencing images that do not exist.

**Never:** Do not edit `_bmad-output/implementation-artifacts/deferred-work.md` — the orchestrator records resolution. Do not change application code, templates, or tests: this is a documentation-only change. Do not document planned Epic 8 search work as if shipped. Do not add screenshots or run `nox -s screenshots` (no UI changed). Do not rewrite unrelated chapters; the only edits outside the new chapter are the TOC entry + renumbering, the Main Navigation list, and one cross-reference in the REST API section.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Category typed with mixed case and trailing slash | Operator types `Electronics/Power/` in **Category** | Chapter states the stored and redisplayed value is `electronics/power` | No error expected |
| Inline create chosen | Operator picks `+ Create "electronics/power"` | Chapter states this creates no category record — it only files the product under that path | No error expected |
| Scan resolves to a product | Scan matches an existing identifier | Chapter states the operator lands on the product detail page with the blue **Scanned: this product** banner | No error expected |
| Scan finds text hits but no record | Free-text scan with matches | Chapter states the operator lands on `/products/search?q=…` | No error expected |
| Scan finds nothing | Unrecognized payload, no hits | Chapter states the operator lands on `/products/add` pre-filled, with the scan text in **Label Description** | No error expected |
| Search cap reached | More than 50 products match | Chapter states only the 50 oldest are listed with no total and no truncation notice | Documented as a known stub limitation (DW-8) |
| First Receipt left blank | All four First Receipt fields empty | Chapter states no purchase record is created | Chapter states the product still saves if the receipt fails, with the flash the operator sees |

</intent-contract>

## Code Map

- `docs/user-manual.md` -- the only file changed: TOC (lines 3-16), Main Navigation (lines 30-36), new chapter, REST API cross-reference near line 1106.
- `app/main/routes.py` -- product routes, validation messages and flashes (`product_add` ~1187, `product_detail` ~1339, `product_search` ~1363, `product_edit` ~2275, `categories` ~2443, `category_rename` ~2451, `tags` ~2547, scan routing ~2116).
- `app/templates/product/` -- `add.html`, `edit.html`, `detail.html`, `search.html`, `categories.html`, `category_rename.html`, `tags.html`, `tag_products.html`, `purchase_add.html`: verbatim labels, help text and empty states.
- `app/templates/base.html` -- Products nav dropdown (~59-64) and the navbar scan field (~91-106).
- `app/utils/category.py`, `app/utils/tag.py` -- canonicalization rules and limits (512-char path, 64-char tag, 50 tags/product).
- `app/utils/scan_router.py`, `app/static/js/scan-capture.js` -- scan classification kinds and client toast text.
- `app/mariadb_catalog_service.py` -- search limits (`SEARCH_RESULTS_DEFAULT_LIMIT = 50`), searched columns, rename semantics.

## Tasks & Acceptance

**Execution:**
- [x] `docs/user-manual.md` -- insert a new `## Products and Catalog` chapter between `## Batch Operations` and `## Data Export` -- products are a parallel domain to inventory items, so the chapter belongs after the item-lifecycle run and before the cross-cutting export/API chapters.
- [x] `docs/user-manual.md` -- within the chapter, write `### What a Product Is`, `### Adding a Product`, `### Categories`, `### Tags`, `### Finding a Product`, `### Scanning`, `### Purchases and Attachments`, `### Editing a Product`, and `### Troubleshooting Products` -- one section per operator task, so each shipped behavior has a home.
- [x] `docs/user-manual.md` -- add `Products and Catalog` to the Table of Contents as item 8 and renumber the following entries -- the TOC is the manual's index; a chapter absent from it stays undiscoverable.
- [x] `docs/user-manual.md` -- add the **Products** menu (Add Product / Manage Categories / Browse Tags) and the navbar scan field to the `### Main Navigation` list -- these are the only entry points to the chapter's pages.
- [x] `docs/user-manual.md` -- add a cross-reference to the new chapter from the `### GET /api/inventory/field-suggestions/<field>` section -- that section currently carries catalog facts that belong in an operator chapter; the link redirects readers who land there first.

**Acceptance Criteria:**
- Given the manual's Table of Contents, when a reader scans it, then a `Products and Catalog` entry links to the new chapter and every following chapter number is sequential with no duplicates or gaps.
- Given the new chapter, when a reader looks for how to reach product pages, then it names the **Products** navbar menu and its three items (`Add Product`, `Manage Categories`, `Browse Tags`) and states that product detail and search pages are reached by scan, search, tag filter or direct URL rather than from the menu.
- Given the Categories section, when a reader wants to know what `+ Create "…"` does, then the chapter states it writes the canonical path into the field and creates no category record, and that the category tree accretes only from paths products are actually filed under.
- Given the Scanning section, when a reader follows each FR36 outcome, then the chapter describes all three landing destinations (product detail, `/products/search`, pre-filled `/products/add`) and states that a scan never dead-ends.
- Given the Finding a Product section, when a reader consults it, then `/products/search` is explicitly labelled a stub with its 50-row oldest-first cap, absent total/paging, and contiguous-substring matching called out, and no Epic 8 capability is described as available.
- Given the whole diff, when it is reviewed, then only `docs/user-manual.md` is modified and no application code, template, test or ledger file is touched.
- Given every quoted on-screen string in the chapter, when it is compared to the template or route it came from, then the strings match verbatim.

## Spec Change Log

_No bad_spec loopback occurred._

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 13: (high 1, medium 3, low 9)
- defer: 3: (high 0, medium 1, low 2)
- reject: 12: (high 0, medium 2, low 10)
- addressed_findings:
  - `[high]` `[patch]` "Where a Scan Lands" claimed an ECIA envelope carrying only quantity/date fields lands on the create form with a blank description; `_scan_prefill_args` always writes the AIM-stripped raw scan into `description` (FR40 forbids losing the scan). Rewrote outcome 3 to state what is actually pre-filled and to tell the operator to overtype the raw label text.
  - `[medium]` `[patch]` "Reaching the Product Pages" told the reader to use **Manage Categories** to see everything in a category; no category-filter page exists and the same chapter later says category rows are not clickable. Rewrote to say Browse Tags lists products but Manage Categories only reports counts.
  - `[medium]` `[patch]` "Promoting `a/b` up to `a` … allowed" stated unconditionally; `rename_category_path` refuses it whenever anything else already sits under the destination. Qualified the sentence.
  - `[medium]` `[patch]` Tag limits list included `A tag cannot contain ',' — that is the separator between tags.`, which `parse_tag_list` can never produce from the form (it splits on the comma before normalizing). Removed the bullet and stated the field simply splits there.
  - `[low]` `[patch]` "the ten most relevant existing paths appear" on an empty field; with no `q` the suggestion query orders alphabetically, as the manual's own REST "Ordering" section already says. Corrected.
  - `[low]` `[patch]` GS1 application identifier `96` documented as fixed while only the token was called configurable; `GS1_INTERNAL_AI` and `GS1_INTERNAL_TOKEN` are both configuration with those defaults. Corrected.
  - `[low]` `[patch]` Rename pre-form guards described as two; there are three — added `No products are filed under category "X".` and kept the service's single-quoted twin in the POST-refusal list where it belongs.
  - `[low]` `[patch]` Rename refusal list presented as complete but omitted the blank-destination and over-length-descendant refusals. Added both.
  - `[low]` `[patch]` **Internal ID** introduced without saying where it is visible; it is on no product page, only the search results table. Stated so.
  - `[low]` `[patch]` "ascending internal order" invited reading the **Internal ID** column as the sort key; internal IDs are randomly generated. Reworded to creation order with an explicit disclaimer.
  - `[low]` `[patch]` "with two differences" followed by three. Corrected.
  - `[low]` `[patch]` Scan message table omitted the server-refusal family. Added `Scan failed: <reason>`, `Scan failed. The scanned text has been kept for retry.` and the `Unrestored scan: <text>` suffix.
  - `[low]` `[patch]` `GTIN_UNVALIDATED` listed as a dropdown choice with no explanation, though it is the remedy the app's own check-digit error names; and the purchase form was documented without its date/price validation. Added both.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 16: (high 1, medium 4, low 11)
- defer: 4: (high 0, medium 1, low 3)
- reject: 20: (high 0, medium 0, low 20)
- addressed_findings:
  - `[high]` `[patch]` "Where a Scan Lands" outcome 3 claimed "Every other scan puts the scanned text itself into **Label Description**". `_scan_prefill_args` returns `_ecia_prefill`'s mapping and returns early whenever the envelope names a part number, so the most common distributor scan lands on the create form with the one *required* field blank — and the paragraph then told the operator to overtype text that is not there. (The previous pass "fixed" this in the wrong direction.) Rewrote outcome 3 as four explicit per-kind bullets naming what each actually pre-fills.
  - `[medium]` `[patch]` "Confirming a Duplicate" opened "If the scan you arrived on already matched an existing product, the form opens with a warning" — a landing that cannot happen: a matched scan routes to the product page, and the duplicate form is reachable only via **Create a separate product instead** in the arrival banner. Rewrote the opening and named the button.
  - `[medium]` `[patch]` "The First Receipt Block" was documented as blank-by-default, but `_PRODUCT_PREFILL_ARGS` whitelists `quantity`/`order_number`/`vendor`/`vendor_sku` and the ECIA arm emits three of them, so a scan-routed create form arrives with the block populated and silently records a Purchase. Added a bullet telling the operator to check and clear it.
  - `[medium]` `[patch]` The `GTIN_UNVALIDATED` advice read as a correctable validation error. The check digit is tested in `add_identifier`, after `create_product` has committed, and `_attach_scanned_identifier` carries an explicit comment that no identifier-management surface exists — so a failed attach is permanent. Added the "get the type right before you save" paragraph and rewrote the matching Troubleshooting row (which also blamed the failure on uniqueness alone).
  - `[medium]` `[patch]` "so every stored path is already canonical" contradicted the chapter's own **Not canonical** badge ten lines later; `_is_canonical_path` exists because the 3.1 backfill leaves non-normalizable rows in place. Qualified to paths written from these forms.
  - `[low]` `[patch]` The arrival banner's kind list included `free_text`; `resolve_scan`'s FREE_TEXT arm sets `product = None` unconditionally, so that kind can never produce the banner. Removed it and said why.
  - `[low]` `[patch]` Outcome 3 said an envelope carrying "a date" pre-fills what it carried; `_ecia_prefill` deliberately never pre-fills `9D`/`10D` (they are `YYWW`). Stated so explicitly.
  - `[low]` `[patch]` "only while the scan field still has focus" is stricter than `refocus()`, which also navigates when nothing is focused; and `handleSuccess` returns *silently* when the field no longer holds the submitted text and does not start with it. Reworded and documented the silent case.
  - `[low]` `[patch]` "Any of the failure messages may end with `Unrestored scan: <text>`" — only the four routed through `handleFailure` can; `Scan status unknown - check before rescanning.` is raised from the outer `.catch` and never touches the field. Named the four and the exception.
  - `[low]` `[patch]` Unit Price rules listed three messages as the set; `_purchase_unit_price` has a fourth, `Unit Price must be less than 100000000.` Added it.
  - `[low]` `[patch]` The Scanned Identifier refusal list omitted `Identifier must be 255 characters or fewer.` (`_validate_product_form`, and the input carries no `maxlength`). Added it.
  - `[low]` `[patch]` The attachment message list omitted `Attachment content is empty.` and `Filename is too long (max 255 characters).` Added both.
  - `[low]` `[patch]` The rename refusal list omitted the POST blank-source refusal `Select a category to rename.`, which is a *different string* from the documented GET guard `Pick a category to rename.` Added it with the distinction called out.
  - `[low]` `[patch]` The tag-failure messages were given as two reason-bearing shapes; `_apply_product_tags` has a third with no reason at all. Added it.
  - `[low]` `[patch]` "Renaming a path down into a subtree of itself (`a` → `a/b`) is **always** allowed" — deepening lengthens every descendant, so the 512-character bound can still stop it. Corrected to "is never a merge".
  - `[low]` `[patch]` "Adding a Product" documented only the success flash; added the two create-failure flashes, matching how the Editing section is written.

**Deferred findings — filed to the ledger as DW-128 through DW-131** (this
invocation instructed appending new entries only; existing entries untouched):
the stale Add-Item "Auto-complete" field list (DW-128), the Table of Contents'
omission of `## Quick Reference Card` (DW-129), the Main Navigation list's
omission of **Admin** and **JA ID Quick Lookup** (DW-130), and the pre-existing
`Barcode Scanner Support` section that competes with the new Scanning section
with no cross-reference (DW-131). All four are pre-existing and were out of
scope for this spec, which forbade edits to unrelated chapters.

_The previous pass's deferred findings, recorded below, are the same first three
issues; they were never filed, and DW-128 through DW-130 file them now._

**Deferred findings — NOT written to the ledger.** The invocation instructed
`Do NOT edit the deferred-work ledger`, so these three pre-existing issues are
recorded here for the orchestrator to file:

- `[medium]` `docs/user-manual.md` "Form Features → Auto-complete" (Add Item
  chapter) enumerates only Thread Size, Purchase Location, Vendor, Location and
  Sub-Location. `app/static/js/field-autocomplete.js` also registers
  `category_path` and `tags`, so that list now contradicts both the new chapter
  and the REST section. This is the exact staleness DW-41's evidence flagged at
  line 89, but the bullet documents the *Item* form, so correcting it belongs to
  an Add-Item-chapter pass, not this one.
- `[low]` `docs/user-manual.md` Table of Contents omits `## Quick Reference
  Card`, which has existed as an unlisted chapter since before this change.
- `[low]` `docs/user-manual.md` "Main Navigation" still omits the **Admin** link
  and the **JA ID Quick Lookup** field, both of which sit in the same navbar as
  the two entries this change added.

### 2026-07-27 — Review pass (second follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 17: (high 1, medium 7, low 9)
- defer: 3: (high 0, medium 1, low 2)
- reject: 10: (high 0, medium 0, low 10)
- addressed_findings:
  - `[high]` `[patch]` "Nothing is silently truncated." is false in the browser. `add.html`/`edit.html` carry `maxlength` equal to every documented limit (255 on description/manufacturer/mpn, 512 on `category_path`, 10 on quantity), so typing stops at the bound and a **pasted** value is cut with no warning — the opposite of the guarantee the chapter gave. The two example refusals are also unreachable by typing for the same reason. Rewrote the paragraph to lead with the client-side cut and to say where the server messages actually come from, and corrected the matching Troubleshooting row, which repeated "Nothing is truncated for you."
  - `[medium]` `[patch]` "the field's own help text says 'A Label Description is required.'" pointed at text no operator can see: it sits in a `.invalid-feedback` div that Bootstrap hides (`app/static/css/main.css:466` overrides only font/margin/color), and the one branch that reveals the div (`d-block` when `validation_errors.description` is set) replaces the string with the error message. Removed the claim; the field is identified by its `*` instead.
  - `[medium]` `[patch]` `_scan_url_value` runs every scan pre-fill through `_without_control_characters` and truncates it to the target column's width, so "goes into **Label Description** exactly as scanned" is wrong for any scan past 255 characters (a scan may be 4096). Stated the two transformations.
  - `[medium]` `[patch]` The ECIA pre-fill bullet promised "**Vendor SKU**, **Quantity** and **Order Number** when the label carried them". `_ecia_prefill` sets `vendor_sku` from `P` *only when `P` was not the value used for `mpn`*, and `quantity` only when `Q` passes `_positive_int_string` (`Q0` and a scaled `1.5K` are deliberately dropped). Rewrote the bullet per field and softened the First Receipt block's matching claim.
  - `[medium]` `[patch]` "Confirming a Duplicate" said the **Scanned Identifier** help text changes "on this path". `_scan_banner_args` emits `scan_type`/`scan_value` for `ScanKind.GTIN` only and `add.html:120` gates the whole card on `identifier_value`, so arriving from an internal or ECIA banner there is no card at all. Scoped the claim to GTIN and added the warning's identifier-specific sentence, which was also missing.
  - `[medium]` `[patch]` "Success flashes `Product updated successfully!`" omitted the branch where `update_product` returns True but `_apply_product_tags` fails: the route flashes only the tag error and redirects, so a saved edit shows no success message. Documented it with "do not re-submit", and added the third flash `An error occurred while updating the product. Please try again.`
  - `[medium]` `[patch]` The `Scan failed: <reason>` row blamed the scan ("an empty one, or one over the 4096-character limit"). `api_scan` also returns `_catalog_json_error('server_error', 'Failed to resolve scan', 500)` for a database outage or malformed `GS1_INTERNAL_*` config, and `scan-capture.js:459` renders it through the same `Scan failed: ${message}` template. Named the backend case, since the operator's response to it is the opposite one.
  - `[medium]` `[patch]` **Internal ID** was described as "what this shop's own printed labels encode" and scan rule 1 as "a label this shop printed", but no product label can be printed: `encode_internal_payload` has no caller in `app/main/routes.py`, `app/templates/**` or `app/static/js/**`, and `/api/labels/print` validates `ja_id.startswith('JA')`. Reworded to "designed to encode" and added the gap explicitly to rule 1, pointing at `## Label Printing` for what does exist.
  - `[low]` `[patch]` "links it for download" — `serve_attachment` passes `as_attachment=False` and `detail.html:137` uses `target="_blank"`, so attachments open inline. Corrected, and added the `No attachments.` empty state and the `An error occurred while uploading the attachment.` flash.
  - `[low]` `[patch]` The tag-collision message was given as one shape. `set_product_tags` has three, distinguished by where the collision is: the documented both-new case (which also truncates a long list with "and N more"), `Tag 'x' conflicts with 'y', which this product already carries — …` against a committed tag, and the retryable `Another save added 'x' to this product at the same time, …`. Split into three bullets and flagged the last as worth retrying unchanged.
  - `[low]` `[patch]` Canonicalization was scoped to "create and … update", but `rename_category_path` normalizes both of its arguments and `category_rename.html:98` says so in help text the chapter had quoted around. Added the rename to the rule and quoted the destination field's help text.
  - `[low]` `[patch]` The rename-refusal list omitted the non-validation branch `An error occurred while renaming the category. Please try again.`, whose re-render is the one that shows **Products affected: unknown** and "The category could not be read, so what would move is unknown." Added it with that page state named.
  - `[low]` `[patch]` "A field left out of the submission is treated as 'not provided' and keeps its stored value" is unreachable from the form (the browser submits all six) and false for `description`, which `product_edit` seeds into `update_fields` unconditionally. Cut to the half an operator can act on and pointed the API semantics at the REST chapter.
  - `[low]` `[patch]` Search matching was described as "case-insensitive" only; under MariaDB's `utf8mb4_unicode_ci` it is also accent-insensitive (`cafe`/`café`), which the Tags section already tells the reader about tags. Added the sentence.
  - `[low]` `[patch]` "**Cancel** abandons the form" understated it: `add.html:215` links to `main.index`, so Cancel goes to the dashboard and, on a scan-routed form, discards every pre-filled value with no confirmation. Said so.
  - `[low]` `[patch]` The scan-timeout row gave the message and "Check before rescanning" but not the threshold (`ScanCapture.config.timeoutMs` = 10000). Added "waited ten seconds".
  - `[low]` `[patch]` The matched-scan banner's body was quoted without the parenthesised identifier type and value `detail.html:23` appends for a GTIN scan. Added it.

**Deferred findings — one new entry filed as DW-132.** The other two were already
in the ledger from the previous pass and were left untouched, per this
invocation's instruction to append new entries only:

- `[low]` **DW-132 (new)** — `## Quick Reference Card` → `### Most Common
  Operations` still lists only the four inventory workflows (Add Item, Find
  Item, Move Items, List All). No product workflow and no mention of the navbar
  scan field reached the manual's at-a-glance page. Distinct from DW-129, which
  is about the TOC omitting the card's heading rather than the card's contents.
- `[medium]` **already DW-128** — the Add-Item chapter's "Form Features →
  Auto-complete" bullet lists five fields while `field-autocomplete.js`
  registers seven. Re-found independently this pass; no duplicate entry written.
- `[low]` **already DW-131** — the top-level `#### "Barcode scanner not
  working"` troubleshooting entry still carries no pointer to the new
  `#### Scan Messages` table. Re-found independently this pass; DW-131 names
  that exact heading, so no duplicate entry written.

**Rejected findings worth recording, because two were factually wrong.** Two
reviewer claims did not survive verification: the rename path was said to refuse
unstorable text with `The category to rename contains characters that cannot be
stored or matched.` — that string exists nowhere in `app/` (`grep -rn` returns
nothing; a NUL merely narrows the subtree scan into the already-documented "No
products are filed under…" refusal) — and the `free_text` arrival banner was
said to be reachable via a hand-edited URL, which is true of the URL but not of
the chapter's claim, which is about scans. The remaining eight were judged out of
an operator manual's scope: a >4096-character typed search query returning `[]`
silently; the `q` 1024-character bound and `_bounded_scan_url` halving; the
plain over-length destination refusal (unreachable behind `maxlength="512"`);
`normalize_suggestion_value` returning None so no `+ Create` appears; a note
exceeding the `TEXT` column; `Decimal` accepting PEP 515 underscores and
non-ASCII numerals in **Unit Price**; `ATTACHMENT_MAX_SIZE` being one byte under
16 MiB; and the 24 MB transport 413 ahead of the documented 16 MB refusal.

## Verification

**Commands:**
- `git diff --name-only` -- expected: `docs/user-manual.md` is the only path listed.
- `grep -n '^## ' docs/user-manual.md` -- expected: `## Products and Catalog` appears between `## Batch Operations` and `## Data Export`.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green (documentation-only change must not disturb the suite).

**Manual checks (if no CLI):**
- Every TOC anchor in the edited list resolves to a heading present in the file (`#products-and-catalog`).
- Each verbatim quoted label/flash in the chapter is found by `grep` in `app/templates/product/` or `app/main/routes.py`.

## Auto Run Result

Status: done
Blocking condition: none

**Implemented change.** A second follow-up review pass over the shipped Products
and Catalog chapter — no new implementation. Two adversarial reviewers re-read
the chapter against the code; every claim they raised was re-verified against the
source before being acted on. 17 findings were confirmed and patched in
`docs/user-manual.md`, 1 pre-existing finding was filed to the ledger as DW-132,
2 more were re-found but already sat in the ledger (DW-128, DW-131) and were left
untouched, and 10 were rejected — two of them because the reviewer's claim was
factually wrong. No intent gaps and no spec defects.

**Files changed.**
- `docs/user-manual.md` — 17 corrections inside the Products and Catalog
  chapter. The consequential ones: "Nothing is silently truncated" was inverted
  (every bounded input carries `maxlength`, so a pasted value is cut with no
  warning); a quoted piece of "help text" turned out to be permanently hidden by
  Bootstrap and was removed; the ECIA pre-fill bullet now says which fields are
  conditional and why; the duplicate-create path's **Scanned Identifier** card is
  scoped to GTIN scans, which is the only kind that produces one; the edit form's
  saved-but-no-success-message branch is documented; `Scan failed: <reason>` no
  longer blames the barcode for what may be a backend outage; and the
  **Internal ID** / scan-rule-1 text no longer implies this shop can print a
  product label, which nothing in the app can do yet.
- `_bmad-output/implementation-artifacts/deferred-work.md` — DW-132 appended.
  Existing entries were not modified, read, or re-opened.
- `_bmad-output/implementation-artifacts/spec-products-user-manual-chapter.md` —
  triage log entry for this pass and this result block. (The previous pass's
  result block had been stripped from the working tree before this run started;
  it was not restored.)

No application code, template or test was touched.

**Review findings.** 17 patches applied (1 high, 7 medium, 9 low), 3 deferred
(1 medium, 2 low — 1 newly filed, 2 already in the ledger), 10 rejected, 0 intent
gaps, 0 spec defects.

Two things are worth flagging about the pattern rather than the count. First,
this pass again found a medium-severity error in a paragraph a previous pass had
already rewritten twice (the ECIA scan pre-fill), and again found the chapter
asserting something the code contradicts in the same region (the First Receipt
block's promise about what a label carries). Second, and new: two reviewer
findings were themselves wrong — one quoted two refusal strings that exist
nowhere in `app/`. Verifying each claim against the source before patching is
what kept those out of the manual, and is the reason this pass's patch list is
shorter than the raw finding count.

**Verification.**
- `git status --porcelain` → only `docs/user-manual.md` and the two
  `_bmad-output` bookkeeping files.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` →
  2631 passed, 413 deselected in 24.87s.
- Every string newly quoted into the chapter was machine-checked with `grep -rF`
  against its source route, service, util or template. The f-string-built ones
  (`Another save added … at the same time, so these tags were not written.`,
  `Tag 'x' conflicts with 'y', …`) were checked against the interpolated source
  lines rather than the assembled string, and `Scan failed: Failed to resolve
  scan` was checked against both halves — `_catalog_json_error(...)` in
  `app/main/routes.py:2249` and the `Scan failed: ${message}` template at
  `app/static/js/scan-capture.js:459`.
- Chapter structure re-checked after editing: `## Products and Catalog` still
  sits between `## Batch Operations` and `## Data Export` with exactly nine
  `###` sections, and every anchor the chapter links to (`#scanning`,
  `#categories`, `#tags`, `#finding-a-product`, `#label-printing`, `#rest-api`,
  `#products-and-catalog`) resolves to a heading present in the file.

**Residual risks.**
- The chapter's error rate is not yet converging on the scan-routing and
  pre-fill prose specifically: three consecutive passes have each found a real
  defect in it. It is the chapter's most branch-dense surface and the one whose
  behavior is spread across `_scan_prefill_args`, `_ecia_prefill`,
  `_scan_banner_args` and `_scan_url_value` — four functions that have to be read
  together to state any one outcome correctly.
- The chapter still quotes many exact on-screen strings with nothing pinning them
  to source, so UI wording changes will stale it silently. A test asserting the
  manual's quoted strings against the templates would end this class of finding;
  it is out of scope for a documentation spec.
- Rejected findings include real-but-deep behaviors (an over-long typed query
  returning a confident "No products match", the `q` truncation bound, the
  one-byte attachment-size off-by-one). They were judged outside an operator
  manual's scope, not untrue.

