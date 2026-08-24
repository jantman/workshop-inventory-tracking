"""
Find Stock Page Object

Page object for the fit search -- "I need a piece this big, what can make it?".
Waits live here; assertions live in the tests.
"""

from typing import Dict, List, Optional

from playwright.sync_api import expect

from .base_page import BasePage
from .inventory_table_mixin import InventoryTableMixin
from tests.e2e.waits import dismiss_material_suggestions


class FindStockPage(InventoryTableMixin, BasePage):
    """Page object for the stock fit search"""

    # Request form
    FORM = "#find-stock-form"
    MATERIAL = "#material"
    SHAPE = "#piece_shape"
    SEARCH_BUTTON = "#find-stock-btn"
    CLEAR_BUTTON = "#clear-find-stock-btn"

    RECTANGULAR_FIELDS = "#rectangular-dimensions"
    ROUND_FIELDS = "#round-dimensions"

    # Results
    RESULTS_SECTION = "#find-stock-results-section"
    COUNTERS = "#find-stock-counters"
    NO_RESULTS = "#find-stock-no-results"
    ERROR = "#find-stock-error"
    TABLE_CONTAINER = "#find-stock-table-container"

    # Mixin overrides for this page's table
    TABLE_BODY_SELECTOR = "#find-stock-table-body"
    TABLE_ROWS_SELECTOR = "#find-stock-table-body tr"
    LOADING_STATE_SELECTOR = "#find-stock-loading"

    # The form field ids each requested shape uses. The round shape's length is
    # `round_length` because the rectangular shape already owns `length` and two
    # inputs cannot share an id.
    RECTANGULAR_INPUTS = {'length': 'length', 'width': 'width',
                          'thickness': 'thickness'}
    ROUND_INPUTS = {'diameter': 'diameter', 'length': 'round_length'}

    def navigate(self):
        """Navigate to the fit search page"""
        self.navigate_to("/inventory/find-stock")
        expect(self.page.locator(self.FORM)).to_be_visible()

    def fill_material(self, material: str) -> None:
        """Type into the material field and close its autocomplete.

        The material input is a MaterialSelector: typing opens a suggestion
        dropdown that overlays what is below it, so it has to be closed before
        anything else is clicked. `dismiss_material_suggestions` carries the
        reasoning about the 200ms debounce that makes that harder than it looks.
        """
        self.fill_and_wait(self.MATERIAL, material)
        dismiss_material_suggestions(self.page)

    def select_shape(self, shape: str) -> None:
        """Choose Rectangular or Round, and wait for the inputs to swap.

        The change handler toggles `d-none` synchronously, so the fields the
        caller is about to fill being visible is the whole condition.
        """
        self.page.select_option(self.SHAPE, shape)
        fields = self.ROUND_FIELDS if shape == 'Round' else self.RECTANGULAR_FIELDS
        expect(self.page.locator(fields)).to_be_visible()

    def _fill_dimensions(self, inputs: Dict[str, str], values: Dict[str, str],
                         tolerances: Optional[Dict[str, str]]) -> None:
        for name, field_id in inputs.items():
            self.fill_and_wait(f"#{field_id}", str(values[name]))
            tolerance = (tolerances or {}).get(name)
            # A field left alone means the dimension is exact. Filling it with
            # an empty string is the same thing, and is what clears one that a
            # previous search set.
            self.fill_and_wait(f"#{field_id}_tolerance",
                               '' if tolerance is None else str(tolerance))

    def search_rectangular(self, material: str, length, width, thickness,
                           tolerances: Optional[Dict[str, str]] = None) -> None:
        """Run one rectangular search, end to end."""
        self.select_shape('Rectangular')
        self.fill_material(material)
        self._fill_dimensions(
            self.RECTANGULAR_INPUTS,
            {'length': length, 'width': width, 'thickness': thickness},
            tolerances,
        )
        self.submit()

    def search_round(self, material: str, diameter, length,
                     tolerances: Optional[Dict[str, str]] = None) -> None:
        """Run one round search, end to end."""
        self.select_shape('Round')
        self.fill_material(material)
        self._fill_dimensions(
            self.ROUND_INPUTS,
            {'diameter': diameter, 'length': length},
            tolerances,
        )
        self.submit()

    def submit(self) -> None:
        """Submit the form and wait for the search to have rendered its outcome."""
        self.page.click(self.SEARCH_BUTTON)
        self.wait_for_search_complete()

    def wait_for_search_complete(self) -> None:
        """Wait until the search has finished and shown one of its three outcomes.

        performSearch() synchronously shows the spinner and hides all three
        outcome panes before it awaits the API, so this cannot pass on the
        previous search's results: it requires the spinner gone *and* one of the
        results table, the empty state, or the refusal shown.
        """
        self.page.wait_for_function(
            """() => {
                const hidden = (id) => {
                    const el = document.getElementById(id);
                    return !el || el.classList.contains('d-none');
                };
                return hidden('find-stock-loading')
                    && (!hidden('find-stock-table-container')
                        || !hidden('find-stock-no-results')
                        || !hidden('find-stock-error'));
            }"""
        )

    def expect_result_count(self, count: int) -> None:
        """Establish the rendered row count before anything reads the table.

        Pattern C: the handler appends rows only after awaiting the fetch, so a
        rendered row cannot predate a completed search. Every negative assertion
        in the tests goes through this first, or it would pass trivially against
        a table that has not loaded.
        """
        expect(self.page.locator(self.TABLE_ROWS_SELECTOR)).to_have_count(count)

    def result_ja_ids(self) -> List[str]:
        """The JA IDs of the rendered rows, in the order they are rendered."""
        return [item["ja_id"] for item in self.get_table_items()]

    def fit_text_for(self, ja_id: str) -> str:
        """The Fit cell of one row -- the last cell before Actions."""
        row = self._row_for(ja_id)
        return (row.locator("td").nth(-2).text_content() or "").strip()

    def expect_counters_to_contain(self, text: str) -> None:
        """The counters line is written in the same handler pass as the rows."""
        expect(self.page.locator(self.COUNTERS)).to_contain_text(text)

    def expect_no_results(self) -> None:
        expect(self.page.locator(self.NO_RESULTS)).to_be_visible()

    def column_headers(self) -> List[str]:
        """Every header of the results table, in order."""
        headers = self.page.locator(f"{self.TABLE_CONTAINER} thead th")
        expect(headers.first).to_be_visible()
        return [(headers.nth(i).text_content() or "").strip()
                for i in range(headers.count())]
