# Phase 0 Research: Product Catalog & Purchase Tracking

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-08-02

The spec carried no unresolved `[NEEDS CLARIFICATION]` markers into planning, so this document
does not resolve spec ambiguity. It resolves the **implementation unknowns** the plan depends
on, and records why each choice was made so a later reader does not re-litigate it.

## Sources

Two kinds of evidence are used, and they are labelled throughout:

- **Codebase** — read directly from this repository at `main`.
- **Prior art** — the unmerged BMAD branches, furthest being
  `backup/story/5-4-derived-on-order-and-recently-received` (96 commits ahead of `main`). Per
  the planning decision this feature is a **fresh implementation from `main`** and no code is
  carried over. Those branches are cited only where they encode a decision made against real
  hardware or a real distributor label, which is expensive to re-derive and cheap to read.

---

## 1. Label composition — how FR-011 gets description and provenance onto a label

**Decision**: Compose the label image in a new `app/services/product_label.py` using Pillow:
render the Code128 symbol via `BarcodeLabelGenerator`, then paste it into a canvas alongside
wrapped description text and a provenance line, and pass the resulting PNG `BytesIO` to the
existing `LpPrinter.print_images()` with the unchanged `lp_options` from `LABEL_TYPES`.

**Rationale**: FR-011 requires the description, the purchase provenance, **and** a scannable
code on one label. The existing path cannot do this. From the codebase
(`app/services/label_printer.py`), `print_label_for_ja_id()` calls `BarcodeLabelGenerator(value=…,
show_text=True)`, and from the installed package the only text that generator draws is
`self.value` — the barcode's own content. There is no parameter for a caption, a second line, or
arbitrary text.

The spec's constraint is: *"Label printing MUST reuse the application's existing label-printing
capability. No new printer control language, driver, or printing path… native printer command
languages such as SBPL are explicitly out of scope; the existing raster-image printing path is
used."* The printing path is `LpPrinter.print_images()`, which (read from the installed package)
accepts `List[BytesIO]`, writes each to a temporary PNG, and shells out to `lp` with the
configured options. Handing it a differently-composed PNG uses that path exactly as-is. What
changes is image composition, which is not a printer control language and not a driver.

**Alternatives considered**:

- *Print only the internal code, as JA-ID labels do today.* Rejected: fails FR-011 and defeats
  the feature's purpose — an operator picking up a bin needs to read what it is without a scanner
  in hand.
- *Extend `pt-p710bt-label-maker` upstream to accept caption text.* Rejected under Principle I:
  it is a separate repository on a pinned git branch, and the change would be a dependency fork
  to avoid ~80 lines of local Pillow code.
- *Add a DataMatrix encoder for a denser 2D symbol.* Rejected — see §2.

**Test approach**: `generate_and_print_label()` already short-circuits on
`current_app.config['TESTING']` or `DISABLE_LABEL_PRINTING` and logs its arguments. The new
composer must keep that seam: **image composition is unit-testable and asserted on directly
(sizes, that text is present, that the code is present); the `lp` call is never made in tests.**

---

## 2. Internal product code — encoding and ownership (FR-015)

