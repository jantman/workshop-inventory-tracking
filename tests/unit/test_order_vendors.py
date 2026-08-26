"""The consolidation seam itself (feature 029, contracts/order-vendor.md).

These tests are deliberately about the *shape* rather than the behaviour. The
behaviour is already specified, exhaustively, by the DigiKey and McMaster suites
that this feature must leave passing unedited -- those are the regression gate
and they say what capture does. What they cannot say, because they predate it,
is that there is now one implementation rather than two.

So what is asserted here is FR-036 and FR-037: that every vendor supplies the
same small set of things, that the things they supply differ where the vendors
genuinely differ, and that nothing else has quietly become vendor-specific.
"""

import pytest

from app.services.order_vendors import (
    LANDING_CHOICE_PAGE,
    LANDING_ORDER_SCREEN,
    OrderVendor,
    REGISTRY,
    for_vendor,
)

# Importing the service is what populates the registry -- the vendor-specific
# functions live there because they need its leaf helpers.
import app.catalog_service  # noqa: F401


class TestRegistry:
    """Every vendor that captures orders is registered, and findable by name."""

    def test_digikey_is_registered(self):
        assert for_vendor('DigiKey') is not None

    def test_mcmaster_is_registered(self):
        assert for_vendor('McMaster-Carr') is not None

    def test_a_vendor_name_no_order_flow_knows_is_none_not_an_error(self):
        """A purchase can carry a vendor recorded by hand.

        The order screen has to render one of those rather than 500, which is
        why this returns None instead of raising.
        """
        assert for_vendor('Some Shop On The High Street') is None
        assert for_vendor('') is None

    def test_each_registered_vendor_is_keyed_by_its_own_name(self):
        for name, vendor in REGISTRY.items():
            assert vendor.name == name


class TestEveryVendorSuppliesTheSameThings:
    """FR-036: the shared flow can drive any of them without knowing which."""

    @pytest.mark.parametrize('name', ['DigiKey', 'McMaster-Carr'])
    def test_the_required_members_are_all_callable(self, name):
        vendor = for_vendor(name)
        for member in (
            'item_id_of', 'order_purchases', 'order_fields', 'line_fields',
            'find_product', 'create_product', 'suggested_description',
        ):
            assert callable(getattr(vendor, member)), f"{name}.{member}"

    @pytest.mark.parametrize('name', ['DigiKey', 'McMaster-Carr'])
    def test_the_landing_is_one_the_receiving_path_understands(self, name):
        assert for_vendor(name).receive_landing in (
            LANDING_ORDER_SCREEN, LANDING_CHOICE_PAGE
        )


class TestTheyDifferWhereTheVendorsDiffer:
    """The measured variation from research.md §9, asserted rather than assumed."""

    def test_only_digikey_enriches(self):
        """DigiKey looks a part up; for the others the page *is* the detail."""
        assert for_vendor('DigiKey').enrich is not None
        assert for_vendor('McMaster-Carr').enrich is None

    def test_only_mcmaster_adopts_a_renamed_order(self):
        """McMaster's order 'number' is the customer's editable PO string.

        Rename it and a re-capture would write a duplicate purchase for every
        line, which is why 028 added purchases.vendor_order_id. Nobody else has
        that problem: DigiKey's sales order number and Amazon's order number are
        both stable.
        """
        assert for_vendor('McMaster-Carr').adopts_renames is True
        assert for_vendor('DigiKey').adopts_renames is False

    def test_digikey_scans_land_on_the_order_screen(self):
        """A DigiKey bag label names its order, so every candidate is one order's."""
        assert for_vendor('DigiKey').receive_landing == LANDING_ORDER_SCREEN

    def test_mcmaster_scans_land_on_the_choice_page(self):
        """A McMaster bag names only the part, so candidates can span orders."""
        assert for_vendor('McMaster-Carr').receive_landing == LANDING_CHOICE_PAGE

    def test_the_review_columns_differ(self):
        """DigiKey shows shipped/backorder; McMaster shows the pack arithmetic."""
        assert for_vendor('DigiKey').review_columns != for_vendor('McMaster-Carr').review_columns


class TestConstruction:
    def test_an_unknown_landing_is_refused_at_construction(self):
        """A typo here would silently send a scan nowhere."""
        with pytest.raises(ValueError, match='receive_landing'):
            OrderVendor(
                name='Nowhere',
                item_id_of=lambda line: '',
                order_purchases=lambda service, session, order: [],
                order_fields=lambda order: {},
                line_fields=lambda service, line, decision: {},
                find_product=lambda service, session, line: (None, False),
                create_product=lambda *a, **k: None,
                suggested_description=lambda line, part: '',
                receive_landing='somewhere-else',
            )

    def test_a_vendor_is_frozen(self):
        """Nothing reconfigures a vendor at runtime; there is no knob here."""
        with pytest.raises(Exception):
            for_vendor('DigiKey').name = 'Something Else'
