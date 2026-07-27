"""
Source tripwire for the toast sink's text-only construction (DW-54).

`WorkshopInventory.utils.showToast` used to interpolate its message into an HTML
string and insert it with `insertAdjacentHTML`, which made all 28 of its call
sites — nine of them carrying server-derived, filename-derived or
scanned-barcode text — unescaped HTML sinks. It now builds the toast out of DOM
nodes and puts the message in through `textContent`.

That property is invisible at runtime until someone injects markup, and the
only behavioral coverage of it lives in `tests/e2e/test_toast_escaping.py` —
a Playwright suite that takes ~20 minutes and is not what a developer runs
before pushing. So the shape is asserted here as text, in the fast `nox -s
tests` session: a rewrite back to a template literal fails in seconds instead of
surviving until a full e2e run.

Two halves, because the invariant has two halves. The sink must render text, and
callers must NOT pre-escape — a caller that keeps escaping now double-escapes,
and the operator reads `&lt;img ...&gt;` instead of the tag. `ScanCapture` was
the one caller that escaped, so its file is the one checked.

Scanned as text rather than parsed: there is no JS test harness in this repo
(see `tests/e2e/test_toast_escaping.py`), and standing one up to assert three
substrings is more machinery than a tripwire deserves.
"""

import re
from pathlib import Path

import pytest

STATIC_JS = Path(__file__).resolve().parents[2] / 'app' / 'static' / 'js'
MAIN_JS = STATIC_JS / 'main.js'
SCAN_CAPTURE_JS = STATIC_JS / 'scan-capture.js'

#: The members of the `utils` object literal are indented eight spaces and each
#: closes on its own `        },` line, so that terminator bounds `showToast`
#: without brace-counting a language this module does not parse. If the file is
#: ever reformatted the extraction below fails loudly rather than silently
#: matching the whole file.
MEMBER_END = re.compile(r'^        \},$', re.MULTILINE)

#: Every way a string can become markup that this file has to stay clear of.
#: `insertAdjacentHTML` is the specific call that was removed; the rest are the
#: neighbouring sinks a "simplification" would reach for instead. The last four
#: are parser entry points that never mention "HTML" at the call site, which is
#: exactly what makes them easy to reintroduce without noticing.
HTML_SINKS = (
    'insertAdjacentHTML', 'innerHTML', 'outerHTML', 'document.write',
    'setHTMLUnsafe', 'createContextualFragment', 'DOMParser', '.html(',
)


def _show_toast_body():
    """The source text of `WorkshopInventory.utils.showToast`, and only it.

    Bounded rather than searching all of `main.js`: the file legitimately uses
    `insertAdjacentHTML` elsewhere (the keyboard-shortcut help modal, built from
    a wholly static string), so a whole-file search would either fail on
    untouched code or have to special-case it.
    """
    source = MAIN_JS.read_text(encoding='utf-8')
    start = source.find('showToast: function')
    assert start != -1, 'showToast is gone from main.js — the sink moved or was renamed'

    end = MEMBER_END.search(source, start)
    assert end is not None, (
        'could not find the end of showToast: the object-literal formatting this '
        'tripwire bounds on has changed')
    return source[start:end.start()]


@pytest.mark.unit
class TestToastSinkIsTextOnly:
    """The sink puts its message into the DOM as text, not as markup."""

    def test_show_toast_sets_the_message_with_text_content(self):
        """`message` itself must be what goes through `textContent`.

        Matched as an assignment rather than as a bare `'textContent' in body`
        substring: the sink sets several properties, so the token's mere
        presence would stay green if the message were routed somewhere else and
        `textContent` survived on a sibling node. The variable holding the body
        element is deliberately left unpinned — renaming it is not a defect.
        """
        assert re.search(
            r'\.textContent\s*=\s*String\(\s*message\s*\)', _show_toast_body()), (
            'showToast no longer routes its message through textContent — the '
            'message is only guaranteed to be inert if it never reaches the '
            'HTML parser')

    @pytest.mark.parametrize('sink', HTML_SINKS)
    def test_show_toast_uses_no_html_sink(self, sink):
        assert sink not in _show_toast_body(), (
            f'showToast reintroduced {sink}: every one of its callers becomes an '
            f'HTML sink again, including the ones passing scanned barcode text')

    def test_the_message_is_not_interpolated_into_toast_body_markup(self):
        """The exact defect, in the exact form it had.

        Kept alongside the sink checks above because a template literal could
        come back through a helper that never names `innerHTML` itself.
        """
        assert not re.search(r'toast-body[^\n]*\$\{', MAIN_JS.read_text(encoding='utf-8')), (
            'a toast-body is being built by interpolation again')


@pytest.mark.unit
class TestCallersDoNotPreEscape:
    """One escaping boundary means the callers must not add a second."""

    def test_scan_capture_no_longer_escapes_before_toasting(self):
        """`ScanCapture` escaped at its call site while the sink interpolated.

        With the sink rendering text, that escaping would show the operator
        `&lt;` where the server sent `<` — so the helper was deleted, and its
        return is what this catches.
        """
        assert 'escapeHtml' not in SCAN_CAPTURE_JS.read_text(encoding='utf-8'), (
            'scan-capture.js escapes again: messages reaching the toast are '
            'double-escaped, and entities render as literal `&lt;` noise')
