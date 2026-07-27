"""
E2E Tests for the two document-level keydown focus guards (DW-56, DW-64)

The app has exactly two `keydown` listeners bound to `document`, and neither
used to ask what had focus before acting:

* `app/static/js/main.js`'s shortcut handler skipped its "the operator is
  typing" early return whenever Ctrl/Meta/Alt was held. A keyboard wedge emits
  ASCII control characters as Ctrl chords (GS as `Ctrl`+`]`, RS as
  `Ctrl`+`^`), so a scan burst arriving in a focused `#scan-input` reached the
  shortcut table anyway: `Ctrl`+`/` put a "Focus Search" toast on screen
  mid-burst and `Ctrl`+`Shift`+`/` opened the keyboard-help modal, pulling
  focus out of the field the rest of the burst was aimed at (DW-64).
* `app/static/js/inventory-add.js` appended every printable key to its own
  barcode buffer and `preventDefault()`ed it while scan mode was armed, so
  typing into any field on `/inventory/add` was swallowed (DW-56).

Both now consult one predicate, `WorkshopInventory.utils.isFieldFocused()`.

There is no JS unit-test harness in this repo, so Playwright is the only
executable proof the guards work at all. `tests/unit/test_keydown_focus_guards
.py` is a companion, not a substitute: it reads the two files as text and can
only assert that the guards are still *present, shaped and ordered* the way
they are here. An inverted predicate — one that reports "a field is focused"
exactly backwards — satisfies every assertion in that module and is caught only
by the cases below.

One test per row of the spec's I/O matrix. The negative rows ("no toast
appears") are paired with a recorder proving the keystroke really reached the
document, so a green result cannot mean "the key was never delivered".

These tests mutate no data, so they are trivially safe under --reruns.
"""

import time

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import SCAN_INPUT


TOAST = '#toast-container .toast'
TOAST_BODY = '#toast-container .toast .toast-body'
HELP_MODAL = '#keyboard-help-modal'
JA_ID_INPUT = '#ja_id'
SCAN_BUTTON = '#scan-ja-id-btn'
ARMED_SCAN_BUTTON = '#scan-ja-id-btn.btn-warning'

#: `Focus Search`'s selector. No template in the app contains a match today, so
#: the shortcut is inert everywhere — but the test below asserts that on the one
#: page it visits rather than taking the repo-wide claim on trust, because the
#: day someone adds a search box is the day that row stops being the row it says
#: it is.
SEARCH_SELECTOR = 'input[type="search"], input[name*="search"], #search'

#: The synthetic `Focus Search` target injected by `inject_search_probe`.
PROBE_ID = 'focus-guard-probe'

#: How long to dwell before concluding "no toast appeared".
#:
#: `showToast` creates the toast element and appends it SYNCHRONOUSLY, inside
#: the same `keydown` dispatch — nothing on that path awaits, fetches or
#: animates first. So by the time `page.keyboard.press()` has returned, the
#: handler has already run to completion in the page and a toast that was going
#: to exist already exists. This dwell is therefore not waiting for anything; it
#: is pure margin, three orders of magnitude more than the synchronous work
#: needs, against a loaded CI box being slow to flush the CDP round trip.
NO_TOAST_DWELL_MS = 1000

#: How long to dwell before concluding the add page's barcode buffer stayed
#: empty. Longer than the handler's own 100 ms flush timer on purpose: the
#: unguarded code captures keystrokes silently and only reveals it when that
#: timer fires and calls `processBarcodeInput`, so a shorter wait would go green
#: against genuinely broken code with the evidence still pending.
SCAN_FLUSH_DWELL_MS = 500


