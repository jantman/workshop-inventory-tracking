"""
Unit tests for typing a count rather than clicking to it (039, issue #139).

Two things are covered here, and neither is the arithmetic -- ``set_quantity``
already had tests and is unchanged.

- **The endpoint really does take an absolute count.** That was always true and
  nothing ever sent it one, which is the whole of issue #139. These assert the
  requests the Stock card now makes, so a later change that quietly turns the
  endpoint into a delta fails here rather than in a browser.
- **``received_total``.** Receiving guards on ``product.quantity is not None``,
  so stock received into an untracked product moved no count. The product page
  states the total where the starting count is entered -- and states it only
  there, because on a tracked product receiving has already added it and saying
  it twice invites counting it twice.
"""

from datetime import datetime

import pytest

from app.catalog_service import CatalogService


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


def received(service, product_id, quantity, vendor='Acme'):
    """A purchase that has arrived. Received purchases are what FR-012 totals."""
    return service.record_purchase(
        product_id=product_id,
        vendor=vendor,
        quantity=quantity,
        received_date=datetime(2026, 8, 1),
    )


def outstanding(service, product_id, quantity, vendor='Acme'):
    """Ordered, not yet arrived. ``is_outstanding`` is ``received_date is None``."""
    return service.record_purchase(
        product_id=product_id, vendor=vendor, quantity=quantity
    )


class TestSettingAnAbsoluteQuantity:
    """PATCH /api/products/<id>/quantity -- the request the Set button makes."""

    def test_a_typed_count_replaces_the_existing_one(self, client, service):
        product = service.create_product(description='Resistor', quantity=3)

        response = client.patch(
            f'/api/products/{product.id}/quantity', json={'quantity': 40}
        )

        assert response.status_code == 200
        assert response.get_json()['success'] is True
        # Replaced, not added to. Forty is forty, not forty-three.
        assert service.get_product(product.id).quantity == 40

    def test_setting_a_count_stamps_its_date(self, client, service):
        product = service.create_product(description='Resistor')
        assert service.get_product(product.id).quantity_updated_at is None

        client.patch(f'/api/products/{product.id}/quantity', json={'quantity': 40})

        assert service.get_product(product.id).quantity_updated_at is not None

    def test_re_committing_the_same_count_refreshes_its_date(self, client, service):
        """FR-003: re-entering the count is "I have just looked again"."""
        product = service.create_product(description='Resistor', quantity=40)
        before = service.get_product(product.id).quantity_updated_at

        client.patch(f'/api/products/{product.id}/quantity', json={'quantity': 40})

        after = service.get_product(product.id)
        assert after.quantity == 40
        assert after.quantity_updated_at >= before

    def test_a_started_count_can_begin_at_a_number(self, client, service):
        """FR-004: beginning a count no longer has to begin at zero."""
        product = service.create_product(description='Resistor')

        client.patch(f'/api/products/{product.id}/quantity', json={'quantity': 12})

        assert service.get_product(product.id).quantity == 12

    def test_zero_is_counted_with_none_on_hand_not_untracked(self, client, service):
        """FR-005. Two of the three states, and they must not collapse."""
        product = service.create_product(description='Resistor', quantity=5)

        client.patch(f'/api/products/{product.id}/quantity', json={'quantity': 0})

        assert service.get_product(product.id).quantity == 0

    def test_only_an_explicit_null_stops_counting(self, client, service):
        product = service.create_product(description='Resistor', quantity=5)

        client.patch(f'/api/products/{product.id}/quantity', json={'quantity': None})

        assert service.get_product(product.id).quantity is None

    @pytest.mark.parametrize('bad', [-1, 'lots'])
    def test_a_refused_count_leaves_the_stored_one_alone(self, client, service, bad):
        product = service.create_product(description='Resistor', quantity=7)

        response = client.patch(
            f'/api/products/{product.id}/quantity', json={'quantity': bad}
        )

        assert response.status_code == 400
        assert response.get_json()['success'] is False
        assert service.get_product(product.id).quantity == 7

    def test_a_fractional_count_is_truncated_rather_than_refused(self, client, service):
        """Recorded because it surprised us, not because it is wanted.

        ``_validate_quantity`` coerces with ``int()``, so 2.5 becomes 2 without
        complaint. Nothing sends a fraction: the Stock card only sends the
        integer parse of a string it has already matched against ``^\\d+$``, and
        a fractional entry is refused in the browser with a message (FR-007) --
        ``tests/e2e/test_typed_quantity.py`` covers that.

        Left alone deliberately. The validator is shared with product creation
        and editing, where quantities arrive as form strings, so tightening it
        here would be a change to two paths that did not ask for one in order to
        guard against a client that does not exist (research.md, section 2).
        """
        product = service.create_product(description='Resistor', quantity=7)

        response = client.patch(
            f'/api/products/{product.id}/quantity', json={'quantity': 2.5}
        )

        assert response.status_code == 200
        assert service.get_product(product.id).quantity == 2


