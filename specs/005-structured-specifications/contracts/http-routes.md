# Contract: HTTP surface

**Feature**: [../spec.md](../spec.md) | **Service**: [catalog-service.md](./catalog-service.md)

Two new endpoints, four changed. All on the `product` blueprint (`app/product/routes.py`) unless noted.

---

## New: `GET /api/specification-names`

Specification names in use, for the name datalist on the product forms and on the catalogue filter (FR-019).

| Query param | Meaning |
|---|---|
| `prefix` | Optional. Narrow to names starting with it, case-insensitively. |

```json
{"success": true, "specification_names": ["Connector", "Output current", "Voltage"]}
```

Modelled on `/api/tags` and `/api/categories` — same shape, same thinness, one call to one service method. No pagination and no limit: the catalogue has tens of products and a bounded set of names.

---

## New: `GET /api/specification-values`

Values recorded under one name, for that row's value datalist (FR-020).

| Query param | Meaning |
|---|---|
| `name` | Required. The specification name, matched whole and case-insensitively. |
| `prefix` | Optional. Narrow the values. |

```json
{"success": true, "specification_values": ["3.3 V", "5 V", "12 V"]}
```

A missing, blank or unrecorded `name` returns `{"success": true, "specification_values": []}` with **200**, not 400. An unknown name is an ordinary state — the operator is mid-word — and a suggestion endpoint that errors while someone types would be a worse experience than one that returns nothing.

---

## Changed: `GET /products` (the catalogue page)

Two filters added to the existing four.

| Query param | Meaning |
|---|---|
| `spec_name` | Products recording this specification name (FR-012). |
| `spec_value` | With `spec_name`, narrows to values containing this text (FR-013). Ignored on its own. |

Both are passed to `search_products` and echoed back into `filters` so the form redisplays them, exactly as `q`, `category`, `tag` and `stock` already are. `search.html` grows a name input backed by the shared names datalist and a value input backed by a datalist refilled when the name changes.

This is the URL the product detail page links to (FR-018): `/products?spec_name=Voltage&spec_value=12+V`.

---

## Changed: `GET /api/products/search`

The same two parameters, passed through to the same service call. Response shape is unchanged apart from each product's `specifications` now being a list — see below.

---

## Changed: product JSON

Everywhere a product is serialized — `GET /api/products/<id>`, `POST /api/products`, `GET /api/products/search` — `specifications` changes from a string or `null` to a list, always present, empty when there are none (FR-011):

```json
"specifications": [{"name": "Voltage", "value": "12 V"}]
```

No consumer outside this repository reads it: products are not part of the Google Sheets export, and `app/api_client.py` does not touch the catalogue. No compatibility shim is provided, and none is warranted for a single-user application with no external clients.

---

## Changed: `POST /api/products`

`data.get('specifications')` now carries the list and is passed to the service unchanged. A malformed entry produces the existing `400` shape:

```json
{"success": false, "error": "Specification \"Voltage\" has no value."}
```

---

## Changed: `GET|POST /products/new` and `/products/<id>/edit`

The form encoding changes. `specifications` as a single textarea field is replaced by parallel repeated fields:

| Field | Cardinality |
|---|---|
| `spec_name` | Once per row, in DOM order |
| `spec_value` | Once per row, in DOM order |

`_form_product_fields` builds the list with `request.form.getlist('spec_name')` and `getlist('spec_value')`, pairing by index and passing the result straight to the service, which is what validates it. Rows where both are blank are dropped by the service (FR-009); a half-filled row is refused there (FR-008), and the refusal re-renders the form with the submitted values, as the existing `ValidationError` path already does.

The two lists are always the same length because every row's markup carries both inputs. If they somehow differ, the shorter one governs — a `zip`, not an index walk that could raise.

**Unchanged on these routes**: the ECIA prefill query parameters, the note block they compose, and the identifier fields. Distributor-label scans do not populate specifications; that is a stated scope decision, not an omission.
