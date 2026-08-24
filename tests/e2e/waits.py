"""Shared readiness waits for E2E tests.

These exist because several places in the UI finish asynchronously in ways that
have no single element to assert on. Each function waits for a specific
observable condition -- never for a duration. See the "Writing e2e tests"
section of `CLAUDE.md` for the rules these support.
"""

import re

from playwright.sync_api import Page, expect

# Mirrors InventoryMoveManager.isJaId() / isLocation() in
# app/static/js/inventory-move.js. The move page classifies scanner input by
# pattern, not by what it prompted for, so a test cannot know which transition a
# scan will take without applying the same rules.
_JA_ID = re.compile(r"^JA[0-9]+$")
_LOCATION = re.compile(r"^(M[0-9]+.*|T-?[0-9]+.*|Other)$")


def scan_on_move_page(page: Page, value: str, press_enter: bool = True) -> None:
    """Type a barcode on the move page and wait for that scan to finish.

    There is no single condition that covers every scan, which is what defeated
    three earlier attempts at this file. `#scanner-status` is set synchronously
    for the two transitions that only change state, and is set *early and
    wrongly* for the one that also finalises a move: processInput() calls
    handleJaIdInput(value) -- which immediately advertises readiness for the next
    scan -- and only then calls finalizeCurrentMove(...) without awaiting it. The
    badge therefore reports the new move while the previous one is still inside
    `await fetch('/api/items/{jaId}')`.

    So the signal is chosen per transition, per
    specs/003-e2e-remove-timed-waits/contracts/readiness-signals.md section 1:

      JA ID, from state `ja_id`      #scanner-status -> Waiting for Location
      location                       #scanner-status -> Waiting for JA ID or Sub-Location
      sub-location                   #queue-count reaching N+1 (finalise awaits a fetch)
      JA ID, from `ja_id_or_sub_location`
                                     BOTH of the above -- one action, two completions
      >>DONE<<                       #queue-count reaching its final N

    The pre-scan state and queue length are read from the page before typing,
    because which transition this is depends on where the state machine already
    was. `Done - Ready to Validate` is still not used as the signal after
    >>DONE<<, even though #67 made it reachable on the one-pending-move path:
    handleDoneCode() also returns early without setting it when the queue ends up
    empty, and #queue-count is the one condition that holds for every path
    through the handler.

    Feature 026 added three more transitions, and none of them is covered by the
    signals above:

      location, from `bulk_location`   the whole preselected group is queued at
                                       once, so #queue-count reaches
                                       queued + pending rather than queued + 1
      sub-location, after a group      the sub-location is written onto rows that
                                       are already queued, so #queue-count does
                                       not move at all; the state reset to
                                       `Ready for JA ID` is what happens last
      anything rejected                nothing on the page changes except an
                                       alert being appended

    That last one is why a rejected scan is waited on by counting `#form-alerts
    .alert` rather than by matching its wording: showAlert() now accumulates
    (issue #107 -- fourteen failed scans used to render as one message), so the
    count is a structural signal that does not couple this file to phrasing.
    """
    before = page.evaluate(
        "() => ({ state: window.moveManager.currentExpectedInput,"
        "         queued: window.moveManager.moveQueue.length,"
        "         pending: window.moveManager.pendingMoves.length,"
        "         grouped: window.moveManager.bulkGroupJaIds.length,"
        "         inProgress: window.moveManager.currentJaId !== null,"
        "         alerts: document.querySelectorAll('#form-alerts .alert').length"
        "       })"
    )
    state, queued = before["state"], before["queued"]

    barcode_input = page.locator("#barcode-input")
    barcode_input.fill("")
    barcode_input.focus()
    barcode_input.type(value)
    if press_enter:
        barcode_input.press("Enter")
    # Otherwise nothing terminates the scan and handleBarcodeInput()'s 100ms
    # fallback timer is what runs processInput(). Every wait below is on
    # observable state, so the timer expiring needs no wait of its own -- which
    # is the point of FR-021: that path is reachable without a fixed delay, and
    # was untested only because every existing scan pressed Enter and cancelled
    # it.

    scanner_status = page.locator("#scanner-status")
    queue_count = page.locator("#queue-count")
    status_text = page.locator("#status-text")

    def _rejected():
        expect(page.locator("#form-alerts .alert")).to_have_count(before["alerts"] + 1)

    if value == ">>DONE<<":
        if state == "bulk_location":
            # Nothing is queued: the group still has no destination. The page
            # says why, and saying so is the only thing that changes.
            _rejected()
            return
        # Only the ja_id_or_sub_location branch with a move in progress
        # finalises anything; otherwise the queue is already what it will be.
        finalises = state == "ja_id_or_sub_location" and before["inProgress"]
        expect(queue_count).to_have_text(_queue_text(queued + 1 if finalises else queued))
        return

    if _JA_ID.match(value):
        if state == "bulk_location":
            # A JA ID is not a destination. Refused, with an explanation.
            _rejected()
            return
        if state == "location":
            # The wedge fix: this unambiguously means the previous item's
            # location was missed, so the machine resolves onto the new item.
            # #scanner-status already reads `Waiting for Location` and so proves
            # nothing here; #status-text names the item that is now in progress.
            expect(status_text).to_contain_text(value)
            return
        if state == "ja_id_or_sub_location" and before["inProgress"]:
            # One action, two completions. Waiting on either alone races.
            expect(queue_count).to_have_text(_queue_text(queued + 1))
        expect(scanner_status).to_have_text("Waiting for Location")
        return

    if _LOCATION.match(value):
        if state == "bulk_location":
            # The destination for the whole preselected group, queued at once.
            expect(queue_count).to_have_text(_queue_text(queued + before["pending"]))
            return
        if state in ("ja_id", "ja_id_or_sub_location"):
            # Two locations in a row, or one where a JA ID was expected.
            _rejected()
            return
        expect(scanner_status).to_have_text("Waiting for JA ID or Sub-Location")
        return

    # A sub-location. Only `ja_id_or_sub_location` accepts one; from anywhere
    # else it is refused, and the appended alert is all that changes.
    if state != "ja_id_or_sub_location":
        _rejected()
        return

    if before["grouped"]:
        # Applied to every row of the group, all of them already queued, so
        # #queue-count cannot move. The state reset is what happens last.
        expect(scanner_status).to_have_text("Ready for JA ID")
        return

    # Sub-location: finalises the current move behind a fetch. #scanner-status
    # changed before that fetch resolved, so only the queue proves it landed.
    expect(queue_count).to_have_text(_queue_text(queued + 1))