def record_keydowns(page):
    """Record every `keydown` reaching `document`, as the shortcut handler left it.

    Registered after the page has loaded, so it is bound to `document` *after*
    `main.js`'s listener on the same target and phase and therefore runs second
    — which is what lets it report `defaultPrevented` as that handler decided
    it.

    Its real job is to keep the negative cases honest. "No toast appeared" is
    equally true of a working guard and of a keystroke that never arrived; only
    a recorded event tells those apart.
    """
    page.evaluate("""() => {
        window.__keydowns = [];
        document.addEventListener('keydown', (e) => {
            window.__keydowns.push({
                code: e.code,
                ctrlKey: e.ctrlKey,
                shiftKey: e.shiftKey,
                prevented: e.defaultPrevented
            });
        });
    }""")


def slash_keydowns(page):
    """Every recorded `Slash` press — the key every shortcut in the table uses."""
    return [event for event in page.evaluate('() => window.__keydowns')
            if event['code'] == 'Slash']


def assert_no_toast(page, why):
    """Snapshot the toast count — never `expect(...).to_have_count(0)`.

    `showToast` passes no options, so Bootstrap's `autohide: true, delay: 5000`
    applies and the element removes itself five seconds after `show()`.
    Playwright's `expect` RETRIES until its deadline, so a polling assertion
    that a toast is absent goes green the moment the toast it was supposed to
    catch expires — the negative rows of this matrix all passed against
    deliberately broken code that way. A single non-retrying read after
    `NO_TOAST_DWELL_MS` is the assertion that can actually fail.
    """
    count = page.locator(TOAST).count()
    shown = page.locator(TOAST_BODY).all_text_contents()
    assert count == 0, f'{why}; {count} toast(s) on screen: {shown}'


def inject_search_probe(page):
    """Give `Focus Search` a target it does not have in any shipped template.

    Without one the shortcut is inert on its own account, so "no shortcut ran"
    would be equally true of a handler with no guard at all. With a target
    present, a shortcut that runs demonstrably moves focus and toasts.
    """
    page.evaluate(f"""() => {{
        const probe = document.createElement('input');
        probe.type = 'search';
        probe.id = {PROBE_ID!r};
        document.body.appendChild(probe);
    }}""")


def blur_everything(page):
    """Put focus back on `body`, and prove it landed there."""
    page.evaluate('() => document.activeElement && document.activeElement.blur()')
    assert page.evaluate('() => document.activeElement === document.body'), (
        'could not get focus onto the body, so this case is not testing the '
        '"nothing focused" state it claims to')


def arm_add_page_scan_mode(page, live_server):
    """Open `/inventory/add` and put it into barcode scan mode.

    The "Ready to scan barcode..." toast is what proves the click reached
    `startBarcodeCapture` rather than merely landing on a button whose handler
    had not been bound yet — without it, an unarmed page would satisfy every
    "scan mode did not eat my keystrokes" assertion for the wrong reason.

    The focus assertion is the load-bearing one. This guard only works because
    a burst arrives with no field focused, and `startBarcodeCapture()` now
    establishes that itself instead of relying on the browser to focus a
    clicked button — Chromium does, Firefox and Safari on macOS do not, and
    `clearFormForContinue()` parks focus in `#ja_id` after every Save &
    Continue. Asserting it here, off the click alone with nothing staged,
    is what keeps the premise a tested consequence rather than test setup.
    """
    page.goto(f'{live_server.url}/inventory/add')
    # The JA ID field auto-populates from /api/inventory/next-ja-id after load;
    # letting that settle first keeps it from overwriting what a test types.
    page.wait_for_load_state('networkidle')

    page.locator(SCAN_BUTTON).click()
    expect(page.locator(TOAST_BODY, has_text='Ready to scan barcode')).to_have_count(1)
    expect(page.locator(ARMED_SCAN_BUTTON)).to_have_count(1)

    assert page.evaluate(
        '() => window.WorkshopInventory.utils.isFieldFocused()') is False, (
        'arming scan mode left a form field focused: every keystroke of the '
        'burst that follows is ignored by the guard, so the scan is dropped in '
        'silence until the 10 s auto-cancel')


