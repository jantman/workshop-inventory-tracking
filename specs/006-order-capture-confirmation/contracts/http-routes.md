# Contract: HTTP surface

No new route and no new endpoint. Three existing handlers in `app/product/routes.py` change behaviour, and two templates change shape.

## `POST /api/capture` — the bookmarklet's entry point

`app/product/routes.py:406`. Still the **only** `@csrf.exempt` in this blueprint, so the assertion in `tests/unit/test_product_csrf.py` that counts exemptions still passes. The two representations diverge further than they do today.

### Form body — the bookmarklet

**Before**: create the product and purchase, redirect to `/purchases/<id>/receive`.

**After**: derive `vendor` and `vendor_item_id` from the URL exactly as now (`_vendor_from_url`, `_asin_from_url`), and **render `product/capture.html` pre-filled**. Status 200. Nothing is created (FR-008, FR-009).

The rendered form posts to `/products/capture` with a CSRF token, because by then the operator is on this application's own origin. The `javascript:` payload in `_capture_bookmarklet` (`app/product/routes.py:377`) is **unchanged** — same endpoint, same two fields, same form-into-a-new-tab mechanism — so `test_the_bookmarklet_is_offered_and_points_at_this_server` stands as written.

This narrows the CSRF exemption rather than widening it: the representation that arrives from a vendor's origin now writes nothing at all. The docstring's justification is updated to say so.

### JSON body — the programmatic path

Still writes. Accepts the same fields as before plus `description`, `manufacturer`, `manufacturer_part_number`, `acknowledged_duplicate_of` and `attach_to`.

| Outcome | Status | Body |
|---|---|---|
| Written | 201 | `{'success': True, 'purchase': {...}, 'url': '/purchases/<id>/receive'}` — unchanged, so `tests/unit/test_product_csrf.py:176` still asserts 201. |
| Validation failed | 400 | `{'success': False, 'error': '...'}` — unchanged. |
| Decision required | **409** | `{'success': False, 'error': '...', 'assessment': {...}}` |

409 is new. The assessment serializes the dataclass fields directly. A caller that wants the old silent behaviour re-posts with `acknowledged_duplicate_of` and/or `attach_to` filled in from the assessment — which is the point: the decision is explicit or it does not happen.

## `POST /products/capture` — where the write happens

`app/product/routes.py:333`. Accepts everything it accepts today plus:

| Field | Type | Meaning |
|---|---|---|
| `description` | text, ≤255 | The label description (FR-001). Blank falls back to the listing title (FR-003). |
| `manufacturer` | text | Optional (FR-002). |
| `manufacturer_part_number` | text | Optional (FR-002). |
| `acknowledged_duplicate_of` | purchase id | Present only when the operator ticked "record it anyway" on a warning naming that purchase. |
| `attach_to` | `new` or a product id | Present only when the operator answered the recycled-identifier question. |

Handler shape, matching what the route already does for `ValidationError`:

```python
try:
    purchase = service.capture_order(...)
except CaptureDecisionRequired as e:
    return render_template('product/capture.html', ..., form_data=request.form,
                           assessment=e.assessment)          # 200, nothing written
except ValidationError as e:
    flash(e.message, 'error')
    return render_template('product/capture.html', ..., form_data=request.form)
flash('Captured. Confirm the details when it arrives.', 'success')
return redirect(url_for('product.purchase_receive', purchase_id=purchase.id))
```

The route makes no decision of its own — it does not detect duplicates, does not compare manufacturers, and does not choose between attach and create. It forwards form fields and renders what comes back, which is what keeps Principle II intact.

**The unambiguous path is still one submit.** A capture with no duplicate and no identifier match writes on the first POST and redirects, exactly as today. The second round-trip happens only when there is genuinely a question, which is why most of the existing e2e tests need no change.

## `GET|POST /purchases/<id>/receive`

`app/product/routes.py:521`. The POST gains one field:

| Field | Type | Meaning |
|---|---|---|
| `description` | text, ≤255 | Passed straight to `receive_purchase(description=...)`. Blank refuses the submission (FR-024). |

Forwarded unconditionally, since the form always renders it. Validation belongs to the service.

## `product/capture.html`

Additions to the existing form (`app/templates/product/capture.html`):

- `#description` — text input, `maxlength="255"`, pre-filled from `form_data`, or from the matched product's description when an assessment is being re-rendered (FR-005).
- `#manufacturer` and `#manufacturer_part_number` — text inputs, optional. Placed next to each other, since the corroboration rule only fires when both are present, and adjacency is the cheapest way to say so.
- `#duplicate-warning` — rendered when `assessment.has_duplicate`. Names the existing purchase, links to it (a plain `GET`, so choosing it writes nothing), and offers a checkbox `acknowledged_duplicate_of` valued with that purchase id: *"This is a separate order — record it anyway."*
- `#identifier-warning` — rendered when `assessment.has_uncorroborated_match`. Shows the matched product's description and part number, and a radio pair for `attach_to`: the product's id (*"Add this purchase to it"*) and `new` (*"This is a different product"*). **No default is selected**, so a submit that skips the question comes straight back — FR-018 says the capture is not written until they choose.

Everything else on the page — the URL box, the vendor autocomplete, the bookmarklet card and its `#bookmarklet-http-warning` — is unchanged. No new JavaScript: `field-autocomplete.js` stays the only script the page loads.

## `product/receive.html`

- The description moves out of the read-only "What was ordered" block and into the form as `#description`, `maxlength="255"`, pre-filled with `product.description` (FR-022).
- The read-only block keeps showing `purchase.listing_title`, which is the point of having both: the operator compares the vendor's wording against their own with the thing in hand.
- `#already-received` (`app/templates/product/receive.html:52`) currently reads "Submitting again changes nothing." That was already an overstatement — quantity, price and notes are amended on re-submit today — and the description makes it wrong. It is corrected to name what re-submitting does and does not change.

## Not built

- **No link to the vendor's listing on the receive screen.** `purchases.listing_url` would make it one line of template, and no requirement asks for it.
- **No pre-emptive warning on the pre-filled bookmarklet form.** The match could be shown before the first submit, at the cost of a detection call on a page render. The question gets asked on submit instead, which is one code path rather than two saying the same thing.
- **No JSON endpoint for assessments.** The 409 body carries everything a programmatic caller needs.
