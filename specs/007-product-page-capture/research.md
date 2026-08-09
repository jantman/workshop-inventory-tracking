# Phase 0 Research: Product Page Capture

Every decision here is one the plan depends on. Where issue #57 already did the probing, this document records what it found and what follows from it rather than repeating the evidence.

---

## How the payload gets from the vendor's page to this application

**Decision**: The extractor builds a form with hidden inputs — including one carrying the whole extraction as JSON — and submits it into a new tab at `POST /api/capture`, exactly as the current four-field bookmarklet already does.

**Rationale**: This is a navigation, not a request the page makes. Three properties follow, and all three are load-bearing:

1. **CORS does not apply.** There is no preflight to be refused and no response header for the vendor to influence. A `fetch` from `amazon.com` to `https://192.168.0.24/api/capture` would need `Access-Control-Allow-Origin`, which means adding CORS configuration to this application for one endpoint.
2. **It is the path already proven to work.** Issue #54 established that Amazon's `upgrade-insecure-requests` rewrites the form action to `https`, and that once the app is behind TLS the navigation lands. That is confirmed working against a real listing. Reusing it means the transport carries zero new risk.
3. **`/api/capture` is already CSRF-exempt**, and already renders the pre-filled form for a form body rather than writing. The extractor adds one field to a POST that already happens. The exemption count stays at one.

