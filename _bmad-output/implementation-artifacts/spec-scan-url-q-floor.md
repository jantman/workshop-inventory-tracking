---
title: 'Floor `_bounded_scan_url`s halving of `q`, and shed the pre-fills first'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: '5c6a788e3b0ce2d7436d5cc50849d5d52987fc5f'
final_revision: '1424f96'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `_SCAN_URL_Q_LIMIT` (1024) is justified in the docstring at `app/main/routes.py:1943-1946` as putting `q`'s truncation point "past every VARCHAR the fallthrough search touches", but `_bounded_scan_url` then halves whichever argument is longest until the assembled URL fits `_MAX_SCAN_URL_CHARS` — so for a multi-byte alphabet (one astral character percent-encodes to twelve characters) `q` is cut to ~256 while `hit_count` was computed from the full scan, re-opening DW-17's eviction risk at a truncation point that is a function of the scanned alphabet rather than the stated 1024.

**Approach:** Shrink the OTHER arguments first — every one of them is a re-editable pre-fill, while `q` is the only value the results page depends on — and floor `q`'s halving at a stated minimum chosen so that a `q` sitting on the floor always fits the transport budget for ANY alphabet. Restate the resulting guarantee in the docstrings in alphabet-independent terms.

## Boundaries & Constraints

