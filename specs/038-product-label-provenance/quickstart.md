# Quickstart: verifying product label provenance

How to convince yourself this works, by test and by hand. Commands assume the repository
virtualenv and pyenv's Python 3.13, per `CLAUDE.md`.

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

Sub-second. Covers everything in [data-model.md](./data-model.md) that can be asserted without a
browser:

- **Line building** — all eight present/absent combinations of manufacturer, part number and
  purchase (SC-003), including whitespace-only fields treated as absent, and no line ever emitted
  as `''`.
- **The per-unit marker** — `$6.50 ea`, and `$0.00 ea` for a zero price, and nothing at all for
  `None`. The existing `test_the_price_never_passes_through_a_float` is extended, not replaced.
- **The band budget** — for every entry in `LABEL_TYPES`, the barcode's first dense row with two
  provenance lines is no lower than with one (SC-004). The existing `first_dense_row` helper is
  what measures this; it already exists in `tests/unit/test_product_label.py` and was written for
  exactly this kind of assertion.
- **The no-provenance label is unchanged** — compose with no provenance before and after and
  compare the PNG bytes (SC-006). In practice this is asserted by composing the empty-provenance
  case and the `provenance_lines=[]` case and requiring identical bytes.
- **Route validation** — `label_count` accepted at 1 and 99, rejected at 0, 100, `2.5`, `"3"` and
  `true`, and a rejected request prints nothing.

```bash
# e2e — needs 15+ minutes; run detached, it outlasts a 10-minute tool cap
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

`tests/e2e/test_label_print.py` gains a case that sets the copy count in the modal and confirms the
result. It waits on `#product-label-alert` — the element the existing tests in that file already
wait on, which is populated only after the POST resolves (pattern C: the alert cannot predate the
response that produced it). No fixed waits.

## By hand

Printing is short-circuited under `TESTING` / `DISABLE_LABEL_PRINTING`, which logs what *would*
have been printed. That log line is the fastest way to see the composed provenance without a
printer:

```bash
DISABLE_LABEL_PRINTING=1 venv/bin/python -m flask --app app run
```

1. Open a product that has a manufacturer, a part number and at least one purchase — the issue's
   example is product 11, MEAN WELL IRM-05-5.
2. Click **Print Label**, choose a stock, set the count to 3, print.
3. The log line reports `provenance=['MEAN WELL  IRM-05-5', '<vendor>  <date>  $<price> ea']` and
   `num_copies=3`.
4. Clear the product's manufacturer and part number, print again: one provenance line, the purchase
   one, still carrying `ea`.
5. On a product with no purchases at all: one provenance line, the identity one. This is the case
   that could not produce a label with any provenance before.

To see the actual image rather than the log, compose one directly:

```bash
venv/bin/python - <<'PY'
from app.services.label_printer import LABEL_TYPES
from app.services.product_label import compose_product_label
png = compose_product_label(
    description='5W AC/DC converter, 5V 1A, PCB mount',
    code='WIT0000000011',
    provenance_lines=['MEAN WELL  IRM-05-5', 'DigiKey  2026-01-14  $6.50 ea'],
    **{k: v for k, v in LABEL_TYPES['Sato 2x4'].items()},
)
open('/tmp/label.png', 'wb').write(png.read())
PY
```

Open `/tmp/label.png`. Check the three things the spec cares about: both identity fields are there,
the price says `ea`, and the barcode plus its text are no smaller than on a one-line label composed
the same way.

## Screenshots

`app/templates/product/detail.html` changes, so the documentation screenshots must be regenerated
and committed with the change:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

Screenshots churn on every run; commit only those that actually differ in content.