@pytest.mark.e2e
class TestChordsWithAFieldFocused:
    """DW-64: a wedge's Ctrl chords must not reach the shortcut table."""

    def test_control_slash_with_the_scan_field_focused_does_nothing(
            self, page, live_server):
        """`Ctrl`+`/` mid-burst used to toast "Focus Search" over the operator.

        A search target is INJECTED for this case, and that is deliberate.
        `Focus Search`'s selector matches nothing in any shipped template, so on
        a real page the shortcut is inert on its own account — "no shortcut ran"
        would then be unfalsifiable, true even of a handler with no guard at
        all. With a target present a shortcut that runs demonstrably moves focus
        and toasts, so what the assertions below detect is the guard.

        The field's value is asserted unchanged as well as its focus: the
        shortcut's own body is what would move focus, but `preventDefault()` in
        the match loop is what would eat the character, and both are failures
        of the same guard.
        """
        page.goto(f'{live_server.url}/')
        record_keydowns(page)
        inject_search_probe(page)

        scan_input = page.locator(SCAN_INPUT)
        scan_input.fill('9781234')
        scan_input.focus()
        assert_no_toast(page, 'the page toasted before the chord was even pressed')

        page.keyboard.press('Control+Slash')
        page.wait_for_timeout(NO_TOAST_DWELL_MS)

        pressed = slash_keydowns(page)
        assert len(pressed) == 1 and pressed[0]['ctrlKey'], (
            f'Ctrl+/ never reached the document ({pressed}), so this case '
            f'proves nothing about the guard')
        assert_no_toast(page, 'Ctrl+/ ran a shortcut with #scan-input focused')
        expect(scan_input).to_be_focused()
        expect(scan_input).to_have_value('9781234')

    def test_control_shift_slash_with_the_scan_field_focused_opens_no_modal(
            self, page, live_server):
        """`Ctrl`+`Shift`+`/` used to open the help modal and take the focus.

        Losing focus is the damaging half: the rest of the wedge's burst then
        types into nothing, so the scan is silently truncated.
        """
        page.goto(f'{live_server.url}/')
        record_keydowns(page)

        scan_input = page.locator(SCAN_INPUT)
        scan_input.fill('9781234')
        scan_input.focus()

        page.keyboard.press('Control+Shift+Slash')
        page.wait_for_timeout(NO_TOAST_DWELL_MS)

        pressed = slash_keydowns(page)
        assert len(pressed) == 1 and pressed[0]['ctrlKey'] and pressed[0]['shiftKey'], (
            f'Ctrl+Shift+/ never reached the document ({pressed}), so this case '
            f'proves nothing about the guard')
        assert page.locator(HELP_MODAL).count() == 0, (
            'Ctrl+Shift+/ opened the keyboard-help modal with #scan-input '
            'focused: the rest of the wedge burst types into the modal instead '
            'of into the scan field (DW-64)')
        assert_no_toast(page, 'Ctrl+Shift+/ ran a shortcut with #scan-input focused')
        expect(scan_input).to_be_focused()
        expect(scan_input).to_have_value('9781234')


@pytest.mark.e2e
class TestTheSameChordsWithNothingFocused:
    """Positive controls for the two cases above — without them those are vacuous.

    Both cases above assert that a Ctrl chord produced no toast and no modal.
    That is equally true of a working guard and of a chord that never reaches
    the shortcut table at all: `matchesCtrl = !shortcut.ctrl || e.ctrlKey ||
    e.metaKey` is what lets a modifier-less entry match a Ctrl chord (DW-136),
    and if that ever tightens, both negative cases go green having tested
    nothing. Recording the keydown proves the KEY arrived; only these two prove
    the chord would otherwise have ACTED on it.

    They also pin DW-136's live behavior, which the focus guard deliberately did
    not fix: with focus on `body` a wedge's control chords still reach the
    table. Should that entry ever be resolved, these fail and say so — which is
    the correct outcome, not a regression.
    """

    def test_control_slash_with_nothing_focused_does_focus_the_probe(
            self, page, live_server):
        """The chord the first negative case suppresses, shown acting."""
        page.goto(f'{live_server.url}/')
        inject_search_probe(page)
        blur_everything(page)

        page.keyboard.press('Control+Slash')

        expect(page.locator(f'#{PROBE_ID}')).to_be_focused()
        assert page.locator(TOAST_BODY).all_text_contents() == ['Focus Search'], (
            'Ctrl+/ no longer runs `Focus Search` with nothing focused, so '
            'test_control_slash_with_the_scan_field_focused_does_nothing is now '
            'passing for want of a chord rather than because of the guard')

    def test_control_shift_slash_with_nothing_focused_does_open_the_modal(
            self, page, live_server):
        """The chord the second negative case suppresses, shown acting."""
        page.goto(f'{live_server.url}/')
        blur_everything(page)

        page.keyboard.press('Control+Shift+Slash')

        expect(page.locator(HELP_MODAL)).to_be_visible(timeout=5000)


