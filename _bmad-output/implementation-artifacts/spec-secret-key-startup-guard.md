---
title: 'Refuse to boot a non-debug app on the committed SECRET_KEY fallback'
type: 'feature'
created: '2026-07-28'
status: 'done'
baseline_revision: '717e5ca'
final_revision: 'dac1565'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `config.py:85` resolves `SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'`, and that literal is published in this repository, so a deployment whose operator forgets the env var signs every Flask session cookie and CSRF token with a public key — forgeable by anyone. Nothing distinguishes the fallback from a real key: no test, no startup check, no log line (DW-98).

**Approach:** Name the fallback literal once as a module constant in `config.py`, and add a boot-time guard, called from `create_app()` alongside the existing `validate_limits` precedent, that raises `ConfigurationError` when a config that is neither `DEBUG` nor `TESTING` resolves `SECRET_KEY` to that constant, and logs at ERROR (without refusing) when it does. Cover both branches with unit tests.

## Boundaries & Constraints

**Always:**
- The fallback literal has exactly ONE home: a module-level constant in `config.py`. The guard compares against that constant — never a re-typed string.
- Refusal is by `raise` out of `create_app()`, so the process fails to start. Use `app.exceptions.ConfigurationError` with `config_key='SECRET_KEY'`, matching `validate_limits` in `app/request_limits.py`.
- The guard runs AFTER `setup_logging(app)` (so its ERROR record reaches the structured JSON pipeline) and BEFORE `csrf.init_app(app)` (so a forgeable key is never armed for CSRF).
- "Non-debug" means `not DEBUG and not TESTING`, read from `app.config`. Flask defaults `TESTING` to `False`, and `config.Config` never sets it, so a production boot evaluates as non-debug.
- The ERROR message must name `SECRET_KEY`, state that the key is published in this repository, and point at how to set one. It must never echo the resolved key value.
- Keep `config.py` free of `app.*` imports (see the `ConfigurationError` docstring at `config.py:8`).

**Block If:**
- Making the guard fire would require changing what config class a production entry point (`wsgi.py`, `app.py`) passes to `create_app()`.

**Never:**
- Do not raise at `import config` time / inside the `class Config` body — `manage.py` and `migrations/env.py` import `Config` without booting an app, and `config.TestConfig` inherits the same attribute.
- Do not change `SECRET_KEY`'s resolution semantics (blank/unset still falls back), rotate keys, add key generation, or touch `.env`.
- Do not override `SECRET_KEY` on `config.TestConfig` to dodge the ERROR branch.
- Do not use `importlib.reload(config)` or a cold-import subprocess in tests: the repo `.env` may itself define `SECRET_KEY`, which makes such a test environment-dependent.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Production, key set | `DEBUG=False`, `TESTING=False`, `SECRET_KEY` = a real value | `create_app()` returns an app; no ERROR logged | No error expected |
| Production, key unset | `DEBUG=False`, `TESTING=False`, `SECRET_KEY` = the fallback constant | `create_app()` raises `ConfigurationError` naming `SECRET_KEY`; process does not start | Raise, `config_key='SECRET_KEY'` |
| Local dev | `DEBUG=True`, `SECRET_KEY` = the fallback constant | App boots; one ERROR record naming `SECRET_KEY` | Logged, not raised |
| Test config | `TESTING=True`, `SECRET_KEY` = the fallback constant | App boots; one ERROR record naming `SECRET_KEY` | Logged, not raised |
| Debug + real key | `DEBUG=True`, `SECRET_KEY` = a real value | App boots; nothing logged | No error expected |

</intent-contract>

## Code Map

