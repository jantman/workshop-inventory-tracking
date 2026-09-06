# Contract: `python manage.py orders receive-outstanding`

**Feature**: 042-bulk-receive-outstanding

The operator-facing surface. It lives in the existing `orders` group in `manage.py`, beside
`amazon-urls`, because it belongs to the same one-time backfill job.

## Synopsis

```
python manage.py orders receive-outstanding --before YYYY-MM-DD [--vendor NAME] [--dry-run]
```

## Options

| Option | Required | Type | Meaning |
|---|---|---|---|
| `--before` | **yes** | `YYYY-MM-DD` | Only purchases ordered **strictly before** this date are selected. Required: the cutoff is the safety rail, and an unbounded sweep is not offered (FR-004). |
| `--vendor` | no | text | Restrict to one vendor. Matched case-insensitively against the stored vendor name, with surrounding whitespace stripped (FR-003). Omitted means every vendor (FR-005). |
| `--dry-run` | no | flag | Print the listing and stop. Writes nothing, prompts for nothing (FR-015). |

An unparseable `--before`, or a missing one, is refused by Click before the command body runs,
naming the offending value (FR-019). Nothing is read from the database.

## Behaviour

1. Select every purchase that is outstanding, carries an order date, is ordered before the
   cutoff, and matches the vendor if one was given.
2. Print the listing — one line per selected purchase, then a summary (see below).
3. **If nothing was selected**: say so, exit 0, prompt for nothing, write nothing (FR-017).
4. **If `--dry-run`**: exit 0. Nothing has been written (FR-015).
5. **Otherwise**: ask for confirmation. Declining prints that nothing was written and exits 0
   (FR-016).
6. Confirming applies the sweep as one unit (FR-020) and reports how many purchases were
   received and how many were skipped for having no order date (FR-018).

## Output

Listing, one line per purchase — vendor, order number, order date, product, quantity (FR-014):

```text
Would receive 3 outstanding purchase(s), each dated from its own order date:

  #412  DigiKey        62301442  2023-04-11  10  Molex 22-23-2021 header, 2 pos
  #418  DigiKey        62301442  2023-04-11   1  Phoenix 1729128 terminal block
  #503  DigiKey        63887190  2024-11-02  25  Vishay CRCW0805 10k resistor

1 outstanding purchase(s) skipped: no order date, so there is no date to receive them at.
```

An order number is shown as `-` for a hand-recorded purchase, which belongs to no order.

The verb changes with the mode: `Would receive` under `--dry-run`, `About to receive` before the
prompt, `Received N outstanding purchase(s).` after the write.

Nothing selected:

```text
No outstanding purchases match. Nothing to do.
```

## Exit status

| Status | When |
|---|---|
| 0 | The sweep ran, or was declined, or matched nothing, or was a dry run. |
| non-zero | Click refused an argument, or the sweep failed. A failed sweep has written nothing. |

## What it deliberately does not offer

- **No per-line or per-order selection.** The cutoff and the dry run are the controls. Per-line
  handling is what the per-purchase receive screen is for, and not going line by line is the
  entire point of this command.
- **No un-receive.**
- **No date override.** The receipt date is always the purchase's own order date (FR-008). A
  sweep spans years by construction, so a single supplied date would be wrong for all but one
  order in it.
- **No amendment of quantity, price, notes or description.**
