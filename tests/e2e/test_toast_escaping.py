"""
E2E Tests for the toast sink's escaping boundary (DW-54)

`WorkshopInventory.utils.showToast` (app/static/js/main.js) renders every
Bootstrap toast in the app and has 28 call sites, 9 of which pass
server-derived, filename-derived or scanned-barcode text. It used to interpolate
its argument into an HTML string, which made every one of those an unescaped
sink; it now builds the toast out of DOM nodes and sets the message with
`textContent`.

It is not the app's only notification renderer — `inventory-list.js:261` builds
its own `.alert` (with `textContent`, so it is safe), `inventory-move.js` and
`inventory-shorten.js` have a separate `showAlert` inline-alert sink, and
`PhotoManager.showToast` falls back to `console` + `alert()` when
`WorkshopInventory` is absent. Those are out of scope here; this file is about
the toast sink.

These tests drive `showToast` DIRECTLY via `page.evaluate` rather than through a
caller: the property under test belongs to the sink, so exercising it through
one caller would leave the other 27 unproven and would fail for reasons that
have nothing to do with escaping. The end-to-end path through a real caller is
still covered by
`tests/e2e/test_wedge_scan.py::test_server_error_message_is_escaped_not_rendered`,
whose single-escape assertion is what proves the call-site escaping in
`ScanCapture.notify` is really gone.

There is no JS unit-test harness in this repo, so Playwright is the only
executable guard for this file.

These tests mutate no data, so they are trivially safe under --reruns.
"""

import time

import pytest
from playwright.sync_api import expect


TOAST = '.toast'
TOAST_BODY = '.toast-body'

#: `showToast` passes no options, so Bootstrap's `autohide: true, delay: 5000`
#: applies and every toast removes ITSELF five seconds after `show()`. The two
#: dismissal cases below exist to prove the close button is what removed the
#: toast, and a short post-click deadline cannot establish that by itself —
#: the clock starts at `show()`, not at the click, and nothing otherwise bounds
#: how long the assertions in between take. Hold the whole pre-click stretch
#: well inside the delay and the two causes stay distinguishable.
AUTOHIDE_DELAY_S = 5.0
PRE_CLICK_BUDGET_S = 2.0


def assert_autohide_cannot_explain_it(started, what):
    """Fail loudly when a run got too slow to tell dismissal from expiry."""
    elapsed = time.monotonic() - started
    assert elapsed < PRE_CLICK_BUDGET_S, (
        f'{what} took {elapsed:.1f}s, within reach of Bootstrap\'s '
        f'{AUTOHIDE_DELAY_S:.0f}s autohide, so this run cannot tell a working '
        f'close button from the toast expiring on its own — passing here would '
        f'mean nothing. This is a loaded-machine failure, not a product defect.')


def show_toast(page, message_js, type_js=None):
    """Invoke the sink with a raw JS expression for the message.

    The message is spliced in as an EXPRESSION, not as a string argument, so a
    case can pass `undefined` or an object literal — the non-string rows of the
    matrix — which a Python-side argument could not express.
    """
    type_arg = '' if type_js is None else f', {type_js}'
    page.evaluate(
        f'() => window.WorkshopInventory.utils.showToast({message_js}{type_arg})')


