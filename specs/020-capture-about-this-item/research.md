# Phase 0 Research: Capture Reads the "About this item" Bullets

**Feature**: `specs/020-capture-about-this-item` | **Date**: 2026-08-19

Issue #92 says in as many words that its selector claims come from earlier probing rather than
from the listings as they stand, and invites the agent to look at the live pages. That was done:
three listings were inspected in the owner's Chrome on 2026-08-19 — `B01N4OSKWE` and `B0FX4PDW6M`
(the issue's two verification cases) and `B0CKXJLP4B` (the ASIN the e2e fixture stands in for).
Everything in section 1 is what those pages actually contained, not what the issue predicted.

**Two of the issue's premises did not survive the probe.** Both are recorded below with what
replaced them.

---

## 1. What the real markup is

### Decision

The bullets are read from the `li` elements inside `#feature-bullets`, one bullet per `li`.

### What was observed

All three listings carry `#feature-bullets`, wrapped in `#featurebullets_feature_div`, with an
identical child sequence:

```
div#feature-bullets.a-section a-spacing-medium a-spacing-top-small
├── hr.a-divider-normal            [aria-hidden="true"]
├── h2.a-size-base-plus a-text-bold   "About this item"
├── ul.a-unordered-list a-vertical a-spacing-mini
│   └── li.a-spacing-mini  ×5 / ×6 / ×5
│       └── span.a-list-item        the bullet's text
└── div.a-section                   "› See more product details"  (caret span + link)
```

| Listing | Bullets | Hidden `li` | `.a-text-bold` in a bullet | Bullet `li` children |
|---------|---------|-------------|----------------------------|----------------------|
| `B01N4OSKWE` | 5 | 0 | 0 | `span.a-list-item` only |
| `B0FX4PDW6M` | 6 | 0 | 0 | `span.a-list-item` only |
| `B0CKXJLP4B` | 5 | 0 | 0 | `span.a-list-item` only |

`B01N4OSKWE`'s five bullets are exactly the content the issue is about — semicolon-separated
physical facts that appear nowhere else on the page:

```
Country of Manufacture: CHINA; Material: Plastic,Metal; Net Weight: 9g
Package Content: 5pcs x Micro Slide Switch; Main Color: Black, Silver Tone; Mount Hole Size: 2mm/0.08"
Hole Center Distance: 20mm/0.79"; Product Name: Micro Slide Switch; Switch Type: Toggle Switch
Action Type: Latching; Contact Type: DPDT; Terminal Quantity: 6
Main Body Size: 15 x 7 x 7mm/0.59"x0.28"x0.28"(L*W*H); Overall Size: 23 x 16 x 7mm/0.91"x0.63"x0.28(L*W*H)
```

### Correction 1 — "See more product details" is not a hidden `li`

Issue #92 warns that `#feature-bullets li` "includes a hidden 'See more product details' item on
some listings". On all three listings today it is **a visible sibling `div.a-section` after the
`<ul>`**, not a list item and not hidden. `li`-scoped reading therefore excludes it structurally,
with no visibility test involved.

The `h2` heading is the same kind of trap and the issue does not mention it: `#feature-bullets`'s
own `textContent` begins `"About this item Built-in ESP32-S3 …"`. Anything that reads the
*container's* text captures the heading as though it were product content. Reading `li` excludes
that too.

The one element in `#feature-bullets` carrying a hidden marker on any of the three listings is the
`<hr aria-hidden="true">` divider, which contributes no text.

### Correction 2 — a visibility test is not implementable here anyway

This is the finding that decides the design, and it is not a preference.

`canonicalDocument()` (`app/static/js/capture-agent.js:618`) fetches `/dp/<ASIN>` and parses it with
`new DOMParser().parseFromString(html, 'text/html')`. That document is **detached**: it has no
layout and no stylesheets applied. `offsetHeight` is `0` for every element in it, and
`getComputedStyle(...).display` reports the UA default rather than what Amazon's CSS would produce.
The probe above could only classify visibility because it ran against the *live rendered* page — the
capture agent never has that document on its primary path.

So spec FR-005 ("a bullet the listing does not display MUST NOT contribute a line") cannot be met by
asking whether an element is visible. It can only be met structurally.

### Rationale

`li`-scoped reading answers both corrections at once and costs one `querySelectorAll`. Every
non-bullet element observed in the container — the divider, the heading, the "See more" link — is
outside the `<ul>`, so it is already excluded.

### Alternatives considered

- **Add `#feature-bullets` to `SPECIFICATION_CONTAINERS`.** Rejected, as the issue anticipates:
  `rowsFrom()`'s bullet shape requires a `.a-text-bold` name span, and the probe found zero across
  all three listings, so this yields nothing at all.
- **Read the container's whole text as prose.** Rejected: it captures the `About this item`
  heading and the `See more product details` link as product content, and it loses the
  one-bullet-per-line structure the row is supposed to have.
- **Filter by computed visibility.** Rejected as not implementable — see Correction 2.
- **Filter by hidden-marking classes (`aok-hidden`, `a-hidden`, `[hidden]`, `[aria-hidden]`).**
  Rejected as speculative generality (Principle I). No bullet on any probed listing carries one.
  Should the shape appear later, the guard is a one-line predicate in a function that already
  exists; adding it now would be machinery for a case with no observed instance.

---

## 2. Where the bullets go

### Decision

One specification row, name `About this item`, value the bullets joined with `\n`, emitted **first**
in `specificationsFrom()`'s output — before the rows read out of the detail containers.

### Rationale

- **A row, not description text**: settled by the spec's Assumptions, following the issue's own
  preference. A named row is findable, editable and deletable on its own; text appended to an A+
  description is none of those.
- **First**, because it matches the page's own order (About this item sits above the detail tables)
  and because it decides FR-009's collision case correctly. `specificationsFrom()` folds with
  first-occurrence-wins, so emitting the bullets first means a detail-table row that happened to be
  named `About this item` loses to the bullets — which is the outcome this feature wants.
- **`\n` between bullets, not `\n\n`.** These are list items, not paragraphs. `proseFrom()` already
  emits `\n\n` around a `LI`, so joining already-trimmed bullet strings with a single `\n` is what
  gives one line per bullet.

### Alternatives considered

- **Appended last.** Works, and loses the collision case: a stray detail-table `About this item`
  row would win over the actual bullets.
- **One row per bullet** (`About this item 1`, `2`, …). Rejected: five to six near-duplicate row
  names is clutter, they sort meaninglessly, and the issue asks for one row.

---

## 3. Line structure is already solved

### Decision

Nothing new is built for FR-013. It is a verification item, not an implementation item.

### Rationale

Issue #91 landed all three halves of it, and each was confirmed in the tree:

| Concern | Where it already works |
|---------|------------------------|
| Reading text with line structure kept | `proseFrom()` / `proseOf()`, `capture-agent.js:95` |
| Displaying a multi-line value | `app/templates/product/detail.html:106`, `white-space: pre-wrap` |
| **Editing** a multi-line value | `app/templates/product/_form_fields.html:51-67` — a value containing `\n` renders as a `<textarea>` rather than an `<input>`, precisely because the HTML value sanitization algorithm strips CR/LF and an unrelated save would otherwise flatten the row |

The spec flagged the edit path as "worth confirming rather than assuming". It is confirmed: the
`{% if '\n' in value %}` branch exists and carries a comment explaining why. No work is needed.

---

## 4. What an empty bullets row would actually do

### Decision

Emit no row when there is no readable bullet (FR-008), and correct the spec's stated consequence.

### Rationale

The spec says an empty-valued row "would cost the whole capture" because
`_validate_specifications` refuses a name with no value. That is not what happens.
`ListingCapture.from_json` runs first, and `_payload_specifications`
(`app/models.py:783`) **silently drops** any entry whose name or value is empty. Such a row would
never reach validation.

The requirement is unchanged — do not emit it — but the failure mode it guards against is a
silently-absent row, not a failed capture. Written down here so nobody later "hardens" a path that
was never exposed.

---

## 5. What this change costs the existing tests

### Decision

Three existing e2e assertions in `tests/e2e/test_product_page_capture.py` move, and they move
because the feature works. None of them is a regression.

| Line | Assertion | Why it moves |
|------|-----------|--------------|
| ~508 | `[row["name"] for row in payload["specifications"]] == ["Material", "Item Length", "Customer Reviews", "Finish", "Country of Origin"]` | An exact, ordered list. Gains `"About this item"` at the front once the A+ fixture carries bullets. |
| ~456 | `before = …count()` then `to_have_count(before)` after re-capture | Self-relative; unaffected in principle, and it is exactly the assertion that proves US2. |
| ~391 | `#summary-specifications` contains "row" | The count is +1; the assertion is on the word, so it holds. |

The line-508 assertion is the one worth keeping rather than loosening: it was written for #91 as a
"nothing else moved" guard, and an ordered list is what makes FR-010's stable position testable.

### Rationale

The fixtures are hand-written, so whether these move at all is a choice about which fixture gains a
bullet list. Both should: `amazon_listing.html` (plain description) and `amazon_listing_aplus.html`
(rich description) are the two paths, and the bullets are independent of which description form a
listing uses.

---

## 6. The screenshot gate

### Decision

`nox -s screenshots_verify` is run and the result reported. Screenshots are regenerated only if it
finds them stale.

### Rationale

The constitution's workflow section requires regenerating documentation screenshots for changes to
`app/static/js/**`, and `capture-agent.js` is under that path. But `capture-agent.js` is never
loaded by any of this application's own templates — it is injected into a *vendor's* page by the
bookmarklet — so no screenshot of this application can depend on it. Running the verify session is
the honest way to establish that rather than assert it.

If a diff appears it will be screenshot churn unrelated to this change; that is measured before
anything is committed, not assumed either way.

---

## The risk that is not mitigated

Unchanged from the capture feature's original research, and worth restating because this feature
adds a fourth selector to the set: Amazon's markup is not a contract. `#feature-bullets` can be
renamed tomorrow and the e2e fixture — hand-written, served locally — cannot notice. What bounds
the damage is FR-011: the reader is one independent, optional step, and a selector that stops
matching costs the bullets row and nothing else.

The probe above narrows this only in the sense that the fixture now reproduces markup that was real
on 2026-08-19. It does not make the fixture a canary.
