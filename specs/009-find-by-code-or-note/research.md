# Phase 0 Research: Find By Any Code Or Note

**Feature**: `specs/009-find-by-code-or-note` | **Date**: 2026-08-09

The Technical Context carried no `NEEDS CLARIFICATION` — the stack is fixed by the constitution and every input this feature reads already exists. What needed research was where each of the three changes belongs, and that turned on facts about the existing code and about Python's own string handling. Ten decisions follow, each with what was rejected.

A note on provenance: decisions R1–R6 re-derive a design the archived `archive/bmad-product-catalog` branch already built and reviewed three times, recorded in `_bmad-output/implementation-artifacts/spec-dw-70-ai-01-element-string.md` on that branch. Its conclusions are adopted where they transfer. They do **not** all transfer: that branch had an `app/utils/gs1.py` and a `strip_aim_prefix` helper that `main` does not have, because its internal product code was itself a GS1 element string and `main`'s is `WIT` + Crockford base32. R1 and R4 are the two places `main` needs a different answer.

---

## R1 — Where the trade-item recognizer lives

**Decision**: A new pure module `app/utils/gs1.py` with one public function, `decode_trade_item_number(raw: str) -> Optional[str]`, returning the 14 digits **verbatim and unjudged**.

**Rationale**: `app/utils/` is already decomposed by encoding, one module per thing-a-scan-might-be:

| Module | Owns |
|---|---|
| `internal_id.py` | this shop's own printed code |
| `ecia.py` | ISO/IEC 15434 format-06 envelopes (DigiKey, Mouser) |
| `gtin.py` | what a valid retail trade item number *is* |

A GS1 element string is a fourth thing, and specifically it is not a GTIN — it is a wrapper that *carries* one. Splitting "how do I find a number inside a payload" from "is this number a valid trade item" keeps each module answering one question, and it is what lets R2 work.

**Alternatives rejected**:

- *Put it in `gtin.py`.* That module's whole contract is check-digit validity and 14-digit normalization; its docstring says "Pure module: standard library only". Adding payload parsing would give it two unrelated jobs and give `scan_router` two unrelated reasons to call it. The seam between "extract" and "validate" is the thing R2 depends on being visible.
- *Inline the parsing in `scan_router.py`.* The classifier is deliberately delegation-only — its docstring says "Classification is **structural only**", and every existing rule is one call to a sibling parser. An AI table and digit arithmetic in there would be the first exception, and the module comment explaining why would be longer than the module it avoided.
- *Extend `ecia.py`.* A different standards body, a different grammar, and a different framing (`ecia.parse` returns a field mapping; this returns one string or nothing). Sharing a module would imply a relationship that does not exist.

---

## R2 — Rules 3 and 4 share one arm

**Decision**: `scan_router.classify()` calls the recognizer, then feeds the result into the **existing** GTIN branch:

```
trade_item = gs1.decode_trade_item_number(scan)
gtin_key = gtin.normalize_and_validate(scan if trade_item is None else trade_item)
if gtin_key is not None: -> ScanKind.GTIN
```

Exactly one `normalize_and_validate` call and exactly one `ScanClassification(kind=GTIN, ...)` construction in the module.

**Rationale**: FR-002 requires a structured scan to be indistinguishable in outcome from the bare number. Sharing the call makes that structurally true rather than something tests have to keep true. It also delivers FR-006 for free: a bad check digit and the all-zero no-read fall through to free text with no code written for either case, because they are refused by the same `gtin.py` that already refuses them. `resolve_scan`, `ScanKind`, `ScanClassification`, every route and every template are untouched — an AI-01 scan simply *is* a GTIN scan the moment it leaves the classifier.

**Alternatives rejected**: a separate branch producing its own `ScanClassification`. It would duplicate the validity decision, and the two copies would drift the first time GTIN validity changed.

---

## R3 — Rule position, and why no existing scan moves

**Decision**: The new rule goes third, between the ECIA envelope and the bare GTIN. The precedence becomes five rules, first match wins, last always matches: internal code → ECIA envelope → GS1 element string → bare GTIN → free text.

