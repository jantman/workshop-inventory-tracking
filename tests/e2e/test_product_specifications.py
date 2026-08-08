"""
E2E tests for structured product specifications.

This file carries the three requirements `nox -s tests` cannot prove. SQLite
collates BINARY, so a case-sensitive implementation of the duplicate check
(FR-004), the name filter (FR-015) and the suggestion dedup (FR-019) passes the
unit suite and always would. The testcontainer runs the deployed collation
(utf8mb4_uca1400_ai_ci), which is the only place those three are observable --
the same gap commit 091e918 paid for when it deleted a tag and every one of its
product associations.

Seeding goes through live_server.add_test_products except where the form itself
is what is under test: the round-trip, the refusals and the suggestions.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.specification_rows import (
    ADD_BUTTON,
    NAME_INPUT,
    ROWS,
    VALUE_INPUT,
    row_pairs,
    set_specifications,
)

SPEC_NAMES = "#product-specifications .specification-name"
SPEC_VALUES = "#product-specifications .specification-value"


def add_product(page, base_url, description, specifications=None, **fields):
    """Create a product through the form, which is what most of US1 is about"""
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)
    for field, value in fields.items():
        page.fill(f"#{field}", value)
    if specifications is not None:
        set_specifications(page, specifications)
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")


def shown_specifications(page):
    """The name/value pairs the detail page is displaying, in display order"""
    names = page.locator(SPEC_NAMES)
    expect(names).not_to_have_count(0)
    values = page.locator(SPEC_VALUES)
    return [
        (names.nth(i).inner_text().strip(), values.nth(i).inner_text().strip())
        for i in range(names.count())
    ]


def listed(page):
    """Descriptions currently shown in the catalogue table"""
    links = page.locator("#product-table tbody tr td:first-child a")
    return sorted(links.nth(i).inner_text().strip() for i in range(links.count()))


# ---------------------------------------------------------------------------
# User Story 1 -- record specifications as named values
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_three_rows_round_trip_in_entry_order(page, live_server):
    """The MVP: named values, laid out as fields, in the order entered"""
    entered = [
        ("Voltage", "12 V"),
        ("Output current", "3 A"),
        ("Connector", "barrel 5.5 mm"),
    ]
    add_product(page, live_server.url, "Buck converter", specifications=entered)

    expect(page.locator("#product-description")).to_have_text("Buck converter")
    # Not alphabetized -- "Connector" would sort first if it were.
    assert shown_specifications(page) == entered


@pytest.mark.e2e
def test_editing_changes_removes_and_adds_a_row(page, live_server):
    """Each specification is an editable pair, and the save is exactly what is left"""
    product = live_server.add_test_products([{
        'description': 'Buck converter',
        'specifications': [
            {'name': 'Voltage', 'value': '12 V'},
            {'name': 'Output current', 'value': '3 A'},
        ],
    }])[0]

    page.goto(f"{live_server.url}/products/{product.id}/edit")
    rows = page.locator(ROWS)
    expect(rows).to_have_count(2)

    # Change the first, remove the second, add a third.
    rows.nth(0).locator(VALUE_INPUT).fill("24 V")
    rows.nth(1).locator(".remove-specification-btn").click()
    expect(rows).to_have_count(1)
    page.click(ADD_BUTTON)
    expect(rows).to_have_count(2)
    rows.nth(1).locator(NAME_INPUT).fill("Connector")
    rows.nth(1).locator(VALUE_INPUT).fill("barrel 5.5 mm")

    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    assert shown_specifications(page) == [
        ("Voltage", "24 V"), ("Connector", "barrel 5.5 mm")
    ]


@pytest.mark.e2e
def test_a_migrated_paragraph_is_shown_whole(page, live_server):
    """What a product created before this change looks like afterwards.

    The revision carries each old paragraph across as one row named
    ``Specifications`` -- never split at its colon or its newline -- so this is
    the shape the detail page has to render. That the *migration* produces this
    row is checked against MariaDB by hand (quickstart, "the migration
    round-trip"); what is checked here is that the page shows it whole.
    """
    paragraph = "Voltage: 12 V\nCurrent: 3 A"
    product = live_server.add_test_products([{
        'description': 'Created before the migration',
        'specifications': [{'name': 'Specifications', 'value': paragraph}],
    }])[0]

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#product-specifications")).to_be_visible()

    assert shown_specifications(page) == [("Specifications", paragraph)]


@pytest.mark.e2e
def test_editing_a_product_does_not_reflow_a_migrated_paragraph(page, live_server):
    """A save that never touched the specifications must not rewrite them.

    A multi-line value cannot survive an ``<input value=...>``: the HTML value
    sanitization algorithm strips CR and LF, so the field posts back one run-on
    line and the paragraph the migration promised to carry across verbatim is
    silently destroyed by an unrelated edit. The value field is therefore a
    textarea whenever the stored value has a newline in it.
    """
    paragraph = "Voltage: 12 V\nCurrent: 3 A, knurled collar"
    product = live_server.add_test_products([{
        'description': 'Created before the migration',
        'specifications': [{'name': 'Specifications', 'value': paragraph}],
    }])[0]

    page.goto(f"{live_server.url}/products/{product.id}/edit")
    expect(page.locator(ROWS)).to_have_count(1)

    # Change something else entirely and save.
    page.fill("#description", "Renamed, specifications untouched")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#product-description")).to_have_text(
        "Renamed, specifications untouched"
    )
    assert shown_specifications(page) == [("Specifications", paragraph)]


@pytest.mark.e2e
def test_a_product_with_no_specifications_shows_no_card(page, live_server):
    """An ordinary state, not an error"""
    add_product(page, live_server.url, "Plain widget")

    expect(page.locator("#product-description")).to_have_text("Plain widget")
    # The description established the page, so this negative cannot pass
    # trivially against a page that has not rendered.
    expect(page.locator("#product-specifications")).to_have_count(0)


@pytest.mark.e2e
def test_a_blank_row_alongside_good_ones_saves_without_complaint(page, live_server):
    """FR-009: an untouched row on the form is not an error"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", "Buck converter")
    set_specifications(page, [("Voltage", "12 V"), ("", ""), ("Current", "3 A")])
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    assert shown_specifications(page) == [("Voltage", "12 V"), ("Current", "3 A")]


