---
title: 'Foreign-payload rejection and ownership text'
type: 'feature'
created: '2026-07-24'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
baseline_revision: '9426c40'
final_revision: '1a238a3'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `gs1.decode()` exists (Story 2.4) but its rejection of foreign payloads is asserted against a dozen ad-hoc strings — the exhaustive matrix that Epic 4 scan routing and Epic 6 labels are entitled to rely on was explicitly deferred to this story, and two grammar holes it left open (an unbounded data field, so a 100 KB scan beginning `96WIT` becomes an "internal id"; and nothing stopping a 43xx AI from being encoded) are still open. FR12d — ownership/return information is human-readable label text and never an encoded element string — has no implementation at all: no config key, no seam, no test, only a sentence in a docstring.

**Approach:** Close the grammar's two remaining holes in `app/utils/gs1.py` (a spec-derived data-field length bound, and a hard refusal of the 43xx logistics AI series in both `encode` and `decode`), then pin the whole foreign-payload space with an exhaustive test matrix covering the barcode families this workshop actually scans. Add the ownership text as what FR12d says it is: a plain human-readable config string (`LABEL_OWNER_TEXT`) reached through a service seam beside `encode_internal_payload`, structurally disjoint from the encoder — Epic 6 composites it into the label's text region.

## Boundaries & Constraints

**Always:**
- `app/utils/gs1.py` stays **pure** — stdlib only, no Flask/SQLAlchemy/`app.*` imports, relative or absolute (AD-4). The existing purity guard must keep passing unchanged.
- `decode()` **never raises on `raw`** (NFR8). Every foreign, malformed, oversized, non-string or hostile input returns `None`. Only a malformed `ai`/`token`/`fnc1_substitute` — a config fault, never scan data — raises `InvalidGs1PayloadError`.
- `encode()` and `decode()` stay a closed pair: whatever `decode` returns, `encode` accepts, and every new rule is applied to **both** sides. `ai`/`token` remain keyword-only with no defaults (FR12c).
- The 43xx refusal is enforced in the one encoder, so "no 43xx element string is ever encoded" (FR12d) is a machine-checked invariant rather than a comment. A `GS1_INTERNAL_AI` in that series fails loudly at the first encode.
- Ownership text is **only** ever returned as text. Nothing in this story passes it to `gs1.encode`, and it must remain the kind of string `encode` refuses (it carries spaces and punctuation), so the two label regions cannot be confused.
- `LABEL_OWNER_TEXT` follows `config.py`'s established `os.environ.get(...) or <default>` idiom and is documented in `.env.example` in the verbose-comment-then-key style of the GS1 block. Unset (or blank) means **no ownership region**, not an error.
- Every new test carries `@pytest.mark.unit`, matches the house parametrize style (inline `#` comment per case), and cites its requirement ID.

**Block If:**
- The exhaustive matrix reveals a payload that resolves to an actual stored Product's `internal_id` other than by that product's own symbol — that is an identity defect, not a test gap.

