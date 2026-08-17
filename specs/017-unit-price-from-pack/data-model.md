# Data Model: Unit Price From a Multi-Pack

**There is no schema change in this feature, and no Alembic revision.** This document exists
to record that, and to pin down the transient values that do appear — because "not stored" is
a design property that has to be written down somewhere to stay true.

## Stored entities: unchanged

| Table | Column | Before | After |
|-------|--------|--------|-------|
| `purchases` | `unit_price` | `Numeric(10, 2)`, nullable, `>= 0` | identical |
| `purchases` | `quantity` | `Integer`, nullable, `> 0` | identical |

`purchases` gains no column. `products` gains no column. Nothing about the pack — neither what
was paid for it nor how many units it held — is recorded anywhere (FR-014). What reaches the
database is the same single unit price it takes today, arrived at differently.

The existing precision is what makes FR-006's rounding the right rule rather than an arbitrary
one: `Numeric(10, 2)` is the definition of "a price is recorded to the cent", so a value the
page displays to the cent is a value that round-trips.

## Transient values (page-scoped, never persisted)

Both live only in the capture confirmation form and its re-renders.

### Amount paid for the pack

- **Form field**: `pack_price`, DOM id `#pack_price`
- **Meaning**: what the whole pack cost — which, for a listing that sells a pack, is the price
  the listing states.
- **Shape**: a decimal string matching `^\d+(\.\d+)?$` after trimming. Not a number, at any
  point; the same digit-string discipline `ListingCapture.price` already keeps for the same
  reason.
- **Initial value**: `form_data.get('pack_price')`, else the extracted `listing.price`, else
  empty (FR-013).
- **Lifetime**: submitted with the form because it is a form field, ignored by
  `product_capture`, and re-emitted on a `CaptureDecisionRequired` re-render by the existing
  `form_data=request.form` (FR-012). It is never passed to `capture_order` and never reaches
  storage.

### Units in the pack

- **Form field**: `pack_size`, DOM id `#pack_size`
- **Meaning**: how many units came in the pack. It is *not* how many units were ordered — that
  is `quantity`, which this feature does not touch.
- **Shape**: a whole number string matching `^\d+$`, greater than zero.
- **Initial value**: `form_data.get('pack_size')`, else `1`.
- **Lifetime**: as above — submitted, ignored, re-emitted, never stored.

### Derived unit price

Not a new field. `#unit_price` is the field it has always been; the feature writes into it and
the operator may overwrite what was written (FR-004). It is what `capture_order` records, by
the path it already takes: form string → `_validate_price` → `Decimal` → `Numeric(10, 2)`.

## The derivation

The rule in full, and its failure cases, are in
[contracts/README.md](contracts/README.md#unitpricefrompackpaid-packsize). In summary:

| Inputs | Result | `#unit_price` | Note shown |
|--------|--------|---------------|------------|
| `pack_size` absent or `1` | the amount paid, verbatim | written | no |
| valid, divides evenly | quotient at 2 dp | written | no |
| valid, does not divide evenly | quotient rounded half-up at 2 dp | written | yes (FR-008) |
| `pack_price` unusable | none | **left as it is** | error naming `pack_price` |
| `pack_size` unusable | none | **left as it is** | error naming `pack_size` |

## State transitions

The only state is which of the three the form is showing — nothing, the note, or an error —
and it is recomputed from the two inputs on every `input` event. There is no accumulated
state: FR-005 requires each computation to start from the two current input values, never from
the previously displayed unit price, which is what makes changing the pack size twice in a row
give the same answer as typing the second value first.

On page load the inexactness note is evaluated, but `#unit_price` is **not** written and the
error line is **not** shown. Two different reasons, both worth stating:

- **Not written**, because a re-render may be carrying a unit price the operator typed over
  the derived one before the form came back with a question, and a load-time write would
  silently discard it.
- **No error**, because an error is feedback on an edit. Every fresh capture page arrives with
  an empty pack price, and an error line is the wrong thing to greet it with.