@pytest.mark.e2e
@pytest.mark.parametrize("entries,offender", [
    # FR-004, and the case SQLite cannot see: these differ only in case.
    ([("Voltage", "12 V"), ("voltage", "5 V")], "voltage"),
    ([("Voltage", "")], "Voltage"),
    ([("", "12 V")], "12 V"),
])
def test_a_refusal_re_renders_with_a_message_and_saves_nothing(
    page, live_server, entries, offender
):
    """FR-008: the refusal names the offender and nothing is created"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", "Never created")
    set_specifications(page, entries)
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator(".alert-danger")).to_contain_text(offender)
    # Still on the form, carrying what was typed rather than a blank slate.
    expect(page.locator("#description")).to_have_value("Never created")
    assert row_pairs(page)[:len(entries)] == entries

    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-filters")).to_be_visible()
    assert listed(page) == []


@pytest.mark.e2e
def test_two_names_differing_only_by_accent_both_save(page, live_server):
    """The case a UniqueConstraint would have broken under the deployed collation.

    utf8mb4_uca1400_ai_ci folds accents as well as case, so a unique index on
    (product_id, name) would reject this pair -- stricter than FR-004, which
    speaks only of case and whitespace. There is no such constraint, and this is
    the test that says why.
    """
    entered = [("Volt", "12"), ("Vôlt", "5")]
    add_product(page, live_server.url, "Accented", specifications=entered)

    assert shown_specifications(page) == entered


# ---------------------------------------------------------------------------
# User Story 2 -- find every product with a given specification
# ---------------------------------------------------------------------------


@pytest.fixture
def converters(live_server):
    """Two recorded voltages and one product that merely mentions 12 V"""
    live_server.add_test_products([
        {
            'description': '12 V buck converter',
            'category_path': 'electronics/power',
            'specifications': [
                {'name': 'Voltage', 'value': '12 V'},
                {'name': 'Output current', 'value': '3 A'},
            ],
        },
        {
            'description': '5 V buck converter',
            'category_path': 'electronics/power',
            'specifications': [{'name': 'Voltage', 'value': '5 V'}],
        },
        {
            'description': 'Bench supply with 12 V input',
            'category_path': 'electronics/test-gear',
        },
    ])
    return live_server


def filtered(page, base_url, **params):
    """Open the catalogue with these filters applied and return what it lists"""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    page.goto(f"{base_url}/products?{query}")
    # The filter card renders with the page, so it establishes the region
    # before any count() is read off the table.
    expect(page.locator("#product-filters")).to_be_visible()
    return listed(page)


@pytest.mark.e2e
def test_a_name_and_value_exclude_the_product_that_merely_mentions_it(
    page, converters
):
    """SC-001, the question the whole feature exists to answer"""
    assert filtered(
        page, converters.url, spec_name="Voltage", spec_value="12+V"
    ) == ["12 V buck converter"]


@pytest.mark.e2e
def test_a_name_alone_returns_every_value_under_it(page, converters):
    assert filtered(page, converters.url, spec_name="Voltage") == [
        "12 V buck converter", "5 V buck converter"
    ]


@pytest.mark.e2e
def test_a_lower_case_name_matches_a_capitalised_one(page, converters):
    """FR-015 end to end, through the route and the form.

    This does *not* guard the implementation the way the other two collation
    tests guard theirs: MariaDB's utf8mb4_uca1400_ai_ci makes a bare ``==``
    case-insensitive on its own, so replacing ``func.lower(name) == ...`` with
    ``name == ...`` leaves this green. Confirmed by doing exactly that (T032).
    The test that turns red is the SQLite one --
    TestSpecificationFilter.test_the_name_filter_is_case_insensitive.
    """
    assert filtered(page, converters.url, spec_name="voltage") == [
        "12 V buck converter", "5 V buck converter"
    ]


@pytest.mark.e2e
def test_a_contained_value_matches(page, converters):
    """FR-014: contained, not exact"""
    assert filtered(
        page, converters.url, spec_name="Voltage", spec_value="12"
    ) == ["12 V buck converter"]


@pytest.mark.e2e
def test_it_narrows_together_with_a_category(page, converters):
    """FR-016"""
    assert filtered(
        page, converters.url, spec_name="Voltage", category="electronics/power"
    ) == ["12 V buck converter", "5 V buck converter"]
    assert filtered(
        page, converters.url, spec_name="Voltage", category="electronics/test-gear"
    ) == []


@pytest.mark.e2e
def test_an_unrecorded_name_is_an_empty_list_not_an_error(page, converters):
    assert filtered(page, converters.url, spec_name="Nobody+records+this") == []


@pytest.mark.e2e
def test_free_text_still_reaches_a_word_only_in_a_specification(page, converters):
    """FR-017: nothing findable before this change may stop being findable"""
    assert filtered(page, converters.url, q="3+A") == ["12 V buck converter"]


@pytest.mark.e2e
def test_following_a_link_from_the_detail_page_lands_on_the_filtered_catalogue(
    page, converters
):
    """FR-018"""
    assert filtered(page, converters.url, spec_name="Voltage") == [
        "12 V buck converter", "5 V buck converter"
    ]
    page.click("text=12 V buck converter")
    expect(page.locator("#product-specifications")).to_be_visible()

    page.locator(SPEC_VALUES).nth(0).locator("a").click()
    expect(page.locator("#product-filters")).to_be_visible()

    expect(page.locator("#filter-spec-name")).to_have_value("Voltage")
    expect(page.locator("#filter-spec-value")).to_have_value("12 V")
    assert listed(page) == ["12 V buck converter"]


# ---------------------------------------------------------------------------
# User Story 3 -- keep specification names consistent
# ---------------------------------------------------------------------------


def datalist_options(page, selector):
    """The option values currently in a datalist.

    Options are appended only after the fetch resolves, so the caller waits with
    expect(...).to_have_count(n) first -- a rendered option cannot predate a
    completed request (CLAUDE.md pattern C).
    """
    options = page.locator(f"{selector} option")
    return sorted(
        options.nth(i).get_attribute("value") for i in range(options.count())
    )


@pytest.mark.e2e
def test_a_name_recorded_elsewhere_is_offered(page, live_server):
    live_server.add_test_products([{
        'description': 'Buck converter',
        'specifications': [
            {'name': 'Voltage', 'value': '12 V'},
            {'name': 'Output current', 'value': '3 A'},
        ],
    }])

    page.goto(f"{live_server.url}/products/new")
    names = "#specification-name-suggestions"
    expect(page.locator(f"{names} option")).to_have_count(2)
    assert datalist_options(page, names) == ["Output current", "Voltage"]


@pytest.mark.e2e
def test_one_name_recorded_in_two_cases_yields_one_suggestion(page, live_server):
    """FR-019. The second case the unit suite cannot prove -- SELECT DISTINCT
    folds under the deployed collation and does not under SQLite, which is why
    the dedup runs in Python."""
    live_server.add_test_products([
        {'description': 'first',
         'specifications': [{'name': 'Voltage', 'value': '12 V'}]},
        {'description': 'second',
         'specifications': [{'name': 'voltage', 'value': '5 V'}]},
    ])

    page.goto(f"{live_server.url}/products/new")
    names = "#specification-name-suggestions"
    expect(page.locator(f"{names} option")).to_have_count(1)


@pytest.mark.e2e
def test_value_suggestions_are_scoped_to_the_entered_name(page, live_server):
    live_server.add_test_products([
        {'description': 'first', 'specifications': [
            {'name': 'Voltage', 'value': '12 V'},
            {'name': 'Connector', 'value': 'barrel 5.5 mm'},
        ]},
        {'description': 'second',
         'specifications': [{'name': 'Voltage', 'value': '5 V'}]},
    ])

    page.goto(f"{live_server.url}/products/new")
    row = page.locator(ROWS).nth(0)
    values = row.locator(".specification-value-suggestions")

    row.locator(NAME_INPUT).fill("Voltage")
    row.locator(NAME_INPUT).blur()
    expect(values.locator("option")).to_have_count(2)

    # Changing the row's name changes that row's value suggestions -- they are
    # per row, not one shared list offering a connector under a voltage.
    row.locator(NAME_INPUT).fill("Connector")
    row.locator(NAME_INPUT).blur()
    expect(values.locator("option")).to_have_count(1)
    expect(values.locator("option").nth(0)).to_have_attribute(
        "value", "barrel 5.5 mm"
    )


@pytest.mark.e2e
def test_a_brand_new_name_and_value_are_accepted_anyway(page, live_server):
    """FR-021: a datalist cannot restrict entry, which is why one is used"""
    live_server.add_test_products([{
        'description': 'existing',
        'specifications': [{'name': 'Voltage', 'value': '12 V'}],
    }])

    add_product(page, live_server.url, "Novel",
                specifications=[("Thread pitch", "M4x0.7")])

    assert shown_specifications(page) == [("Thread pitch", "M4x0.7")]


@pytest.mark.e2e
def test_the_filter_offers_the_same_names(page, live_server):
    live_server.add_test_products([{
        'description': 'Buck converter',
        'specifications': [
            {'name': 'Voltage', 'value': '12 V'},
            {'name': 'Output current', 'value': '3 A'},
        ],
    }])

    page.goto(f"{live_server.url}/products")
    names = "#specification-name-suggestions"
    expect(page.locator(f"{names} option")).to_have_count(2)
    assert datalist_options(page, names) == ["Output current", "Voltage"]
