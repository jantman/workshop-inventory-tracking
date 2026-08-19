# Phase 0 Research: The Captured Listing Fills In the Manufacturer Part Number

**Feature**: `specs/019-capture-mpn-default` | **Date**: 2026-08-18

Everything this feature needs already exists. The research below is therefore not about picking
technologies — it is about locating the one place the rule belongs and pricing the three details
that are not obvious from the spec: what "whitespace-insensitive" already means in this codebase,
what actually goes wrong with an over-long value, and how a cleared field survives a re-render.

---

## 1. Where the rule lives

**Decision**: a method on `ListingCapture` in `app/models.py`:

```python
def manufacturer_part_number(self) -> Optional[str]
```

**Rationale**:

- It is a fact derived from the listing and nothing else. No storage, no session, no request. That
  makes it a domain question, and Principle II puts domain logic in `app/models.py`.
- Every place that needs it already holds a `ListingCapture`: all four render sites and the one
  write path in `app/product/routes.py` either receive or parse one. Nothing has to be plumbed.
- It is unit-testable with no app, no database, no browser and no fixture — which is the concrete
  cash value of the issue's "keeps the rule in Python where it is testable without a browser".
- One rule, both paths, satisfying FR-007 by construction rather than by discipline.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| In `app/static/js/capture-agent.js`, emitting a `manufacturer_part_number` on the payload | The issue considered and set this aside. It also costs a `LISTING_CAPTURE_VERSION` bump — `from_json` refuses a payload whose version it does not recognize, so every operator with a cached bookmarklet silently captures with no payload at all until they re-drag it. A payload field is a poor trade for a value derivable from a field already in the payload. |
| A function or method on `CatalogService` | Mixes a pure derivation into the class that owns the database session, and forces `routes.py` to import a module-level function from a service module — a shape the file does not currently use. |
| In the Jinja template | The priority walk is five names deep with two per-row conditions. Written in Jinja it is unreadable and only testable through a browser, which is the opposite of what the issue asked for. |
| In `app/product/routes.py` as a private helper | Testable, but it is domain logic in the route layer, and it would have to be called from four render sites instead of being reachable from the one `listing` variable each already has. |

---

## 2. What "case- and whitespace-insensitive" already means here

**Decision**: reuse the existing row-name normalization, extracted so both callers share it.

`app/catalog_service.py:2541` already answers this question for the barcode names:

```python
def _is_barcode_row_name(name):
    return ' '.join((name or '').split()).upper() in BARCODE_ROW_NAMES
```

`' '.join(s.split())` trims **and collapses internal runs**, so `Mfr  Part   Number` folds to
`MFR PART NUMBER`. That is stronger than the spec's descriptive parenthetical ("ignoring surrounding
whitespace") and is exactly what issue #90 asked for. FR-001's operative clause is the reuse
requirement — "MUST use the same name-folding rule the recognized barcode names already use" — so
the stronger rule governs and the spec's parenthetical is the loose description of it, not a second
specification.

**Implementation**: move the normalization into `app/models.py` as

```python
def normalized_row_name(name: Optional[str]) -> str
```

and have `_is_barcode_row_name` call it. `app/catalog_service.py` already imports from `.models`
(line 38), so the dependency direction is the one that exists. This is the whole of FR-001's "a
second folding implementation MUST NOT be introduced": one function, two callers, no new concept.

**Note on the comparison itself.** `_is_barcode_row_name` upper-cases; `_fold` (same file, line
2536) case-*folds* and does not collapse. They are different tools for different jobs —
`_is_barcode_row_name` matches against a fixed list of ASCII names, `_fold` compares two arbitrary
operator-supplied strings — and this feature uses the first. Do not unify them; that is a refactor
this feature does not need and Principle I forbids on spec.

**Alternatives considered**: a per-feature `PART_NUMBER_ROW_NAMES` matcher with its own inline
folding. Rejected by FR-001, and it is how two lists drift apart.

---

## 3. Priority order, and how ties resolve

**Decision**: a module-level tuple of already-normalized names in priority order, walked outer, with
the listing's rows walked inner.

```python
PART_NUMBER_ROW_NAMES = (
    'MANUFACTURER PART NUMBER',
    'MFR PART NUMBER',
    'PART NUMBER',
    'MODEL NUMBER',
    'ITEM MODEL NUMBER',
)
```

**Rationale**: walking the names outer gives FR-002's two rules for free and without a comparison
key — priority is by position in this tuple, never by position on the vendor's page, and among rows
sharing a name the first in captured order wins because that is the order the inner walk visits
them. The cost is five passes over a list that is about twenty-five entries long, on a request that
already spends eight to fifteen seconds retrieving images. There is nothing here to optimize
(Principle I).

