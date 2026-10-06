# Quickstart: validating product moves

Prerequisites: the repository venv, and nox on PATH with Python 3.13. See the project
memory and `CLAUDE.md` for setup.

## Automated

```bash
nox -s tests                     # unit: service, endpoints, hand-off, batch_move helpers
nox -s e2e                       # run detached; ~20 min. Includes tests/e2e/test_product_move.py
                                 # and every existing test_move_*.py / test_bulk_move_handoff.py
```

Expected: both pass. The item Move e2e files keep their assertions (SC-004).

## Manual (dev server)

1. Create two products: A with no location, and B at `M2` / `Bin 4`. Note their `WIT`
   codes from the detail pages.
2. Open **Products → Move Products** (`/products/move`).
3. Scan A's code, then `M1-A`, then `Drawer 3`. The queue shows A: current **None / None**,
   new **M1-A / Drawer 3**.
4. Scan B's code (typed in lower case is fine), then `T-3`, then `>>DONE<<`. The queue
   shows B: current **M2 / Bin 4**, new **T-3 / Cleared**.
5. Click **Validate & Preview**. Both entries show `validated`, and current locations are
   still correct, not "Unknown".
6. Click **Execute Moves** and confirm. "Successfully moved 2 items!" appears, and the
   detail pages show the new locations.
7. Refusals:
   - a location scanned first is refused;
   - `JA000001` is refused with a pointer to Move Items;
   - scanning A twice is refused as a duplicate;
   - a made-up `WIT` code is queued, then validated as `not_found`, and Execute stays
     disabled.
8. On A's detail page, click **Move**. The page opens with A awaiting a destination. Scan
   `M5`; it is queued.
9. On `/inventory/move`, repeat the existing item flow. It behaves as before, and after
   validation the current location is kept rather than replaced by "Unknown".
