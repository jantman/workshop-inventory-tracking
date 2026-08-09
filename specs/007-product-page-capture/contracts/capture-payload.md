# Contract: the capture payload

The one contract that crosses a machine boundary. `app/static/js/capture-agent.js` produces it inside the vendor's page; `ListingCapture.from_json` consumes it in this application. Everything else in this feature is a Python call.

## Transport

A single hidden form field named `listing`, holding the JSON as a string, on the form the agent submits into a new tab:

```
POST {endpoint}                      # endpoint = url_for('product.api_capture', _external=True)
Content-Type: application/x-www-form-urlencoded
target: _blank

url            = <canonical listing address>
listing_title  = <page title>
listing        = <this JSON, serialized>
```

`url` and `listing_title` are the two fields today's bookmarklet already sends, and they are still sent, unchanged. A server that ignored `listing` entirely would behave exactly as it does today — which is the compatibility property FR-007 rests on.

The same field then rides the confirmation form. `capture.html` re-emits it from `form_data`, so it survives a `CaptureDecisionRequired` re-render (FR-016) with no code of its own.

## Schema

```json
{
  "version": 1,
  "source_url": "https://www.amazon.com/dp/B0CKXJLP4B",
  "vendor_item_id": "B0CKXJLP4B",
  "listing_title": "12V 3A Power Supply Adapter, 5.5x2.1mm Barrel …",
  "price": "24.99",
  "brand": "Acme Components",
  "description_text": "This power supply provides …",
  "specifications": [
    {"name": "Material", "value": "6061 Aluminium"},
    {"name": "Item Length", "value": "300 Millimeters"}
  ],
  "images": [
    "https://m.media-amazon.com/images/I/71AbCdEfGh.jpg",
    "https://m.media-amazon.com/images/I/81ZyXwVuTs.jpg"
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `version` | integer | yes | `1`. Any other value → the payload is ignored with a log line. |
| `source_url` | string | yes | The address the agent actually read from — the canonical `/dp/<ASIN>` page where it could reach it, otherwise the tab's own address. |
| `vendor_item_id` | string \| null | no | |
| `listing_title` | string \| null | no | |
| `price` | **string** \| null | no | Never a JSON number. See below. |
| `brand` | string \| null | no | |
| `description_text` | string \| null | no | Uncapped — sent in full, per FR-006. `product_specifications.value` is `MEDIUMTEXT` after `b1a0c0d10009`. |
| `specifications` | array of `{name, value}` | no | Both strings. Already merged across the page's sections and folded for duplicates by the agent. |
| `images` | array of string | no | `http`/`https` addresses, gallery first, transform token already stripped, description images already size-filtered. |

### `price` is a string and this is not negotiable

JSON's only number type is an IEEE double. `24.99` arriving as a JSON number is a `float` before any Python in this repository sees it, and Principle III prohibits `float` for a measured quantity with no exemption for values in transit. The agent serializes the price exactly as it read it off the page, minus the currency symbol and thousands separators. `capture_order` hands it to `_validate_price`, which produces the `Decimal` — the same path a hand-typed price takes.

An agent that emitted `"price": 24.99` would be a bug in the agent, and the reviewer's check is that the value in the JSON has quotes around it.

## What the agent guarantees

- **Every field is optional except `version` and `source_url`.** The agent emits what it found and omits what it did not. A listing with no price yields no `price` key, not `"price": ""`.
- **The description is sent whole.** The agent does not truncate, and there is no truncation flag to report, because after `b1a0c0d10009` there is nothing to truncate against: 16,777,215 bytes, against a largest observed description of 28,767 characters. See [research.md](../research.md#the-description-ceiling) for the capped design this replaced.
- **`images` holds original-resolution addresses.** The transform token (`._AC_SL1500_.` and its kin) has been stripped. The server does not strip, retry, or fall back to a tokened address — FR-004 is satisfied here or reported as a failure.
- **`images` is already filtered.** Gallery images are included unconditionally; description images only when both edges are ≥ 300 pixels, or when the dimensions could not be established at all (FR-019). The server cannot tell the two kinds apart and does not need to.
- **`specifications` names are unique** under case- and whitespace-folding, first occurrence winning, across all of the page's product-information containers. The server folds again on merge, against the *product's* existing names — that is a different comparison, not a repeat of this one.
- **No row is dropped for being uninteresting.** Marketplace bookkeeping — Best Sellers Rank, Customer Reviews, Date First Available — is emitted like everything else (FR-008).

## What the server guarantees

- **An absent, empty, malformed, or wrong-version payload is not an error.** `from_json` returns `None` and the capture proceeds on `url` and `listing_title` alone, which is today's behaviour exactly (FR-007).
- **A malformed entry inside a well-formed payload is dropped, not raised on.** One bad specification row does not cost the operator the other twenty-four.
- **Nothing in the payload is written before the operator confirms** (FR-014). Until then it is a string in a hidden input.

## Versioning

`version` exists because the agent is cached in a browser this application does not control and the payload is the only thing that crosses between them. The loader's `?v=Date.now()` cache-buster makes a stale agent very unlikely; `version` is what makes a stale agent *harmless* rather than a 500.

There is exactly one version and no compatibility machinery. When the shape changes, the number goes to `2` and `from_json` stops accepting `1` — the old agent then degrades to today's behaviour on its next use and is replaced on the one after. Supporting two shapes at once would be building for a future that has not arrived.