- `config.py:85` -- where the fallback literal lives today; gains the named constant.
- `app/__init__.py:15-50` -- `create_app()`; the ordered `setup_logging` → `init_request_limits` → `csrf.init_app` block (comment at :30-44) is where the guard call is inserted.
- `app/request_limits.py:454-538` -- `validate_limits(config, logger)` / `init_request_limits(app)`: the exact precedent to mirror (signature, raise style, `from app.exceptions import ConfigurationError`).
- `app/exceptions.py:74-107` -- `ConfigurationError(message, config_key=...)`, already registered in `app/error_handlers.py:415-416`.
- `tests/test_config.py:12` -- the `TestConfig` used by `tests/conftest.py`; it overrides `SECRET_KEY` to a non-fallback value, so existing tests are unaffected. Subclass it to build the spec's scenario configs.
- `tests/unit/test_request_limits.py:118-136, 2259-2292` -- the `capsys` + JSON-log-line helper pattern for asserting on records emitted during `create_app` (`caplog` cannot see them: `setup_logging` clears the root handlers).
- `.env.example:2` -- documents `SECRET_KEY`.

## Tasks & Acceptance

**Execution:**
- [x] `config.py` -- add a module-level constant (e.g. `DEV_SECRET_KEY_FALLBACK`) holding `'dev-secret-key-change-in-production'` and use it in the `Config.SECRET_KEY` expression -- so the guard and the definition cannot drift.
- [x] `app/secret_key_guard.py` -- new module: `validate_secret_key(config, logger)` implementing the I/O matrix; raise `app.exceptions.ConfigurationError` on the non-debug branch, `logger.error(...)` on the debug/testing branch, return silently otherwise. Docstring states why the debug branch only logs.
- [x] `app/__init__.py` -- call `validate_secret_key(app.config, app.logger)` between `setup_logging(app)` and `init_request_limits(app)`, and extend the existing ordering comment to cover it.
- [x] `tests/unit/test_secret_key_guard.py` -- new `@pytest.mark.unit` module covering every row of the I/O matrix through `create_app(...)` with `storage_backend=test_storage`, plus the single-home assertion below.
- [x] `.env.example` -- add a comment above `SECRET_KEY` stating that a non-debug app refuses to start without it.

**Acceptance Criteria:**
- Given a config class with `DEBUG=False` and `TESTING=False` whose `SECRET_KEY` is the fallback constant, when `create_app()` is called, then it raises `ConfigurationError` whose message contains `SECRET_KEY` and whose `config_key` is `'SECRET_KEY'`, and no app object is returned.
- Given `config.py` is read as text, when the fallback literal is counted, then it appears exactly once — proving the guard compares against the definition rather than a copy.
- Given the guard is inserted, when `inspect.getsource(create_app)` is examined, then the guard call appears after `setup_logging(` and before `csrf.init_app(`.
- Given the existing suite, when `nox -s tests` runs, then it passes with no new failures (the `tests/test_config.TestConfig` used by `tests/conftest.py` sets a non-fallback `SECRET_KEY`, so no existing test hits either new branch).

## Spec Change Log

