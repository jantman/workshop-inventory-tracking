# Quickstart: Say When the Image Count Was Swept

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
# e2e takes ~17 minutes; run detached
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- -k "swept or gallery or listing_summary"
```

Expected:

- `test_a_gallery_it_cannot_parse_is_swept_loudly_not_silently` — the confirmation page's
  `#summary-images .images-swept` is visible **and** the console warning is still emitted.
- A normal capture's `#summary-images` has no `.images-swept`.
- The order test with one unreadable-gallery listing shows `.images-swept` on that line's
  summary only.

## Manual (real Amazon)

1. Reload the extension from `extension/`.
2. Capture an Amazon listing. If its gallery parses (the ordinary case), the summary reads
   "N images" with no caveat.
3. To see the swept path without a broken listing, capture the e2e fixture
   `tests/e2e/fixtures/amazon_listing_unreadable_gallery.html` as the e2e suite does; the
   summary reads "N images — the listing's own gallery data could not be read, so this count
   is a guess".
4. With an extension loaded from before this change, a capture still lands with no caveat.