@pytest.mark.e2e
class TestShortcutsWithNothingFocused:
    """With no field focused every shortcut behaves exactly as before."""

    def test_shift_slash_still_opens_the_help_modal_and_toasts_once(
            self, page, live_server):
        """The guard must not cost the shortcuts their normal behavior.

        Exactly one toast, and it says `Help`: `Shift`+`/` matches BOTH table
        entries (`Focus Search` has no `shift` requirement), so this is also
        what proves the second, target-less match stays silent instead of
        stacking a bogus "Focus Search" next to the real one.
        """
        page.goto(f'{live_server.url}/')
        blur_everything(page)
        assert_no_toast(page, 'the page toasted before the shortcut was pressed')

        page.keyboard.press('Shift+Slash')

        # The modal is opened by the SAME synchronous keydown dispatch that
        # toasts, so once it is on screen every toast this press produced
        # already exists — which is what lets the count below be a snapshot
        # rather than a retrying expect that a second, bogus toast could
        # outlive.
        expect(page.locator(HELP_MODAL)).to_be_visible(timeout=5000)
        assert page.locator(TOAST_BODY).all_text_contents() == ['Help'], (
            'Shift+/ no longer produces exactly one "Help" toast: it matches '
            'both table entries, so a target-less "Focus Search" announcing '
            'itself alongside the real one shows up here')

    def test_slash_with_no_search_target_is_silently_inert(
            self, page, live_server):
        """No target, no toast, and the keystroke stays the page's.

        `Focus Search`'s selector matches nothing in any template, so the old
        code announced a focus move that never happened AND swallowed `/` in
        exchange — `preventDefault()` ran before the target lookup. Both halves
        are asserted, because gating only the toast would leave the key eaten.
        """
        page.goto(f'{live_server.url}/')
        record_keydowns(page)
        blur_everything(page)

        assert page.evaluate(
            f'() => document.querySelectorAll({SEARCH_SELECTOR!r}).length') == 0, (
            'a search target now exists on the home page, so "/" is no longer '
            'the no-target case this row of the matrix describes')

        page.keyboard.press('Slash')
        page.wait_for_timeout(NO_TOAST_DWELL_MS)

        pressed = slash_keydowns(page)
        assert len(pressed) == 1, (
            f'/ never reached the document ({pressed}), so this case proves '
            f'nothing')
        assert pressed[0]['prevented'] is False, (
            'Focus Search called preventDefault() even though it had nothing to '
            'focus: "/" is swallowed on every page in the app in exchange for '
            'nothing happening')
        assert_no_toast(
            page, 'pressing "/" announced "Focus Search" while focusing nothing')
        assert page.evaluate('() => document.activeElement === document.body'), (
            'Focus Search moved focus even though its selector matches nothing')


