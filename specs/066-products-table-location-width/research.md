# Research: Products Table Location Columns and Width

## R1 — Why the operator "doesn't see" a Location column

- **Finding**: `product/search.html` has had a Location column since the catalog was
  introduced, with sub-location appended as `<span class="text-muted small">/ …</span>`.
  `<main class="container">` caps content at 1320px (≈1294px inside padding at 1920px),
  and the table sits in `.table-responsive`, so long descriptions plus tag badges push
  the right-hand columns past the visible edge into a horizontal scroll.
- **Decision**: Fix both halves the issue names — separate columns, and full width.

## R2 — How to widen only the product list

- **Decision**: Wrap the `<main>` container class in `base.html` in a Jinja block
  (`main_container_class`, default `container`) and override it to `container-fluid`
  in `product/search.html`.
- **Rationale**: FR-009 confines the change to one page. A block is the idiomatic Jinja
  hook and leaves every other page byte-identical. `container-fluid` keeps Bootstrap's
  12px gutters, so phones and tablets lay out as before.
- **Alternatives considered**: Switching every page to `container-fluid` (out of scope,
  churns every screenshot); `container-xxl`/custom `max-width` CSS (still caps width,
  and a new number to maintain); a nested `container-fluid` inside `container` like
  `index.html` does (does not escape the parent's max-width).

## R3 — Column presentation

- **Decision**: Two plain columns, `Location` then `Sub-location`, between Category and
  Quantity. Empty value → empty cell. Empty-state row `colspan` 6 → 7.
- **Rationale**: Matches the issue's wording and the Needs Action filter, which treats
  sub-location alone as not a location. Long values wrap naturally in table cells.
- **Alternatives considered**: Keeping one combined cell with a clearer separator —
  rejected; the issue asks for location and sub-location as columns.

## R4 — Small screens

- **Decision**: Keep `.table-responsive`; at tablet/phone widths the table scrolls
  inside its card, the page does not. The filter form's `col-md-*` grid already stacks.
- **Rationale**: Phones are an edge case per the issue; no extra responsive code needed.
