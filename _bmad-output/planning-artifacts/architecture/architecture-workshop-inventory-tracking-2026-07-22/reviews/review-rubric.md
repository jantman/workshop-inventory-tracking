# Good-Spine Rubric Review — Architecture Spine: Product Catalog & Purchase Tracking

- **Target:** `_bmad-output/planning-artifacts/architecture/architecture-workshop-inventory-tracking-2026-07-22/ARCHITECTURE-SPINE.md`
- **Altitude / posture:** FEATURE altitude, BROWNFIELD build-substrate, governing 10 epics of a product-catalog enhancement to the existing `workshop-inventory-tracking` Flask app.
- **Sources cross-checked:** PRD (`prd.md`), addendum (`addendum.md`), `_bmad-output/project-context.md`, and the live codebase (`app/database.py`, `app/models.py`, `app/services/label_printer.py`, `migrations/versions/`, `requirements.txt`, PyPI).
- **Reviewer method:** read-only. Every load-bearing brownfield claim in the spine was verified against the actual code, not taken on faith.

## Overall Verdict

This is a **strong** build-substrate spine. It fixes the marquee cross-epic invariants that the PRD's 10 epics could otherwise implement incompatibly — stored-vs-derived stock (AD-6), the equivalence partition (AD-10), the GTIN namespace (AD-7), internal-ID authority with config-driven GS1 encoding (AD-8), a single server-side scan router (AD-5), and capture idempotency/de-dup (AD-9) — and it ratifies the brownfield precisely rather than reinventing it (the "enhanced-ORM" claim, the Alembic HEAD, and the label-submission seam all verified against the code). Named tech is verified-current (pyStrich 0.18 is the latest PyPI release) and appropriately hedged behind the Q7 spike. The one genuine gap is a shared free-text-search seam between Epic 4 (scan fallthrough) and Epic 8 (search) that the spine leaves unstated and, worse, explicitly disclaims under Deferred. **0 critical, 0 high, 1 medium, 3 low.**

## Per-Checklist-Point Judgments

### 1. Does it fix the real divergence points and miss none? — **STRONG** (one medium miss)

The cross-epic invariants that two epics could implement incompatibly are the spine's strongest work, and the highest-risk ones are all governed:

- **Stored-vs-derived stock (AD-6)** binds Epics 5, 7, 10 and kills the PRD's C3 flip-flop by construction: `stock_status` stores only the manual assertion; **Effective Low** and **On Order** are computed at read and *have no column* (confirmed absent from the Structural Seed ER). Receipt clears only a manual `low`/`out`, never writes `quantity_on_hand`. This is the marquee invariant and it is airtight.
- **Equivalence partition (AD-10)** binds Epic 10 plus the reorder/on-order views in 5 and 7: nullable `equivalent_group_id` FK, ≤1 group per product, cross-group add rejected (not moved), On-Order/reorder collapse across siblings. Matches PRD §4.5 / FR62–64 / NG11 exactly.
- **GTIN namespace (AD-7)**, **internal-ID authority + config-driven encoding (AD-8)**, **single scan router (AD-5)**, **capture idempotency/de-dup (AD-9)**, **integer PK / `internal_id` business key (AD-3)**, and **attachment XOR owner (AD-12)** each pin a genuine multi-epic seam.
- The internal-ID string is a 4-epic contract (generated in Epic 2; recognized by the scan router in Epic 4; encoded on labels in Epic 6; keys URLs in Epic 8) and is well-handled: AD-4 makes `utils/internal_id.py` the single source, AD-8/FR12a wrap it in the `WIT` token, and AD-5 precedence (rule 1 AI-96+`WIT` before rule 3 bare-GTIN) prevents any collision with the digit-GTIN path.

**Miss (see Finding 1):** the free-text search surface is shared by Epic 4 (AD-5 rule-4 / FR36 fallthrough over identifiers/descriptions/MPNs) and Epic 8 (FR52), and the spine names no single search entrypoint. This is exactly the checklist's "key failure" shape — an epic-level invariant two epics could implement incompatibly, left unstated — though its blast radius is modest.

### 2. Is every AD's Rule enforceable, and does it prevent its stated divergence? — **STRONG**

Every AD's Rule is enforceable at schema, import, test, or review time, and each actually prevents the divergence it names:

- **AD-6** is enforced by *absence* — there is no derived column to write, so no epic can persist derived state.
- **AD-3 / AD-7 / AD-12** are enforced structurally (integer PK, `UNIQUE(type,value)`, `CHECK ((product_id IS NULL) <> (purchase_id IS NULL))` — MariaDB 11.8 honors CHECK).
- **AD-4** is enforced by "no Flask/DB imports" (grep/import-lint checkable) plus exhaustive unit tests, mirroring the existing `location_validator.py` pattern (verified present).
- **AD-5** is enforced by making `scan_router.py` the *sole* classifier and pushing the client to post raw text — no route or JS can re-classify.
- **AD-14** is enforced by chaining migrations from a specific HEAD and is fully verified (below).