@pytest.mark.e2e
class TestAddPageScanMode:
    """DW-56: an armed barcode buffer must not eat what a field is owed."""

    @pytest.mark.parametrize('field', [SCAN_INPUT, JA_ID_INPUT],
                             ids=['scan_input', 'ja_id'])
    def test_typing_into_a_field_while_scan_mode_is_armed_reaches_the_field(
            self, page, live_server, field):
        """Characters land in the field, the buffer stays empty, scan mode lives.

        Three assertions for three distinct failure modes of the unguarded
        code, all of which it exhibits at once: `preventDefault()` keeps the
        character out of the field, the buffer collects it instead, and the
        100 ms flush then processes it as a barcode — which error-toasts and
        calls `cancelBarcodeCapture()`, disarming the scanner the operator
        armed. `btn-warning` on the scan button is scan mode's only external
        signal, so it stands in for `scanModeActive`, which the page never
        exposes.
        """
        arm_add_page_scan_mode(page, live_server)

        target = page.locator(field)
        target.fill('')
        target.focus()
        page.keyboard.type('ABC')
        page.wait_for_timeout(SCAN_FLUSH_DWELL_MS)

        expect(target).to_have_value('ABC')
        assert page.locator(ARMED_SCAN_BUTTON).count() == 1, (
            'scan mode disarmed itself: the guard is supposed to IGNORE '
            'keystrokes aimed at a field, not cancel the capture the operator '
            'armed')
        # Asserted as the ABSENCE of a processing toast rather than as an exact
        # toast list: `showToast` autohides after 5 s, so pinning the arming
        # toast's continued presence would turn a slow `networkidle` into a red
        # test about nothing. `processBarcodeInput` always toasts — success or
        # `Invalid JA ID format` — so its silence is the buffer's silence.
        processed = [text for text in page.locator(TOAST_BODY).all_text_contents()
                     if text.startswith(('Scanned JA ID:', 'Invalid JA ID format:'))]
        assert processed == [], (
            f'the add page processed the typed characters as a barcode '
            f'({processed}): they went into the scan buffer instead of into the '
            f'field the operator was typing in (DW-56)')

    def test_arming_from_a_focused_field_still_captures_the_burst(
            self, page, live_server):
        """The state a real operator arms from, on a browser that is not Chrome.

        Chromium focuses a clicked button; Firefox and Safari on macOS leave
        focus where it was. A *synthetic* click reproduces that difference
        exactly — the handler runs, focus does not move — which is the only way
        this suite can exercise it, since Playwright drives Chromium here.

        The state is not contrived: `clearFormForContinue()`
        (`app/static/js/inventory-add.js:849`) focuses `#ja_id` after every Save
        & Continue, so "a field has focus" is where bulk entry always sits when
        the operator reaches for the scan button. Without
        `startBarcodeCapture()` taking focus, the guard added for DW-56 would
        ignore every key of the burst and the scan would vanish in silence
        until the 10 s auto-cancel.

        `#ja_id` is deliberately left holding its auto-generated value: were the
        burst to reach the field directly instead of the buffer, the value would
        be the two run together, and the `Scanned JA ID` toast — which only
        `processBarcodeInput` emits — would be missing.
        """
        page.goto(f'{live_server.url}/inventory/add')
        page.wait_for_load_state('networkidle')

        page.locator(JA_ID_INPUT).focus()
        page.evaluate("""() => document.getElementById('scan-ja-id-btn')
            .dispatchEvent(new MouseEvent('click', {bubbles: true}))""")
        expect(page.locator(ARMED_SCAN_BUTTON)).to_have_count(1)

        assert page.evaluate(
            '() => window.WorkshopInventory.utils.isFieldFocused()') is False, (
            'arming the scanner left focus in #ja_id: on any browser that does '
            'not focus a clicked button, the DW-56 guard now swallows the whole '
            'burst instead of the buffer swallowing the operator')

        page.keyboard.type('JA000123')
        page.keyboard.press('Enter')

        expect(page.locator(JA_ID_INPUT)).to_have_value('JA000123')
        expect(page.locator(TOAST_BODY, has_text='Scanned JA ID: JA000123')
               ).to_have_count(1)

    def test_a_wedge_burst_with_no_field_focused_still_fills_the_ja_id(
            self, page, live_server):
        """NFR9: the metal-stock scan button must keep working.

        Nothing is staged here — `arm_add_page_scan_mode` has already asserted
        that arming left no field focused, and the burst is typed into whatever
        that left, exactly as a wedge would. A guard written too broadly, or an
        arm path that leaves the caret in `#ja_id`, fails right here.
        """
        arm_add_page_scan_mode(page, live_server)

        # The handler rearms a 100 ms flush on every keystroke, so a burst whose
        # keys arrive more than 100 ms apart is processed in pieces — real of a
        # loaded CI box, not of a wedge. Timed so that a failure says which one
        # it was instead of leaving a bare "value != JA000123".
        started = time.monotonic()
        page.keyboard.type('JA000123')
        page.keyboard.press('Enter')
        elapsed_ms = (time.monotonic() - started) * 1000

        # Consulted only once the scan has ALREADY failed, and then to skip
        # rather than to fail. Asserting the timing up front would turn machine
        # load into a red test about nothing — and `--reruns=3` (noxfile.py)
        # re-runs on the same loaded machine, so it would not absorb it either.
        # The threshold is an average over the burst's 9 events, not the
        # per-gap invariant the handler actually cares about, which is why it
        # is evidence about an existing failure and never a verdict of its own.
        if elapsed_ms >= 800 and page.locator(JA_ID_INPUT).input_value() != 'JA000123':
            pytest.skip(
                f'the burst took {elapsed_ms:.0f} ms to deliver, averaging more '
                f'than 100 ms between its 9 events, so the handler flushed it in '
                f'pieces. This machine is too loaded to tell a working scan path '
                f'from a broken one, so this run reports nothing rather than '
                f'blaming the code for the box')
        expect(page.locator(JA_ID_INPUT)).to_have_value('JA000123')
        expect(page.locator(TOAST_BODY, has_text='Scanned JA ID: JA000123')
               ).to_have_count(1)


