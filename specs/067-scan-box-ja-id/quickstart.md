# Quickstart: validating JA IDs in the header scan box

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e   # ~20 min; run detached
```

Expected: the classifier, resolution and route tests for `JA_ID` / `'item'` pass; existing scan
tests pass unchanged; `tests/e2e/test_ja_id_lookup.py` and
`tests/e2e/test_edit_inactive_item_via_search.py` pass against `#global-scan-input`.

## Manual

1. Any page: the header shows one code-entry box (the scan box).
2. Type an existing JA ID, press Enter → that item's edit page.
3. Type it in lowercase → same page.
4. Type a JA ID that does not exist → inventory list with "Item JA… not found."
5. Scan a product barcode / `WIT…` code → same destination as before.

## Static check

```bash
grep -rn "ja-id-lookup\|setupJaIdLookup" app docs   # must return nothing
```

`tests/e2e/test_ja_id_lookup.py` names `#ja-id-lookup` once, to assert it is gone.