**Never:**
- Do **not** make `decode` validate the *shape* of the extracted id (length 10, Crockford alphabet, `is_valid_internal_id`). That was raised and rejected three times in Story 2.4: `gs1.py` owns the grammar, `internal_id.py` owns the id, and coupling them is the drift AD-16 exists to prevent. The new length bound is admissible only because it is a property of the **AI's own GS1 format**, not of our id.
- No AIM-prefix stripping, no routing/precedence, no scan classifier (Story 4.2), no `decode_internal_payload` service method and no third GS1 config key (Epic 4 adds both with its consumer).
- No label rendering, no template change, no product-detail UI, no length/wrapping/truncation rule for the ownership text — Epic 6 owns layout (Stories 6.1–6.3).
- No 43xx encoder, no second element string, no separator handling (FR12b).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Foreign AI-96, no token | `'9612345'`, `'96ACME1234567'`, `'\x1d96FOO123'`, `'9612345678903'` (a UPC that starts `96`) | `None` — the token is what makes a symbol ours (FR12a) | Never raises |
| Retail digit strings | `'012345678905'` (UPC-A), `'0012345678905'` (EAN-13), `'00012348'` (GTIN-8), `'00012345678905'` (GTIN-14) | `None` | Never raises |
| GS1 element strings, other AIs | `'0109506000134352'`, `'\x1d0109506000134352\x1d10LOT42'`, `'\x1d00123456789012345675'`, `'\x1d21SN0001'`, `'\x1d17260101'` | `None` | Never raises |
| Distributor / vendor payloads | ECIA ISO-15434 label `'[)>\x1e06\x1dP12345\x1d1PABC\x1dQ10\x1d\x1e\x04'`, `'B08N5WRWNW'` (ASIN), `'X001ABCDEF'` (FNSKU), `'https://example.com/p/1'`, `'JA000123'`, `'M1-A'` | `None` | Never raises |
| AIM-prefixed | `']d2 96WITABC1234567'`, `']C10109506000134352'`, `']Q3…'`, `']d196WITABC1234567'` | `None` — prefix stripping belongs to Story 4.2 | Never raises |
| Near-miss prefixes | `'096WITABC1234567'`, `'9WITABC1234567'`, `'WITABC1234567'`, `'96 WITABC1234567'`, `'96-WITABC1234567'`, `'96wit…'`/`'96Wit…'`, `'96WIT'`, `'96WIT   '` | `None` | Never raises |
| Unicode / homoglyph | `'９６WITABC1234567'` (full-width), `'96WIT​ABC1234567'`, `'96WITABC123456é'`, `'٩٦WIT…'` | `None` | Never raises |
| Oversized data field | `'96WIT' + 'A' * 100000`, and any payload whose `token + id` exceeds `MAX_DATA_FIELD_LENGTH` (30) | `None` | Never raises |
| Oversized encode | `encode('A' * 28, ai='96', token='WIT')` (data field 31) | rejected | `InvalidGs1PayloadError` |
| At the bound | `encode('A' * 27, ai='96', token='WIT')` round-trips through `decode` | `InternalPayload(internal_id='A'*27, …)` | No error |
| 43xx AI refused | `encode('X', ai='4311', token='WIT')`, `encode(…, ai='4300')`, `decode('4311WITX', ai='4311', token='WIT')` | rejected — no 43xx element string can be produced or recognized (FR12d) | `InvalidGs1PayloadError` (both functions; this is a config fault, not scan data) |
| Non-43xx AI unaffected | only a leading `43` is barred: `ai='96'`, `'97'`, `'01'`, `'4'`, `'3'`, `'34'`, `'243'` all remain valid | encodes/decodes as before (FR12c preserved) | No error |
| Token superstring | `'96WITTY42'` under `token='WIT'` | decodes to `internal_id='TY42'` — **by design**; grammar matched, and no stored product carries that id | No error |
| Ownership text configured | `LABEL_OWNER_TEXT='If found, return to J. Antman — 555-0100'` → `CatalogService().ownership_label_text()` | that exact string, stripped | No error |
| Ownership text unset/blank | key absent, `''`, or `'   '` | `''` — no ownership region, not an error | No error |
| Ownership text is not encodable | `gs1.encode(<that same string>, ai='96', token='WIT')` | rejected — human-readable text can never become an element string | `InvalidGs1PayloadError` |
| Regions disjoint | `LABEL_OWNER_TEXT` set, then `encode_internal_payload('ABC1234567')` | `'\x1d96WITABC1234567'` — unchanged, contains no ownership text and no 43xx AI | No error |

</intent-contract>

## Code Map