**A tuple, not a frozenset**, unlike `BARCODE_ROW_NAMES` — order is the point here and is not there.
The names are stored pre-normalized so the tuple is compared against `normalized_row_name(...)`
directly; a test asserts each entry is its own normalized form, so a typo cannot make an entry
permanently unmatchable.

**Alternatives considered**: one pass over the rows keeping the best-priority match seen so far.
Same result, needs an index lookup and a "best so far" variable, and gets the tie rule wrong unless
the comparison is written as strictly-better. More code for nothing.

---

## 4. What actually goes wrong with an over-long value

**Decision**: refuse a candidate longer than 100 characters and continue down the list (FR-003).
Define `MANUFACTURER_PART_NUMBER_MAX_LENGTH = 100` in `app/models.py`.

**This was researched because the spec's first draft had the failure mode wrong**, and the
correction is worth recording. The initial reasoning was that `maxlength="100"` on the input would
put an over-long rendered value into the `tooLong` state and block submission with a browser bubble
naming no field — the silent-submission failure `CLAUDE.md` documents. That is not what happens:
HTML's `tooLong` constraint applies only once the control's dirty value flag is set, i.e. after the
*user* edits it. A value the server rendered is not too long as far as constraint validation is
concerned.

What happens instead is worse. Nothing in the stack checks the length — `_clean`
(`app/catalog_service.py:2513`) strips and nothing else, and there is no length validation anywhere
in `catalog_service.py`. So the over-long value submits, `capture_order` runs, images are retrieved,
and the write fails on `Product.manufacturer_part_number` — `String(100)` at
`app/database.py:838` — with a data-too-long error at the end of a fifteen-second operation, over a
value the operator never typed. Refusing to manufacture a value the database cannot hold is the
whole of the ceiling's justification.

**Why a named constant rather than reading the column width**: reaching into
`Product.__table__.columns['manufacturer_part_number'].type.length` from `app/models.py` would make
the domain layer import the ORM layer, inverting Principle II's dependency direction, to save one
integer. A named constant carrying a comment that points at `app/database.py:838` is the boring
option, and boring is the instruction.

**Why not truncate to fit**: a truncated part number is a wrong part number, and a wrong one
corroborates a later repeat buy against the wrong product (`_corroborates`,
`app/catalog_service.py:2574`). FR-003 says so explicitly.

**Scope note**: this adds one constant. It does not touch `app/database.py`, and it does not touch
the `maxlength="100"` attributes in `app/templates/product/capture.html` or
`app/templates/product/_form_fields.html`. Three existing statements of 100 stay as they are;
sweeping them into one constant is a refactor with no bug behind it.

---

## 5. How a cleared field survives, and why the presence test is the whole trick

**Decision**: the template tests **presence of the key**, not truthiness of the value.

```jinja
value="{{ form_data['manufacturer_part_number']
          if 'manufacturer_part_number' in form_data
          else (listing.manufacturer_part_number() or '' if listing else '') }}"
```

**Rationale**: this single expression satisfies FR-002, FR-005 and FR-006 across all four render
sites, because of what `form_data` actually is at each of them:

| Render site | `form_data` | Key present? | Result |
|---|---|---|---|
| `api_capture`, bookmarklet lands (`routes.py:673`) | a literal dict of five keys | no | derived default (FR-002) |
| `product_capture` GET (`routes.py:499`) | `request.args` | no | derived default; `listing` is usually `None` here anyway |
| `product_capture`, capture asks a question (`routes.py:451`) | `request.form` | yes | what the operator submitted, empty included (FR-006) |
| `product_capture`, validation refused (`routes.py:461`) | `request.form` | yes | same |

The confirmation form always submits the field, so on any re-render the key is present and the
operator's decision — including the decision to empty it — is what redisplays. On any first render
the key is absent and the listing fills it. No flag, no extra template variable, no route change at
any render site.

**This is deliberately not what the adjacent fields do.** `manufacturer` (`capture.html:154`) and
the unit price use `form_data.get(...) or <listing value>`, and `''` is falsy, so they re-apply
their default over a field the operator cleared. Their *write* path is already correct — `routes.py`
draws the absent-versus-empty distinction explicitly at lines 415–421, with a comment explaining it
— so the wart is confined to redisplay after a question. Spec assumption: bringing those two into
line is a separate change against a separate issue. **The diff for this feature must not touch
those two fields.**

**On the write path**, this feature copies the existing pattern exactly rather than inventing one:

