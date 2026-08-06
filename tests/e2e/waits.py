"""Shared readiness waits for E2E tests.

These exist because several places in the UI finish asynchronously in ways that
have no single element to assert on. Each function waits for a specific
observable condition -- never for a duration. See
`specs/002-e2e-test-performance/contracts/e2e-test-authoring.md` for the rules
these support.
"""


def wait_for_modal_shown(page, modal_id):
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


def wait_for_modal_hidden(page, modal_id):
    """Wait until a Bootstrap modal has finished fading out and been detached."""
    page.wait_for_function(
        "id => { const m = document.getElementById(id);"
        "        return !m || !m.classList.contains('show'); }",
        arg=modal_id,
    )


def wait_for_material_suggestions(page, query):
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


def wait_for_select_populated(page, select_id):
    """Wait for a select that is filled from an API call after render.

    These selects ship with a single placeholder option, so "more than one
    option" is the observable proof that the fetch came back.
    """
    page.wait_for_function(
        "id => document.querySelectorAll(`#${id} option`).length > 1",
        arg=select_id,
    )