- `app/utils/gs1.py` — add `MAX_DATA_FIELD_LENGTH = 30` (GS1 GenSpecs: AIs 90–99 are `N2+X..30`; a conservative upper bound on the single variable-length field) and `_require_ai(value)` = `_require_grammar_part('ai', value)` plus a refusal of any `ai` whose first two characters are `43`. `encode` calls `_require_ai`, and raises `InvalidGs1PayloadError` when `len(token + internal_id) > MAX_DATA_FIELD_LENGTH`; `decode` calls `_require_ai` and returns `None` when the recovered data field exceeds the same bound (checked before building the payload, so a 100 KB scan is rejected on length, not scanned character-by-character first). Update the module docstring's "Future extensibility" paragraph: FR12d is now enforced, not merely intended.
- `config.py` — add `LABEL_OWNER_TEXT = os.environ.get('LABEL_OWNER_TEXT') or ''` below the GS1 block (line ~38) with a short comment naming FR12d and stating that it is human-readable label text only, never encoded.
- `.env.example` — document `LABEL_OWNER_TEXT` in the same verbose-comment style as the GS1 block: what it is for, that blank/unset means no ownership region, that it is printed as text and never encoded (43xx rejected — see PRD addendum), and that Epic 6 owns where it lands on the label.
- `app/mariadb_catalog_service.py` — new `ownership_label_text(self) -> str` immediately after `encode_internal_payload` (line ~743): reads `Config.LABEL_OWNER_TEXT`, returns it stripped (`''` when unset/blank). Session-free, no audit logging, mirroring `encode_internal_payload`'s shape as the config seam. Docstring states the FR12d contract: the return value is human-readable label text, is never passed to `gs1.encode`, and Epic 6 is its consumer.
- `tests/unit/test_gs1.py` — new `TestForeignPayloadRejection` class holding the matrix's foreign/near-miss/unicode/AIM/distributor rows as parametrized `decode(...) is None` cases (the existing scattered foreign cases in `TestDecode` stay; do not delete coverage), plus new cases for the length bound (both sides, and the at-bound round trip) and for the 43xx refusal in `encode` and `decode`. Add an FR12d case showing a representative ownership string is rejected by `encode`.
- `tests/unit/test_catalog_service.py` — new `TestOwnershipLabelText` beside `TestEncodeInternalPayload` (line ~911): configured/unset/blank/padded cases via `monkeypatch.setattr(Config, 'LABEL_OWNER_TEXT', …)`, and the disjointness case (ownership set → `encode_internal_payload` output unchanged and free of that text).

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/gs1.py` — bound the data field and refuse the 43xx AI series in both `encode` and `decode`, keeping the pair closed and the module pure, so an oversized or logistics-AI payload can neither be produced nor recognized (FR12a, FR12d, NFR8).
- [x] `config.py` + `.env.example` — add and document `LABEL_OWNER_TEXT`, defaulting to "no ownership region", so ownership/return information is operator-configurable without a code edit (FR12d).
- [x] `app/mariadb_catalog_service.py` — add the `ownership_label_text()` seam beside `encode_internal_payload`, so Epic 6 reads the text from one place and never from the encoder (FR12d, AD-16 pattern).
- [x] `tests/unit/test_gs1.py` — implement the exhaustive foreign-payload matrix plus the length-bound and 43xx rows, so every family this workshop scans is pinned as non-internal (FR12a).
- [x] `tests/unit/test_catalog_service.py` — cover the ownership seam and the region-disjointness case (FR12d).

**Acceptance Criteria:**
- Given every foreign payload family in the I/O matrix, when `decode()` is called under the deployed grammar, then each returns `None` and none raises — including inputs that are non-string, unicode, hostile, or 100 KB long (FR12a, NFR8).
- Given the configured grammar is any AI in the 43xx logistics series, when a payload is encoded or decoded, then it is refused with `InvalidGs1PayloadError`, so no 43xx element string can exist anywhere in the system (FR12d).
- Given `LABEL_OWNER_TEXT` is set to a realistic return-to string, when a Product's payload is encoded, then the element string is exactly `FNC1 + AI + token + internal_id` and carries none of that text — and that same text is itself rejected by `gs1.encode` (FR12d).
- Given `app/utils/gs1.py` after this story, when the purity guard runs, then the module still imports nothing from Flask, SQLAlchemy or `app.*` (AD-4, NFR7).
- Given `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`, when the suite runs, then all new tests pass and every pre-existing test stays green.

## Spec Change Log

## Review Triage Log

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 14: (high 0, medium 5, low 9)
- defer: 0
- reject: 11
- addressed_findings:
  - `[medium]` `[patch]` Every justification for `MAX_DATA_FIELD_LENGTH` (module docstring, constant comment, `encode` comment, test-class docstring) cited "AIs 90-99 are `N2+X..30`" and claimed the constant "enforces exactly that". Verified against GS1: **GSCN 16-000528 ("AI 91 to 99 - Data Length Extension"), effective 2017-07-31, raised the series to `X..90`**, so the citation was a decade out of date and the code was three times tighter than the standard it claimed to transcribe — with the false claim stated most confidently in the place a maintainer would trust. The constant is kept at 30 (the whole data field is `WIT` + a 10-character id, so nothing legitimate approaches even that, and a tighter bound dismisses a garbled scan sooner), but it is now described honestly as this module's deliberate cap below the AI's real ceiling, with the raise-it-to-90 option named as standards-conformant. The load-bearing distinction — a bound on the *element string's field* is admissible where a rule about the *id's shape* is not (AD-16) — is restated in the form that survives the correction.
  - `[medium]` `[patch]` The FR12d guard checked `ai` alone, so the split configuration `ai='4', token='311'` assembled the identical `4311…` element string and walked straight past it — the invariant was one config key away from being false. `_require_ai` is replaced by `_require_grammar(ai, token)`, which validates both halves and matches the barred prefix against the **marker** (`ai + token`) that every element string actually opens with. Both `encode` and `decode` now go through it.
  - `[medium]` `[patch]` No test verified that `config.py` reads an environment variable *named* `LABEL_OWNER_TEXT`: every ownership test monkeypatched `Config` directly, and the one test that appeared to cover it re-implemented `config.py`'s own expression inline and asserted on the result — a tautology that a typo like `LABEL_OWNER_TXT` would have passed. The single piece of wiring that could realistically be wrong was the one piece untested. Replaced with a source-level assertion in the established purity-guard idiom. (First attempt used `importlib.reload`, which rebinds `config.Config` while `mariadb_catalog_service` holds the old class — it broke four sibling tests; the failure is recorded here because the reload approach will look attractive again.)
  - `[medium]` `[patch]` The claim that the label's two regions are "structurally" disjoint because ownership text "carries spaces and punctuation" was a property of the three example strings chosen, not of the type — and it was asserted in four places (`gs1.py`, `config.py`, the service docstring, two test classes) while every test probing it used a string with a space. `ReturnTo:J.Antman` encodes perfectly well. All four now state the real guarantee (no code path passes `ownership_label_text()` into `gs1`) and demote the character rule to the backstop it is, with a test pinning the encodable case so the overclaim cannot creep back.
  - `[medium]` `[patch]` `.env.example` shipped `LABEL_OWNER_TEXT=If found, please return to ...` — a live placeholder on the normal onboarding path (copy `.env.example` → `.env`), which would print a literal trailing ellipsis on physical thermal labels. It now ships blank, which the surrounding comment already documented as the valid "no ownership region" default, with the sample moved into the comment. Added the python-dotenv quoting caveat: an unquoted value containing ` #` is silently truncated at that point.
  - `[low]` `[patch]` A `token` at or beyond `MAX_DATA_FIELD_LENGTH` left no room for an id, so `encode` could never build a payload while `decode` returned `None` for every scan of a genuine label — a total two-way outage with no error anywhere. Rejected loudly in `_require_grammar`, matching this module's standing fail-loud-on-bad-grammar choice.
  - `[low]` `[patch]` `InvalidGs1PayloadError`'s docstring asserted that "an oversized or 43xx-prefixed *scan* is a None from `decode`" — there is no scan-side 43xx check at all (a `43…` scan fails the ordinary marker match), so the sentence described a code path that does not exist, in the same breath as its own contradiction. Rewritten around the real split (fault in the *grammar* raises from both functions; anything about *`raw`* is only ever a `None`), along with the mangled mid-sentence wrapping the same edit had left behind.
  - `[low]` `[patch]` `decode`'s length check claimed a 100 KB scan "is dismissed on its length rather than walked character by character" — but `raw.strip()` and the marker slice have already copied the input twice by then, so the claim was false about memory and true only about the character scan. Corrected, including why an early `len(raw)` guard is not the fix (it would precede the FNC1/whitespace tolerance this module exists to provide).
  - `[low]` `[patch]` The module docstring stated in the present tense that an unbounded id "flows onward into a DB query" — no internal-id resolver exists yet, and this story's own boundaries defer it to Epic 4. Restated as the conditional it is.
  - `[low]` `[patch]` `test_the_two_label_regions_are_disjoint` asserted `'43' not in payload` — not FR12d, not an invariant of anything, and false for any generated id containing those two adjacent Crockford characters (`A43BCDEFGH` is a legal `generate_internal_id` output); it survived only because the id was hard-coded. Removed, along with two substring assertions logically implied by the exact-equality assertion above them.
  - `[low]` `[patch]` The only place in the diff that named AI 4311's meaning named it wrongly ("ship to / deliver to postal code"), in a story whose entire subject is return-to information. Corrected to "return-to contact name", per GS1 and the project's own PRD addendum.
  - `[low]` `[patch]` `test_only_a_leading_43_is_barred` asserted that `ai='4'` and `ai='3'` round-trip, regression-locking one-character values as supported AIs. The cases are kept (they are the boundary probes for a prefix match) but relabelled as exactly that, with an explicit note that this module has never validated AI *formats* — so the next person adding real AI validation is not blocked by a passing test. Added `'8200'` so a real four-digit AI is covered.
  - `[low]` `[patch]` Three tests chained `.internal_id` on a possibly-`None` `decode` result, so a regression would surface as `AttributeError: 'NoneType'…` instead of a readable failure. All now assert non-`None` first, matching the one sibling test that already did.
  - `[low]` `[patch]` No at-bound case was exercised through `fnc1_substitute`, despite FNC1 transmission variance being this module's headline hazard and the substitute being stripped before the length is measured. Added, both at the bound and one over it.
  - Deferred (0): nothing new. The two open ledger entries touching this area (no test executes a migration; the SQLite-only collision-retry coverage) were not re-opened or duplicated.
  - Rejected (11, by-design / out-of-scope / previously-rejected): general per-AI GS1 format validation, and restricting `ai` to the 90-99 range or to two digits (this module owns its own grammar, not the AI registry — rejected repeatedly through Story 2.4, and a `len == 2` rule would break the legitimate four-digit AIs the same reviewer cites); the 43xx guard "not enforcing FR12d" because ownership text could still reach `encode` as an `internal_id` (no such code path exists; the guard delivers exactly FR12d's stated testable consequence, and the overclaimed wording around it was patched instead); `ownership_label_text` not touching `self` and forcing an engine-constructing service instance (mirrors the `encode_internal_payload` seam; the engine-per-instance cost is already on the deferred ledger); reading `Config` rather than `app.config` (rejected twice in Story 2.4 as by-design and pre-existing); the encode-side bound being unreachable in production (defensive by design); the story's `Block If` not being tested (a workflow condition for the run, not a unit-test obligation, and unresolvable in a module with no DB); duplicate coverage between the two ownership tests and between `TestDecode`/`TestForeignPayloadRejection` (the spec mandates not deleting coverage); control-character and length sanitization of `LABEL_OWNER_TEXT` before rendering (operator-controlled config, and the spec's `Never` assigns label-side handling to Epic 6); the `.env.example` value needing escaping guidance beyond the quoting caveat already added.

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 1, low 7)
- defer: 2
- reject: 12
- addressed_findings:
  - `[medium]` `[patch]` `.env.example` still carried the exact overclaim the previous pass corrected in four other files: "GS1 has logistics AIs (the 43xx series) ... this system refuses them outright, **so there is no way for this text to end up as machine-readable data**". The "so" is a non-sequitur — verified by execution that `encode('ReturnTo:J.Antman', ai='96', token='WIT')` succeeds — and the one file left carrying the false guarantee is the one an operator actually reads on the onboarding path, while `gs1.py`, `config.py`, the service docstring and the tests all now say the opposite. Rewritten to state the real guarantee (no code path passes the value to the encoder) and to name the 43xx refusal as a separate guarantee about the AI, not about this text.
  - `[low]` `[patch]` `_FORBIDDEN_AI_PREFIX`'s defining comment claimed the prefix is "matched against the AI *and* the AI+token marker". There is exactly one comparison (`marker[:2]`); the AI is never matched alone. Harmless today because the marker subsumes it, but the comment invites a maintainer to assume a second guard exists or to "restore" a redundant one. Rewritten to describe the single marker comparison and why it is sufficient.
  - `[low]` `[patch]` `_require_grammar`'s "It costs nothing: ... no legitimate configuration is lost" was unqualified, but matching the concatenated marker over-bars: `encode('X', ai='4', token='3WIT')` is refused (verified) though no 43xx AI is involved. The choice stands — nothing the PRD addendum leaves legitimate lands in that corner — but it is now described as the price of one comparison rather than as literally free.
  - `[low]` `[patch]` `encode` discarded `_require_grammar`'s returned marker and re-derived `ai + token` by hand, while `decode` used the returned value. In the module whose stated purpose is preventing encoder/decoder drift (AD-16), the one function that must agree with `decode` about the marker was the one not using the shared derivation; any future change to marker construction would have split the pair silently. `encode` now builds from the returned marker.
  - `[low]` `[patch]` `InvalidGs1PayloadError`'s docstring makes an explicit behavioural claim — a scanned string opening `43` is simply foreign, failing the ordinary marker match with the forbidden-prefix rule never consulted — and nothing tested it, in a story whose whole subject is the raise-vs-None split by source. Added `test_a_scanned_43_payload_is_merely_foreign_not_an_error`: the one input family that touches both new rules at once.
  - `[low]` `[patch]` The matrix billed as exhaustive omitted our own AI+token inside a composite symbol — `'\x1d96WITABC1234567\x1d10LOT42'` opens with our marker and clears the new length bound, and is refused only by the interior FNC1 (verified `None`). That is the FR12b ours/foreign boundary a real multi-AI label physically produces and the answer Epic 4 routing will see while separator handling stays deferred. Added as three parametrized rows.
  - `[low]` `[patch]` `test_config_reads_the_environment_variable_of_that_name` — itself a product of the previous pass — over-specified formatting while under-specifying wiring: its regex would fail on an equivalent double-quoted assignment, yet would match the same expression parked on any other class, so it could not distinguish `Config.LABEL_OWNER_TEXT` from a binding nothing reads. Regex made quote-agnostic, a `vars(config.Config)` assertion added for the class location, and the docstring now states the two limits a source scan genuinely has instead of claiming more.
  - `[low]` `[patch]` Nothing pinned that the id length actually issued fits inside the new bound. `INTERNAL_ID_LENGTH` (10) plus the token (3) is 13 against a bound of 30 today, but raising `INTERNAL_ID_LENGTH` past 27 would make every encode fail at the label printer with no test objecting. Added a cross-module fit check, explicitly labelled as such — it is not an id-shape rule inside `gs1.py`, which still knows nothing about the id (AD-16).
  - Deferred (2, both pre-existing Story 2.4 code surfaced by this change): a `fnc1_substitute` equal to the marker's first character silently breaks every decode of a genuine label (the same total outage the new token-room rule fails loudly on, with no guard); and `encode_internal_payload` reports a configured-grammar fault as `ValidationError(field='internal_id', value=<valid id>)`. Appended as new ledger entries only; no existing entry was modified or re-opened.
  - Rejected (12): the disjointness test called vacuous (it is not — it asserts exact equality, so code that appended ownership text to the payload would fail it; the duplicate-coverage half was rejected in the previous pass); tests hard-wiring the literal 30 "contradicting one-place" (tests legitimately pin boundary values, and the constant is the one place the *production* decision is made); the oversize test's performance claim being prose-only; non-`str` `LABEL_OWNER_TEXT` raising `AttributeError` (`os.environ.get` yields `str` or `None` for every reachable value, and silently coercing a misconfiguration is worse); control-character sanitization of `LABEL_OWNER_TEXT`, and the claimed asymmetry with the character-checked GS1 pair (previously rejected; the GS1 rule exists because a stray FNC1 corrupts a machine-readable grammar, which free label text cannot do); zero-width-space-only ownership text rendering an invisible region; a length cap on the ownership text (the spec's `Never` assigns label-side handling to Epic 6); an unbounded `ai` (config, character-checked, and a non-matching marker is simply foreign); calibrating the token-room rule to `INTERNAL_ID_LENGTH` rather than `MAX_DATA_FIELD_LENGTH` (the proposed fix is precisely the AD-16 coupling this module refuses); extending FR12d to bar non-43xx AIs that could carry ownership data (previously rejected — the guard delivers FR12d's stated testable consequence); the volume-of-prose meta-finding (the two concrete stale instances it cited are patched above); and flake8 line-length drift (>79 characters appears on 653 lines across `app/` already, and `lint` is neither in the default nox sessions nor gated in CI).

## Design Notes

**Why a length bound is admissible when an alphabet check is not.** Story 2.4 rejected, three times, any rule in `gs1.py` derived from the id's *shape* — that belongs to `internal_id.py`, and duplicating it is the encoder/router drift AD-16 exists to prevent. `MAX_DATA_FIELD_LENGTH` is a different kind of rule: it bounds the *element string's* single data field, not the id. Note the standards detail the first review pass corrected — the company-internal series (AIs 90–99) permits `X..90`, not `X..30`, since GSCN 16-000528 took effect on 2017-07-31 — so 30 is this module's deliberately tighter cap rather than a transcription of the AI's ceiling. It is kept because the whole field is `WIT` plus a 10-character id, so 30 is already more than double anything legitimate, and the tighter bound dismisses a garbled scan sooner. Raising it to 90 stays standards-conformant; adding `is_valid_internal_id` here would not be the same kind of change at all. Either way the bound has teeth the alphabet check would not: without it, any foreign scan that happens to begin `96WIT` yields an unbounded `internal_id` that a future resolver (Epic 4) would carry into a DB query and that the UNTRUSTED `raw` field carries into logs today.

**Why the 43xx guard lives in `encode`.** FR12d's testable consequence is a negative — "no 43xx element string is ever encoded". There is exactly one encoder and its grammar comes from config, so the only way that negative can become false is a reconfiguration. Refusing it there converts a documented intention into an invariant, and costs nothing: the addendum rejected AI 4311 outright, so no legitimate configuration is lost. It is matched against the **marker** (`ai + token`) rather than the AI alone, because `ai='4', token='311'` assembles the identical element string — a gap the first review pass found and closed. `decode` refuses the same grammar, purely to keep the pair closed.

**Why the ownership text is a bare config string.** The label's human-readable region is Epic 6's to lay out; what Epic 2 can own is the *source* of the text and the guarantee that it never crosses into the symbol. A config key plus a service seam mirrors the `encode_internal_payload` pattern exactly. The guarantee is that **no code path passes `ownership_label_text()` into `gs1`** — not the shape of the text. A realistic return-to string is refused by `encode` because it carries spaces, but `ReturnTo:J.Antman` is not, so the character rule is a backstop for the ordinary case and is documented as one (the first review pass corrected four places that claimed otherwise). No length cap is imposed here deliberately — truncation depends on media geometry that does not exist yet.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — expected: all pass; no pre-existing test regresses (notably `TestDecode`, `TestConfigDrivenGrammar`, and both purity guards).
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- -k "ForeignPayload or OwnershipLabelText or Gs1"` — expected: the new matrix and seam classes run and pass.

**Manual checks (if no CLI):**
- `venv/bin/python -c "from app.utils import gs1; print(gs1.decode('96WIT' + 'A'*100000, ai='96', token='WIT'))"` prints `None`, and `grep -n "43" app/utils/gs1.py` shows the series refusal is the only 43xx reference in the module.


## Auto Run Result

Status: `done`. Follow-up review pass over the already-implemented story (spec arrived `status: done`, so this was a fresh review, not a resumption). No intent gaps and no spec defects: the implementation still satisfies every acceptance criterion, and this pass changed **no runtime behaviour** — the eight patches are documentation corrections, one internal refactor that is output-identical, and four new test cases.

**Implemented change (unchanged from the prior pass, re-verified here):** two grammar holes in `app/utils/gs1.py` closed — a 30-character bound on the single variable-length data field, enforced on both sides of the encode/decode pair, and a hard refusal of any grammar whose `ai + token` marker opens `43` (FR12d) — plus the exhaustive foreign-payload matrix, and `LABEL_OWNER_TEXT` surfaced as human-readable label text through `CatalogService.ownership_label_text()`.

**Files changed in this pass:**
- `.env.example` — replaced the false "so there is no way for this text to end up as machine-readable data" guarantee with the structural one; the 43xx refusal is now described as a guarantee about the AI, not about the text.
- `app/utils/gs1.py` — `_FORBIDDEN_AI_PREFIX`'s comment now describes the single marker comparison that actually exists; `_require_grammar`'s "costs nothing" claim qualified with the over-barred corner it does have; `encode` now builds its output from the marker `_require_grammar` returns instead of re-deriving `ai + token` by hand.
- `tests/unit/test_gs1.py` — added a scanned-`43`-payload-is-merely-foreign case (the one input touching both new rules), three composite/multi-element-string rows for the matrix, and a cross-module check that the deployed id length fits inside the bound.
- `tests/unit/test_catalog_service.py` — the env-var wiring test made quote-agnostic, given a `vars(Config)` class-location assertion, and its docstring corrected to state what a source scan can and cannot prove.
- `_bmad-output/implementation-artifacts/deferred-work.md` — two new entries appended (no existing entry touched).

**Review findings breakdown:** 8 patched (1 medium, 7 low), 2 deferred, 12 rejected, 0 intent_gap, 0 bad_spec. Both reviewers ran in parallel with no prior context; every load-bearing claim was re-verified by executing the code rather than reading it, which is what reclassified several confident-sounding findings as rejects.

**Verification:** `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` → **737 passed, 305 deselected** (730 before this pass; the 7 new cases account for the difference), no regressions, both purity guards green. Individual claims verified by direct execution: the compact ownership string `ReturnTo:J.Antman` does encode; `decode('4311ABC', …)` and the composite `'\x1d96WITABC1234567\x1d10LOT42'` both return `None`; `ai='4', token='3WIT'` is refused; `fnc1_substitute='9'` silently breaks every genuine scan.

**Residual risks:** the two deferred entries are both real and both pre-existing — the `fnc1_substitute`/marker collision is the sharper of the two and should be guarded before Epic 4 gives that knob a config key. The 43xx over-barring of `ai='4'` + a `3`-prefixed token is accepted and now documented. `MAX_DATA_FIELD_LENGTH = 30` remains a deliberate cap below the standard's current `X..90`.