@pytest.mark.e2e
class TestToastEscaping:
    """The sink renders its message as text, never as markup."""

    def test_plain_message_renders_with_its_type_styling(self, page, live_server):
        """The ordinary case: text arrives intact and the type still styles it.

        Guards the DOM shape as much as the text — `text-bg-{type}` is what
        every existing e2e selector keys on.
        """
        page.goto(f'{live_server.url}/')
        show_toast(page, "'Photo deleted'", "'success'")

        toast = page.locator('.toast.text-bg-success')
        expect(toast).to_be_visible(timeout=5000)
        expect(toast.locator(TOAST_BODY)).to_have_text('Photo deleted')

    def test_markup_in_message_is_literal_text_and_runs_nothing(
            self, page, live_server):
        """The bug this file exists for.

        A scanned barcode label is attacker-suppliable physical input, so an
        injected tag must stay text instead of becoming an element.

        The element count is the load-bearing assertion. `window.__pwned` is a
        cheap backstop and nothing more: `onerror` fires only after the browser
        has tried and failed to fetch `src=x`, which is asynchronous, so a
        synchronous read right after the toast appears could come back
        `undefined` even against genuinely vulnerable code. It is kept because
        a payload that fired early would still be caught, not because its
        silence proves anything.
        """
        page.goto(f'{live_server.url}/')
        show_toast(page, '\'<img src=x onerror="window.__pwned=1">\'')

        toast = page.locator(TOAST)
        expect(toast).to_be_visible(timeout=5000)
        assert '<img' in toast.inner_text()
        assert page.locator('.toast img').count() == 0
        assert page.evaluate('() => window.__pwned') is None

    def test_message_is_escaped_exactly_once(self, page, live_server):
        """Single escaping boundary: entities survive as the characters typed.

        The failure this catches is double-escaping — the shape that appears if
        a caller keeps pre-escaping now that the sink escapes. `&amp;` would
        come back as `&amp;amp;` and `<` as `&lt;`, i.e. visible entity noise in
        an operator's error message.
        """
        page.goto(f'{live_server.url}/')
        show_toast(page, "'a &amp; b < c'")

        body = page.locator(TOAST_BODY)
        expect(body).to_be_visible(timeout=5000)
        assert body.inner_text() == 'a &amp; b < c'

    @pytest.mark.parametrize('message_js,expected', [
        ('undefined', 'undefined'),
        ('null', 'null'),
        ('{a: 1}', '[object Object]'),
    ])
    def test_non_string_messages_stringify_as_before(
            self, page, live_server, message_js, expected):
        """Non-strings keep the interpolation's old rendering.

        `textContent` is a nullable IDL attribute, so a bare assignment would
        turn `undefined` and `null` into an EMPTY toast — a silently lost
        notification rather than a visibly wrong one. Behaviour for every caller
        is meant to be unchanged, so the word still shows. `null` is the one
        that matters in practice: it is what a JSON `data.message` carries when
        the server omits it, and `undefined` is what a missing key gives.
        """
        page.goto(f'{live_server.url}/')
        show_toast(page, message_js)

        body = page.locator(TOAST_BODY)
        expect(body).to_be_visible(timeout=5000)
        assert body.inner_text() == expected

    def test_close_button_dismisses_and_removes_the_toast(
            self, page, live_server):
        """Bootstrap still owns the toast built by hand.

        `data-bs-dismiss` has to be a real attribute and the element has to be a
        real child of `#toast-container`, or dismissal and the `hidden.bs.toast`
        cleanup both stop working — the parts an HTML string used to get for
        free.

        The removal deadline is DELIBERATELY short, and the pre-click stretch
        is bounded: Bootstrap autohides at ~5s (see `AUTOHIDE_DELAY_S`), so a
        button wired to nothing goes green the moment the click lands late
        enough for expiry to finish the job inside the deadline. The short
        deadline narrows that window and the elapsed-time guard closes it.
        """
        page.goto(f'{live_server.url}/')
        started = time.monotonic()
        show_toast(page, "'Dismiss me'", "'info'")

        toast = page.locator(TOAST)
        expect(toast).to_be_visible(timeout=5000)
        expect(page.locator('#toast-container .toast')).to_have_count(1)

        assert_autohide_cannot_explain_it(started, 'showing and asserting the toast')
        page.locator('.toast .btn-close').click()

        expect(page.locator('#toast-container .toast')).to_have_count(
            0, timeout=1000)

    def test_a_second_toast_stacks_and_dismisses_independently(
            self, page, live_server):
        """The container-reuse path, which every other case skips.

        All the cases above show one toast, so they only ever exercise the
        branch that CREATES `#toast-container`. Appending into a non-empty
        container is where the rewrite's `appendChild` replaced
        `insertAdjacentHTML` + `lastElementChild` — an idiom that binds
        `bootstrap.Toast` to whatever element happens to be last, so getting it
        wrong here means dismissing one toast and watching the other vanish.

        The surviving first toast is what makes the assertions below meaningful,
        and its autohide clock starts before the second one is even created — so
        the same elapsed-time guard applies here, and for the stronger reason:
        without it a slow run reports the wrong toast disappearing as a product
        failure.
        """
        page.goto(f'{live_server.url}/')
        started = time.monotonic()
        show_toast(page, "'First message'", "'info'")
        show_toast(page, "'Second message'", "'success'")

        toasts = page.locator('#toast-container .toast')
        expect(toasts).to_have_count(2)
        expect(toasts.first.locator(TOAST_BODY)).to_have_text('First message')
        expect(toasts.last.locator(TOAST_BODY)).to_have_text('Second message')

        assert_autohide_cannot_explain_it(started, 'showing and asserting both toasts')
        toasts.last.locator('.btn-close').click()

        expect(page.locator('#toast-container .toast')).to_have_count(
            1, timeout=1000)
        expect(page.locator(TOAST_BODY)).to_have_text('First message')