**Always:**
- `q` is never cut below `_SCAN_URL_Q_FLOOR` characters, whatever the alphabet.
- `_SCAN_URL_Q_FLOOR` is at least the largest VARCHAR the fallthrough search touches (255), so DW-17's "a cut `q` can only over-match through `products.notes` (TEXT)" stays literally true after a cut.
- `_SCAN_URL_Q_FLOOR * 12 + the endpoint path` fits inside `_MAX_SCAN_URL_CHARS` — 12 being the most characters one Python character can percent-encode to (4 UTF-8 bytes, each `%XX`). A `q` on the floor with every other argument gone must always be transportable.
- Every non-`q` argument is exhausted (halved to nothing and dropped) before `q` is touched at all.
- The loop terminates on every input, and `_bounded_scan_url` still returns a non-empty in-app URL for every scan (FR36/FR40: no dead ends).
- Path arguments (`product_detail`'s int `product_id`) are never candidates for shrinking.

**Block If:** No unattended decision is expected. Block only if the floor arithmetic cannot hold — i.e. if `_MAX_SCAN_URL_CHARS` cannot accommodate a floored `q` in the worst-case alphabet.

**Never:**
- Do not change `_SCAN_URL_Q_LIMIT` (1024), `_MAX_SCAN_URL_CHARS` (7000), `_SCAN_URL_ARG_LIMITS`, or `_scan_search_text`'s uncapped derivation.
- Do not re-introduce a per-value BYTE cap in `_scan_url_value` (an earlier reading did; the docstring records why it was removed).
- Do not close DW-17 itself — the `products.notes` residue stays open and stays unclaimed.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| ASCII scan already inside budget | 4096 ASCII chars, search arm | URL built once, no shrinking; `q` is the full 1024-char `_SCAN_URL_Q_LIMIT` slice | No error expected |
| Astral scan, search arm | 4096 astral chars (12 encoded chars each), search arm with pre-fills | Pre-fills shed first, then `q` halved 1024 -> 512 and stopped there; `len(url) <= 7000` and `len(q) == 512` | No error expected |
| Pre-fills shed before `q` | Over-budget search URL carrying `description` etc. | `description` shrinks/disappears while `q` is still untouched | No error expected |
| `q` already at or under the floor | Over-budget URL whose `q` is <= 512 chars | `q` unchanged; only pre-fills shrink | Returns best-effort URL |
| Non-search arms | `create` / `product` outcomes (no `q`) | Behaviour unchanged: longest pre-fill halved until the URL fits | No error expected |
| Nothing left to shrink | All args gone and `q` on the floor | Loop exits, URL returned as-is (still an in-app path) | No exception, no empty URL |

</intent-contract>

## Code Map

- `app/main/routes.py:1874-1880` -- `_SCAN_URL_Q_LIMIT` and the comment stating the 1024 guarantee.
- `app/main/routes.py:1913-1975` -- `_scan_url_value` docstring; its "`q` is bounded by the URL budget ... past every VARCHAR the search touches" paragraph is the claim being made true.
- `app/main/routes.py:2076-2079` -- `_MAX_SCAN_URL_CHARS = 7000`, the transport budget.
- `app/main/routes.py:2080-2105` -- `_bounded_scan_url`, the halving loop being replaced.
- `app/main/routes.py:2107-2147` -- `_scan_destination`, the only caller; passes `q` only on the search arm.
- `app/mariadb_catalog_service.py:1894` -- `search_products` docstring names the six searched columns; max VARCHAR among them is 255 (`products.internal_id` 32, `description`/`manufacturer`/`mpn`/`product_identifiers.value` 255, `notes` TEXT).
- `tests/unit/test_scan_routes.py:719-861` -- `TestTheRoutedUrlIsAlwaysBuildable`, where the bounding tests live; `_query`/`_path` helpers at :77/:87.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- add `_SCAN_URL_Q_FLOOR = 512` beside `_MAX_SCAN_URL_CHARS`, with a comment deriving it: 512 >= the largest searched VARCHAR (255), and 512 * 12 (worst-case percent-encoding per Python character) + the endpoint path fits 7000 -- so the floor is simultaneously the strongest bound the transport allows and past every VARCHAR.
- [x] `app/main/routes.py` -- rewrite `_bounded_scan_url` as two phases: halve the longest non-`q` string argument (dropping it once halving empties it) until the URL fits or none remain; only then halve `q`, clamped with `max(len // 2, _SCAN_URL_Q_FLOOR)`, stopping at the floor. Keep the existing `isinstance(value, str)` guard so path arguments are never candidates.
- [x] `app/main/routes.py` -- update `_bounded_scan_url`'s docstring to state the two-phase rule and the alphabet-independent guarantee; amend the `_SCAN_URL_Q_LIMIT` comment and `_scan_url_value`'s `q` paragraph so the stated truncation point (`_SCAN_URL_Q_LIMIT` down to `_SCAN_URL_Q_FLOOR`, never below) matches what the code does for every alphabet.
- [x] `tests/unit/test_scan_routes.py` -- extend `TestTheRoutedUrlIsAlwaysBuildable` with the I/O matrix cases: an astral max-length search scan keeps `len(q) >= _SCAN_URL_Q_FLOOR` while `len(url) <= _MAX_SCAN_URL_CHARS`; pre-fills shrink before `q` does; the floor arithmetic holds (`_SCAN_URL_Q_FLOOR * 12 < _MAX_SCAN_URL_CHARS` and `_SCAN_URL_Q_FLOOR >= 255`); non-search arms are unchanged. Import the constants rather than repeating literals.

**Acceptance Criteria:**
- Given a 4096-character astral-plane scan that falls through to the search arm, when `/api/scan` routes it, then the returned URL is at most `_MAX_SCAN_URL_CHARS` characters and its decoded `q` is at least `_SCAN_URL_Q_FLOOR` characters.
- Given an over-budget search URL that also carries pre-fill arguments, when `_bounded_scan_url` shrinks it, then no pre-fill argument survives at its original length while `q` has been cut.
- Given any scan of any alphabet, when `_bounded_scan_url` runs, then it terminates and returns a non-empty in-app path, and `q` is either absent or at least `min(original length, _SCAN_URL_Q_FLOOR)` characters.
- Given the existing suite, when `nox -s tests` runs, then every previously passing scan-routing test still passes -- in particular `test_a_max_length_scan_produces_a_transportable_url`, `test_the_search_url_carries_a_bounded_q` and `test_a_truncatable_q_does_not_evict_the_hits_it_counted`.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 5: (high 0, medium 1, low 4)
- reject: 4: (high 0, medium 0, low 4)
- addressed_findings:
  - `[medium]` `[patch]` Phase 1 ranked candidates by CHARACTER count, which is the same cost-blindness the new docstring calls the bug. `_scan_url_args` caps each pre-fill at its column, so a 512-character ASCII `category_path` (512 characters of URL) outranked a 255-character astral `description` (3060) — the loop cut the cheap readable value and left the expensive one whole; with values tied at 255, `max` broke the tie by dict order. Ranking is now `len(quote(value, safe=''))`, with `test_the_prefill_that_is_shed_is_the_one_that_costs_the_most` pinning it. Mutation-verified: reverting the key to `len(args[name])` turns that test red.
  - `[low]` `[patch]` `test_the_floor_arithmetic_holds_from_both_ends` asserted `_SCAN_URL_Q_FLOOR >= 255` and `<= _SCAN_URL_Q_LIMIT`, and both boundaries it admitted break the property it guards: a floor OF 255 lets a cut `q` match a full-width `products.description`, falsifying DW-17's "only through `products.notes`"; a floor EQUAL to the limit makes the second loop's `> _SCAN_URL_Q_FLOOR` guard unsatisfiable, so an astral scan ships a 12288-character URL. Both tightened to strict, with the reason stated inline.
  - `[low]` `[patch]` `_bounded_scan_url`'s docstring justified its fallthrough return with "an over-long URL is a bad outcome and a dead end is a forbidden one", which is self-contradictory — an over-long URL IS the 414/400 dead end. Reworded: the `break` is unreachable as the constants stand, it exists as a guard against a future edit to them, and if reached it returns the shortest URL it managed because an exception in `url_for` is the same dead end through a 500.
  - `[low]` `[patch]` `test_an_astral_search_scan_still_leaves_q_on_the_floor` carried `assert _SCAN_URL_Q_FLOOR <= len(q) <= _SCAN_URL_Q_LIMIT` immediately above `assert len(q) == _SCAN_URL_Q_FLOOR` — strictly implied by it, and it read as pinning an interval no input can land inside. Removed.
  - `[low]` `[patch]` `test_a_non_search_arm_still_halves_its_longest_prefill` was renamed and re-worded to `..._costliest_prefill` so the test names no longer assert the ranking rule the patch above replaced.

Rejected: that an empty-string argument is unsheddable (the `and value` filter) — worth 13 characters against 837 of headroom, with no behavioral consequence; that the ledger's DW-28 entry still reads `status: open` (the orchestrator owns it, per the Never list, and the invocation forbids editing it); that 68 `url_for` rebuilds for a maximal scan is a hot-path cost (this endpoint already runs a leading-wildcard `LIKE` over six unindexed columns — the rebuilds are noise beside it); and that the unreachable `break` needs test coverage (it is unreachable by construction, and the arithmetic that makes it so is pinned directly).

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 4: (high 0, medium 1, low 3)
- reject: 10: (high 0, medium 0, low 10)
- addressed_findings:
  - `[medium]` `[patch]` `_bounded_scan_url`'s docstring stated that phase 1's `break` "is unreachable as the constants stand ... a guard against a future edit to those constants, not a live path". That is false, and the paragraph reasoned from it. Instrumented: `_bounded_scan_url('main.product_search', q='\U0001f600' * 1024)` takes the `break` — as does every over-budget search URL carrying nothing but `q`, which is the commonest over-budget shape there is; it is the ordinary handoff from phase 1 to phase 2, not an error path. What is actually unreachable is RETURNING an over-budget URL. The claim was load-bearing in the wrong direction: it invites a maintainer to delete the `break` as dead code, and without it `costliest is None` reaches `args[None]` and 500s on exactly that commonest shape. Paragraph rewritten to say which of the two is unreachable and why.
  - `[low]` `[patch]` The cost ranking used `quote(value, safe='')`, which is not the encoder that builds the URL being measured. `werkzeug.urls._urlencode` is `urlencode(items, safe="!$'()*,/:;?@")`, and `urlencode` quotes with `quote_plus` — so a space costs one character (`+`) and each of those reserved characters costs one, where `quote(safe='')` charges three apiece. Verified against emitted URLs: `len(quote_plus(v, safe="!$'()*,/:;?@"))` matches `url_for`'s actual per-value cost exactly for spaces, slashes, reserved characters, CJK and astral, while `quote(safe='')` over-charges spaced English and slash-heavy `category_path` values by up to 3x. That is the same class of error the previous pass's patch set out to remove, one level down: 255 characters of spaced English score 331 and cost 255, so they outrank and get cut instead of a 50-character Cyrillic value that really costs 300. Ranking key corrected and the safe set named as `_URL_QUERY_SAFE` beside the other budget constants. New test `test_cost_is_measured_with_the_encoder_that_builds_the_url` pins it; mutation-verified — restoring `quote(args[name], safe='')` turns it red.
  - `[low]` `[patch]` Nothing pinned the ASCII end of the interval the whole change rests on. `test_the_search_url_carries_a_bounded_q` asserted `len(q) <= 1024`, which stays green if an ASCII scan were ever cut to the floor as an astral one is — so only the floor end of "one interval, identical for ASCII and for astral" had a test. Tightened to `== _SCAN_URL_Q_LIMIT`, importing the constant rather than repeating the literal.
  - `[low]` `[patch]` `test_the_prefill_that_is_shed_is_the_one_that_costs_the_most` closed on `sum(len(...)) < 3 * 255`, which any shrinking of any ONE of the three values satisfies; the actual outcome leaves `vendor_sku` untouched at 255 and nothing said so. Replaced with per-name assertions that state which values are cut and which is spared.
  - `[low]` `[patch]` Formatting left over from the previous pass's rewording: one 90-character line in a module that wraps at 80 (`nox -s lint` runs flake8 over it), and a stranded mid-sentence break where "Only then is `q` / touched, and it is halved / against a floor" left a five-word fragment on its own line. Rewrapped; every line added by this story is now within the file's 80-column style.

Rejected: that four of the seven `test_every_shape_terminates_with_an_in_app_path` cases do not enter either loop (they are deliberate coverage of the no-shrink path, and the property the test names — terminates with an in-app path — is what they assert); that `test_a_floor_length_q_fits_the_budget_in_the_worst_alphabet` is a no-op wrapper around the arithmetic test (it measures the real endpoint's path length end to end, which the arithmetic test only approximates); that `test_a_path_argument_is_never_a_shrink_candidate` cannot distinguish the behavior it names (if `product_id` were sliced, `_path(url)` would change — the assertion pins exactly that); that a non-`str` `q` can never be shrunk because phase 1 excludes by name and phase 2 by type (`_scan_destination` always passes `_scan_url_value('q', ...)`, which returns a `str`); that the function should log when it returns an over-budget URL (that state is unreachable, so the log line would never fire); that "one interval, identical for ASCII and for astral" overstates the result (the docstrings claim a two-sided BOUND, which is accurate — that only two values inside it are reachable is DW-143, not an overclaim); that the docstring is too long and the `quote_plus` import comment is misplaced; that a floored `q` consuming 6163 of 7000 characters deserves a note (7000 is already the budget net of scheme, host and cookies, per its own comment); that `'q'` appears as a magic string in four places; and that the "12 encoded characters per character" worst case wants a named constant shared by the code and the test.

### 2026-07-27 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 0, low 5)
- defer: 1: (high 0, medium 0, low 1)
- reject: 11: (high 0, medium 1, low 10)
- addressed_findings:
  - `[low]` `[patch]` `test_the_prefill_that_is_shed_is_the_one_that_costs_the_most` asserted argument order, not the ranking rule. Its three astral values were all 255 characters, so all three cost exactly 3060 — tied under BOTH metrics — and which two were halved was decided by `max`'s first-wins tie-break over kwargs order. Verified: reordering the keywords to `(category_path, vendor_sku, manufacturer, description)` flips the outcome and `assert query['vendor_sku'] == ...` fails, so the previous pass's per-name assertions and their "the two the loop reaches are halved; the third is spared" comment were reading insertion order as a cost property. The values are now given distinct lengths (255/200/150), which makes the expected outcome unique: one halving of the costliest suffices and the two cheaper ones come back whole. Mutation-verified — ranking by `len(args[name])` still turns it red.
  - `[low]` `[patch]` The same test's docstring justified its oversized values with "pre-fills at their real caps cannot overrun the budget, so the ranking is not observable at production sizes at all", which is false and contradicted `_bounded_scan_url`'s own docstring ("in the shape production actually emits the candidates are routinely TIED at 255 characters") in the same diff. Measured: five pre-fills at their real `_SCAN_URL_ARG_LIMITS` caps in astral text build a 15371-character URL that the loop cuts every one of. Reworded to the real reason — oversizing isolates the whole overrun into ONE comparison between TWO values the two metrics order oppositely.
  - `[low]` `[patch]` Nothing pinned `_URL_QUERY_SAFE` against the encoder it copies; the previous pass recorded that as an accepted residual risk on the grounds that a test would have to name the private `werkzeug.urls._urlencode`. It does not: new `test_the_safe_set_is_the_one_url_for_actually_uses` probes every printable ASCII character plus one representative of each UTF-8 width through `url_for` and compares the emitted characters against the predicted cost. Mutation-verified in both directions — removing `,` from the safe set and adding `&` to it each turn it red. The probe is spelled out rather than built from the constant, because a probe derived from `_URL_QUERY_SAFE` shrinks with it and cannot detect a removal (the first attempt did exactly that and passed under the mutation).
  - `[low]` `[patch]` `test_a_q_already_at_the_floor_is_not_cut_to_pay_for_a_prefill` did not test its own title: it passed `q` of 400 characters, which is UNDER the floor, clearing the second loop's `> _SCAN_URL_Q_FLOOR` guard by 112 characters. Parametrized over 400 and `_SCAN_URL_Q_FLOOR` so the boundary the comparison actually turns on is covered from the exact-floor side.
  - `[low]` `[patch]` `test_an_astral_search_scan_still_leaves_q_on_the_floor` measured the URL but never followed it, where its ASCII sibling `test_the_search_url_carries_a_bounded_q` issues `client.get` and asserts a 200. Since FR36/FR40 are about the page arriving rather than about the string's length, the astral case now follows its URL too.

Deferred: DW-146 — a pre-fill shortened for transport reasons arrives inside its column limit, so it renders as an ordinary valid entry and nothing marks it as a prefix of what the label carried, against `_prefill_form_data`'s stated rule that length earns a field message "rather than being silently shortened behind the operator's back". Pre-existing (the pre-change halving truncated the same values) and distinct from DW-142/DW-145.

Rejected: the four structural findings both reviewers reproduced are already on the ledger and were not re-recorded — that phase 1 sheds pre-fills that cannot close the gap and the search-arm create link then falls back to `description = q` (DW-142, the one medium); that the second loop can only ever run once, so the stated interval has two reachable points and `q` is cut ~263 characters past necessity (DW-143); that `isinstance(value, str)` is a blanket type exemption rather than an allow-list, leaving non-`str` query arguments unbounded and `del` able to raise `BuildError` on a string path argument (DW-144); and that atomic values like `quantity` and `identifier_value` are halved into plausible wrong values (DW-145). Also rejected: that the docstring frames the change as a pure bug fix without stating what was given up (it states the pre-fill/`q` trade-off explicitly, and DW-142 records the cost); that "a pre-fill the operator can retype" is false of a DROPPED pre-fill (the sentence justifies the priority order, and the drop is the mandated exhaustion, not a separate claim); that truncating an in-cap prose value saves silently wrong data (deferred as DW-146 in the one form that is real — the missing signal — and rejected as a data defect, since the value is rendered in an editable field the operator reviews before POST); that three of the seven `test_every_shape_terminates_with_an_in_app_path` cases are inert (deliberate coverage of the no-shrink path, rejected on the same grounds last pass); and that the commentary has outgrown the code and the import comment forward-references symbols defined later (rejected last pass; the prose that was actually wrong was patched above rather than deleted wholesale).

## Design Notes

Why 512 and not 1024: `q` reaches `_bounded_scan_url` already capped at `_SCAN_URL_Q_LIMIT` (1024). In the worst alphabet that is 1024 * 12 = 12288 encoded characters — over budget no matter what else is dropped, so the floor cannot be 1024. One halving gives 512, which encodes to at most 6144 characters; plus `/products/search?q=` that is ~6163, inside 7000. So 512 is the largest floor the transport can actually guarantee, and it is still double the largest VARCHAR the search touches — the two constraints meet with room to spare rather than in conflict.

Shape of the loop (not a literal patch):

```python
url = url_for(endpoint, **args)
while len(url) > _MAX_SCAN_URL_CHARS:          # phase 1: pre-fills only
    longest = <longest non-empty str arg, excluding 'q'>
    if longest is None: break
    args[longest] = args[longest][:len(args[longest]) // 2] or <drop>
    url = url_for(endpoint, **args)
while len(url) > _MAX_SCAN_URL_CHARS and len(args.get('q', '')) > _SCAN_URL_Q_FLOOR:
    args['q'] = args['q'][:max(len(args['q']) // 2, _SCAN_URL_Q_FLOOR)]
    url = url_for(endpoint, **args)
```

Both loops strictly decrease a non-negative quantity each iteration (`n // 2 < n` for `n >= 1`; `max(n // 2, floor) < n` for `n > floor`), so both terminate.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all unit tests pass, including the new bounding cases.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (no `app/utils/` change, run as a regression guard).


## Auto Run Result

Status: done

**Implemented change.** `_bounded_scan_url` no longer halves whichever argument is longest. It runs two phases: every non-`q` argument is shed first -- the costliest by what it actually costs the assembled URL is halved, and dropped outright once halving empties it -- and only when nothing is left to shed is `q` touched, halved against `_SCAN_URL_Q_FLOOR = 512` and stopped AT the floor. 512 satisfies two constraints at once: it is past the largest VARCHAR the fallthrough search touches (255), so DW-17's "a cut `q` can only over-match through `products.notes`" stays true of a floored `q`; and 512 x 12 (the most one Python character can percent-encode to) plus the endpoint path is ~6163, inside `_MAX_SCAN_URL_CHARS`, so a floored `q` is transportable on its own in the worst alphabet. The guarantee is now one interval -- `_SCAN_URL_Q_LIMIT` down to `_SCAN_URL_Q_FLOOR`, never below -- identical for ASCII and astral, where before the truncation point slid with the scanned alphabet (~256 characters for astral).

**Files changed**
- `app/main/routes.py` -- added `_SCAN_URL_Q_FLOOR` with its two-sided derivation and `_URL_QUERY_SAFE` with the cost model it is measured against; rewrote `_bounded_scan_url`'s loop and docstring; amended the `_SCAN_URL_Q_LIMIT` comment and `_scan_url_value`'s `q` paragraph so both state the ceiling-and-floor rule rather than a single 1024 bound; added `from urllib.parse import quote_plus` for the cost ranking. Unchanged by this third pass.
- `tests/unit/test_scan_routes.py` -- eleven tests (18 cases) in `TestTheRoutedUrlIsAlwaysBuildable`, importing `_SCAN_URL_Q_FLOOR` / `_SCAN_URL_Q_LIMIT` / `_MAX_SCAN_URL_CHARS` / `_URL_QUERY_SAFE` / `_bounded_scan_url` rather than repeating literals; `test_the_search_url_carries_a_bounded_q` tightened to pin the ceiling exactly.

**Review.** Three passes. Pass 1: 5 patches (1 medium, 4 low), 5 deferred, 4 rejected. Pass 2: 5 patches (1 medium, 4 low), 4 deferred, 10 rejected. Pass 3 (this one): 5 patches (5 low), 1 deferred, 11 rejected. No intent gaps and no spec loopbacks in any pass. Pass 3 changed no production code -- every patch was a test that asserted something other than what it claimed, or a comment that stated something false. See the Review Triage Log above.

**Deferred findings.** This pass added DW-146 only (a transport-shrunk pre-fill reaches the create form with nothing marking it as shortened). The four structural findings both reviewers independently reproduced -- greedy pre-fill shedding, the one-shot cut to the floor, the type-test shrink guard, and atomic values being halved -- are already recorded as DW-142/143/144/145 and were deliberately not re-recorded, per the invocation's new-entries-only instruction. That both reviewers landed on the same four and found nothing new of that class is the pass's main convergence signal.

**Verification**
- `nox -s tests` -- 2687 passed, 427 deselected (2685 before this pass; +2 from the new safe-set test and the new boundary parametrization). Run three times: after patching, under each mutation below, and once more on the final state.
- `nox -s doctests` -- 21 passed.
- Mutation-tested every patch that pins behaviour: ranking by `len(args[name])` instead of encoded cost turns both `test_the_prefill_that_is_shed_is_the_one_that_costs_the_most` and `test_cost_is_measured_with_the_encoder_that_builds_the_url` red; removing `,` from `_URL_QUERY_SAFE` and adding `&` to it each turn `test_the_safe_set_is_the_one_url_for_actually_uses` red. `app/main/routes.py` was restored from a byte copy after each mutation and `git diff` confirmed empty.
- The first version of the safe-set test did NOT survive its own mutation -- it built the probe from `_URL_QUERY_SAFE`, so a character removed from the constant left the probe at the same moment and the test passed under the mutant. Rewritten with a literal probe (every printable ASCII character plus one representative of each UTF-8 width) and re-mutated in both directions before being kept.
- Every reviewer claim acted on was reproduced against the live app first: the 3060-character three-way cost tie and the kwargs-order flip, the 15371-character unbounded URL at real column caps, `q` at exactly the floor coming back whole, and the emitted-vs-predicted encoding match.
- `flake8` (from the `lint` session's venv) reports nothing on any line this pass changed; the file has substantial pre-existing lint noise, so it was filtered to changed lines rather than run whole.
- `nox -s e2e` not run (~20 minutes; no template, CSS, or JS changed, and this pass changed no production code at all). No screenshot regeneration for the same reason.

**Residual risks**
- DW-17 itself is untouched and stays open: a `q` cut to the floor is still a PREFIX, and `products.notes` is TEXT, so the eviction path through `notes` remains. This change bounds where the cut can land; it does not remove the cut.
- `_URL_QUERY_SAFE` still mirrors a private werkzeug detail (`werkzeug.urls._urlencode`), but the drift is no longer unpinned: `test_the_safe_set_is_the_one_url_for_actually_uses` compares the constant against what `url_for` emits, so a werkzeug upgrade that changes the query encoding fails the suite instead of silently making the ranking approximate. Previously recorded here as an accepted risk; closed this pass.
- The floor is a compile-time constant validated by arithmetic in one test rather than derived at runtime. If `_MAX_SCAN_URL_CHARS` is lowered below ~6200, `test_the_floor_arithmetic_holds_from_both_ends` goes red -- which is the intended signal, but the failure names the arithmetic, not the operational reason the budget moved.
- Worst-case percent-encoding is taken as 12 characters per Python character. That holds for UTF-8 and for `_scan_url_value`'s `errors='replace'` surrogate handling; a change to either invalidates the derivation silently.
- The pre-fill losses recorded as DW-142 and DW-146 are live behaviour, not hypotheticals: every multi-byte search scan reaches the results page with its create link stripped, and every multi-byte create scan at column caps reaches the form with values silently shortened. Both are what the intent contract asks for, and both stay until those entries are taken up.
