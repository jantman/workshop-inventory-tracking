# Contract: How a capture travels from a vendor page to the application

This replaces the bookmarklet's transport. What arrives at the application is unchanged; how it
gets there is entirely different, and this document is the boundary.

Everything below the application's front door is already specified and unmodified — see
[028's capture payload contract](../../028-mcmaster-order-capture/contracts/capture-payload.md)
and [028's routes contract](../../028-mcmaster-order-capture/contracts/routes.md).

---

## The path

```
  operator                extension                    vendor page          application
     │                        │                             │                    │
     │─ clicks action ───────▶│                             │                    │
     │  or context menu       │                             │                    │
     │                        │── reads stored address      │                    │
     │                        │   (absent ⇒ open options,   │                    │
     │                        │    stop)                    │                    │
     │                        │                             │                    │
     │                        │── inject capture-agent.js ─▶│ (isolated world)   │
     │                        │── invoke entry point ──────▶│                    │
     │                        │                             │ reads DOM          │
     │                        │                             │ (order pages also  │
     │                        │                             │  fetch each line's │
     │                        │                             │  listing, same     │
     │                        │◀─ payload (awaited) ────────│  origin)           │
     │                        │                             │                    │
     │                        │── store payload, session ───│                    │
     │                        │── open tab: submit page ────│                    │
     │                        │                             │                    │
     │                        │  submit page builds form,   │                    │
     │                        │  POSTs in its own tab ──────┼───────────────────▶│
     │                        │                             │                    │
     │◀─ confirmation / order review renders in that tab ───┼────────────────────│
```

The vendor tab is never navigated away from.

---

## What the extension sends

A `POST`, `application/x-www-form-urlencoded`, to **`<configured address>/api/capture`**.

The fields, and the rule that governs them:

| Field | Present when | Value |
|---|---|---|
| `url` | always | the payload's `source_url` |
| `listing_title` | always | the listing's title, falling back to the document's |
| `listing` | always | the extraction, JSON |
| `order` | order pages only | the order and its lines, JSON |
| `vendor` | McMaster pages only | `McMaster-Carr` |

**The governing rule is FR-003: this must be byte-identical to what the bookmarklet sent for the
same page.** In particular a plain Amazon listing sends **no `vendor` field at all** — not an
empty one — because that is what it sent before, and the application derives the vendor from the
address in that case.

No header is added. No `Origin` is relied upon. The endpoint is `@csrf.exempt` and stays so; a
token cannot travel with a submission composed outside the application.

## What the extension does *not* send

- No extension identifier, no version header, no telemetry.
- No credentials of any kind. The extension holds none.
- Nothing about any page other than the one the operator invoked it on.

---

## Preconditions the extension enforces before submitting

| Condition | Behavior |
|---|---|
| No address configured | Do not capture. Tell the operator and open the options screen. (FR-011) |
| Address configured, not `https` | Warned at configuration time (FR-012). Capture is attempted; the browser decides. |
| Page kind is unrecognized | Do not capture. Tell the operator the page is not one it can read. (FR-008) |
| Reader threw | Do not submit a partial payload. Report that the page could not be read. |
| A single field was not found | **Submit anyway.** One field lost, nothing else. (FR-006) |

The last two are a deliberate pair, and the distinction is the one 007 FR-007 drew: a reader
that cannot find a selector degrades, a reader that cannot run at all fails.

---

## What the application must not have to change

This contract exists to pin that list to nothing:

- `product.api_capture` keeps its signature, its methods, its CSRF exemption, and its branch on
  the presence of `order`.
- `ListingCapture.from_json` keeps refusing anything that is not `PAYLOAD_VERSION` 1.
- The order review, the confirmation form, the matching, the writing and the receiving flows are
  all untouched.
- The paste-an-address path is untouched (FR-019).

The single application-side change in this feature is **removal**: `_capture_bookmarklet()`, the
`#capture-bookmarklet` control, and the `#bookmarklet-http-warning` alert, replaced by a pointer
to the extension (FR-017, FR-018).

---

## The reader's own interface, after this feature

`capture-agent.js` stops being a self-executing script and becomes a file that defines an entry
point.

| Before | After |
|---|---|
| Trailing IIFE reads `document.currentScript.dataset.endpoint`, dispatches on `location`, builds a form, submits it into a new tab | Entry point takes nothing, dispatches on `location`, **returns a promise for the payload** |
| Every reader above it | Unchanged |

The entry point returns rather than submits. That is the whole of the change to this file, and
it is what lets the submission happen somewhere the vendor's policy cannot reach.

**Return shape**, matching the table above:

```
{ url, listing_title, listing, order?, vendor? }
```

`order` and `vendor` are absent — not null, not empty — when they do not apply, because the
form is built from this object's own keys and an empty field is not the same as no field.
