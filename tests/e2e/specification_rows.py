"""Shared helpers for driving the repeating specification-row editor.

Every row posts under the same two field names, so a row is addressed by its
position rather than by an id. Adding a row is synchronous DOM work, which makes
``expect(rows).to_have_count(n)`` a complete signal for it -- there is no request
to wait on (CLAUDE.md pattern C, the cheap case).
"""

from playwright.sync_api import expect

ROWS = "#specification-rows .specification-row"
ADD_BUTTON = "#add-specification-btn"
NAME_INPUT = "[name='spec_name']"
# Not `input[...]`: a row holding a multi-line value renders a textarea, because
# an <input> silently strips the newlines out of one.
VALUE_INPUT = "[name='spec_value']"


def rows(page):
    """The specification rows currently on the form"""
    return page.locator(ROWS)


def row_pairs(page):
    """What the rows are showing, as (name, value) tuples in DOM order"""
    present = rows(page)
    expect(present).not_to_have_count(0)
    return [
        (
            present.nth(index).locator(NAME_INPUT).input_value(),
            present.nth(index).locator(VALUE_INPUT).input_value(),
        )
        for index in range(present.count())
    ]


def set_specifications(page, entries):
    """Make the form show exactly these ``(name, value)`` pairs.

    Grows the editor to fit, then fills positionally. Rows beyond the supplied
    entries are blanked rather than removed -- a fully blank row is dropped on
    save (FR-009), and removal has its own test rather than being smuggled in
    through every caller of this helper.
    """
    present = rows(page)
    # The editor keeps at least one row present, so there is always something
    # here to establish the region before reading its count.
    expect(present).not_to_have_count(0)

    already = present.count()
    for index in range(already, len(entries)):
        page.click(ADD_BUTTON)
        expect(present).to_have_count(index + 1)

    for index in range(max(already, len(entries))):
        name, value = entries[index] if index < len(entries) else ("", "")
        row = present.nth(index)
        row.locator(NAME_INPUT).fill(name)
        row.locator(VALUE_INPUT).fill(value)
