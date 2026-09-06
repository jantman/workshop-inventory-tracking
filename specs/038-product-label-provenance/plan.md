# Implementation Plan: Product label provenance — identity, per-unit price, copy count

**Branch**: `robot-army/issue-141-a-product-label-omits-manufacturer-and` | **Date**: 2026-09-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/038-product-label-provenance/spec.md`

## Summary

Three changes to the product label path, all inside `app/services/product_label.py` and
`app/product/routes.py`.

1. **Provenance becomes a list of lines rather than one string.** `format_provenance` gains the
   product's manufacturer and part number and returns up to two lines: an identity line
   (`MEAN WELL  IRM-05-5`) and a purchase line (`Amazon  2026-01-14  $6.50 ea`). Either may be
   absent; both absent means no provenance band, exactly as today.
2. **The price gains an `ea` suffix.** Three characters, on the band that already truncates last.
3. **The print route accepts `label_count`**, validated 1–99 like the item label route, and the
   product label modal gains the same number input the item label modal already has.

The load-bearing constraint is FR-006 / the module's own FR-012: the code band must not shrink.
The second provenance line is therefore paid for out of the description's share, not the code's.
The band arithmetic is restructured so that the total above the code is a fixed budget
(`DESCRIPTION_BAND + PROVENANCE_BAND`) and provenance lines are subtracted from the description
inside it. With one provenance line that arithmetic reduces to exactly today's numbers, so a
one-line label is unchanged and a no-provenance label is byte-identical (SC-006).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x, Pillow (PIL) for composition, `pt_p710bt_label_maker`
(`BarcodeLabelGenerator`, `LpPrinter`). No new dependency.

**Storage**: MariaDB via SQLAlchemy. **No schema change and no Alembic revision** — `manufacturer`
and `manufacturer_part_number` already exist on `Product` (`app/database.py:837,839`).

**Testing**: `nox -s tests` (unit, network-blocked) and `nox -s e2e` (Playwright,
`-m "e2e and not screenshot"`). Existing coverage: `tests/unit/test_product_label.py`,
`tests/e2e/test_label_print.py`.

**Target Platform**: Linux server on a home LAN, single user, server-rendered Bootstrap 5 UI.

**Project Type**: Web application — Flask blueprints, Jinja templates, vanilla JS modules.

**Performance Goals**: None. Label composition is a per-click operation on a single-user LAN app;
no measurement exists showing it to be slow and none is sought.

**Constraints**:
- The code band's share of the label MUST NOT shrink (FR-006, and the module docstring's FR-012).
- Prices MUST NOT pass through `float` (Constitution III).
- No test may reach `LpPrinter.print_images()` — it drives real hardware. The existing
  TESTING/DISABLE_LABEL_PRINTING short-circuit in `print_product_label` is the seam.
- Changing `app/templates/product/detail.html` and `app/static/js/product-label-modal.js` triggers
  the screenshot regeneration gate (Constitution, Development Workflow).

**Scale/Scope**: Two source files plus one template and one JS module; roughly 60 lines changed.

## Constitution Check

*GATE: passed before Phase 0 research. Re-checked after Phase 1 design — see below.*

| Principle | Assessment |
|-----------|------------|
| **I. Simplicity First (NON-NEGOTIABLE)** | **PASS.** No new module, class, abstraction, or configuration knob. One function's return type changes from `Optional[str]` to `List[str]`; one parameter is renamed; the band arithmetic gains two lines of subtraction. The copy count reuses the item label path's existing 1–99 convention rather than inventing a second one. No new dependency. |
| **II. Layered Architecture Boundaries** | **PASS.** Composition stays in `app/services/product_label.py`; the route stays thin (fetch, validate, delegate). The label service is given `manufacturer` and `part_number` as plain optional strings rather than an ORM object, so no ORM type crosses into the composition layer. |
| **III. Exact Numerics** | **PASS.** The price continues to be rendered with `str()` on the `Decimal`. The `ea` suffix is string concatenation after that. No arithmetic is performed on the price at all, so no opportunity for a `float` to appear. Asserted directly by an existing test, extended. |
| **IV. Test Discipline Through Nox** | **PASS.** Run via `nox -s tests` and `nox -s e2e`. New unit tests cover all eight present/absent combinations of manufacturer, part number and purchase, plus the band-budget invariant across every stock. The new e2e assertions wait on observable state (`#product-label-alert` text), never on a clock. No new pytest marker is needed. |
| **V. MariaDB Is the Source of Truth** | **PASS, not engaged.** No schema change, no migration, no `create_all`. The fields being printed already exist. |
| **VI. Item Lifecycle and History Invariants** | **PASS, not engaged.** This is the product catalog. No inventory item, JA ID, active-row, or shortening path is touched. |
| **Operating Context / Threat Model** | **PASS.** The `label_count` validation exists because a bad count wastes a roll of labels, not because the input is hostile. No sanitization layer is added. CSRF stays as it is — `csrfFetch` already carries the token. |
| **Development Workflow** | **PASS.** Feature branch + PR. Screenshots regenerated and committed because `product/detail.html` changes. `nox -s tests` and `nox -s e2e` green before merge. |

