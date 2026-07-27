"""
Source tripwires for the two document-level keydown focus guards (DW-56, DW-64).

Both of the app's global `keydown` listeners used to act without asking what had
focus:

* `app/static/js/main.js`'s shortcut handler early-returned while the operator
  was typing — but *only* when no modifier was held. A keyboard wedge emits
  ASCII control characters as Ctrl chords (GS as `Ctrl`+`]`, RS as `Ctrl`+`^`),
  so a scan burst walked straight through that exemption into the shortcut
  table with `#scan-input` focused: `Ctrl`+`/` toasted "Focus Search" mid-burst
  and `Ctrl`+`Shift`+`/` opened the help modal, taking the focus the rest of the
  burst needed (DW-64).
* `app/static/js/inventory-add.js`'s barcode buffer appended every printable key
  and `preventDefault()`ed it whenever scan mode was armed, so typing into any
  field on `/inventory/add` — including the navbar scan field — was swallowed
  (DW-56).

Both are now gated on one shared predicate, `WorkshopInventory.utils
.isFieldFocused()`, which reads `document.activeElement` at keydown time.

The behavioral proof lives in `tests/e2e/test_keydown_focus_guards.py`, but the
e2e session takes ~20 minutes and is not what a developer runs before pushing —
and there is no JS unit-test harness in this repo (see
`tests/unit/test_toast_markup.py`, whose shape this file follows). So the
guards' *structure* is asserted here as text, in the fast `nox -s tests`
session: a regression that re-adds the modifier escape hatch, or moves the
add-page guard below the timeout it must precede, fails in seconds.

Structure is all it can assert, and the limit is worth stating plainly rather
than discovering later. Nothing here executes a line of JavaScript, so it reads
that the guards are present, correctly shaped and correctly ordered — never
that they answer correctly. A predicate whose body is `return !(...)`, which
inverts both fixed defects at once, passes every test in this module. That is
the e2e file's job, and this one does not stand in for it.

Where practical the regexes pin the invariant rather than an identifier: the
toast gate, for instance, captures whatever variable receives
`shortcut.action(...)` and then demands the conditional test that same variable,
so renaming it is not a failure but decoupling the toast from it is.
"""

import re
from pathlib import Path

import pytest

STATIC_JS = Path(__file__).resolve().parents[2] / 'app' / 'static' / 'js'
MAIN_JS = STATIC_JS / 'main.js'
INVENTORY_ADD_JS = STATIC_JS / 'inventory-add.js'

#: Members of the top-level `WorkshopInventory` object literal are indented four
#: spaces and each closes on its own `    },` line; members of the nested
#: `utils` literal use eight. Those terminators bound a function without
#: brace-counting a language this module does not parse, the same way
#: `tests/unit/test_toast_markup.py` does. Reformatting the file makes the
#: extraction fail loudly instead of silently matching everything.
OBJECT_MEMBER_END = re.compile(r'^    \},$', re.MULTILINE)
UTILS_MEMBER_END = re.compile(r'^        \},$', re.MULTILINE)

#: `inventory-add.js` is an ES6 class, so its methods close on `    }` with no
#: comma.
CLASS_METHOD_END = re.compile(r'^    \}$', re.MULTILINE)

#: The selector deciding which elements count as "typing". Kept verbatim from
#: the handler it was lifted out of — widening or narrowing it changes which
#: keystrokes the app considers the operator's, which is a product decision and
#: not something a refactor should do by accident.
FIELD_SELECTOR = "'input, textarea, select, [contenteditable]'"


def _slice(source, start_marker, end_pattern, what):
    """The CODE of one function, bounded by its terminator line.

    Full-line `//` comments are dropped, because several assertions below are
    about ORDER — "the guard runs before the `clearTimeout`" — and the comment
    explaining that placement necessarily names `clearTimeout` while sitting
    above it. Matching prose would invert the very check it documents.

    Only whole-line comments go: every comment in the three slices this module
    extracts is one, and a blanket strip would have to reason about `//` inside
    string literals, which none of these functions contain either.
    """
    start = source.find(start_marker)
    assert start != -1, (
        f'{what} is gone or was renamed: `{start_marker}` no longer appears, so '
        f'nothing below is checking the guard it is supposed to contain')

    end = end_pattern.search(source, start)
    assert end is not None, (
        f'could not find the end of {what}: the indentation this tripwire bounds '
        f'on has changed, so the slice it checks is no longer that function')
    return '\n'.join(line for line in source[start:end.start()].splitlines()
                     if not line.lstrip().startswith('//'))