Softer spots are appropriately application-level, not weaknesses: AD-8's "INTERNAL row is a derived read index, not independently editable" and AD-9's idempotency (keyed on a *nullable* `request_key`, so guaranteed only when a key is supplied — consistent with FR51) are review/logic invariants by nature.

### 3. Could anything under Deferred let two epics diverge? — **ADEQUATE**

Three of four Deferred items are correctly non-invariant: Q1 (scanner round-trip) and Q7 (pyStrich GS1 scan-test) are blocking hardware/empirical spikes that gate single epics; category storage depth and attachment size/thumbnailing are single-epic implementation details behind fixed mechanisms (materialized-path convention; AD-12). **The exception is "Full-text search mechanism (Epic 8)"**, which asserts "no other epic depends on the choice" — this is incorrect, and is the substance of Finding 1: Epic 4's scan fallthrough consumes the same free-text surface. Deferring the *mechanism* (LIKE vs FULLTEXT vs ranking) is fine; deferring it while disclaiming a real cross-epic dependency is the finding.

### 4. Is named tech verified-current and does it fit? — **STRONG**

- **pyStrich[png] 0.18** — verified as the latest PyPI release (0.18 is the top of the version list). Pure-Python DataMatrix rendering, no `apt` dependency, which fits NFR1 (no new services) and the RPi-5/Docker envelope. The spine correctly flags that pyStrich's GS1 support is recent and gates it behind the Q7 spike with a documented `treepoem`+Ghostscript fallback — the right posture for a ~6-week-old capability on which offline identifiability (SM-3) depends.
- **Existing pins** all match the codebase: Python 3.13, Flask 3.1.3 / Werkzeug 3.1.8, SQLAlchemy 2.0.51 (legacy `Query` API), Alembic 1.18.5, PyMySQL 1.2.0, Pillow ≥12.3.0, PyMuPDF 1.28.0, `pt-p710bt-label-maker @ git+…@jantman`, Bootstrap 5.3.2 (verified against `requirements.txt` and `project-context.md`). MariaDB 11.8 matches the recent upgrade commit.

### 5. Does it RATIFY the brownfield rather than contradict it? — **STRONG**

The one place the spine could have contradicted the codebase — AD-1's "enhanced-ORM" framing — was verified and holds:

- `project-context.md` states tersely that the dataclass domain layer and the ORM layer are separate and "must not be merged." AD-1 instead says to put domain logic *on* the ORM class via `@hybrid_property`/`@property` "exactly as `InventoryItem` does," reserving `models.py` dataclasses for composite/validated sub-values and enums. **The code confirms AD-1:** `InventoryItem` in `app/database.py` uses `@hybrid_property` (5×) and `@property` (8×) for domain logic, while `models.py` holds value-object dataclasses (`Thread`, `Dimensions`) and enums (`ItemType`, `ItemShape`, `ThreadSeries`, …). AD-1 is the *more accurate* statement of the pattern; there is no contradiction — the "don't merge" rule refers to the value-object dataclasses, which AD-1 preserves.
- **Alembic HEAD `8213852b0b94` verified as the true single head.** The full chain is linear (`6e64cd1f734a → 5d61d892776a → 3b7d76c3fb8d → 649ff0d93d25 → dce1254cd381 → e4f344204264 → 56dc95692b79 → 8213852b0b94`) with exactly one head. AD-14's `down_revision = 8213852b0b94` is correct.
- **Label seam verified:** `LABEL_TYPES` in `app/services/label_printer.py` already defines `Sato 1x2 / 2x4 / 4x6` (+ Flag variants), and the submission seam is `printer.print_images(images: List[BytesIO])`. AD-11's "extend `LABEL_TYPES` + new generator branch → pyStrich `BytesIO` → unchanged `print_images()`" matches reality; the addendum's brownfield note (2D rendering is the real gap, media already present) is corroborated.
- Other cited conventions verified present: `api_client.py`, `utils/location_validator.py`, `log_audit_operation` (`app/logging_config.py`), `_get_storage_backend()` (routes), the `Photo` BLOB precedent (`MEDIUMBLOB`-variant columns) that AD-12 leans on, and Decimal/`ROUND_HALF_UP` money handling.

### 6. Does it cover the PRD's capabilities / FRs / NFRs? — **STRONG** (two minor gaps)

