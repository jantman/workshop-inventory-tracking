# Contract: the bullets reader

**Unit**: a new function in `app/static/js/capture-agent.js`, alongside `specificationsFrom()`.
Internal to one file — recorded here because it is the whole of the feature's new logic and its
obligations are easier to test than to infer.

## Signature

```
bulletsRow(doc) -> { name: 'About this item', value: '<line>\n<line>…' } | null
```

`doc` is whatever `canonicalDocument()` yielded: **usually a detached `DOMParser` document with no
layout and no stylesheets**, and on the fallback path the live `document`. The function must behave
identically against both. See research.md §1, Correction 2 — this is why no visibility test is
available.

## Obligations

| # | Obligation | Spec |
|---|------------|------|
| R-1 | Reads only `li` elements inside the bullet container. The `About this item` heading and the `See more product details` link are outside the `<ul>` and are excluded structurally, not by filtering. | FR-005 |
| R-2 | Each surviving `li` contributes exactly one line, using the file's existing prose reader so stylesheets and scripts cannot appear as text. | FR-003, FR-007 |
| R-3 | An `li` whose prose is empty contributes no line and no blank line. | FR-006 |
| R-4 | Lines are joined with a single `\n`, in document order, and the result is trimmed. | FR-003, FR-004 |
| R-5 | Returns `null` — never a row with an empty value — when the container is absent or no `li` yields text. | FR-008 |
| R-6 | **Never throws, for any input.** A missing container, a container with no list, a document that is not a listing at all: each yields `null`. | FR-011 |
| R-7 | Does not mutate `doc`. The fallback path hands it the page the operator is looking at. | existing FR-003 of feature 007 |

## Call site

`specificationsFrom(doc)` calls it once and, when it returns a row, seeds both the output array and
the `seen` fold with it **before** the container loop. Seeding the fold is what makes C-5 and FR-009
true; appending without seeding would let a detail table produce a second row of the same name.