def _braced_block(source, open_brace_index):
    """The text between `source[open_brace_index]` == '{' and its match.

    Brace-counted rather than regex-matched because the block under test
    contains a template literal (`${name}`) whose own braces would terminate any
    `[^}]*` shortcut. The counting is safe on these slices — they hold no string
    literal with an unbalanced brace — and it is what lets "the toast is INSIDE
    the conditional" be asserted rather than merely "appears after it".
    """
    assert source[open_brace_index] == '{'
    depth = 0
    for index in range(open_brace_index, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[open_brace_index + 1:index]
    raise AssertionError('unbalanced braces while bounding a block')


def _setup_keyboard_shortcuts():
    return _slice(MAIN_JS.read_text(encoding='utf-8'),
                  'setupKeyboardShortcuts: function',
                  OBJECT_MEMBER_END, 'setupKeyboardShortcuts')


def _is_field_focused():
    return _slice(MAIN_JS.read_text(encoding='utf-8'),
                  'isFieldFocused: function',
                  UTILS_MEMBER_END, 'utils.isFieldFocused')


def _setup_barcode_scanning():
    # The leading newline + indent pins the METHOD DEFINITION; a bare
    # `setupBarcodeScanning()` would match its call in `init()` first and slice
    # the wrong function.
    return _slice(INVENTORY_ADD_JS.read_text(encoding='utf-8'),
                  '\n    setupBarcodeScanning() {',
                  CLASS_METHOD_END, 'InventoryAddForm.setupBarcodeScanning')


@pytest.mark.unit
class TestFocusPredicate:
    """One predicate, asked of the live focus rather than of a tracked flag."""

    def test_predicate_reads_document_active_element(self):
        """`document.activeElement` is the whole point of the predicate.

        A focusin/focusout flag is only as good as the listeners maintaining it,
        so focus that lands before `DOMContentLoaded` (an `autofocus`
        attribute, an inline `.focus()`) leaves it reading `false` with the caret
        in a field — exactly the state DW-64's fix has to be trustworthy in.
        """
        assert 'document.activeElement' in _is_field_focused(), (
            'utils.isFieldFocused no longer reads document.activeElement: the '
            'guard is back to trusting a tracked flag that can be stale at the '
            'moment a key arrives')

    def test_predicate_keeps_the_original_field_selector(self):
        assert FIELD_SELECTOR in _is_field_focused(), (
            f'utils.isFieldFocused no longer matches against {FIELD_SELECTOR}: '
            f'which elements count as "the operator is typing" has silently '
            f'changed, so some fields lost their guard or some non-fields gained '
            f'one')

    def test_predicate_tolerates_a_missing_or_exotic_active_element(self):
        """`document.activeElement` can be `null`, and need not be an Element.

        A bare `document.activeElement.matches(...)` throws in that state, and
        this predicate runs inside a `keydown` handler — a throw there takes out
        every shortcut and, in `inventory-add.js`, the barcode buffer with it.
        """
        body = _is_field_focused()
        assert re.search(r'typeof\s+\w+\.matches\s*===\s*[\'"]function[\'"]', body), (
            'utils.isFieldFocused calls .matches() without checking it exists: a '
            'null or non-Element activeElement now throws inside a keydown '
            'handler instead of answering "no field owns focus"')

    def test_the_stale_tracked_flag_is_gone(self):
        """DW-64's acceptance criterion, verbatim.

        Leaving `inInputField` behind means there are two answers to "is the
        operator typing" and only one of them is fresh.
        """
        assert 'inInputField' not in MAIN_JS.read_text(encoding='utf-8'), (
            'the inInputField flag is back in main.js: the focusin/focusout '
            'proxy it depends on can be stale at keydown time, which is the '
            'defect utils.isFieldFocused replaced')


@pytest.mark.unit
class TestShortcutHandlerGuard:
    """The shortcut table is unreachable while a field owns keyboard input."""

    @pytest.mark.parametrize('modifier', ['ctrlKey', 'metaKey', 'altKey'])
    @pytest.mark.parametrize('spelling', [r'!\s*e\.{modifier}\b',
                                          r'e\.{modifier}\s*===?\s*false'])
    def test_no_modifier_escapes_the_focus_guard(self, modifier, spelling):
        """The exact shape DW-64 had: `... && !e.ctrlKey && !e.metaKey ...`.

        A wedge sends control characters as Ctrl chords, so any negated modifier
        in this handler is a door a scan burst walks through while the scan
        field is focused. `!shortcut.ctrl` in the match loop is a different
        thing — it tests the TABLE ENTRY, not the event — and is deliberately
        not matched here.

        Two spellings of the same negation are covered, plus
        `getModifierState` below. That is not exhaustive and cannot be from a
        text scan; it is the shapes an exemption is realistically reintroduced
        in. The behavioral guarantee is the e2e file's.
        """
        pattern = spelling.format(modifier=modifier)
        assert not re.search(pattern, _setup_keyboard_shortcuts()), (
            f'setupKeyboardShortcuts negates e.{modifier} again (matched '
            f'`{pattern}`): holding that modifier bypasses the focus guard, so '
            f'a wedge burst fires shortcuts out from under a focused '
            f'#scan-input (DW-64)')

    def test_the_handler_does_not_consult_modifiers_by_another_name(self):
        """`getModifierState` is the same exemption spelled differently."""
        assert 'getModifierState' not in _setup_keyboard_shortcuts(), (
            'setupKeyboardShortcuts inspects modifier state again: whatever it '
            'does with the answer, the focus guard is meant to be '
            'unconditional in the modifiers (DW-64)')

    def test_the_guard_returns_before_the_shortcut_table_exists(self):
        """Consulted first, and as an early return — not as one more condition.

        Ordering is the assertion. A guard evaluated after the table is built
        is a guard that can be reordered below a `preventDefault()` or an
        action, and the point of DW-64's fix is that nothing in the table can
        run while a field has focus.
        """
        body = _setup_keyboard_shortcuts()

        # Braces optional on purpose: `if (x) return;` and `if (x) { return; }`
        # are the same guard, and the two files this module checks happen to
        # write it both ways. Failing one of them for a formatter's choice would
        # be a red test about nothing, with a message pointing at the wrong
        # thing entirely.
        guard = re.search(
            r'if\s*\([^)]*isFieldFocused\s*\(\s*\)[^)]*\)\s*\{?\s*return;', body)
        assert guard is not None, (
            'the keydown handler no longer early-returns on '
            'utils.isFieldFocused(): shortcuts can run while the operator is '
            'typing (DW-64)')

        table = body.find('const shortcuts')
        assert table != -1, (
            'the `shortcuts` table is gone or was renamed — this ordering check '
            'no longer proves anything and needs rewriting')
        assert guard.start() < table, (
            'the focus guard now runs AFTER the shortcut table is built: it is '
            'no longer the first thing the handler does, so a later edit can '
            'slip an action or a preventDefault() in ahead of it')

    def test_the_confirmation_toast_is_gated_on_what_the_action_returned(self):
        """A shortcut only announces itself when it actually did something.

        `Focus Search`'s selector matches no element in any template, so an
        unconditional toast reported a focus move that never happened. The
        variable name is captured rather than assumed — renaming it is not the
        defect; showing the toast regardless of it is.
        """
        body = _setup_keyboard_shortcuts()

        assignment = re.search(
            r'\b(?:const|let|var)\s+(\w+)\s*=\s*shortcut\.action\s*\(', body)
        assert assignment is not None, (
            "nothing captures shortcut.action(...)'s return value: the "
            'confirmation toast cannot be telling the truth about whether the '
            'action ran')
        acted = assignment.group(1)

        conditional = re.search(rf'if\s*\(\s*{re.escape(acted)}\s*\)\s*\{{',
                                body[assignment.end():])
        assert conditional is not None, (
            f'`{acted}` is captured from shortcut.action(...) but never tested: '
            f'the toast fires whether or not the shortcut did anything')

        opening = assignment.end() + conditional.end() - 1
        assert 'showToast' in _braced_block(body, opening), (
            f'showToast is no longer inside `if ({acted})`: pressing "/" toasts '
            f'"Focus Search" again while focusing nothing at all')

    def test_focus_search_prevents_default_only_when_it_has_a_target(self):
        """No target, no `preventDefault()` — the keystroke stays the page's.

        `preventDefault()` used to run before the target lookup, so "/" was
        swallowed on every page in the app in exchange for nothing.
        """
        # Scoped to the `Focus Search` entry, not to the whole handler: `Help`
        # calls preventDefault() too, so a check counting occurrences from the
        # top of the function would start failing the moment the two table
        # entries are listed in the other order — and would blame the wrong one.
        entry = _slice(_setup_keyboard_shortcuts(), "'Focus Search'",
                       re.compile(r'^\s*description:', re.MULTILINE),
                       "the `Focus Search` table entry")

        lookup = entry.find('input[type="search"]')
        assert lookup != -1, (
            "Focus Search's selector is gone — this ordering check no longer "
            'proves anything and needs rewriting')

        prevent = entry.find('preventDefault', lookup)
        assert prevent != -1, (
            'Focus Search no longer calls preventDefault() at all: focusing the '
            'search box now also types "/" into it')
        assert entry.count('preventDefault', 0, lookup) == 0, (
            'Focus Search calls preventDefault() before it knows whether a '
            'search box exists: "/" is swallowed on every page even though '
            'nothing gets focused')


@pytest.mark.unit
class TestAddPageBarcodeGuard:
    """Scan mode stops eating keystrokes aimed at a form field (DW-56)."""

    def test_the_guard_runs_before_the_buffer_and_the_flush_timer(self):
        """Placement is the invariant, not merely presence.

        The guard has to sit after the `scanModeActive` gate and before the
        `clearTimeout`: clearing the pending flush on a keystroke that this
        handler then ignores would postpone the 100 ms flush for as long as the
        operator keeps typing, so a burst already in the buffer would never be
        processed.
        """
        body = _setup_barcode_scanning()

        guard = re.search(r'isFieldFocused\s*\(\s*\)', body)
        assert guard is not None, (
            "the add page's scan handler no longer consults "
            'utils.isFieldFocused(): scan mode swallows everything the operator '
            'types into #scan-input or #ja_id again (DW-56)')

        for marker, consequence in (
                ('scanModeActive',
                 'the guard now runs before the scan-mode gate, so it is asked '
                 'on every keystroke in the app'),
                ('clearTimeout',
                 'the guard now runs after the clearTimeout, so typing into a '
                 'field postpones the pending 100 ms flush indefinitely'),
                ('scanBuffer',
                 'the guard now runs after the buffer append, so keystrokes '
                 'aimed at a field are captured anyway'),
                ('preventDefault',
                 'the guard now runs after preventDefault(), so the field never '
                 'receives the keystroke'),
        ):
            position = body.find(marker)
            assert position != -1, (
                f'`{marker}` is gone from setupBarcodeScanning — this ordering '
                f'check no longer proves anything and needs rewriting')
            if marker == 'scanModeActive':
                assert position < guard.start(), consequence
            else:
                assert guard.start() < position, consequence

    def test_the_guard_is_an_early_return(self):
        """Ignoring the keystroke is all it does.

        Cancelling scan mode here instead would mean a field taking focus
        disarms the scanner, which is a behavior change nobody asked for — scan
        mode still ends only through Enter, the flush, the 10 s auto-cancel or
        `cancelBarcodeCapture()`.
        """
        body = _setup_barcode_scanning()
        assert re.search(
            r'if\s*\([^)]*isFieldFocused\s*\(\s*\)[^)]*\)\s*\{?\s*return;', body), (
            "the add page's focus guard is no longer a bare early return: it is "
            'now doing something else to scan mode, which the guard was '
            'explicitly not supposed to touch')

    def test_arming_the_scanner_takes_focus_off_whatever_field_had_it(self):
        """The guard's premise, established rather than inherited.

        Ignoring keystrokes while a field owns focus only works if a burst
        arrives with no field focused. Chromium focuses a clicked button by
        itself; Firefox and Safari on macOS do not, and
        `clearFormForContinue()` parks focus in `#ja_id` after every Save &
        Continue — so without this, arming from the normal between-items state
        drops the whole burst in silence until the 10 s auto-cancel.
        """
        body = _slice(INVENTORY_ADD_JS.read_text(encoding='utf-8'),
                      '\n    startBarcodeCapture(fieldId) {',
                      CLASS_METHOD_END, 'InventoryAddForm.startBarcodeCapture')
        assert re.search(r'\.focus\s*\(\s*\)', body), (
            'startBarcodeCapture no longer moves focus: on any browser that '
            'does not focus a clicked button, the scan button now arms a '
            'capture that ignores every key of the burst that follows')

    def test_the_guard_uses_the_shared_predicate(self):
        """One definition of "a field owns focus", not two.

        `inventory-add.js` reaching for `document.activeElement` itself would
        let the two handlers drift apart, which is how they ended up disagreeing
        in the first place.
        """
        body = _setup_barcode_scanning()
        assert 'WorkshopInventory.utils.isFieldFocused' in body, (
            "the add page's guard no longer goes through "
            'WorkshopInventory.utils.isFieldFocused: the two keydown handlers '
            'can now disagree about what counts as a focused field')