NFR spot-check (NFR1–NFR11): 10 of 11 map cleanly — NFR1 → Operational envelope; NFR2 → Schemaless convention (`attributes` JSON); NFR3 → AD-14; NFR4 → Epic-9 map; NFR5 → AD-6 tri-state/opt-in; NFR6 → Testing convention (E2E for scan+label); NFR7 → AD-4; NFR9 → AD-14 + AD-11; NFR10 → AD-13; NFR11 → AD-11 ("deterministic for a given record"). **NFR8** (graceful ECIA degradation — surface the raw scan on malformed format-06) is only *implied* by AD-5's free-text fallthrough and is not explicitly governed (Finding 2). The 64 FRs' cross-epic invariants are governed via the AD set and the Capability→Architecture map; the one FR-level structural seam with no home is **FR60/FR61** (the Enrichment Interface), which the map never places (Finding 3).

### 7. Is every dimension the feature altitude owns decided/deferred/open? — **STRONG**

No whole dimension is silent. The **operational/environmental** dimension — the one most often missed — is explicitly decided in the *Operational envelope*: no new services/containers, ships inside the existing Docker image on the RPi 5, shares MariaDB/auth/backups, only new runtime dep is pure-Python pyStrich (no `apt`), attachment BLOBs grow the DB and are covered by the existing backup, label printing via `lp`/CUPS unchanged. Data model (Structural Seed + ADs), testing (convention), observability/audit (`log_audit_operation`), security/auth (inherited per NFR1, CSRF-exempt JSON stated), and performance/scale (explicitly out of scope; hundreds–low-thousands, one user) are all placed.

## Findings

### Finding 1 — Shared free-text search seam (Epic 4 ↔ Epic 8) is unstated and mis-disclaimed under Deferred — **MEDIUM**

AD-5 rule 4 and PRD FR36 route any unmatched scan into "free-text search across identifiers, descriptions, MPNs" — the *same* surface as Epic 8's FR52 full-text search. The spine names no single search entrypoint, and AD-2 only guarantees both go *through the service*, not that they call the *same method*. The Deferred item "Full-text search mechanism (Epic 8)" then asserts "no other epic depends on the choice," which is false: Epic 4's fallthrough depends on it. If Epic 4 and Epic 8 build separate implementations, the same query can return different results from the scan box versus the search page (different fields searched, different GTIN-at-query-time handling, different ranking). Blast radius is modest (single user, hundreds of products, both recoverable), hence Medium not High. **Recommendation:** add a one-line convention or extend AD-2/AD-5 to name a single service search method (single source of truth) that both the scan-router fallthrough and Epic-8 search invoke, and correct the Deferred disclaimer to "the *mechanism* is deferred; the *entrypoint* is shared and fixed."

### Finding 2 — NFR8 (graceful ECIA degradation) has no explicit AD/convention home — **LOW**

AD-5 fixes routing precedence and a free-text fallthrough but does not encode NFR8's specific behavior: on a malformed/unrecognized ISO/IEC 15434 format-06 envelope, surface the raw scan for manual handling rather than raising. It is single-epic (Epic 4), so cross-epic divergence risk is low, but it is an NFR the spine does not visibly govern. **Recommendation:** one clause in AD-5 (rule 2) or a Consistency convention stating the ECIA parser degrades to the raw-scan/free-text path on malformed input.

### Finding 3 — FR60/FR61 Enrichment Interface seam is unplaced — **LOW**

FR60 mandates "a single internal Enrichment Interface" (typed Identifiers in, partial Product record out, no-op impl this phase) and FR61 the backfill-forward creation shape. The Capability map routes Epic 7 to AD-9/AD-13/AD-6 but never mentions this interface, so its home in the layered structure is undefined. Risk is low (no-op, single epic), but it is an FR-level structural seam; if a real implementation is added later its location is unspecified. **Recommendation:** note the Enrichment Interface as a service-layer seam (e.g. a pure/injected hook the create path calls) in the source tree or Capability map.

### Finding 4 — AD-11 under-describes the label composite — **LOW**

AD-11 reads "the generator renders the DataMatrix via pyStrich to a `BytesIO` and hands it to the unchanged `print_images()`." pyStrich renders only the symbol; the generator must composite it with the Label Description and Provenance Block into the full label raster (as the existing `BarcodeLabelGenerator` does) before submission. The seam is correct; the phrasing could be misread as printing a bare DataMatrix. Cosmetic, Epic-6-local. **Recommendation:** reword to "composites the pyStrich DataMatrix into the label raster, then hands the raster to `print_images()`."

## Finding Counts

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 1 |
| Low | 3 |