```python
manufacturer_part_number = request.form.get('manufacturer_part_number')
if listing is not None and manufacturer_part_number is None:
    manufacturer_part_number = listing.manufacturer_part_number()
```

which is FR-005, and is the same three lines already written for `manufacturer` and `unit_price`
directly above.

**Alternatives considered**: computing the field's final value in the route and passing it to the
template. Equivalent, more testable in isolation — and it needs the same helper called at four
render sites, four keyword arguments added, and a new template variable, to replace an expression
that is already only a presence test. Rejected on Principle I.

---

## 6. Why this feature does *not* copy 016's added-rows rule

016 (promote a captured barcode to an identifier) promotes only rows the merge actually **added**
to the product, and reports the ones it dropped. This feature deliberately does not condition on the
merge at all.

The difference is that 016 writes to the catalog unattended, so a value that is not visible in the
specification list must not become an identifier nobody can see the source of. This feature writes
nothing — it fills a form field, in front of the operator, before they confirm. The row it came from
is on the same screen either way. Conditioning a *form default* on a merge outcome that has not
happened yet would also require running the merge to decide what to render, which is a write path
called from a render path.

**Consequence, and it is correct**: a capture onto a product that already carries a `Model Number`
row still offers that row's value as the default, even though the merge will drop the captured row.
The value shown is the value the listing published, which is what the operator is being asked about.

---

## 7. The JSON representation of `/api/capture` is out of scope

`api_capture` writes when its body is JSON (`routes.py:695`), and it calls `capture_order` **without
a `listing`** — the JSON representation has no product information rows to derive from. There is
therefore nothing to apply and no change to make there. FR-007's "single shared rule" is satisfied:
the rule is on `ListingCapture`, and any caller that acquires one gets it. Adding a derivation to a
call site that has no listing would be speculative generality.

---

## 8. Test approach

**Unit** — all of it in `tests/unit/test_capture.py`, which is where every capture test already
lives, including `ListingCapture`'s own (`TestTheListingPayload`, line 952). `test_models.py` holds
dimensions, threads and enums and is the wrong file; `test_product_routes.py` is about reaching a
product by its code. Four new classes, each sited next to its nearest relative:

| New class | Sits beside | Covers |
|---|---|---|
| `TestWhichRowNamesMeanAPartNumber` | `TestWhichRowNamesMeanABarcode` (1762) | FR-001, and the guard that every `PART_NUMBER_ROW_NAMES` entry is its own normalized form |
| `TestThePartNumberTheListingNames` | `TestTheListingPayload` (952) | FR-002 through FR-004 — priority beats page order, ties, the fold, empty values, the length ceiling. No app, no database. |
| `TestThePartNumberFillsTheForm` | `TestTheListingFillsTheForm` (1064) | FR-002 and FR-005 at the route: prefill on each render path, absent-versus-empty on the write |
| `TestAClearedPartNumberStaysCleared` | `TestThePayloadSurvivesAQuestion` (1579) | FR-006, the re-render |

Existing fixtures (`tests/conftest.py`: `test_storage` → `app` → `client`) cover all of it; the unit
suite runs with the network blocked and nothing here makes a request.

**E2E** — `tests/e2e/test_product_page_capture.py` against
`tests/e2e/fixtures/amazon_listing.html`, which today carries a `UPC` row (line 120) and **no
part-number row**. The fixture gains one, matching the real listings from the issue. Both pages
involved are server-rendered, so `expect(locator).to_have_value(...)` is the whole wait — Pattern C
in `CLAUDE.md`, render-implies-completion. No new page object is needed; the existing
`capture_from_listing` / `confirm` helpers already reach the confirmation form.

**Screenshots** — `app/templates/product/capture.html` is edited, so the constitution's screenshot
gate applies. The capture page is genuinely screenshotted:
`tests/e2e/test_screenshot_generation.py::test_screenshot_order_capture` writes
`docs/images/screenshots/user-manual/order_capture.png`, and 018 regenerated exactly that file when
it last touched this template. Note it is **not** listed in `tests/e2e/screenshot_config.yaml` —
that file drives a different set, and grepping it for "capture" is how you talk yourself out of a
gate that does apply.

**Documentation** — `docs/user-manual.md:900` shows that screenshot, and the paragraph below it
lists what the bookmarklet reads ("the price, the brand, the description, every *Product
information* row, and every image..."). The part number joins that list.

---

## Resolved unknowns

None outstanding. The spec carried no `[NEEDS CLARIFICATION]` markers, and every question this
research opened is answered above. One spec correction came out of §4 and has been applied to
`spec.md` (US3 rationale, US3 scenario 2, FR-003).
