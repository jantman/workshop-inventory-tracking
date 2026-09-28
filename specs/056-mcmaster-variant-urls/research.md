# Research: Capture McMaster Variant Product Pages

## §1 What the variant page is

Observed on the live site, 2026-09-28, logged in:

- `/3408A521-3408A523/` with "Threadlocker" chosen renders a normal product detail page:
  primary/secondary headers, `_price_`, the specification table, the CAD picker.
- Both `[class*="_partNumber_"]` elements (`_productDetailPartNumber_` and its print
  twin `_productDetailPartNumberPrint_`) read **3408A521** — the address's *first* number.
- The chosen option is a link to the same address (`_parameter_ _isSelected_` →
  `/3408A521-3408A523/`).
- The 3-D PDF link on the page names `3408A523`, the *second* number. So neither number is
  obviously "the family" and the other "the variant"; McMaster's convention is not
  documented anywhere reachable.

**Decision**: the page's displayed part number is the authority when it is one of the
address's two numbers; otherwise the first number in the address.

**Rationale**: the displayed number is what the owner sees and what they would order.
Restricting it to the address's numbers means a mis-read element (a related-product
card, a future markup change) can never put a number on the product that the address does
not name. The first-number fallback matches the one observation available.

**Alternatives considered**:

- *Always the first number.* Matches the observation, but rests on an undocumented
  convention; the displayed number costs one selector.
- *Always the displayed number, for every address.* Would change single-part captures
  (FR-003) on the strength of a selector, and could record a number the address does not
  name.
- *Refuse and tell the owner to use the bare address.* The bare address is the one without
  the drawing — the opposite of what the owner needs.

## §2 The selector

`[class*="_productDetailPartNumber_"]`, the stem convention every McMaster product-page
selector in `capture-agent.js` uses (hashed CSS-module names). It is the on-screen element;
`_productDetailPartNumberPrint_` also contains the stem `_productDetailPartNumber` but not
`_productDetailPartNumber_` (its next character is `P`), so the selector does not
ambiguously match the print copy — and both read the same anyway.

The existing fixture `tests/e2e/fixtures/mcmaster_product.html` already carries this
element (`91290A115`), so the e2e tests can serve it at variant addresses unchanged.

## §3 The server copy

`_mcmaster_part_from_url` is documented as a deliberate duplicate of the agent's pattern,
used by the paste-a-URL form with no page available. It takes the same optional second
group and returns the first number (FR-004) — the only answer available without the page.
It is also the fallback when a capture payload carries no `vendor_item_id`.

## §4 The drawing half of the issue

`/3408A521/` without a variant chosen showed no 2-D drawing. That is McMaster's page, not
the reader: the reader reads the picker the page renders (051). Once the variant page can be
captured, its drawing is read like any other. No warning for an unchosen variant is added
(spec Assumptions); detecting "a choice is outstanding" would need markup from a page that
could not be re-observed (it served an unrendered shell to the probe after navigation).
