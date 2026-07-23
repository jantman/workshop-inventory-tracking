# Architecture Spine — Version / Technology Reality-Check Review

**Reviewer role:** Verify every committed technology decision in the spine was web-researched or reality-checked against the actual project, not asserted from training data.
**Spine reviewed:** `ARCHITECTURE-SPINE.md` (created/updated 2026-07-22)
**Review date:** 2026-07-22

**Verdict:** PASS — every claim holds. One low-severity caveat (pyStrich does not explicitly classify Python 3.13, and 0.18 is only 2 days old) and one cosmetic naming note (`pyStrich[png]` extra). Nothing blocks the build; the spine already carries the right de-risking spike (Deferred Q7).

---

## 1. pyStrich 0.18 — NEW dependency for GS1 DataMatrix rendering

**Spine claim (Stack table + AD-11 + Operational envelope):** `pyStrich[png] 0.18 — NEW: GS1 DataMatrix rendering (pure-Python, no system dep)`; renders DataMatrix to a `BytesIO`; label payload is GS1 FNC1-first, AI 96, token `WIT`+`internal_id`. Fallback (Deferred Q7): `treepoem` + Ghostscript.

| Sub-claim | Result | Evidence |
| --- | --- | --- |
| pyStrich exists on PyPI | PASS | https://pypi.org/project/pyStrich/ — active project (mmulqueen/pyStrich, "fast pure-Python 1D/2D barcode encoder"). |
| 0.18 is a real / current version | PASS | Live PyPI page lists **0.18 released 2026-07-20** as the latest (only 2 days before this review). Note: a WebSearch snapshot still showed 0.16 as latest — cache lag — but the live page and changelog both confirm 0.18. |
| Pure-Python, no system dep | PASS | PyPI + docs: "fast pure-Python module." PNG output requires **Pillow only** (already pinned `Pillow>=12.3.0`); SVG/EPS/DXF/terminal need nothing. No `apt`/Ghostscript/native lib. Matches the spine's "no `apt` package" operational claim. |
| Supports GS1 DataMatrix with FNC1-in-first-position | PASS | Docs (datamatrix.html): `DataMatrixData.gs1()` / `FNC1` marker places FNC1 as the first codeword to signal GS1 mode and auto-inserts FNC1 separators after non-final variable AIs. Changelog: formal GS1 support in **0.15 (2026-06-26)**; FNC1 constant since **0.11 (2026-05-07)**; 0.15 note: "Payloads built with FNC1 stay in single-mode ASCII as the GS1 Data Matrix spec requires." |
| Python 3.13 compatible | CAVEAT | PyPI metadata: `Requires-Python >=3.10`, classifier `Programming Language :: Python :: 3 :: Only` — **no explicit 3.13 classifier**. 3.13 is permitted by the version floor (no upper cap) and the package is pure-Python, so risk is low, but "3.13 compatible" is inferred, not vendor-asserted. |
| Fallback: treepoem needs Ghostscript | PASS | treepoem wraps BWIPP and shells out to the Ghostscript CLI; Ghostscript is a required system dependency installed separately (`apt-get install ghostscript`). Confirmed via treepoem README + issue tracker (adamchainz/treepoem #53). The spine's fallback trade-off (pure-Python pyStrich vs. treepoem+GS system dep) is accurate. |

**Recency cross-check of Deferred Q7:** Spine says "pyStrich's GS1 support is ~6 weeks old." GS1 field wrappers landed in 0.15 on 2026-06-26 (~4 weeks before review); the FNC1 constant landed in 0.11 on 2026-05-07 (~11 weeks). "~6 weeks" is a fair mid-point approximation. The blocking scan-test spike (print + verify it scans/validates as GS1 DataMatrix) is the correct call for a feature this fresh.

**Severity:** LOW. pyStrich is real, current, pure-Python, and genuinely does FNC1-first GS1 DataMatrix. The only build risks are (a) no explicit 3.13 classifier — mitigated by pure-Python + `>=3.10`, and (b) 0.18 is 2 days old — pin exactly (already done) and rely on the Q7 spike before committing.

**Minor note:** The `pyStrich[png]` extra syntax should be confirmed against the package's declared extras at pin time; regardless, the PNG path's only real requirement is Pillow, which is already a first-class dependency, so a bare `pyStrich==0.18` + existing Pillow also satisfies it.

---

## 2. Existing pins vs. the actual repo

Checked the Stack table against `requirements.txt`, `_bmad-output/project-context.md`, templates, and CI.

| Pin in spine | Repo reality | Result |
| --- | --- | --- |
| Flask 3.1.3 | `requirements.txt:1` `Flask==3.1.3` | PASS |
| Werkzeug 3.1.8 | `requirements.txt:7` `Werkzeug==3.1.8` | PASS |
| SQLAlchemy 2.0.51 | `requirements.txt:10` `SQLAlchemy==2.0.51` | PASS |
| Alembic 1.18.5 | `requirements.txt:11` `alembic==1.18.5` | PASS |
| PyMySQL 1.2.0 | `requirements.txt:9` `PyMySQL==1.2.0` | PASS |
| MariaDB 11.8 | `.github/workflows/test.yml:174` and `screenshots.yml:23` `image: mariadb:11.8`; recent merge `#42 upgrade/mariadb-11.8` | PASS |
| Pillow >=12.3.0 | `requirements.txt:14` `Pillow>=12.3.0` | PASS |
| PyMuPDF (`fitz`) 1.28.0 | `requirements.txt:15` `PyMuPDF==1.28.0` | PASS |
| Bootstrap 5.3.2 | `app/templates/base.html:9,118` CDN `bootstrap@5.3.2`; `project-context.md:26` "Bootstrap 5.3.2" | PASS |
| pt-p710bt-label-maker git @jantman | `requirements.txt:13` git `@jantman` | PASS |

**Severity:** NONE. Every existing pin in the spine matches the repo exactly. No pin disagrees. (MariaDB 11.8 is defined in CI workflow images rather than in `requirements.txt`, which is expected for the DB engine — it is not a pip dependency.)

---

## 3. GS1 / AI-96 encoding claims (standards accuracy)

**Spine claims (AD-8, Consistency Conventions):** label payload is a single GS1 element string — FNC1-first, AI **96**, data = token `WIT`+`internal_id`; single element string needs no separator.

| Claim | Result | Evidence |
| --- | --- | --- |
| FNC1 in first position signals a GS1 AI payload | PASS | GS1 DataMatrix intro/overview + GS1 general specs: FNC1 in the first position tells scanners the data is structured with GS1 Application Identifiers. |
| AI 96 is valid for company-internal use | PASS | AIs **91–99** are reserved for company-internal information (GS1 General Specifications / AI reference). 96 is within that range — appropriate for a private internal-ID scheme with no GS1 licensing. |
| A single (last) element string needs no FNC1 separator | PASS | GS1 rule: variable-length element strings "SHALL be delimited unless this element string is the last one to be encoded in the symbol." A lone AI-96 string is both first and last, so no trailing FNC1 separator is required — exactly what pyStrich's `gs1()` does automatically. |

**Severity:** NONE. The encoding design is standards-accurate. (Reminder for the build spike, not a spine defect: AI 96 in the current GS1 tables carries a defined data-title/format; the `WIT`+`internal_id` content and length should be validated against a real scanner's GS1 parser — already covered by Deferred Q1 and Q7.)

---

## 4. Migration HEAD `8213852b0b94`

**Spine claim (AD-14 + Structural Seed):** new catalog migration chains from current HEAD `8213852b0b94`; `down_revision = 8213852b0b94`.

**Verification:** Enumerated every file in `/home/jantman/GIT/workshop-inventory-tracking/migrations/versions/` and read each `revision` / `down_revision`:

```
6e64cd1f734a  (initial, down=None)
  -> 5d61d892776a  -> 3b7d76c3fb8d  -> 649ff0d93d25
  -> dce1254cd381  -> e4f344204264  -> 56dc95692b79
  -> 8213852b0b94  (refactor_photo_schema_for_many_to_many)
```

`8213852b0b94` (`migrations/versions/8213852b0b94_refactor_photo_schema_for_many_to_many.py:17`) is the **only** revision that is never referenced as any other migration's `down_revision`, so it is the single current HEAD. Corroborated by recent history (`ebcc266 Fix alembic downgrade at 8213852b0b94`).

**Result:** PASS. **Severity:** NONE.

---

## Summary

| # | Claim | Result | Severity |
| --- | --- | --- | --- |
| 1 | pyStrich 0.18 (exists, current, pure-Python, GS1 FNC1-first) | PASS w/ caveat | LOW (no explicit 3.13 classifier; 0.18 is 2 days old) |
| 1b | Fallback: treepoem needs Ghostscript | PASS | — |
| 2 | Existing pins match repo (all 10) | PASS | NONE |
| 3 | GS1 / AI-96 encoding (FNC1-first, 91–99 internal, single-string no separator) | PASS | NONE |
| 4 | Migration HEAD `8213852b0b94` is current | PASS | NONE |

**Counts:** 5 PASS (1 with caveat), 0 FAIL. No claim was found to be out-of-date or overstated; the sole freshness risk (pyStrich GS1 support) is explicitly de-risked by the spine's Deferred Q7 spike.

### Sources
- pyStrich: https://pypi.org/project/pyStrich/ · https://www.method-b.uk/pyStrich/docs/datamatrix.html · https://www.method-b.uk/pyStrich/docs/changelog.html · https://github.com/mmulqueen/pyStrich
- treepoem / Ghostscript: https://github.com/adamchainz/treepoem · https://github.com/adamchainz/treepoem/issues/53
- GS1: https://www.gs1.org/gs1-application-identifiers · https://ref.gs1.org/ai/ · GS1 DataMatrix technical overview (gs1ca.org)
- Repo: `requirements.txt` · `app/templates/base.html:9,118` · `_bmad-output/project-context.md:24,26` · `.github/workflows/test.yml:174` · `.github/workflows/screenshots.yml:23` · `migrations/versions/*.py`
