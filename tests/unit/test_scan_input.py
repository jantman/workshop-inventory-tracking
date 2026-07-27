"""
Unit tests for `app/utils/scan_input.py` — the scan-text rule (FR35).

One test module per pure util, as for `ecia.py`, `gs1.py`, `gtin.py`,
`internal_id.py`, `category.py` and `tag.py`. These assertions were written for
Story 4.1 and lived in `tests/unit/test_scan_routes.py` while the rule itself
lived beside the `/api/scan` handler; they moved here unchanged when the rule
did (DW-59). What stayed behind is the route's own behavior — the length
refusal, the blank refusal, the log lines — which is endpoint conduct rather
than a property of this function.

The rule's other two guards, for orientation:

* `tests/unit/test_scan_trim_rule.py` compares the JavaScript copy of the trim
  set (`ScanCapture.stripOuter`) against `SCAN_TRIM` as source text.
* `tests/e2e/test_wedge_scan.py` proves the two agree in a real browser.

The two constants are pinned as literals where their consequence lives, not a
third time here: `SCAN_TRIM` in `test_scan_trim_rule.py` (beside the JS copy it
has to equal) and `MAX_SCAN_LENGTH` in `test_scan_routes.py` (beside the
refusal message that quotes it).
"""

import pytest

from app.utils.scan_input import clean_scan_input


@pytest.mark.unit
class TestCleanScanInput:
    """The one narrow whitespace rule, isolated from the transport."""

    @pytest.mark.parametrize('value, expected', [
        ('  0123 \r\n', '0123'),                     # every trimmed character at once
        (' 0123', '0123'),                           # leading space
        ('0123 ', '0123'),                           # trailing space
        ('\t0123\t', '0123'),                        # tabs
        ('\r\n0123\r\n', '0123'),                    # CR/LF a wedge may append
        ('a b\tc', 'a b\tc'),                        # interior whitespace kept
        ('96WITabc', '96WITabc'),                    # case never folded
        ('', ''),                                    # empty stays empty
        ('   ', ''),                                 # whitespace-only collapses to blank
    ])
    def test_trims_only_space_tab_cr_lf(self, value, expected):
        """FR35: leading/trailing space, tab, CR and LF only."""
        assert clean_scan_input(value) == expected

    @pytest.mark.parametrize('value', [
        '\x1dP123',                                  # leading GS
        '[)>\x1e06\x1dP123\x1e\x04',                 # full ISO/IEC 15434 format-06 envelope
        '\x1e06\x1d',                                # bare RS/GS pair
        '\x04',                                      # trailing EOT alone
        '\x1c\x1f',                                  # FS/US - str.strip() would eat these
    ])
    def test_iso15434_control_characters_are_never_trimmed(self, value):
        """A bare str.strip() eats \\x1c-\\x1f; Story 4.4's parser needs them."""
        assert clean_scan_input(value) == value

    @pytest.mark.parametrize('char', [
        '\x0b',                                      # VT - a programmable wedge suffix
        '\x0c',                                      # FF - likewise
        '\x00',                                      # NUL
    ], ids=['vertical_tab', 'form_feed', 'nul'])
    def test_other_control_characters_are_also_never_trimmed(self, char):
        """Pins the exact boundary of `SCAN_TRIM`.

        FR35 names space, tab, CR and LF and nothing else, so these survive
        even though `str.strip()` would remove \\x0b and \\x0c. If a scanner is
        ever programmed with one of these as a suffix, Story 4.4 sees it in the
        payload — that is a deliberate consequence of the narrow rule, not an
        oversight, and this test exists so changing it is a conscious act.
        """
        assert clean_scan_input(f'{char}P123{char}') == f'{char}P123{char}'

    def test_bare_strip_would_have_destroyed_the_envelope(self):
        """Guards the reason `SCAN_TRIM` is explicit rather than defaulted.

        Python classifies \\x1c-\\x1f as whitespace, so `str.strip()` with no
        argument eats the record separator that terminates an ISO/IEC 15434
        record — Story 4.4 would then parse a truncated envelope.
        """
        envelope = '[)>\x1e06\x1dP123\x1e'
        assert envelope.strip() == '[)>\x1e06\x1dP123'   # this is what NOT to do
        assert clean_scan_input(envelope) == envelope    # RS survives


@pytest.mark.unit
class TestPurity:
    """AD-4: the module's own body reaches for nothing outside the stdlib.

    A statement about `scan_input.py` itself, not about the cost of importing
    it package-qualified — that still runs `app/__init__.py`, as it does for
    every other pure util here. What this pins is that the rule can be read and
    applied without an app context, a config or a database.

    Stdlib imports are allowed, which is the contract the module's own
    docstring states and the one every sibling pure util keeps: `ecia.py`
    imports `re`, `gs1.py` imports `dataclasses`, `internal_id.py` imports
    `secrets`. `scan_input.py` happens to need none of them today, but adding
    `from typing import Optional` to a signature would not make it impure and
    must not turn this red.
    """

    def test_the_module_imports_nothing_outside_the_standard_library(self):
        import ast
        import sys
        from pathlib import Path

        import app.utils.scan_input as module

        tree = ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
        offenders = []
        for node in ast.walk(tree):
            # A deferred import is still an import. `importlib.import_module`
            # and `__import__` reach exactly as far as the statement forms do
            # while leaving no Import node to walk, so a dependency hidden in
            # a function body would otherwise pass a test whose message
            # asserts the module depends on nothing.
            if isinstance(node, ast.Call):
                target = node.func
                dotted = (f'{getattr(target.value, "id", "")}.{target.attr}'
                          if isinstance(target, ast.Attribute)
                          else getattr(target, 'id', ''))
                if dotted in ('__import__', 'importlib.import_module',
                              'import_module'):
                    offenders.append(f'line {node.lineno}: {dotted}(...)')
                continue
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # `level > 0` is a relative import, which inside `app/utils/`
                # can only be an `app.*` one however it is spelled.
                names = ['.' * node.level + (node.module or '')]
            else:
                continue
            for name in names:
                root = name.split('.')[0]
                if root == 'app' or root not in sys.stdlib_module_names:
                    offenders.append(f'line {node.lineno}: {name}')

        assert offenders == [], (
            'app/utils/scan_input.py has grown a non-stdlib import '
            f'({", ".join(offenders)}): the scan trim rule is meant to be '
            'readable by anything, and a dependency here is a dependency for '
            'every consumer of the rule')