def _queue_text(count: int) -> str:
    """Reproduce updateQueueDisplay()'s exact wording, so `1 item` cannot be
    satisfied by `11 items`."""
    return f"{count} item{'' if count == 1 else 's'}"


def wait_for_move_executed(page: Page) -> None:
    """Wait for Execute Moves to have committed on the server.

    executeMoves() awaits POST /api/inventory/batch-move and, on success, calls
    clearAll() -- which is the only thing in the file that writes `All data
    cleared` into #status-text. Waiting on that is waiting on the response, and
    therefore on the transaction: the row is committed before the response is
    sent. The success alert is not usable here, because clearAll() calls
    clearAlerts() in the same tick and wipes it again immediately.
    """
    expect(page.locator("#status-text")).to_contain_text("All data cleared")


def dismiss_material_suggestions(page: Page) -> None:
    """Close the MaterialSelector autocomplete, and confirm it closed.

    Typing into a material field opens a dropdown that overlays whatever is
    below it -- a submit button, a checkbox -- so it has to be out of the way
    before the next interaction.

    Dismissing it is trickier than it looks. MaterialSelector debounces its input
    handler by 200ms, and its keydown handler returns immediately while the
    dropdown is hidden:

        if (!this.suggestionsContainer ||
            this.suggestionsContainer.style.display === 'none') return;

    So pressing Escape straight after fill() lands inside the debounce window, is
    swallowed as a no-op, and does not cancel the pending timer -- the dropdown
    then opens ~200ms later, over whatever the caller is about to click, after
    the code meant to close it has returned.

    The debounced handler is therefore allowed to run first. It either opens the
    dropdown (dismiss it, and confirm it closed) or leaves it closed (nothing to
    do). The bounded wait below is the one place the suite waits on a clock: a
    pending debounce has no observable start, so no state distinguishes "has not
    run yet" from "ran and matched nothing".
    """
    suggestions = page.locator(".material-suggestions")
    try:
        expect(suggestions.first).to_be_visible(timeout=2000)
    except AssertionError:
        # The debounced handler ran and opened nothing: no matches for this
        # query, so there is no overlay to dismiss.
        return

    page.keyboard.press("Escape")
    expect(suggestions.first).not_to_be_visible()


def wait_for_photo_viewer_open(page: Page) -> None:
    """Wait until the photo viewer is on screen, whichever one opened.

    viewPhoto() uses PhotoSwipe when the library loaded and falls back to a
    Bootstrap modal when it did not, so there are two possible outcomes and the
    test cannot know in advance which it will get -- which is why the assertion
    that follows is an `or`. Both outcomes settle on the same observable: one of
    the two containers being laid out.
    """
    page.wait_for_function(
        """() => {
            const pswp = document.querySelector('.pswp');
            const modal = document.getElementById('fallback-image-modal');
            return (pswp && pswp.getClientRects().length > 0)
                || (modal && modal.getClientRects().length > 0);
        }"""
    )