**Rationale, and the FR-008 argument**: The change cannot capture a scan that resolves today, and this is provable rather than hopeful.

- **It cannot steal a bare GTIN.** A match needs at least 16 characters (`01` + 14 digits) after decoration is removed. `gtin.ACCEPTED_LENGTHS` is `(8, 12, 13, 14)`. The two candidate sets are disjoint.
- **It cannot steal an internal code.** Rule 1 runs first, and `WIT…` cannot open with `01` anyway.
- **It cannot steal an ECIA envelope.** Rule 2 runs first, and an envelope opens `[)>`.

So the only inputs whose classification changes are the ones this feature exists to change: strings that are free text today and are element strings in fact.

---

## R4 — The symbology identifier is handled by the new rule only

**Decision**: `decode_trade_item_number` tolerates one leading AIM symbology identifier — `]` followed by one ASCII letter and one ASCII digit. Nothing else in the application learns about AIM prefixes.

**Rationale**: `main` has no AIM handling anywhere today (verified: no occurrence of `]d1`, `]C1`, `]d2` or any AIM stripping in `app/` or `tests/`). So this is a genuine addition, not the reuse the archived branch had, and the question is how wide to make it.

Narrow is right here, because the prefixes that matter *are* the announcement of an element string. `]C1` means "Code 128, FNC1 in first position" and `]d2` means "DataMatrix, FNC1 in first position" — in both cases the identifier's entire message is "what follows is GS1 data". Tolerating them belongs to the element-string recognizer in the same way that recognizing `[)>` belongs to `ecia.py`.

The wider option actively costs something. Stripping AIM prefixes at the top of `classify()` would also change how `]d2[)>…` and `]C0WIT…` classify — from free text to ECIA and internal respectively. Those are improvements in the abstract, but they are behaviour changes outside this feature's scope, and FR-008 says not to disturb what already resolves. There is also evidence the operator's scanner does not prefix: if it did, their own `WIT` labels would already fail to scan, and they do not.

**Alternatives rejected**: global stripping (above); enumerating only the GS1-signalling identifiers (`]C1`, `]d2`, `]e0`, …) — a table to maintain, when the general three-character shape cannot collide with an element string opening `01` anyway.

---

## R5 — Transmission tolerance, in this order

**Decision**: `raw.strip()`, then remove at most one AIM identifier, then remove at most one leading FNC1 (`\x1d`). In that order, because that is the order they arrive on the wire (`']C1\x1d01…'`).

**Rationale, and a Python fact that matters**: `'\x1d'.isspace()` and `'\x1e'.isspace()` are both **True** (verified on this checkout), so `str.strip()` already absorbs a leading or trailing GS or RS. The explicit FNC1 removal is therefore *not* redundant: it is needed precisely for the case where an AIM identifier preceded the GS, because after `]C1` is removed the GS is no longer at either end of the string and `strip()` has already run.

The same fact settles two edge cases without extra code: `EL + '\x1d'` is accepted (the trailing GS is stripped, so the tail is end-of-input), and `EL + '\r\n'` is accepted. `'\x04'` (EOT) is **not** whitespace, which is why `ecia.py` strips it by hand.

This puts the new rule on the padding-tolerant side of the classifier's existing asymmetry: rule 1 strips (`is_internal_id` calls `.strip()`), rule 4 strips (`gtin.normalize` calls `.strip()`), rule 2 only rstrips newlines. The new rule matching rules 1 and 4 is the consistent choice.

---

## R6 — The tail rule

**Decision**: after `01` and exactly 14 ASCII digits, what follows must be **end of input, or another element string** — meaning, after at most one separator, at least **two** ASCII digits.

