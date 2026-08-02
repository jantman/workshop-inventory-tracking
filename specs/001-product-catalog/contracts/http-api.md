# Contract: HTTP Surface

**Feature**: [../spec.md](../spec.md) | **Plan**: [../plan.md](../plan.md)

All routes live in the new `app/product/` blueprint unless marked *(existing)*. Routes stay thin
per Constitution II — no ORM queries, no raw SQL; everything delegates to `CatalogService`.

Conventions follow the existing app: server-rendered pages return HTML, `/api/*` returns JSON,
CSRF is enabled on state-changing form posts, and errors go through the centralized handlers in
`app/error_handlers.py` using the exceptions in `app/exceptions.py`. No new error machinery.

---

## Pages

| Method | Path | Purpose | FR |
|---|---|---|---|
| `GET` | `/products` | Catalogue list + search entry | FR-032 |
| `GET` | `/products/new` | Create form; accepts `?identifier=` and `?prefill=` from a scan | FR-001, FR-018 |
| `POST` | `/products/new` | Create | FR-001, FR-003 |
| `GET` | `/products/<id>` | Detail: description, specs, identifiers, purchase history, latest price, quantity + age, attachments | FR-006, FR-024 |
| `GET`/`POST` | `/products/<id>/edit` | Edit | FR-003 |
| `GET`/`POST` | `/products/<id>/purchases/new` | Record a purchase against an existing product | FR-019 |
| `GET`/`POST` | `/purchases/<id>/receive` | Mark received; amend quantity/price; **clear a manual low flag** | FR-005, FR-029 |
| `GET` | `/products/reorder` | Unified reorder view, on-order marked | FR-027, FR-028 |
| `GET` | `/products/categories` | Browse the category tree | FR-030 |
| `GET` | `/products/capture` | Paste-a-URL fallback for order-time capture | FR-020 |

---

## JSON API

| Method | Path | Body / Params | Returns | FR |
|---|---|---|---|---|
| `POST` | `/api/scan` | `{"scan": "<raw>"}` | `ScanResolution` — see [scan-contract.md](./scan-contract.md) | FR-014 |
| `POST` | `/api/products` | product fields | created product | FR-001 |
| `GET` | `/api/products/search` | `q`, `category`, `tag`, `stock` | matching products | FR-032 |
| `POST` | `/api/products/<id>/identifiers` | `{id_type, value, vendor?, override?}` | created identifier | FR-007, FR-010 |
| `DELETE` | `/api/products/<id>/identifiers/<iid>` | — | `204` | FR-007 |
| `PATCH` | `/api/products/<id>/quantity` | `{"quantity": <int\|null>}` | updated product | FR-022, FR-023 |
| `PATCH` | `/api/products/<id>/stock-status` | `{"stock_status": "low"\|"out"\|null}` | updated product | FR-025 |
| `POST` | `/api/products/<id>/label` | `{"label_type": "<key>"}` | print acknowledgement | FR-011, FR-013 |
| `GET` | `/api/labels/types` | — | label type names | FR-037 |
| `POST` | `/api/capture` | `{vendor, vendor_item_id, listing_title, url, price?, order_date?}` | created/attached purchase | FR-020, FR-021 |
| `POST` | `/api/products/<id>/attachments` | multipart file | created attachment | FR-034 |
| `POST` | `/api/purchases/<id>/attachments` | multipart file | created attachment | FR-034 |
| `GET` | `/api/categories` | `prefix?` | distinct category paths | FR-030 |
| `GET` | `/api/tags` | `prefix?` | tag names | FR-031 |

*(existing, reused unchanged)*: `GET /api/labels/types`, and the photo endpoints under
`/api/photos/*` that back attachment retrieval.

---

## Notable behaviours

**`POST /api/scan` never 4xxs an unrecognized scan.** "Unrecognized" is a successful answer with
`outcome='search'`. `4xx` means the *request* was malformed.

**`PATCH /api/products/<id>/quantity` accepts explicit `null`** to stop tracking, which is
distinct from omitting the field. This is the API-level expression of the tri-state in
[data-model.md](../data-model.md) §1, and it is the thing SC-007 is measured on.

**`POST /api/capture` is idempotent** on `(vendor, vendor_item_id, order_date)` — capturing the
same listing twice attaches nothing new (research §8). It attaches to an existing product when
the identifier matches (FR-021) and creates one otherwise.

**`POST /api/capture` is the one CSRF-exempt endpoint**, because the bookmarklet posts from the
vendor's origin. The exemption is proportionate under the constitution's stated threat model
(LAN-only, single trusted user, no hostile input in scope) and must be commented as to why. It
should remain the only exemption.

**`GET /api/products/search`'s `stock` filter** accepts `low`, `on-order`, `tracked`,
`untracked`, `none-on-hand` — the last two being the distinction SC-007 requires be unambiguous
everywhere quantity appears.

---

## Touch and handheld (FR-036, SC-010)

Every action reachable at the workshop cart is reachable on a touch device with no keyboard.
Concretely, and testably:

- Quantity adjust and stock-status set are **buttons on the product detail view**, not
  keyboard-only shortcuts or type-a-number-only fields.
- The scan-result view is self-sufficient: everything the operator needs after a scan is on that
  screen, with no hover-only affordances and no second window.
- The UI stays the single responsive Bootstrap interface. No separate mobile interface — that is
  explicitly out of scope in the spec's constraints.