def wait_for_modal_shown(page: Page, modal_id: str) -> None:
    """Wait until a Bootstrap modal is fully open and holds focus.

    Two separate races hide behind the fixed delays this replaces:

    - Bootstrap guards hide() with _isTransitioning, so a close click issued
      during the fade-in is silently dropped. Full opacity rules that out.
    - Bootstrap only moves focus into the modal on transitionend, so a keyboard
      dismiss sent before that lands on whatever opened the modal and never
      reaches Bootstrap's keydown handler.

    Waiting for focus covers both, because focus happens last.
    """
    page.wait_for_function(
        "id => { const m = document.getElementById(id);"
        "        return m && getComputedStyle(m).opacity === '1'"
        "                 && m.contains(document.activeElement); }",
        arg=modal_id,
    )


def wait_for_modal_hidden(page: Page, modal_id: str) -> None:
    """Wait until a Bootstrap modal has finished fading out and released the page.

    The `show` class is not enough on its own. Bootstrap removes it at the *start*
    of the fade-out and only tears the backdrop down on transitionend, so a wait
    that settles on the class alone returns while a full-screen `.modal-backdrop`
    is still over the page, intercepting the caller's next click. The backdrop
    being gone is what "hidden" has to mean here.
    """
    page.wait_for_function(
        "id => { const m = document.getElementById(id);"
        "        const closed = !m || !m.classList.contains('show');"
        "        return closed && !document.querySelector('.modal-backdrop'); }",
        arg=modal_id,
    )


def wait_for_material_suggestions(page: Page, query: str) -> None:
    """Wait for the material autocomplete to show results for `query`.

    MaterialSelector debounces its input handler by 200ms, so immediately after
    typing the dropdown is still showing the *previous* query's matches.
    Asserting that the dropdown is visible would pass against that stale list.

    The condition is that *every* entry matches the query, not merely one: a
    half-replaced list can briefly satisfy "some", and settling on the wrong
    moment is exactly the bug this is meant to rule out.
    """
    page.wait_for_function(
        """q => {
            const items = document.querySelectorAll(
                '.material-suggestions .suggestion-item');
            return items.length > 0 && Array.from(items).every(
                el => el.textContent.toLowerCase().includes(q.toLowerCase()));
        }""",
        arg=query,
    )


# The flag values the product page has buttons for, and the class each button
# carries once it is the active one. A value outside this mapping has no button
# to wait on, so it is rejected rather than turned into a selector.
_STOCK_FLAG_ACTIVE_CLASS = {'low': 'btn-warning', 'out': 'btn-danger'}


def wait_for_stock_flag(page: Page, status: str | None) -> None:
    """Wait for a stock-status button click to have taken effect.

    The buttons are type="button": they PATCH the API and then reload the page,
    so nothing has happened yet at the moment the click returns. Waiting on the
    reloaded button's own styling is the only observable proof the round trip
    finished -- and without it the next goto() aborts the in-flight PATCH.

    Args:
        page: The page showing the product detail view.
        status: 'low', 'out', or None for a cleared flag.

    Raises:
        ValueError: If status is not one of those three. Interpolating an
            unknown value into `#flag-{status}-btn` would instead wait out
            Playwright's full timeout against an element that never existed,
            and report it as a flaky UI rather than as the typo it is.
    """
    if status is not None and status not in _STOCK_FLAG_ACTIVE_CLASS:
        valid = ', '.join(repr(s) for s in _STOCK_FLAG_ACTIVE_CLASS)
        raise ValueError(f"Unknown stock flag {status!r}. Expected {valid}, or None")

    if status:
        colour = _STOCK_FLAG_ACTIVE_CLASS[status]
        expect(page.locator(f"#flag-{status}-btn")).to_have_class(
            re.compile(rf"\b{colour}\b")
        )
    else:
        # Cleared: every status button is back to its outline variant.
        expect(page.locator("#flag-low-btn")).to_have_class(
            re.compile(r"\bbtn-outline-warning\b")
        )
        expect(page.locator("#flag-out-btn")).to_have_class(
            re.compile(r"\bbtn-outline-danger\b")
        )


def wait_for_select_populated(page: Page, select_id: str) -> None:
    """Wait for a select that is filled from an API call after render.

    These selects ship with a single placeholder option, so "more than one
    option" is the observable proof that the fetch came back.
    """
    page.wait_for_function(
        "id => document.querySelectorAll(`#${id} option`).length > 1",
        arg=select_id,
    )
