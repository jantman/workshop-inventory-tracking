# Data Model: Browser Capture Extension

**This feature adds no database tables, no columns and no migration.** Nothing it produces is
persisted by the application; the capture endpoint's behavior is unchanged, so everything it
writes it already wrote. The entities below live in the browser.

---

## Captured payload

What the reader extracts from a vendor page and the extension hands to the application.

**Unchanged by this feature.** Its shape is fixed by
[`specs/028-mcmaster-order-capture/contracts/capture-payload.md`](../028-mcmaster-order-capture/contracts/capture-payload.md)
and by `ListingCapture.from_json` in `app/models.py`, and FR-003 requires it to stay
byte-identical to what the bookmarklet submitted. It is listed here only to state that it does
not move.

| Field | Origin | Notes |
|---|---|---|
| `url` | `listing.source_url` | The address the reader read from. |
| `listing_title` | the listing, falling back to `document.title` | |
| `listing` | JSON | The whole extraction, at `PAYLOAD_VERSION` 1. |
| `order` | JSON, conditional | Present only for an order page. |
| `vendor` | constant, conditional | Sent for McMaster pages; absent for the plain Amazon listing path, which must stay byte-identical. |

**Validation**: none added. The application continues to be the only validator, and a payload it
does not recognize continues to render the ordinary confirmation form rather than failing —
the documented fall-through.

---

## Configured application address

The extension's entire configuration: one value.

| Property | Value |
|---|---|
| Where | `chrome.storage.sync`, single key |
| Set by | The operator, on the options screen (FR-009) |
| Lifetime | Persists across browser restarts (FR-010); roams to the operator's other signed-in browsers |
| Shape | A bare origin — scheme, host, optional port. No path, no trailing slash. |

**Normalization**, applied once on save (FR-013): surrounding whitespace trimmed, trailing
slashes stripped. The submitting page appends the endpoint path itself, so a stored value with a
path would produce a wrong address — stripping is what makes a pasted browser-bar address work.

**Validation on save**:

| Condition | Result |
|---|---|
| Empty | Rejected; nothing is stored. |
| Not parseable as an address | Rejected, with the reason shown. |
| Parseable but not `https` | **Saved, with a warning shown** (FR-012). It is the operator's installation; they are told it will not work, not prevented. |
| Parseable and `https` | Saved. |

**State transitions**: *unset* → *set* on first save; *set* → *set* on later saves. There is no
delete, because an empty value is rejected rather than stored.

**When unset** (FR-011): a capture does not proceed. The operator is told the address has not
been configured and is taken to the options screen. This is the single most important behavior
in the model — silently doing nothing is the symptom of the bug this whole feature fixes, and
the extension must never reproduce it.

---

## Pending capture

The payload in transit, between the reader returning it and the submitting page sending it.

| Property | Value |
|---|---|
| Where | `chrome.storage.session` |
| Key | Single-use, generated per capture |
| Lifetime | Written before the tab opens; deleted by the submitting page once it has built the form |
| Contents | The captured payload, plus the resolved application address |

Single-use keys rather than one fixed key so two captures started in quick succession cannot
overwrite one another. Session rather than local storage because the value is meaningless after
the submission and captured vendor data should not outlive the browser session on disk.

**Failure**: if the submitting page finds no value for its key — the session was cleared, or the
tab was restored later — it says so rather than submitting an empty form.

---

## Supported page kind

Which recognized vendor page an address names. Determined from the address alone, exactly as
today, by `pageKind()` in the reader.

| Kind | Recognized by |
|---|---|
| `amazon-order` | path `/your-orders/order-details` **and** an `orderID` in the query |
| `mcmaster-order` | path `/order-history/order/<24 hex>` |
| `mcmaster-product` | path `/<digits><uppercase letter><alphanumerics>/` |
| `other` | everything else, including a plain Amazon listing |

**Two consumers now, where there was one.** The reader still uses it to dispatch. The service
worker also uses it, against the tab's address, to decide whether the context-menu entry applies
(FR-016) and whether to report "this is not a page I can read" (FR-008). The rules must not
diverge, which is an argument for the worker asking the reader rather than reimplementing the
patterns.

`other` is deliberately not "unsupported": a plain Amazon listing lands there and is captured.
Only a page matching no vendor at all is refused.

---

## Packaged extension

The published artifact.

| Property | Value |
|---|---|
| Form | A zip of the extension directory (research.md §10) |
| Version | Equal to the application's `pyproject.toml` version, enforced by a test (FR-024) |
| Published | As a build output on every build, and as a release asset on every release (FR-022, FR-023) |

**Invariant**: the declared version in `manifest.json` and the declared version in
`pyproject.toml` are the same string. This is the model's only cross-artifact constraint and the
only one a test enforces.
