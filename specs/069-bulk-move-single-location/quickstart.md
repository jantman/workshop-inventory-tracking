# Quickstart: validating bulk scan-to-one-location

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" ~/GIT/workshop-inventory-tracking/venv/bin/nox -s e2e   # detached; ~20 min
```

(From a worktree, use the main checkout's venv; see CLAUDE.md for the timeout rules.)
`tests/e2e/test_bulk_scan_group.py` covers each acceptance scenario; the existing move tests
cover FR-006 and FR-015.

## Manual

1. Products → Move Products. Scan three product codes. The *Awaiting a destination* card
   lists all three with their current locations; the queue is empty.
2. Scan `Shelf 2`. All three appear in the queue for `Shelf 2`; the card disappears.
3. Scan `Bin 4`. All three rows show sub-location `Bin 4`.
4. `>>DONE<<`, Validate & Preview, Execute Moves. Each product's detail page shows
   `Shelf 2` / `Bin 4`.
5. Repeat on Move Items with JA IDs and `M1-A`.
6. Scan A, A → second refused. Scan B, click Remove on B → only A waits. Remove A → page
   back to *Ready*.