**Corrected in review (PR #82) — "or an ASCII digit" was too loose, in three ways.** The sentence above originally read "end of input, a GS, or an ASCII digit", copied from the archived branch's *intent contract*. That contract's own review log records that its shipped code ended up stricter than its sentence, and this implementation reproduced the sentence rather than the code — so it reproduced the defect the archived review had already found. All three forms below resolved to GTIN `00012345678905`, a key a real product can carry:

| Payload | Why it got through |
|---|---|
| `01<gtin>1 RES 10K 0805` | one digit is not an AI — every AI is 2–4 digits |
| `01<gtin>` + GS + `RES 10K 0805` | the separator was treated as an exemption rather than a delimiter |
| `01<gtin>` + GS + GS + `10LOT42` | a doubled separator encloses an empty element string the grammar forbids |

`_MIN_AI_LENGTH = 2` is the operative constant. Exactly one separator is consumed, and only on the tail — deliberately asymmetric with the leading side, where `strip()` absorbs any number. Relaxing any of the three re-opens a defect that has now been found three times across two branches.

**Rationale**: AI `01` is predefined-length (`n2+n14`) in the GS1 General Specifications, so no separator terminates it — on a real label the next element string abuts it directly, and every AI opens with a digit. Accepting an arbitrary tail would make `'0109506000134352 RES 10K 0805'` a barcode scan. Accepting only end-of-input would reject the very common `01`+`17`+`10` concatenation. Digit-or-GS-or-nothing is the rule that admits every legal chain and no prose. It delivers FR-004 and FR-005 as one condition.

`str.isdigit()` is True for Arabic-Indic and other Unicode digits, so the digit checks must be ASCII-only — `gtin.py` already learned this and has `_ASCII_DIGITS` for it.

**FR-007** (only a payload *opening* with the trade item number is read) needs no code: the recognizer anchors at the head, so `'\x1d10LOT42\x1d0109506000134352'` stays free text. Reading a number out of the middle of an arbitrary payload is how a wrong match happens.

---

## R7 — Notes join the existing text-search clause

**Decision**: add `Product.notes.like(pattern)` to the `or_(...)` already in `CatalogService.search_products`. One line.

**Rationale**:

- **FR-011 (no duplicate rows) is structural.** The clause is a disjunct on a column of the same `Product` row, not a join — unlike the identifier clause, which uses `Product.id.in_(subquery)` for exactly that reason. A row cannot be returned twice by an `or_`.
- **Empty and absent notes are handled by SQL.** `NULL LIKE '%x%'` is NULL, which is not true, so a product with no notes is never returned on the strength of the field.
- **FR-013 (other filters still apply) is free.** The category, tag, stock and specification filters are separate `.filter()` calls conjoined with this one; nothing about matching through notes escapes them.

**On case-insensitivity (FR-012), stated honestly**: this comes from the column collation, not from the query. SQLite's `LIKE` is ASCII-case-insensitive by default and MariaDB's `utf8mb4_*_ci` collation is too — **both backends agree**, so a unit test asserting case-insensitive matching would pass whether the code used `like` or `ilike`, and would prove nothing about which. The guarantee that actually holds is *sameness*: notes use the identical construct as its five sibling clauses, so notes and description can never diverge. The test worth writing asserts that sameness (a term matching one product by description and another by notes returns both), not a case-folding claim no suite can distinguish.

**Alternatives rejected**: `ilike()` — it would make notes the one field with different semantics, which is precisely what FR-012 forbids. A separate "search notes" control — not asked for, and it makes the operator choose a field before searching, which is the problem.

---

## R8 — The code-formed address is a route that redirects

**Decision**: `@bp.route('/products/<product_code>')`. The handler upper-cases the segment, validates it with `internal_id.is_internal_id`, looks the product up with `find_product_by_identifier(code, id_type='INTERNAL')`, and **redirects** to `url_for('product.product_detail', product_id=product.id)`. A malformed or unknown code raises `ItemNotFoundError`, which `app/error_handlers.py` already renders as a 404.

**Rationale**:

- **Redirect, not render.** FR-015 requires the same content and the same available actions as the canonical page. A redirect makes that identically true instead of a property to be tested, and avoids a second copy of a handler that assembles purchases, photos, purchase attachments and the latest price. FR-017 says the record number stays canonical — a redirect *is* that statement, made in the address bar.
- **`/products/<product_code>`, not `/products/code/<code>`.** The requirement is an address formed from the printed code; this is that address. Werkzeug sorts rules so a rule with no arguments outranks one with an argument on the same path shape, so `/products/new`, `/products/capture`, `/products/reorder`, `/products/categories` and `/products/tags` keep their own handlers. That is defined behaviour rather than luck — but it is exactly the kind of thing that breaks silently and far from its cause, so **a test enumerating every existing static `/products/…` route and asserting it still reaches its own endpoint is part of this work**, not an optional extra.
- **Upper-casing the segment.** Crockford's alphabet is uppercase-only and omits I, L, O and U precisely so a person can retype a scuffed label. Someone typing a code into an address bar is that person. Folding is injective here (there are no lowercase codes to collide with), so FR-018 is not at risk. It is one `.upper()` in the route and changes nothing else.

**Alternatives rejected**:

- *Loosen `internal_id.is_internal_id` to accept lowercase.* That would change scan classification — `witabc…` is free text today and would become an internal code — which is an FR-008 violation for a convenience that belongs to one route.
- *A custom Werkzeug URL converter with a regex.* Machinery for one route, against Principle I.
- *Render the detail template directly from the new route.* Two code paths to the same page, and FR-015's "same actions" becomes a promise instead of a fact.

---

## R9 — Screenshots: regenerate, expect no change

**Decision**: run `nox -s screenshots_headless` and `nox -s screenshots_verify`; expect zero changed files and a clean working tree.

**Rationale**: the constitution requires regenerating documentation screenshots for any change under `app/templates/**`, and this feature edits one template (`app/templates/product/search.html`, for FR-014). But `tests/e2e/screenshot_config.yaml` defines no product-catalogue screenshot at all — the `search_form.png` and `search_results.png` entries are the *inventory* advanced search (`wait_for: "#search-form"`, captioned "Figure 12: Advanced search form with range queries and filters"), a different page.

**Corrected during implementation — "expect no change" was wrong.** Running `nox -s screenshots_headless` rewrote eight PNGs plus `metadata.json`. None is a product-catalogue page; the PNG diffs are under 0.5% of file size and the metadata diff is timestamps only. This is the known non-reproducibility of the generator (issue #77), which feature 008 hit and documented in the same terms. The prediction accounted for *which pages the config covers* and not for the generator's instability.

So the correct action is the one feature 008 took: run the session to satisfy the gate, then **revert the noise** rather than committing it, and confirm `nox -s screenshots_verify` passes on the committed set. Committing eight rewritten unrelated PNGs would destroy review signal, which the constitution's own rationale for prohibiting mass reformatting argues against. A screenshot diff on a *product* page would still be the real signal to investigate — there was none.

---

## R10 — Documentation that states the old behaviour

**Decision**: three documents carry claims this feature falsifies, and all three are edits, not appendices.

| File | Line | What it says now | Why it must change |
|---|---|---|---|
| `docs/user-manual.md` | 749 | "searches descriptions, specifications, part numbers and every recorded identifier at once, including internal codes" | An exhaustive list that omits notes. FR-014's screen copy and this sentence must agree. |
| `docs/user-manual.md` | 557–566 | The "A scan always gets an answer" table, five rows | A manufacturer's 2D code has no row; it currently falls under "Anything else → a search", which after this change is wrong. |
| `docs/product-functionality-gap.md` | 95–106 | The "Finding things" section, three paragraphs | All three gaps close. Gets the strikethrough-plus-*Built — feature 009* treatment features 006 and 008 established, so the reasoning stays readable rather than being deleted. |

The manual also gains a sentence for the code-formed address, next to the existing labels material.

---

## Consolidated: what is touched

**Production code** — four files changed, one added:

- `app/utils/gs1.py` *(new)* — the recognizer. Pure: standard library only.
- `app/utils/scan_router.py` — one new rule, renumbered docstring, shared GTIN arm.
- `app/catalog_service.py` — one disjunct added to `search_products`.
- `app/product/routes.py` — one new route.
- `app/templates/product/search.html` — the search box's stated coverage.

**Not touched, and their not being touched is the design's main claim**: `app/models.py`, `app/database.py`, `app/utils/gtin.py`, `CatalogService.resolve_scan`, `POST /api/scan`, `app/static/js/scan-capture.js`, and every other template. No Alembic revision — this feature stores nothing new.
