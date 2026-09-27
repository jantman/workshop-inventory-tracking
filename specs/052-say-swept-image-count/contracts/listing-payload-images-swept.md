# Contract: `images_swept` on the listing payload

Additive to the listing payload `extension/capture-agent.js` produces (version 1), both as
the single-listing `listing` form field and as each Amazon order line's `listing` object.

```json
{
  "version": 1,
  "source_url": "https://www.amazon.com/dp/B0...",
  "images": ["https://m.media-amazon.com/images/I/....jpg"],
  "images_swept": true
}
```

| Producer (extension) | Consumer (server) |
|----------------------|-------------------|
| Sets `"images_swept": true` when, and only when, the gallery data could not be parsed and the sweep supplied at least one gallery address — the same condition that emits the `[capture-agent] could not read the gallery data` console warning. Omits the key otherwise. | `images_swept` is `True` iff the key's value is JSON `true`. Absent, `false`, or any other value → `False`. |

- `version` stays `1`. A payload from an extension predating this key is valid and reads as
  not swept.
- The flag never changes which images are captured or stored.

## Rendered surfaces

- `product/capture.html`, `#summary-images`: when set, contains an element with class
  `images-swept` reading "the listing's own gallery data could not be read, so this count is
  a guess". When not set, no such element and the text is unchanged.
- `product/order_review.html`, `.line-listing-summary`: when the line's listing is swept,
  contains an element with class `images-swept` saying the picture count is a guess. Lines
  whose listing is not swept are unchanged.
