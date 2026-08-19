# Contract: the `listing` payload, after this feature

**Boundary**: `app/static/js/capture-agent.js` (producer) → `POST /product/capture`, field `listing`
→ `ListingCapture.from_json` (consumer, `app/models.py`).

This is the one machine boundary the feature crosses. Both sides are in this repository, but they
are separated by a *cached* script the operator may not have reloaded, so the compatibility rule
below is real rather than ceremonial.

## Version

```
version: 1        (unchanged — LISTING_CAPTURE_VERSION = 1)
```

**The version does not move.** The payload's shape is identical; only the contents of an existing
array change. A stale cached agent keeps producing a valid version-1 payload without the bullets
row, which degrades to today's behavior and is replaced on the next load. Bumping to 2 would make
`from_json` reject every stale agent for no benefit.

## The delta

`specifications` is unchanged in type — `[{name, value}, …]` — and gains **at most one entry**:

```json
{
  "version": 1,
  "specifications": [
    { "name": "About this item",
      "value": "First bullet, as the listing wrote it\nSecond bullet\nThird bullet" },
    { "name": "Material", "value": "6061 Aluminium" },
    { "name": "Item Length", "value": "300 Millimeters" }
  ]
}
```

Guarantees the producer makes:

| # | Guarantee |
|---|-----------|
| C-1 | The entry's `name` is exactly `About this item`. |
| C-2 | Its `value` holds one bullet per line, `\n`-separated, in the listing's own order. No trailing newline, no blank line between bullets. |
| C-3 | The entry is **first** in the array when present, before every container-derived row (FR-010). |
| C-4 | The entry is **absent entirely** when the listing has no bullet list or none of its bullets yields text (FR-008). An entry with an empty `value` is never produced. |
| C-5 | At most one such entry exists per payload — `specificationsFrom()`'s existing case-insensitive fold guarantees it even if a detail table also publishes the name. |
| C-6 | No other field of the payload changes for any listing (FR-012). |

Guarantees the consumer already makes, which this feature relies on rather than re-implements:

| # | Guarantee | Where |
|---|-----------|-------|
| C-7 | An entry with an empty name or value is dropped, not an error | `_payload_specifications`, `app/models.py:783` |
| C-8 | A captured name the product already carries is dropped whole, value included | `CatalogService.merge_specifications` |
| C-9 | Newlines in a `value` survive storage, display and editing | #91's work; `detail.html:106`, `_form_fields.html:51` |

## What is not in the contract

- Any promise about *which* bullets exist. That is the vendor's, and it changes without notice.
- Any promise that the row is present for a given ASIN. FR-011 makes reading the bullets optional;
  a payload with no `About this item` entry is well-formed and always was.
