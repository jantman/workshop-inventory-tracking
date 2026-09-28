# Quickstart: Capture McMaster Variant Product Pages

## Automated

```bash
nox -s tests -- tests/unit/test_mcmaster_routes.py
nox -s tests          # full unit suite
nox -s e2e            # detached; ~20 min warm (see CLAUDE.md)
```

Expected: all pass. The new variant-address tests fail on `main`: the unit test gets `''`,
the extension test gets "this is not a page it can read".

## Manual (the reported case)

1. Reload the unpacked extension so it picks up the new `capture-agent.js`.
2. Open `https://www.mcmaster.com/3408A521/`, choose "Threadlocker" under Locking Type.
   The address becomes `/3408A521-3408A523/` and the 2-D PDF option appears.
3. Capture the page with the extension.
4. **Expect**: no "not a page it can read" message; the confirmation page opens with
   part number `3408A521` (the number the page shows), vendor McMaster-Carr, the title,
   price and specifications, and a PDF among the images.
5. On the application's own capture page, paste `https://www.mcmaster.com/3408A521-3408A523/`.
   **Expect**: vendor McMaster-Carr and part number `3408A521`.
