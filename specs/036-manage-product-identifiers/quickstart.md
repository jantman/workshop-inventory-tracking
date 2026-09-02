# Quickstart: Manage Product Identifiers After Creation

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-09-02

How to run and validate this feature. Implementation belongs in `tasks.md`; this is the
run-and-check guide.

---

## Prerequisites

- The repository virtualenv at `venv/`. Invoke its binaries **by path** — `venv/bin/nox`,
  `venv/bin/python` — rather than activating it.
- `nox` needs Python 3.13 on `PATH`:

  ```bash
  export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
  ```

- Docker, for the MariaDB container the e2e session brings up.
- A local `.env` (untracked) if you intend to run the app by hand.

---

## Automated validation

### Unit tests — fast, run these constantly

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

Expected: green, in under a second of test time. The new `tests/unit/test_product_identifiers.py`
pins the HTTP contract in [contracts/identifiers.md](./contracts/identifiers.md) — every status
code and both JSON shapes.

### End-to-end tests — the operator flows

**This session outlasts a 10-minute agent bash timeout.** Run it detached and poll; a
foreground run reports a false timeout on a passing suite.

```bash
nohup env PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" \
  venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
# then poll /tmp/e2e.log
```

Expected: about 14 minutes warm; budget 20 if the environment is cold (image pull, Playwright
browser install). To iterate on just this feature's file while developing, run that file alone
rather than the suite.

Watch specifically that `test_touch_readiness.py` still passes — the new form and per-row
buttons land in the narrow right-hand column, and that file asserts the page does not scroll
sideways at 390px.

### Screenshots — required by the constitution

This feature edits `app/templates/**` and adds to `app/static/js/**`, which trips the
screenshot gate.

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
git status --short docs/images/screenshots/
```

`user-manual/product_detail.png` is a capture of this very card, so it genuinely changes and is
committed. Every other capture churns byte-for-byte on each run even against unchanged code --
measured by running the session twice and diffing -- so those are reverted rather than committed,
as feature 032 did. `nox -s e2e` must leave the working
tree clean; if it does not, a screenshot test leaked into the e2e selection.

---

## By-hand validation

These are the checks no automated test covers, and the second one closes an item carried over
from the #80 verification pass.

### 1. The card, on a real page

Run the app and open any product:

```bash
venv/bin/flask run --debug
```

- The Identifiers card shows an **Add identifier** control; pressing it reveals type, value,
  vendor and the override checkbox.
- The type list offers exactly `MPN`, `GTIN`, `VENDOR`, `DISTRIBUTOR` — and **not** `INTERNAL`.
- Each listed identifier has a remove control. The internal code does not.
- Add a `VENDOR` identifier with no vendor: refused, with the reason, and what you typed is
  still in the form.
- Add a barcode with a broken check digit: refused. Tick the override and retry: stored, and the
  row shows "Validation overridden".
- Add a value that belongs to another product: refused, naming that product, and the name is a
  link you can follow.

### 2. SC-002 — the fourth GS1 verification vector

This is the concrete outcome the issue was filed for, and it closes the verification item
inherited from #80 §3. Pick any of the three products whose valid UPC is recorded only as a
specification row:

| Product | Description | UPC on the spec row |
|---|---|---|
| 4 | Dorhea ESP32-S3-DevKit C N16R8 | `687117723741` |
| 6 | uxcell 3 Position 6P DPDT switch | `604267063299` |
| 8 | Gigabit USB-C PoE+ Splitter | `746131403210` |

1. Open the product and add that UPC as a `GTIN` from the Identifiers card.
2. Confirm the card now shows it as the normalized 14-digit key — `687117723741` is stored as
   `00687117723741`.
3. Put the code into the scan box in the header and press Enter.
4. It lands on that product's detail page.

**A caveat recorded in #80 §6**: all three are Amazon-sourced and their manufacturers' barcodes
are covered by opaque FBA labels, so step 3 may have to be typed rather than scanned unless a
non-Amazon item carrying a printed barcode is to hand. Typing it exercises the same resolution
path; only the wedge itself goes unproven, and `test_wedge_scan.py` covers that separately.

### 3. On a phone

Open a product on a handheld or a 390px window. The card must not push the page sideways, and
the add form must be reachable and usable. Typing is expected here — this control needs a
keyboard by nature, which is why it is not part of the touch-only suite.

---

## Rolling back

There is nothing to roll back in the database — this feature adds no migration and changes no
schema. Reverting the branch removes the controls; identifiers added while it was deployed stay
exactly where they are, indistinguishable from ones added at creation time.
