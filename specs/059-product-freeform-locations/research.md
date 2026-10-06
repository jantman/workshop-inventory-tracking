# Research: Free-Text Locations on the Product Move Page

## R1: How to tell a product location from a sub-location

- **Decision**: Use position. While the machine waits for a location (`location`,
  `bulk_location`), any value that is not a product code, JA ID or `>>DONE<<` is the location.
  In `id_or_sub_location`, free text is the sub-location, and an item-shaped location is
  still "two locations in a row".
- **Rationale**: The page already knows what it is waiting for. This is the only rule that
  accepts a never-before-used location the first time it is scanned. It also keeps every
  existing product-page test true, including the two-locations warning for `M…` and `T…` values.
- **Alternatives considered**:
  - *Match against existing product locations*: this refuses a new shelf on first use, and
    costs a fetch per scan.
  - *A barcode prefix for location labels*: this means reprinting every label the owner has,
    and no such convention exists for products.
  - *Purely positional in every state* (an `M…` value after a location becomes a
    sub-location): this would drop the existing two-locations guard for no gain.

## R2: Where the change lives

- **Decision**: Override `isLocation` in `ProductMoveManager`. `classifyInput`'s order stays
  as it is, so subject and foreign IDs win before the location rule is consulted.
- **Rationale**: The item page inherits the base method and is untouched. `classifyInput` stays
  the one thing `waits.scan_on_move_page` asks, and it is evaluated in the page's current
  state just before typing, so the waiter needs no change.

## R3: Wording

- **Decision**: Add a base `locationHint` getter that returns `' (M*, T*, or Other)'`. The
  product page overrides it with `''`, and the four messages that name the convention
  interpolate it. A `location_example` macro parameter replaces the hard-coded
  `M1-A, T-5, or Other` in the instructions.
- **Rationale**: This keeps the item page's strings identical (FR-005), and on the product
  page it stops telling the owner about a convention their locations do not follow.