**Decision**: The internal code is the literal token `WIT` followed by a 10-character
Crockford-base32 random identifier (alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ` — digits plus
A–Z less I, L, O, U). It is stored as a `product_identifiers` row of type `INTERNAL` and printed
as a **Code128** symbol. A scan is one of ours if and only if it matches
`^WIT[0-9A-HJKMNP-TV-Z]{10}$` after whitespace stripping.

**Rationale**: FR-015 requires distinguishing codes this system printed from foreign codes with
coincidentally similar values. A fixed literal prefix does that: no manufacturer barcode, no
distributor envelope, and no GTIN can begin with `WIT` (GTINs are all-digit; ECIA envelopes begin
`[)>`). Crockford base32 excludes the four letters that get misread when a human retypes a
degraded label, which matters because FR-012 requires the code in human-readable form precisely
so a worn label stays usable. Code128 encodes the full ASCII set and is what the installed
`BarcodeLabelGenerator` already produces by default (`barcode_class_name='Code128'`), so this
needs no new dependency.

**Departure from prior art, deliberate**: the prior branches encoded the internal identifier as a
**GS1 element string** — `FNC1` + AI `96` + token `WIT` + id — in `app/utils/gs1.py` (785 lines).
That module's own docstring records the cost: *"Scanners disagree about FNC1. `decode` therefore
absorbs all three transmissions it can arrive as: the GS character itself, a configured
substitute character, or stripped entirely — the deployed hardware does the last of these."* That
transmission variance is a problem **created by choosing GS1**, not one the requirement imposes.
AI 96 buys standards-conformance that nothing in a single-person LAN workshop consumes. Dropping
it removes an entire grammar module, its configuration pair, and three transmission variants,
while FR-015 is still met by the token. This is Principle I applied to a real fork in the road.

**Alternatives considered**:

- *GS1 AI 96 element string* — rejected above.
- *DataMatrix symbol* — rejected: needs a new encoder dependency, and Code128 fits the internal
  code comfortably on every stock in `LABEL_TYPES` (shortest is `Sato 1x2` at 2.0 in).
- *Sequential integers (`P000001`)* — rejected: a sequence leaks nothing useful here but invites
  transcription collisions with the existing `JA######` scheme, which is also a prefix + digits.

---

## 3. Retail barcode normalization and validation (FR-009, FR-010)

**Decision**: Normalize every retail/consumer barcode to a **14-digit GTIN key** by left-padding
with zeros. Accept raw input of length 8, 12, 13, or 14 (GTIN-8, UPC-A, EAN-13, GTIN-14).
Validate with the standard GS1 mod-10 check digit. Store the normalized 14-digit key as the
`product_identifiers.value` for type `GTIN`; uniqueness therefore falls out of the normalized
form. Reject an all-zero key. Per FR-010 the operator may **override** a validation failure and
store the value deliberately, recorded with a flag so the override is visible rather than
silent.

**Rationale**: FR-009 requires equivalent forms of the same barcode to resolve to one product.
Left-zero-padding to 14 is the GS1-sanctioned way to make UPC-A `012345678905` and EAN-13
`0012345678905` the same key, and it makes the "resolve to a single product" requirement a
plain unique-index property rather than application logic that could be bypassed. The all-zero
rejection is not theoretical: it is the shape a wedge scanner emits on a no-read.

**Prior art agrees** — `app/utils/gtin.py` on the branches uses exactly these accepted lengths,
the same 14-digit key, and names the all-zero case explicitly. No reason to differ.

**Note on UPC-E**: 8-digit input is treated as GTIN-8. True UPC-E (6 data digits, zero-suppressed)
expansion is **not** implemented, because whether the deployed scanner emits UPC-E expanded or
suppressed is a property of the scanner, and no observed case requires it. If a UPC-E label ever
fails to resolve, that is the moment to add expansion — with a real example to test against.

**Alternatives considered**: storing the barcode as scanned and normalizing at query time —
rejected, because it makes FR-009 a property of every read path instead of one write path, and
the unique index could no longer enforce it.

---

## 4. Distributor label parsing — ECIA / ISO/IEC 15434 (FR-016)

**Decision**: Parse the ISO/IEC 15434 **format-06** envelope:

```text
'[)>' RS '06' GS <record> GS <record> … RS EOT
```

where `RS` = `\x1e`, `GS` = `\x1d`, `EOT` = `\x04`. Each record is one ANSI MH10.8.2 data
identifier immediately followed by its value. Extract these seven:

| DI | Meaning |
|----|---------|
| `P` | Customer (distributor) part number |
| `1P` | Manufacturer part number — required by the ECIA spec |
| `Q` | Quantity |
| `K` | Customer order number |
| `1K` | Supplier order number |
| `9D` / `10D` | Date, `YYWW` |

Any other legal MH10.8.2 identifier a distributor prints (`1T` lot, `4L` country of origin,
`30P`, …) is **ignored silently** — an unrecognized identifier is a field this system has no home
for, not a damaged scan. Values are extracted **as strings, uncoerced**: no date parsing, no
quantity-to-int, no content validation. A scan that is not a well-formed envelope, or is a
well-formed envelope carrying no recognized identifier, yields no fields and falls through to
free-text handling per FR-016's non-conforming clause and Story 4's acceptance scenario 3.

**Rationale**: This satisfies FR-016 ("at least the manufacturer part number, quantity, and order
references") and FR-017 (every extracted value stays editable). Keeping values as scanned strings
is what makes FR-017 honest — coercing a malformed date would either lose data the operator can
read with their own eyes or raise on a label that is perfectly legible.

**Confirmed by the spec's clarification**: the operator confirmed the deployed scanner reads the
2D symbol and **preserves the field separators**, which is precisely what this grammar depends
on. Had separators been stripped, the fallback would have been best-effort extraction with the
raw scan always shown.

**Prior art agrees and is worth reading** — `app/utils/ecia.py` on the branches implements this
grammar with the same seven identifiers and the same never-raise-on-`str` contract. Two of its
hard-won details are adopted here: (a) a character glued directly onto the format indicator means
the indicator was never delimited, so the string only *resembles* an envelope and must not be
parsed as one; (b) a half-delivered trailer — data followed by `EOT` with no `RS` — must not read
the `EOT` as data.

**Alternatives considered**: a general MH10.8.2 table covering all identifiers — rejected under
Principle I; six more fields with no screen to show them on is speculative generality.

---

## 5. Scan classification precedence (FR-014)

**Decision**: One pure function classifies a captured scan. Five rules, first match wins, rule 5
always matches so **no scan dead-ends** (FR-018, SC-008):

1. Matches the internal code pattern (`WIT` + 10 Crockford chars) → `INTERNAL`
2. Is a format-06 envelope carrying ≥1 recognized data identifier → `ECIA`
3. Is check-digit-valid after GTIN normalization → `GTIN`
4. Matches a stored vendor item identifier (e.g. an ASIN) → `VENDOR`
5. Anything else → `FREE_TEXT`, carrying the raw scan into search

Classification is **structural only** — it takes text and returns a kind. It performs no database
lookup. Resolution (kind → product, or → "offer to create") is a separate `CatalogService`
method.

**Rationale**: FR-014 requires routing scanned input to the right outcome without the operator
choosing a type first. Splitting classification (pure) from resolution (needs a session) is what
lets the classifier be unit-tested with no app context and reused by the order-time capture path
in §8, which has no scanner involved at all. Rule 1 outranks rule 3 because an internal code must
never resolve to somebody else's trade item.

**Departure from prior art**: the prior `scan_router.py` had a rule for GS1 AI-01 element-string
substitution. Dropped here along with the GS1 grammar (§2) — a manufacturer's GS1-128 symbol is
rare on the unbranded Amazon imports this catalogue is mostly for, and rule 5 routes it to search
rather than dead-ending. If one shows up, adding a rule is a contained change.

**Departure, and it is a real one**: rule 4 (vendor identifier lookup) is *not* purely structural
— an ASIN has no distinguishing shape from free text, so it can only be recognized by lookup.
Resolution therefore tries rule 4 after the pure classifier returns `FREE_TEXT`. Stated plainly
here because it is the one place the clean pure/impure split bends, and the contract in
[scan-contract.md](./contracts/scan-contract.md) reflects it.

---

## 6. Category hierarchy (FR-030)

**Decision**: **Materialized path** — a single `products.category_path` column holding a
`/`-separated path of arbitrary depth. Canonical form: lowercase, no leading/trailing separator,
no empty segments, each segment whitespace-stripped. Normalization only shortens or lowercases;
it never slugs, hyphenates, or folds Unicode. Blank, `'   '`, `'/'`, and `NULL` all mean "no
category" and are not errors. Descendant queries use the segment-boundary predicate
`path = X OR path LIKE 'X/%'`. Categories are created **inline** by typing one, with no separate
setup step.

**Rationale**: FR-030 needs arbitrary depth and inline creation; FR-032's category filter needs
"this category and its sub-categories" (Story 7 scenario 1). A materialized path gives both with
one indexed column and a `LIKE` prefix — no recursive CTE, no adjacency-list joins, no separate
`categories` table to keep in sync with the products referencing it. Not slugging matters: the
operator's own vocabulary *is* the taxonomy, and `Power Supplies/DC DC` has nothing to be slugged
for.

**Prior art agrees** — `app/utils/category.py` on the branches uses the same canonical form and
the same boundary predicate, and the existing `MaterialTaxonomy` table in the codebase shows the
alternative (fixed 3-level parent-pointer), which cannot do arbitrary depth.

**Alternatives considered**: a `categories` table with a `parent_id` — rejected; needs recursive
queries for the subtree filter and an orphan-cleanup story, for no gain at this scale. Fixed
depth like `MaterialTaxonomy` — rejected; FR-030 says arbitrary.

---

## 7. Attachments (FR-034)

**Decision**: Reuse the existing photo pattern. The codebase already has a `photos` table storing
BLOBs in three sizes with `MEDIUMBLOB` on MySQL, an `item_photo_associations` many-to-many table,
20 MB max, MIME allow-list, SHA-256 for dedup, and **PDF support with PyMuPDF thumbnails**. Add a
`product_attachments` association table keyed to a product **or** a purchase, reusing the `photos`
table for the bytes.

**Rationale**: FR-034 names "datasheets, wiring diagrams, saved listings, photographs" — datasheets
are PDFs and PDFs already work. Building a second blob store beside the working one would be the
opposite of Principle I. The association-table split (bytes once, referenced many times) is
already the established shape.

**Note**: the existing `PhotoService.MAX_PHOTOS_PER_ITEM = 10` cap is per-item; the product
equivalent should be a named constant of its own rather than reusing that one, so the two limits
can differ without either surprising the other.

---

## 8. Order-time capture (FR-020, FR-021)

**Decision**: A **bookmarklet**. The operator, viewing a vendor listing, clicks a browser
bookmark; a small script reads the page title, URL, and — for known vendors — the item identifier
from the URL, then POSTs them to a capture endpoint on the app. The endpoint creates an
unreceived `Purchase`, attaching it to an existing product when the captured identifier matches
one (FR-021) and creating a new product otherwise. The operator completes or amends the
mechanical fields on the app's own form; nothing is auto-submitted.

**Rationale**: FR-020 requires capture "from the vendor's listing" while it is on screen, and the
spec's constraints forbid a separate service, a separate mobile app, and *"automated or unattended
scraping of vendor websites… Order-time capture is an operator-initiated action while viewing a
listing."* A bookmarklet is operator-initiated by construction (it runs only on click), needs no
extension store, no manifest, no background process, and no new deployment surface — it is a URL
the operator saves once.

**Constraints this imposes, stated so planning does not discover them late**:

- The endpoint must accept a cross-origin POST from the vendor page. This is a LAN-only,
  no-auth app whose threat model explicitly excludes hostile input, so the simple approach —
  a form POST or a CORS-permitted endpoint exempted from CSRF — is proportionate. It should be
  the **only** such exemption, and it should be commented as to why.
- Amazon's DOM is not a contract. The bookmarklet reads `location.href` and `document.title`, and
  extracts the ASIN from the URL path (`/dp/<ASIN>/`), which is far more stable than any selector.
  Anything it cannot find is simply left blank for the operator to fill.
- **Idempotency**: capturing the same listing twice must not create two purchases. Key on
  (vendor, vendor item identifier, order date).

**Alternatives considered**: a browser extension — rejected, more machinery and a distribution
story for one user. Pasting the URL into a form in the app — viable and *should be the fallback
path that always works*, but it loses the listing title and forces a tab switch, which is the
manual effort FR-020 exists to remove. Both are built: the bookmarklet is the fast path, the
paste-a-URL form is the one that cannot break.

---

## 9. Tri-state quantity and staleness (FR-022, FR-023, FR-024)

**Decision**: `products.quantity` is a **nullable integer**. `NULL` means "not tracked"; `0`
means "tracked, none on hand". New products default to `NULL` (FR-023). A separate
`quantity_updated_at` timestamp records when the count was last set, and every display of a
tracked quantity shows its age in relative terms ("counted 8 months ago") rather than presenting
the number bare (FR-024).

**Rationale**: FR-022 requires "tracked and none on hand" to be visibly distinct from "quantity
not tracked", and SC-007 makes that unambiguity a success criterion. Nullable-integer is the
narrowest representation that carries three states, and it makes the default (FR-023) simply
"the column default". Age comes from a timestamp rather than a staleness flag because a flag
needs a policy — how old is stale? — that nobody has measured and the spec does not state.
Showing the age lets the operator apply their own judgment, which is what FR-024 actually asks
for ("convey the age").

**Quantities are `Integer`, not `Decimal`.** Constitution III governs *physical measurements*;
these are counts of discrete parts. Prices remain `Numeric(10,2)`.

---

## 10. Reorder state — derived, not stored (FR-025 – FR-029)

**Decision**: Compute all reorder state at query time. A product is **effectively low** when
either its manual `stock_status` flag says low/out (FR-025), or it is tracked and
`quantity <= reorder_threshold` (FR-026). It is **on order** when it has at least one purchase
with `received_date IS NULL` (FR-028). The reorder view is one query returning both sets with
the on-order ones marked. FR-029 ("clear low status when an outstanding order is received") is
satisfied for the tracked case automatically once the receipt updates the quantity; for the
**manual** flag it requires an explicit clear at receipt, because nothing else knows the operator's
intent.

**Rationale**: FR-028 says the on-order indication must appear *"without the operator recording
that state separately"* — i.e. it must be derived from purchase data. Once one half is derived,
deriving the other half too means there is no stored status to fall out of sync, no background
job, and no reconciliation task. At tens of products in the reorder view, the query cost is
irrelevant, and Principle I forbids optimizing without a measurement.

**The FR-029 asymmetry is the one subtle point in this feature** and is called out here so it
lands in tasks rather than being discovered in review: receiving an order updates a tracked
quantity (so the derived low clears itself), but a manually flagged product stays flagged until
something clears the flag. The receipt path must clear it explicitly.

---

## 11. Draft persistence against a dropped connection (FR-035)

**Decision**: Persist in-progress form state to **`localStorage`** on input, keyed by form and
product. On load, if a draft exists for that form, offer to restore it. Clear the draft on
successful submit.

**Rationale**: FR-035 requires only that composed text survives an interrupted connection, and
the spec's environmental assumptions are explicit that *"full offline operation with local
storage and later synchronization is out of scope; the only resilience required is that a
momentary interruption not discard in-progress entry."* `localStorage` meets that in a few dozen
lines with no server involvement and no service worker.

**Precedent exists in the codebase**: the label-printing modal already persists the selected
label type to `localStorage` on the Add Item form.

**Alternatives considered**: server-side draft records — rejected, they need a schema, a cleanup
story, and a network round-trip, and the network is the thing that just failed. A service worker
/ offline sync — explicitly out of scope per the spec.

---

## Summary of decisions

| # | Area | Decision | New dependency |
|---|---|---|---|
| 1 | Label composition | Pillow canvas → existing `LpPrinter.print_images()` | none |
| 2 | Internal code | `WIT` + Crockford base32(10), Code128 | none |
| 3 | Retail barcodes | Normalize to 14-digit GTIN key, mod-10 check, override allowed | none |
| 4 | Distributor labels | ISO/IEC 15434 format-06, 7 MH10.8.2 identifiers, values uncoerced | none |
| 5 | Scan routing | 5-rule pure classifier + separate resolution | none |
| 6 | Categories | Materialized path, arbitrary depth, inline create | none |
| 7 | Attachments | Reuse `photos` BLOB pattern + new association table | none |
| 8 | Order capture | Bookmarklet POST, plus a paste-a-URL fallback | none |
| 9 | Quantity | Nullable int (3 states) + `quantity_updated_at` | none |
| 10 | Reorder state | Fully derived at query time | none |
| 11 | Draft persistence | `localStorage` | none |