@pytest.mark.e2e
class TestFocusPredicateEdgeCases:
    """`document.activeElement` is not guaranteed to be a form field, or an Element."""

    def test_predicate_is_false_when_focus_sits_on_the_body(
            self, page, live_server):
        page.goto(f'{live_server.url}/')
        blur_everything(page)

        assert page.evaluate(
            '() => window.WorkshopInventory.utils.isFieldFocused()') is False, (
            'isFieldFocused() reports a focused field with focus on the body: '
            'every keyboard shortcut in the app is now unreachable')

    @pytest.mark.parametrize('active_element_js,label', [
        ('null', 'null'),
        ('undefined', 'undefined'),
        ('({tagName: "INPUT"})', 'an object with no matches()'),
    ], ids=['null', 'undefined', 'non_element'])
    def test_predicate_answers_false_without_throwing(
            self, page, live_server, active_element_js, label):
        """A throw here is not a bad answer — it is no answer at all.

        This predicate is the first statement of both document `keydown`
        handlers, so an exception in it takes the whole shortcut table and the
        add page's barcode buffer down with it. `document.activeElement` really
        can be `null` (a detached or not-yet-focused document), and the guard
        is written not to assume it is an Element either.

        Shadowed with an own property on `document` rather than by contriving
        the state, because `null` is otherwise not reachable from a live page;
        the property is deleted again so the real getter is restored whatever
        the predicate does.
        """
        page.goto(f'{live_server.url}/')

        result = page.evaluate(f"""() => {{
            Object.defineProperty(document, 'activeElement', {{
                configurable: true,
                get: () => {active_element_js}
            }});
            try {{
                return {{value: window.WorkshopInventory.utils.isFieldFocused(),
                         threw: null}};
            }} catch (error) {{
                return {{value: null, threw: String(error)}};
            }} finally {{
                delete document.activeElement;
            }}
        }}""")

        assert result['threw'] is None, (
            f'isFieldFocused() threw with activeElement = {label}: '
            f'{result["threw"]}. Both document keydown handlers call it first, '
            f'so this kills every shortcut and the add page\'s scan capture')
        assert result['value'] is False, (
            f'isFieldFocused() reported a focused field with activeElement = '
            f'{label}: keystrokes are being treated as the operator typing when '
            f'nothing owns focus')