The payload is roughly 40 KB for a rich listing — a dozen image addresses at ~150 characters each, twenty-five name/value rows, and a description that reached 28,767 characters on the largest of the six sampled. It is not capped (see [the description ceiling](#the-description-ceiling)), so a pathological listing could make it larger; `MAX_CONTENT_LENGTH` is unset, so Flask imposes no limit of its own, and a 40 KB form body is unremarkable.

**Alternatives considered**:

- **`fetch` with CORS.** Needs response headers this application does not emit, for the sole benefit of not opening a tab — but a tab must open anyway, because the operator has to confirm.
- **Clipboard hand-off** (bookmarklet copies JSON, operator pastes into the form). Works against any CSP, including a hypothetical `form-action` directive. Costs a paste every time and cannot carry 40 KB comfortably. Recorded in issue #54 as the fallback if a vendor ever blocks the form outright; still the fallback, still not the design.
- **A dedicated new endpoint** for the rich payload. `/api/capture` already renders the pre-filled form for a form body; a second endpoint would duplicate that and add a second thing to keep exempt.

---

## Where the extraction code runs

**Decision**: A script served by this application at `app/static/js/capture-agent.js`, loaded into the vendor's page by a bookmarklet that is now only a loader.

**Rationale**: Argued in [plan.md](./plan.md#why-the-extractor-is-a-served-script-and-not-an-extension). In short: the CSP prediction that justified an extension was tested and found false, and what is left is a second codebase versus an ordinary file in this one.

The loader bakes in two absolute URLs rendered with `url_for(..., _external=True)` — the script and the endpoint — and cache-busts the script:

```
javascript:(function(){var s=document.createElement('script');
s.src='https://HOST/static/js/capture-agent.js?v='+Date.now();
s.dataset.endpoint='https://HOST/api/capture';
document.body.appendChild(s);})();
```

The agent reads its endpoint from `document.currentScript.dataset.endpoint`, which is populated for dynamically inserted classic scripts. The `Date.now()` cache-buster is what makes FR-024 true: the operator never re-drags the bookmarklet, and never runs a stale agent. It costs one uncached ~10 KB fetch per capture, which is not a cost worth a version-stamping mechanism.

**Alternatives considered**:

- **Chrome extension (MV3)**. Highest ceiling, immune to a future `script-src`. A manifest, a build, an install and an update path for one file, maintained in spare time. Retained as the fallback.
- **The whole extractor inline in the `javascript:` string.** What the extension argument was trying to avoid; a few hundred lines of unreviewable, untestable, un-updatable URL.
- **Stamping the app version instead of `Date.now()`.** Correct caching, and wrong the moment the file is edited without a version bump — which is every edit during development.

---

## Who owns the captured images

**Decision**: The product.

**Rationale**: The specification decided this before the plan did, and it is worth being explicit that the deferral resolved rather than being ruled on. FR-018 requires an image to be stored "at most once against a given owner", and US5 scenarios 5–7 describe a re-capture checking what "the product already holds". Under purchase ownership every purchase is a new owner, so the dedupe could never fire and the second buy of a consumable would store the entire gallery a second time. The requirement is only coherent with product ownership.

The rest of the trade-off, written out because issue #57 asked for it:

| | Product (chosen) | Purchase |
|---|---|---|
| **What the images describe** | The thing. A spec sheet is a fact about the part. | The transaction. A receipt is a fact about the order. |
| **Dedupe across repeat buys** | Works — one stable owner. | Impossible — every purchase is a fresh owner. |
| **Consistency with the text** | `ProductSpecification` is product-only, so the captured rows and description go on the product regardless. Images follow. | Splits one capture across two owners. |
| **Where FR-012's cap applies** | Per product, as the spec words it. | Per purchase, so a busy product has no cap at all. |
| **Presentation** | The product page's attachments card, which FR-013 makes a grid. | One cell of the purchase-history table — untenable for a dozen images. |
| **What it costs** | A listing that changes between buys mixes old and new images on one product, distinguishable only by upload date. | — |

That last row is the genuine cost of the choice, and it is accepted: the alternative is a product whose images are scattered across its purchases, and the operator's question is almost always "what is this thing" rather than "what did that order look like".

Purchase-owned attachments are **not** removed. They remain the right home for a receipt or an order confirmation, which is what feature 001 built them for.

---

## Why image retrieval is synchronous

**Decision**: The confirmation POST fetches and stores every image before it redirects. No queue, no thread, no background job.

**Rationale**: Principle I prohibits background job machinery without a measured problem, and there is no measurement — this feature has never run. The predicted cost is 8–15 seconds for a fourteen-image gallery, dominated by Pillow producing a thumbnail and a medium rendition per image, not by the network (issue #57 measured ~350 KB per image against a CDN that answered a cold cache MISS in one request). Fifteen seconds, once, at the moment the operator has just decided to spend money, is a poor experience and an acceptable one. A queue is a durable store, a worker, a status surface and a failure mode where the operator does not know whether their images arrived.

The prediction is written into [plan.md](./plan.md#technical-context) precisely so that "this feels slow" can later be a comparison against a number rather than an impression — which is what Principle I means by a measurement.

**Alternatives considered**:

- **A background thread**, results appearing later. Removes the wait and introduces "did it work?" as a permanent question with no page to answer it.
- **Fetch in the browser and POST the bytes.** Issue #57 verified cross-origin `fetch` → `createImageBitmap` succeeds, so the CDN's CORS is permissive enough. It moves ~5 MB through the form POST instead of ~40 KB and makes the payload no longer human-readable. Held in reserve as the answer if the CDN ever stops serving the application directly — same extraction, bigger payload, no redesign.
- **Lazy retrieval on first view.** A product page that fetches from Amazon when opened, forever. Worse in every dimension.

---

## Getting the original file rather than the gallery rendition

**Decision**: Strip the transform token from the image address before fetching.

**Rationale**: Issue #57 measured this. The addresses in the page data carry a token such as `._AC_SL1500_.`, and that is not the original: 1446×1500 with the token, 1601×1601 without, 345,670 bytes against 358,055. FR-004 requires the original, so the token comes off — the segment matching `\._[^./]*_\.` immediately before the extension is replaced with `.`.

This is also the one place where being wrong is cheap and detectable: if a stripped address 404s, the fetcher records that image as failed under FR-020 and the capture still succeeds. It does not fall back to the tokened address, because a silent fallback would satisfy FR-004 only by accident and nobody would know which images were originals.

---

## Reading the canonical listing rather than the open tab

**Decision**: Where the address yields an item identifier, the agent performs a same-origin `fetch` of `/dp/<ASIN>`, parses the response with `DOMParser`, and extracts from that document. Any failure falls back to the live `document`.

**Rationale**: Issue #57 found the open tab silently acquiring `?th=1` during testing — a variant selection that changes what the page shows. The same-origin fetch carries the session and returns the real HTML, so the capture is of the item the identifier names rather than of whatever state the tab drifted into. That is FR-002.

The fallback is not defensive decoration: it is FR-007. If the fetch fails, the parse fails, or there is no identifier in the address at all, the agent extracts from what is on screen, and if that yields nothing it posts the URL and title and the capture behaves exactly as it does today.

---

## Merging specifications instead of replacing them

**Decision**: A new `CatalogService.merge_specifications(product_id, entries)`. `update_product`'s replace-on-write semantics are untouched.

**Rationale**: `update_product` clears and re-extends because "the form always posts the complete set and no row has an identity to diff against" (`app/catalog_service.py:589`). That is correct for the form and catastrophic for a capture: a capture landing on an existing product would delete every specification the operator had typed, which FR-011 forbids in as many words.

The merge folds names with `str.lower()` **in Python**, never in SQL, for the reason already established in this codebase twice: the deployed collation is `utf8mb4_uca1400_ai_ci`, which folds accents as well as case, while SQLite collates `BINARY`. A name comparison performed in SQL would call `Volt` and `Vôlt` the same row on MariaDB and different rows under the unit suite — a rule that means two things on two backends. `ProductSpecification`'s own docstring already says `_validate_specifications` is the authority and it compares in Python; the merge joins it.

The rule itself is FR-010's: a captured name the product already carries is dropped entirely, value and all. Not merged, not appended, not suffixed. The operator's value wins because the operator looked at the thing.

**Alternatives considered**:

- **Build the merged list in `capture_order` and call `update_product`.** Reuses validation, and rewrites every row on every capture, churning `display_order` and making an unrelated concurrent edit lossy. It also hides a merge inside a method documented as a replace.
- **A unique constraint on `(product_id, name)` to enforce it.** Rejected for this feature for the reason `ProductSpecification`'s docstring already gives: the constraint would mean different things on the two backends, and the invariant is cosmetic rather than integrity.

---

## Dedupe by content, not by address

**Decision**: `photos.sha256_hash` is populated on every attachment upload from this point on, and a captured image whose hash already appears among the product's attachments is skipped.

**Rationale**: The operator asked for this specifically, and it is right for a reason beyond stability. Amazon serves the same source file under several transform tokens, so two addresses routinely name identical bytes; address-keyed dedupe would store the same picture twice and believe it had deduped. Hashing also collapses FR-018's two clauses — the same image named twice within one capture, and the same image seen again in a later capture — into one mechanism, because by the time the second copy is considered the first is already stored.

The column exists. `8213852b0b94` created it, indexed it, and its own backfill left the note `sha256_hash=None,  # Will be populated on future uploads`; `app/photo_service.py:114` repeats the note as `# Optional: can add hash calculation later`. This is that later.

A cheap address-level pass runs first, purely so the same URL is not fetched twice in one capture. It is an optimization of the network, not the correctness rule.

**Alternatives considered**:

- **Perceptual hashing**, so a re-encode is recognized. A new dependency, a threshold to tune, and false positives that silently discard a genuinely different image. A byte hash's failure mode is a duplicate the operator deletes; a perceptual hash's failure mode is a missing image nobody knows about.
- **Backfilling hashes for existing photos.** See [data-model.md](./data-model.md#existing-photos-keep-a-null-hash).

---

## The description ceiling

**Decision**: Widen `product_specifications.value` from `TEXT` to `MEDIUMTEXT` on revision `b1a0c0d10009`. The agent imposes no cap, and FR-006 holds unconditionally.

**Rationale**: `TEXT` holds 65,535 **bytes** — not characters, so multi-byte text hits the wall sooner than its length suggests — and MariaDB in strict mode raises on overflow. Left alone, that would refuse an over-long capture at the confirmation step, on a page the operator cannot fix, after they have already lost the listing state.

There were two ways out and the first draft of this plan took the wrong one. Capping the agent at 60,000 characters avoids the migration, and the largest description across the six sampled listings was 28,767 characters, so nothing observed would have been touched. But it buys that by writing a permanent asterisk onto a requirement: FR-006 says a captured description is kept in full, and a cap means it is kept in full *except when it is not*, forever, with a marker where the rest used to be. The exception would outlive everyone's memory of why it existed.

Widening removes the exception instead of documenting it. `MEDIUMTEXT` holds 16,777,215 bytes — 580× the largest description ever seen on these listings — and the cost is one DDL migration with no data movement, because every existing value already fits inside the new type. That is about as cheap as a migration gets, and it is bounded work done once, against an asterisk that would be carried indefinitely.

**The downgrade is the interesting half.** Narrowing back to `TEXT` is exactly the operation that can lose data, so it refuses instead:

```sql
SELECT id, product_id FROM product_specifications WHERE LENGTH(value) > 65535
```

If that returns anything, `downgrade` raises and names the rows rather than performing the `MODIFY`. `LENGTH` is deliberate — it counts bytes, which is what the type limits, where `CHAR_LENGTH` counts characters and would under-report multi-byte text. Principle I never licenses losing data, and a downgrade that silently truncates a specification is exactly that.

That guard turns out to protect something older, too. `b1a0c0d10007`'s downgrade folds every specification row back into the `products.specifications TEXT` column it replaced. Alembic runs downgrades newest-first, so `b1a0c0d10009` refuses before `b1a0c0d10007` can meet a value that cannot fit — the new guard closes a hole in a migration written before this feature existed. (It does not close all of it: `b1a0c0d10007` concatenates *all* of a product's rows into one `TEXT`, so a product with many large rows could still overflow. That is pre-existing, unchanged by this feature, and not this feature's to fix.)

**Alternatives considered**:

- **Cap the agent at 60,000 characters** and mark the truncation. What this plan said before the trade-off was put to the operator. Cheaper today, permanently qualified.
- **`LONGTEXT`.** 4 GB for a product description. The same migration cost for headroom that means nothing.
- **Silent truncation.** Same data loss as a cap, no evidence it happened.
- **No cap and no migration.** A capture that fails at the last step, having already created the product and the purchase, leaving the operator to work out which half landed.

---

## What we are not defending against

**Decision**: No URL allow-list, no host validation, no SSRF mitigation, no content sniffing beyond the MIME allow-list that already exists.

**Rationale**: This deserves stating plainly because "the server fetches a URL from a web page" is exactly the shape that normally triggers a defensive checklist. The constitution's threat model rules it out: one trusted operator, LAN-only, no anonymous attackers, and "validation serves correctness, not defense". The addresses come from a page the operator is looking at, submitted by the operator, on a machine only the operator can reach. There is no adversary in this system to build a wall against, and Principle I prohibits building one anyway.

What the fetcher does have is bounded for correctness, not for defence, and the bounds are the ones already in the codebase:

- a fixed per-request timeout, so one unresponsive address cannot hold the POST open indefinitely;
- the existing 20 MB per-file limit from `PhotoService.MAX_FILE_SIZE`;
- the existing MIME allow-list (`image/jpeg`, `image/png`, `image/webp`, `application/pdf`), enforced by a `CheckConstraint` on `photos.content_type` as well as in the service;
- the per-product attachment cap, now 100.

Each of those exists because bad data breaks the inventory, which is the constitution's stated reason to validate.

---

## The risk that is not mitigated

The extractor reads Amazon's markup, and Amazon's markup is not a contract. Today's capture deliberately reads only the URL for exactly this reason — `_asin_from_url`'s docstring says so — and this feature knowingly gives that up, because the requirement cannot be met from a URL.

Three things bound the damage, and none of them prevent it:

- **FR-007 makes failure graceful.** Every extraction step is independent and optional. A changed gallery structure loses the images; it does not lose the capture, the price, or the specifications.
- **The extractor is one file in this repository.** Fixing it is an edit and a reload, not a release.
- **The e2e coverage is a snapshot**, fulfilled through `page.route`, which means it verifies that the extractor reads *that page* correctly. It cannot fail when Amazon changes. Nothing in this design can. The honest statement is that the first signal will be a capture that comes back thin, and the operator will notice because the confirmation page tells them what it found before they commit it — which is FR-017 doing a second job.

---

## Test strategy for the two things that cannot be tested normally

**The extractor.** No JavaScript test runner exists in this project and none is added — that is a dependency, a configuration and a second suite for one file. Instead, `tests/e2e/fixtures/amazon_listing.html` is a snapshot with the structures the six sampled listings exhibited (a gallery data block naming more images than there are thumbnails, both description forms, and several product-information containers), and Playwright's `page.route` fulfils a fake listing address with it. `page.route` is already used in this suite (`tests/e2e/test_label_printing.py:283`), so the mechanism is not new here.

**The image fetch.** The unit suite blocks the network, which is a feature: any unmocked `requests.get` fails loudly. The fetcher's branches — success, timeout, non-200, wrong MIME, oversize, duplicate hash, cap reached — are unit tests with `requests.get` patched. End to end, a stdlib `http.server` thread serves `tests/e2e/fixtures/images/` (six real JPEGs already in the repository) and the payload's addresses point at it, so the application performs a real HTTP fetch of real bytes from an origin the test controls.

Neither substitute proves the feature works against Amazon. [quickstart.md](./quickstart.md#what-no-suite-can-check) says which two checks have to be done by hand, and against what.