**Result: no violations.** The Complexity Tracking section is therefore omitted.

One judgement call is recorded rather than hidden: the `label_count` validation is **duplicated**
from `app/main/routes.py` rather than extracted into a shared helper. See
[research.md](./research.md#decision-5) — extracting it would touch a second blueprint that this
issue does not concern, for eight lines. Simplicity here means the smaller blast radius.

## Project Structure

### Documentation (this feature)

```text
specs/038-product-label-provenance/
├── plan.md              # This file
├── research.md          # Phase 0 output — the five decisions and what was rejected
├── data-model.md        # Phase 1 output — the label's content model and band budget
├── quickstart.md        # Phase 1 output — how to verify this by hand and by test
├── contracts/
│   ├── label-composition.md   # The service-level signatures that change
│   └── product-label-api.md   # POST /api/products/<id>/label
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── services/
│   └── product_label.py          # CHANGED: format_provenance signature and return type;
│                                 #   per-unit suffix; multi-line provenance band; band budget
├── product/
│   └── routes.py                 # CHANGED: api_print_product_label — pass manufacturer and
│                                 #   part number; accept and validate label_count
├── static/js/
│   └── product-label-modal.js    # CHANGED: read the count input, send label_count
├── templates/product/
│   └── detail.html               # CHANGED: number input in the product label modal
└── database.py                   # UNCHANGED — Product.manufacturer and
                                  #   .manufacturer_part_number already exist

tests/
├── unit/
│   └── test_product_label.py     # CHANGED: provenance line-building cases, band budget,
│                                 #   per-unit suffix, Decimal exactness
└── e2e/
    └── test_label_print.py       # CHANGED: copy count round-trips through the modal

docs/images/screenshots/          # REGENERATED: product detail page changed
```

**Structure Decision**: The existing layout is used unchanged. This feature adds no file to
`app/`. It is a change to two source files, one template and one JS module, which is the whole
of it — the label composition service already owns everything about what a label says, and the
route already owns everything about what a print request means.

## Phase 0 — Research

See [research.md](./research.md). Five decisions, all resolved without a blocking question:

1. Two lines rather than one reflowed line, identity first.
2. Where the second line's vertical space comes from (the description, never the code).
3. How `format_provenance` is reshaped, and why it takes strings rather than the `Product`.
4. `ea` as the per-unit marker, applied at formatting time and never to a `float`.
5. `label_count` duplicated rather than extracted.

No `NEEDS CLARIFICATION` markers were carried into this plan.

## Phase 1 — Design

See [data-model.md](./data-model.md) for the content model and the band budget arithmetic,
[contracts/](./contracts/) for the two changed signatures and the changed endpoint, and
[quickstart.md](./quickstart.md) for how to verify the result.

### Post-design Constitution re-check

Re-evaluated against the finished design. **Still no violations.** The design added no module, no
class, no dependency and no configuration; the largest single addition is a nine-line loop that
draws N provenance lines where one was drawn before. The one thing worth re-stating after design:
the band budget was chosen specifically so that the one-line and zero-line cases reduce to today's
arithmetic exactly, which is what makes SC-006's byte-identical claim testable rather than
aspirational.
