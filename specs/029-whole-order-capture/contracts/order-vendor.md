# Contract: `OrderVendor` — the consolidation seam

**Feature**: 029-whole-order-capture

This is the whole of FR-036: what a vendor is allowed to differ in. Anything not on this list is
shared, and a vendor that needs something not on this list is a signal the seam is wrong
(FR-037), not a reason to add a branch.

Lives in `app/services/order_vendors.py`. One frozen dataclass, three module-level instances,
no subclassing.

---

## The fields

| Field | Type | DigiKey | McMaster-Carr | Amazon |
|---|---|---|---|---|
| `name` | `str` | `'DigiKey'` | `'McMaster-Carr'` | `'Amazon'` |
| `item_id_of(line)` | callable → `str` | `line.digikey_part_number` | `line.part_number` | `line.asin` |
| `identifier_types` | tuple | `DISTRIBUTOR` (scoped) + `MPN` | `DISTRIBUTOR` (scoped) + `MPN` **only where stated** | `ASIN` (scoped) |
| `suggested_description(line, part)` | callable → `str` | enriched part detail, else the line's | the line's description | the line's title |
| `find_product(session, line)` | callable → `Product \| None` | by DKPN, then by MPN | by part number, scoped | by ASIN, scoped |
| `enrich(client, lines)` | callable | the part lookup | no-op | no-op |
| `line_arithmetic` | callable \| `None` | `None` | packs → units | `None` |
| `receive_landing` | enum | `ORDER_SCREEN` | `CHOICE_PAGE` | `CHOICE_PAGE` |
| `review_columns` | tuple | shipped / backorder | packs / pack size / pack price | — |

**`identifier_types` is data, not a callable**, because what a captured line writes is a fact
about the vendor rather than about the line — with one exception, McMaster's conditional MPN,
which is expressed as "write it only where the line states one" and is already the behaviour
today.

---

## What the shared flow guarantees

Given any `OrderVendor`, these behave identically and are implemented once:

* **Review.** One `ReviewedLine` per order line, states tested in the order
  `CAPTURED → CONFLICT → MATCHED → NEW`. Writes nothing.
* **Pairing.** Recorded purchases pair to lines in two passes — by `order_line_number` first
  (exact), then by item id for purchases carrying no line number, each claimed once. **Never
  positionally at re-capture time**; that is the defect PR #116 fixed.
* **Orphans.** Purchases against this order that no line claims are reported and **never
  deleted**.
* **Confirmation.** One transaction for the whole order. A refused line aborts the lot; nothing
  partial is ever left (FR-020).
* **Exclusions, descriptions, conflict resolution, change application.** One implementation.
* **Order screen and receiving.** One template, one route, one rule.

## What it must not become

* Not a place to put per-vendor *display strings* beyond `review_columns` — those belong in the
  template.
* Not a place for network configuration; the DigiKey client is passed in, as it is today.
* Not a base class. If polymorphism starts to look necessary, the variation has outgrown the
  measurement in research.md §9 and should be re-measured rather than accommodated.

## Enrichment stays outside the session

`enrich()` is called **before** the write transaction opens, for the reason both existing
captures state at their call sites: it is network I/O at up to ten seconds a call, and holding a
transaction open across twenty-five of them is a long-lived lock in exchange for nothing.

The shared flow must preserve this ordering. It is the kind of property a refactor silently
breaks, and it has been broken here once before (PR #116 moved a review's enrichment back out of
its session).