class TestReceivedTotal:
    """FR-012 to FR-014 -- what the page states next to the starting count."""

    def context(self, client, product_id):
        """The rendered page. There is one render path for product detail."""
        return client.get(f'/products/{product_id}')

    def test_received_purchases_are_summed(self, client, service):
        product = service.create_product(description='Resistor')
        received(service, product.id, 60)
        received(service, product.id, 40)

        assert b'100 received' in self.context(client, product.id).data

    def test_an_outstanding_purchase_is_not_counted(self, client, service):
        """It has not arrived. Nothing about it is on any shelf."""
        product = service.create_product(description='Resistor')
        received(service, product.id, 60)
        outstanding(service, product.id, 40)

        page = self.context(client, product.id).data
        assert b'60 received' in page
        assert b'100 received' not in page

    def test_a_received_purchase_with_no_quantity_contributes_nothing(
        self, client, service
    ):
        """And does not suppress the ones that do carry a quantity."""
        product = service.create_product(description='Resistor')
        received(service, product.id, 60)
        received(service, product.id, None)

        assert b'60 received' in self.context(client, product.id).data

    def test_nothing_is_stated_when_there_are_no_purchases(self, client, service):
        product = service.create_product(description='Resistor')

        assert b'received for this product' not in self.context(client, product.id).data

    def test_nothing_is_stated_when_nothing_has_been_received(self, client, service):
        product = service.create_product(description='Resistor')
        outstanding(service, product.id, 40)

        assert b'received for this product' not in self.context(client, product.id).data

    def test_a_zero_total_states_nothing(self, client, service):
        """FR-014: there is no "0 received" rendering, because it is noise."""
        product = service.create_product(description='Resistor')
        received(service, product.id, None)

        assert b'received for this product' not in self.context(client, product.id).data

    def test_the_line_does_not_claim_the_total_is_uncounted(self, client, service):
        """It cannot know, so it must not say (PR #151 review).

        The sum is over every received purchase for the product's whole life;
        the guard is on whether it is tracked *now*. Receive into a tracked
        product -- where the count does absorb the arrival -- then stop
        counting, and the line is reached with a total that *was* counted. A
        claim of "none of it counted" would be false there, and false in the
        direction that invites double-counting.
        """
        product = service.create_product(description='Resistor', quantity=5)
        purchase = outstanding(service, product.id, 100)

        # Received while tracked, so the count really does absorb it. Asserted
        # rather than assumed: `receive_purchase` only adds when the purchase
        # was not already received, so seeding one with a received_date and
        # calling it again would prove nothing.
        service.receive_purchase(purchase.id)
        assert service.get_product(product.id).quantity == 105

        # Then tracking stops, which clears the count and leaves the purchase
        # history untouched -- so the line below is reached with a lifetime
        # total that a count did once absorb.
        service.set_quantity(product.id, None)

        page = self.context(client, product.id).data
        assert b'100 received' in page
        assert b'none of it counted' not in page

    def test_nothing_is_stated_once_the_product_is_counted(self, client, service):
        """FR-013. Receiving already added it; saying so again invites
        adding it a second time."""
        product = service.create_product(description='Resistor')
        received(service, product.id, 100)
        assert b'100 received' in self.context(client, product.id).data

        service.set_quantity(product.id, 100)

        assert b'received for this product' not in self.context(client, product.id).data


class TestTheTypedControlIsRendered:
    """The contract the E2E suite binds to (contracts/stock-card-ui.md)."""

    def test_the_entry_is_present_on_a_counted_product(self, client, service):
        product = service.create_product(description='Resistor', quantity=40)

        page = client.get(f'/products/{product.id}').data
        assert b'id="quantity-input"' in page
        assert b'id="quantity-set-btn"' in page

    def test_the_entry_carries_the_current_count(self, client, service):
        """So that committing an unchanged field is a re-verification rather
        than an accident."""
        product = service.create_product(description='Resistor', quantity=40)

        assert b'value="40"' in client.get(f'/products/{product.id}').data

    def test_the_set_button_is_absent_while_untracked(self, client, service):
        """FR-011. "Start counting this" is the commit control in that state,
        and two commit buttons would be ambiguous."""
        product = service.create_product(description='Resistor')

        page = client.get(f'/products/{product.id}').data
        assert b'id="quantity-input"' in page
        assert b'id="quantity-set-btn"' not in page
        assert b'id="start-tracking-btn"' in page

    def test_the_steppers_survive(self, client, service):
        """FR-009. The typed entry is an addition, never a replacement -- they
        are the only count control that works with no keyboard."""
        product = service.create_product(description='Resistor', quantity=40)

        page = client.get(f'/products/{product.id}').data
        assert b'id="quantity-decrement"' in page
        assert b'id="quantity-increment"' in page
        assert b'id="stop-tracking-btn"' in page

    def test_the_entry_asks_for_the_numeric_keypad(self, client, service):
        """FR-010. A control that needs a physical keyboard does not exist on
        the handheld this card was built for."""
        product = service.create_product(description='Resistor', quantity=40)

        assert b'inputmode="numeric"' in client.get(f'/products/{product.id}').data
