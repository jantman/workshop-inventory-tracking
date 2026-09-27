# Data Model: Say When the Image Count Was Swept

## ListingCapture (`app/models.py`, not persisted)

| Field | Type | Default | Source | Meaning |
|-------|------|---------|--------|---------|
| `images_swept` | `bool` | `False` | payload key `images_swept`, `True` only when it is exactly JSON `true` | The listing's gallery images came from the sweep fallback, so its image count is a guess |

- No other field changes. `images` holds the same addresses whether swept or not (FR-007).
- Reaches the order review unchanged: each `AmazonOrderLine.listing` is built by the same
  `ListingCapture.from_data`.
- Not written to the database; no migration.