## Review Triage Log

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 14: (high 0, medium 6, low 8)
- defer: 1: (high 0, medium 1, low 0)
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[medium]` `[patch]` The guard recognised only the fallback, while the repo publishes two more `SECRET_KEY` placeholders (`.env.example`, `docs/deployment-guide.md`) — including the one the deployment guide told operators to paste into a **production** `.env`. Added `config.PUBLISHED_SECRET_KEYS` (never-shrinking) and made the guard check membership.
  - `[medium]` `[patch]` `docs/deployment-guide.md:64` handed out `SECRET_KEY=your-secret-key-here-change-this` in its production `.env` block. Replaced with an empty value plus a comment pointing at the key-generation step; the old literal stays in the set so existing `.env` files are still caught.
  - `[medium]` `[patch]` `python app.py` — the documented dev entrypoint — would refuse to boot on a fresh checkout: it passes `debug=True` to `app.run()` *after* `create_app()` has read a `DEBUG=False` config, and unlike `flask run` it never reads `.flaskenv`. `app.py` now `os.environ.setdefault('FLASK_DEBUG', '1')` before importing the factory.
  - `[medium]` `[patch]` `config.get('DEBUG') or config.get('TESTING')` was a bare truthiness test, so the string `'False'` — what an unguarded `os.environ.get('FLASK_DEBUG')` yields — read as debug-on and downgraded a production refusal to a log line. Now only the boolean `True` counts (fail-closed).
  - `[medium]` `[patch]` A whitespace-only `SECRET_KEY` is truthy, so `config.py`'s `or` never reached the fallback and the guard saw a "real" key: the app signed cookies with spaces, silently. Blank, missing and wrong-type keys are now refused on the same terms, each with its own diagnosis.
  - `[medium]` `[patch]` The added `.env.example` text claimed a blank value falls back (false) and named `DEBUG`/`TESTING` rather than the `FLASK_DEBUG` on the next line. Rewritten, including the fact that copying the file as-is yields a debug app that logs once per boot.
  - `[low]` `[patch]` A published key spelled as `bytes`, or carrying surrounding whitespace, compared unequal. The guard now decodes utf-8 bytes and strips before comparing (undecodable bytes — `secrets.token_bytes(32)` — stay valid).
  - `[low]` `[patch]` The "before `csrf.init_app` so a forgeable key is never armed" rationale in `app/__init__.py` and the guard docstring was vacuous: a raise anywhere in the factory aborts the boot equally. Reworded to state the one real dependency (`setup_logging`) and mark the position a preference.
  - `[low]` `[patch]` The ordering test indexed raw `inspect.getsource` output, so the 20-line comment block naming the same functions could satisfy or break it. Now strips comment lines first, and is split into a requirement test and a preference test.
  - `[low]` `[patch]` `test_the_factory_passes_app_config_and_app_logger` asserted an exact source substring; a line wrap would have failed it. Now a whitespace-tolerant regex.
  - `[low]` `[patch]` The no-copy check inspected only `validate_secret_key`'s body, so a copy in a module-level constant passed. Now reads the whole module file, for every published key.
  - `[low]` `[patch]` The two "logs nothing" tests asserted `== []` over *all* ERROR records, so any unrelated startup error would fail them pointing at this guard. Narrowed to records naming `SECRET_KEY`.
  - `[low]` `[patch]` `typing.Mapping` → `collections.abc.Mapping` (deprecated spelling in a new 3.13 module).
  - `[low]` `[patch]` Function-local `import os` in the test module hoisted to the top.

### 2026-07-28 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 3, low 6)
- defer: 5: (high 0, medium 2, low 3)
- reject: 6: (high 0, medium 0, low 6)
- addressed_findings:
  - `[medium]` `[patch]` The refusal branch emitted **nothing** through the logging pipeline the call was deliberately ordered behind `setup_logging` to reach — only a stderr traceback. The branch that matters most was the one branch invisible to an operator aggregating JSON logs. Now `logger.critical(problem)` immediately precedes the raise (CRITICAL, not ERROR, so a stopped boot is distinguishable from a debug app that carried on), with tests at both the `create_app` and unit levels.
  - `[medium]` `[patch]` `SECRET_KEY=` — exactly what the previous pass changed `docs/deployment-guide.md` to prescribe — is falsy, so `config.py`'s `or` resolves it to the fallback and the operator got "set to a placeholder that is committed to this repository" about a placeholder they never wrote. `_PUBLISHED` now reads "unset, empty, or set to a placeholder committed to this repository", which is true of all three ways of reaching it.
  - `[medium]` `[defer → DW-234]` Nothing automated exercises the shipped `config.Config` through `wsgi.py`; every scenario goes through a hand-built subclass, so a regression in `config.py`'s `SECRET_KEY`/`DEBUG` resolution would leave the suite green. The fix — cold-import subprocess tests — was written and verified green (6 boots: every published key, unset, a private key, the debug path) and then **reverted**: the intent contract's **Never** list forbids cold-import subprocesses, and an automated pass may not amend an intent contract. The contract's stated reason is factually wrong (`dotenv.load_dotenv` defaults to `override=False`, so a child's environment wins deterministically, and `test_request_limits.py::TestColdInterpreterImports` already relies on that), which is why this is deferred as a human decision rather than rejected. The test module's docstring now records the true reason for the absence instead of repeating the false one, and the manual equivalents are in Verification below.
  - `[medium]` `[patch]` `config.py` claimed `PUBLISHED_SECRET_KEYS` holds "EVERY `SECRET_KEY` value this repository has published", which is false — `tests/test_config.py:21` commits another one. The comment now states the real invariant ("could a deployment end up running this?") and records why the test key is deliberately excluded: it is reachable only from `TESTING = True`, and adding it would make every unit-test app boot emit an ERROR about a key no deployment can resolve to.
  - `[low]` `[patch]` `os.environ.setdefault('FLASK_DEBUG', '1')` sat at `app.py` module scope, mutating the whole process's environment — and `DEBUG=True` is precisely what disarms the refusal. Moved into `if __name__ == '__main__':` along with the factory import, so loading the file cannot flip the switch as an import side effect. Pinned by an AST test rather than a substring check.
  - `[low]` `[patch]` A placeholder retyped or autocapitalised (`Your-Secret-Key-Here`) compared unequal. Membership is now tested casefolded — same fail-closed direction as the existing whitespace strip, and no random key is one casefold from a published one.
  - `[low]` `[patch]` `_BLANK` asserted "being non-empty, it does NOT trigger the fallback in config.py", which is true only for whitespace-only values; `''` reaches it solely via a config class that hard-codes it. Reworded to cover both without the false claim.
  - `[low]` `[patch]` The remedy drifted three ways: the guard and `.env.example` said `token_hex(32)` while `docs/deployment-guide.md:170` said `token_urlsafe(32)` — and the previous pass's new `.env` comment points the operator at exactly that section. Harmonised on `token_hex`, with a line stating that the generator is not what matters (nothing checks format).
  - `[low]` `[patch]` The guard's docstring justified the log-only branch with "a forgeable cookie only matters where untrusted clients can reach the app, and that is exactly the case where `DEBUG` and `TESTING` are both false" — contradicted by `flask run --host=0.0.0.0` and by `tests/e2e/test_server.py`, which boots a real listening server from a `TESTING` config. Replaced with the argument that actually holds: a debug app has already accepted the Werkzeug debugger, a strictly larger exposure. The docstring now also records the `.flaskenv` hole (DW-230) and the absence of a quality floor (DW-233).
  - `[low]` `[patch]` `test_the_app_boots_and_logs_one_error_naming_secret_key` de-duplicated messages before counting, so it could not distinguish one guard call from ten while its name claimed to pin "one error". Renamed to `..._logs_a_single_diagnosis_...` and its docstring now points at the unit-level test that does pin exactly-once.

### 2026-07-28 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 1, low 8)
- defer: 2: (high 0, medium 0, low 2)
- reject: 9: (high 0, medium 0, low 9)
- addressed_findings:
  - `[medium]` `[patch]` `app.py` set `FLASK_DEBUG` **before** `config.py`'s `load_dotenv` ran, and `load_dotenv` defaults to `override=False` — so an operator's `FLASK_DEBUG=0` in `.env` was silently discarded and the app came up in debug, which is exactly what disarms the refusal. The comment promising "an explicit FLASK_DEBUG=0 still wins" was true only of a shell variable, not of the `.env` the documentation tells people to write. `app.py` now loads `.env` first and only then defaults; a blank `FLASK_DEBUG=` counts as unset (it satisfied `setdefault` while parsing as OFF, which would have made `python app.py` refuse to boot for the very reason the line exists).
  - `[low]` `[patch]` The guard ignored `SECRET_KEY_FALLBACKS`. Flask 3.1 still **validates** session cookies and CSRF tokens against every key in that list, so a published key left there after a rotation is forgeable even when `SECRET_KEY` itself is private — and leaving the old value behind is precisely what Flask's documented rotation produces. Every entry now gets the same diagnosis, with `SECRET_KEY` itself reported first when both are wrong.
  - `[low]` `[patch]` The CRITICAL record accompanying a refusal was byte-identical to the ERROR record a debug app emits; only the level field distinguished "this process is dying" from "this developer carried on". The refusal now logs the same `Refusing to start: …` text it raises.
  - `[low]` `[patch]` `_PUBLISHED_CASEFOLDED` casefolded the published keys but did not strip them, while `_diagnose` strips the candidate. Since entries are never removed, one added with a stray space would have matched nothing, permanently and silently. Both sides are now normalised identically.
  - `[low]` `[patch]` `test_the_default_is_confined_to_running_the_script` treated *any* module-level `if` as the `__main__` guard and excluded all of them from its "not at module scope" check — so a `FLASK_DEBUG` mutation under some other top-level conditional would have passed the test that exists to forbid exactly that. Now matched on the `__name__` test.
  - `[low]` `[patch]` `test_flask_debug_is_defaulted_before_the_factory_is_imported` indexed raw `app.py` source, comments included, twelve lines after `_factory_statements()` strips comments for the same class of assertion and documents why. Comment stripping is now a shared helper used by both.
  - `[low]` `[patch]` `test_it_is_a_default_not_an_override` asserted the presence of the string `setdefault` and the absence of an assignment — a claim about spelling, not about behaviour. Replaced with an AST check that the write is guarded by a condition reading the current value and treating blank as unset.
  - `[low]` `[patch]` `test_an_unset_or_blank_key_refuses_a_non_debug_boot` parametrized `None` and `''` under a docstring asserting "a blank value is non-empty, so `config.py`'s `or` does not even reach the fallback" — true only of the whitespace-only cases. Reworded to name both routes (the same correction `_BLANK` itself received last pass).
  - `[low]` `[patch]` `docs/deployment-guide.md`'s production `.env` still set `FLASK_ENV=production` — removed in Flask 2.3 and ignored by the installed 3.1.3 — three lines above a new callout teaching that debug state is what decides whether the refusal fires. Replaced with `FLASK_DEBUG=0` and a note; `FLASK_APP` moved to `wsgi.py`, matching `.flaskenv` and the guide's own "serve through `wsgi.py`".
  - `[low]` `[patch]` `app.py` had no trailing newline.

## Design Notes

The guard is a separate leaf module rather than inline factory code so it is unit-testable on its own and so `create_app` keeps delegating, matching `app/request_limits.py`. It raises the `app.exceptions` `ConfigurationError` (not the `config.py` leaf one) for parity with `validate_limits`; the two are one hierarchy — `app.exceptions.ConfigurationError` subclasses `config.ConfigurationError` — so either is caught by `except config.ConfigurationError`.

`app/error_handlers.py` already registers `ConfigurationError`, but that registration is about request-time rendering; a raise from `create_app()` happens before any request exists and therefore aborts the boot. That is the intended outcome, not a gap.

Note `config.TestConfig` (used by `tests/e2e/test_server.py`, `tests/test_database.py`, `tests/integration/conftest.py`) defines no `SECRET_KEY` of its own and has `TESTING=True`, so wherever it does resolve to the fallback it can only take the log branch. Whether it actually resolves to the fallback is **environment-dependent**: `config.py` calls `load_dotenv` at import, so a checkout whose `.env` defines `SECRET_KEY` (as a configured developer machine does) never reaches the fallback at all. Tests therefore assert on the `TESTING` flag, which decides the branch, and never on the resolved value.

Two existing tests assert on the absence of WARNING/ERROR output (`tests/unit/test_request_limits.py:2302` and `:3048`); both build apps from `tests/test_config.py::TestConfig`, which sets a non-fallback `SECRET_KEY`, so neither is affected.

One `logger.error` call surfaces as more than one captured line: `setup_logging` installs a JSON handler on `app.logger`, a plain-text ERROR handler, and a third JSON handler on the root logger that `app.logger` propagates to. This fan-out predates the guard (every startup warning already lands twice), so the tests compare distinct messages rather than counting lines.

**Widened after review** (the I/O matrix above remains true; these are additional unsafe states the guard also refuses, all in the fail-closed direction):

- The comparison is against `config.PUBLISHED_SECRET_KEYS`, not the fallback alone — the repository publishes three placeholder keys, and the deployment guide used to offer one of them as production `.env` content. Entries are never removed: a `.env` created from the old text still contains the old value.
- Unset, blank/whitespace-only, and non-string/non-bytes keys are refused with their own diagnoses. A whitespace-only value is truthy, so `config.py`'s `or` never reaches the fallback — that state was strictly worse than the one this story set out to catch, and was invisible.
- `DEBUG`/`TESTING` count as on only for the boolean `True`. A truthiness test would read the string `'False'` as debug-on and downgrade a production refusal to a log line.
- `app.py` declares `FLASK_DEBUG` before importing the factory. It already ran `app.run(debug=True)` against a config built with `DEBUG=False`; that latent incoherence became a boot failure once the guard existed, because `.flaskenv` (which carries `FLASK_DEBUG=1`) is read only by the Flask CLI, not by `python app.py`. **Follow-up review:** that declaration now lives inside `if __name__ == '__main__':`, with the factory import, because it mutates the environment of the whole process and `DEBUG=True` is exactly what disarms the refusal — a control that can be switched off by importing a file is not a control.

**Widened again by the follow-up review** (same fail-closed direction; the I/O matrix still holds):

- The refusal is logged at CRITICAL as well as raised. The raise alone reaches only stderr, unstructured; the ordering constraint that puts this call after `setup_logging` bought observability for the debug branch and nothing for the branch that stops a deployment.
- Membership is tested casefolded, so a retyped or autocapitalised placeholder is caught.
- The `_PUBLISHED` diagnosis names all three routes to a published value (unset / empty / placeholder), because `config.py`'s `or` collapses the first two into the third before the guard sees them — and `SECRET_KEY=` is what the deployment guide now tells an operator to write.

**Widened once more by the second follow-up review** (same fail-closed direction; the I/O matrix still holds):

- `SECRET_KEY_FALLBACKS` is held to the same standard as `SECRET_KEY`. Flask 3.1 keeps **validating** cookies and tokens against every entry in that list while a new key signs, so a published value parked there is forgeable even though the primary key is private. Nothing in the repository sets it today; the check is there because the rotation Flask documents is the procedure that leaves the old value behind. `SECRET_KEY` itself is diagnosed first when both are wrong, so the operator is not told to fix the list while the app still signs new cookies with a public key.
- `app.py` loads `.env` **before** applying its `FLASK_DEBUG` default. `load_dotenv` defaults to `override=False`, so the previous order meant a value written by `app.py` beat the operator's own `.env` — silently, and in the fail-open direction, since `DEBUG=True` is what disarms the refusal. Blank now counts as unset, because `FLASK_DEBUG=` satisfies "already set" while parsing as OFF.

**Known holes, recorded rather than closed** (see the deferred-work ledger):

- `.flaskenv` is committed with `FLASK_DEBUG=1`, so `flask run` from a checkout takes the log branch, not the refusal (DW-230). Such a deployment is also running the Werkzeug debugger, which is a larger problem than its signing key, and closing it is a decision about development ergonomics rather than about this guard. The deployment guide and the guard's docstring now say so explicitly.
- There is no key-quality floor: `SECRET_KEY=x` boots (DW-233). The guard answers "is this a key the repository handed out?", not "is this key strong".
- `tests/test_config.py` commits a key that is deliberately *not* in `PUBLISHED_SECRET_KEYS`: it is reachable only from `TESTING = True`, so adding it would put an ERROR in every unit-test boot about a value no deployment can resolve to.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: passes, including the new `tests/unit/test_secret_key_guard.py`. Actual: **3514 passed, 2 skipped, 466 deselected**.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: passes (no `app/utils/` change, so this is a regression guard only). Actual: **22 passed**.
- Real-entrypoint checks, forcing non-debug because the repo `.env` sets `FLASK_DEBUG=True` and a real `SECRET_KEY` (which is why the unit tests build config subclasses instead of relying on the environment):
  - `FLASK_DEBUG=False SECRET_KEY='dev-secret-key-change-in-production' venv/bin/python -c "import wsgi"` -- expected and observed: `ConfigurationError: Refusing to start: SECRET_KEY is set to a placeholder ...`. Same for `your-secret-key-here` and for `'   '` (blank diagnosis).
  - `FLASK_DEBUG=False SECRET_KEY='a-real-private-key' venv/bin/python -c "import wsgi"` -- expected and observed: boots.
  - `env -u FLASK_DEBUG SECRET_KEY='dev-secret-key-change-in-production'` running `app.py`'s module body -- expected and observed: `FLASK_DEBUG` defaults to `1`, the app boots with `DEBUG=True`, and one ERROR naming `SECRET_KEY` is logged. With `FLASK_DEBUG=0` set explicitly it stays `0`.

**Follow-up review pass (2026-07-28):**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: passes with the 6 added tests. Actual: **3520 passed, 2 skipped, 466 deselected** (was 3514). An earlier run of this pass reached 3526 with 6 cold-subprocess tests of `wsgi.py`, all passing; they were reverted because the intent contract forbids that test shape (DW-234), so the manual checks below stand in for them.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- Actual: **22 passed**.
- `FLASK_DEBUG=0 SECRET_KEY='' venv/bin/python -c "import wsgi"` -- expected and observed: exit code 1, and the diagnosis now appears at `"level": "CRITICAL"` in the JSON stream as well as in the traceback. The message reads "SECRET_KEY is unset, empty, or set to a placeholder ...", which fits an operator whose `.env` says `SECRET_KEY=`.
- Importing `app.py` by path in a fresh interpreter (`importlib.util.spec_from_file_location`) -- expected and observed: `os.environ.get('FLASK_DEBUG')` is still `None` afterwards. Before this pass it was `'1'`.
- `env -u FLASK_DEBUG SECRET_KEY='dev-secret-key-change-in-production' venv/bin/python app.py` -- expected and observed: still boots `DEBUG=True` and logs one ERROR naming `SECRET_KEY`; the `__main__` move did not change the documented dev entry point.
- `git ls-files --error-unmatch .flaskenv` succeeds and the file sets `FLASK_DEBUG=1` -- the basis for DW-230.
- Three consecutive refused `create_app()` calls leave `performance`/`api_access`/`inventory` at 3 handlers each -- the basis for DW-231.
- `nox -s e2e` not run (20-minute session, out of scope for a review pass). No template, CSS or JS changed, so no screenshot regeneration is implied.

**Second follow-up review pass (2026-07-28):**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- Actual: **3535 passed, 2 skipped, 466 deselected** (was 3520; +15 tests).
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- Actual: **22 passed**.
- `FLASK_DEBUG` precedence, exercised as a standalone reproduction of `app.py`'s block in a scratch directory (the repo `.env` could not be edited for this): with `.env` saying `FLASK_DEBUG=0` and nothing in the shell, the resolved value is `'0'` -- the operator's `.env` now wins, where before this pass `app.py`'s `'1'` did. With `.env` saying `0` and the shell saying `1`, the shell wins (`'1'`). With no `.env` entry and `FLASK_DEBUG=` in the shell, the blank is treated as unset and becomes `'1'`.
- `FLASK_DEBUG=0 SECRET_KEY='' venv/bin/python -c "import wsgi"` -- exit code 1, and the JSON stream now carries `"level": "CRITICAL"` with the message `Refusing to start: SECRET_KEY is unset, empty, or set to a placeholder ...` -- the same text that is raised, prefix included.
- `FLASK_DEBUG=0 SECRET_KEY='a-real-private-key' venv/bin/python -c "import wsgi"` -- boots.
- `env -u FLASK_DEBUG SECRET_KEY='dev-secret-key-change-in-production' venv/bin/python app.py` -- still boots with the debugger active and logs one ERROR naming `SECRET_KEY`; no CRITICAL, no refusal. With `FLASK_DEBUG=0` set explicitly in the shell it refuses, naming `SECRET_KEY`.
- `SECRET_KEY_FALLBACKS` branch driven directly (no config class in the tree sets it): a private `SECRET_KEY` with `[DEV_SECRET_KEY_FALLBACK]` in the list raises with `config_key='SECRET_KEY'` and a message naming `SECRET_KEY_FALLBACKS`; the same config with no fallback list returns silently.
- `flask.helpers.get_debug_flag` compared against `config.py`'s parser across `on`/`y`/`t`/`enabled` -- all four are debug-on to Flask and debug-off to `config.py`. Fail-closed for this guard; recorded as DW-236 rather than "fixed", since agreeing with Flask would widen the disarm surface.
- `nox -s e2e` not run (20-minute session, out of scope for a review pass). No template, CSS or JS changed.

## Auto Run Result

Status: done — second follow-up review pass complete.

**Implemented change (this pass).** No new feature: an independent adversarial + edge-case review of the shipped guard, with nine fixes applied. The one that matters most closes a fail-open path in `app.py` — it declared `FLASK_DEBUG` *before* `.env` was read, and `load_dotenv` does not override, so an operator who turned debug off in `.env` got a debug app and a refusal downgraded to a log line, under a comment promising the opposite. The guard itself gained one real widening (`SECRET_KEY_FALLBACKS`, which Flask still validates against) and two normalisation/observability corrections; the rest are test-strength and documentation fixes, including three tests that asserted spellings rather than behaviour.

**Files changed**
- `app.py` — `.env` is loaded before the `FLASK_DEBUG` default is applied, and the default is now conditional on the current value being absent *or blank* rather than on `setdefault`. Comment rewritten to state why the order decides who wins. Trailing newline added.
- `app/secret_key_guard.py` — `SECRET_KEY_FALLBACKS` diagnosed on the same terms as `SECRET_KEY` (`_fallbacks_are_unsafe`, `_FALLBACKS`), with the primary key reported first; the refusal logs the same `Refusing to start: …` text it raises; `_PUBLISHED_CASEFOLDED` strips as well as casefolds.
- `docs/deployment-guide.md` — `FLASK_ENV=production` (dead since Flask 2.3) replaced by `FLASK_DEBUG=0` with an explanation; `FLASK_APP` pointed at `wsgi.py`.
- `tests/unit/test_secret_key_guard.py` — +15 tests: the whole `SECRET_KEY_FALLBACKS` matrix, the refusal's log text, and a rewritten `app.py` group (AST-based, matching the `__main__` guard on its `__name__` test and pinning `.env`-before-default ordering). Comment stripping is now a shared helper. Two docstrings corrected.
- `_bmad-output/implementation-artifacts/deferred-work.md` — DW-235, DW-236 appended (new entries only).

**Review findings.** 0 intent_gap, 0 bad_spec, 9 patch (1 medium, 8 low — all applied), 2 defer, 9 reject. Full breakdown in the Review Triage Log.

**Deferred.** DW-235 (`wsgi.py`'s `__main__` block runs `app.run(debug=True)` on an app already built non-debug — low), DW-236 (`config.py` and Flask disagree on which `FLASK_DEBUG` spellings mean debug; fail-closed here, but the resulting `SECRET_KEY` error names nothing that points at the spelling — low).

**Rejected.** `.env.example` still shipping a placeholder while the guide ships a blank (both refuse identically; the template behaviour was deliberate and was rejected on the same grounds last pass); `LOG_LEVEL=CRITICAL` suppressing the debug-branch ERROR (already a recorded residual risk, and the refusal branch now logs at CRITICAL and survives it); the absence of cold-import/`wsgi.py` coverage (open as DW-234, awaiting a human); undecodable bytes passing unconditionally (deliberate — `secrets.token_bytes`); a published placeholder wrapped in literal quotes by systemd/YAML (speculative); the absence of a test pinning that `TESTING` is never derived from the environment (speculative future-proofing of prose); `_MISSING`/`_UNUSABLE` being reachable only from hand-built mappings (defensive by design); the ordering rationale being restated in the module, the factory and two test docstrings, and `logger: Any` (style); and the removal of `app.py`'s module-scope `create_app` binding (verified to have no importer).

**Residual risks.**
- DW-230 remains the real limit on this control: `.flaskenv` commits `FLASK_DEBUG=1`, so `flask run` from a checkout is a debug app and takes the log branch. Documented in four places now, closed in none.
- The regression guard for the real boot path is still missing (DW-234). Everything above was verified by hand.
- `PUBLISHED_SECRET_KEYS` is still hand-maintained; a fourth placeholder introduced in a future document is protected only if someone adds it.
- `SECRET_KEY_FALLBACKS` is checked but is not reachable from any config in this tree, so its tests exercise the function rather than a shipped path — the same gap DW-234 records for `SECRET_KEY` itself.
- The `app.py` fix is verified by an equivalent reproduction in a scratch directory plus source/AST assertions, not by a subprocess running the real file with a controlled `.env`; the intent contract forbids that test shape (DW-234).
- `nox -s e2e` was not run.


