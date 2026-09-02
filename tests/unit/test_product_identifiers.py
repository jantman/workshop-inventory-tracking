"""
The identifier add/remove HTTP contract, as the product detail card consumes it.

Both endpoints predate this feature and neither had a UI caller (#136), so the
service-level rules were covered but the *wire* was not: what a browser actually
receives for each outcome, and under which key the message arrives. That last
part is the trap. A route's own refusal answers ``{'error': ...}``; a missing
product is raised past the route and answered by the central handler as
``{'message': ...}``. Reading only one of the two shows the operator "undefined"
for the other, and no service-level test can see it.

These pin the contract in specs/036-manage-product-identifiers/contracts/.
"""

import pytest

from app.catalog_service import CatalogService
from app.models import IdentifierType, OPERATOR_IDENTIFIER_TYPES

# A real UPC-A and the 14-digit key it normalizes to. Same trade item, and what
# is stored is the key -- which is why the card cannot echo what was typed.
VALID_UPC = '687117723741'
VALID_GTIN_KEY = '00687117723741'

# Right length, wrong check digit.
BAD_CHECK_DIGIT = '687117723742'


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def product(service):
    return service.create_product(description='Dorhea ESP32-S3-DevKit')


def identifiers_url(product_id):
    return f'/api/products/{product_id}/identifiers'


class TestOperatorIdentifierTypes:
    """FR-003: one list, so the two forms cannot drift apart"""

    def test_internal_is_not_offered(self):
        """It is generated, never typed -- there is nothing to enter"""
        assert IdentifierType.INTERNAL.value not in OPERATOR_IDENTIFIER_TYPES

    def test_every_other_type_is_offered(self):
        """A sixth type added later joins both forms or fails here"""
        assert set(OPERATOR_IDENTIFIER_TYPES) == {
            member.value for member in IdentifierType
        } - {IdentifierType.INTERNAL.value}

    def test_the_order_is_the_enum_order(self):
        assert OPERATOR_IDENTIFIER_TYPES == ('MPN', 'GTIN', 'VENDOR', 'DISTRIBUTOR')


class TestAddIdentifier:
    """POST /api/products/<id>/identifiers"""

    def test_a_valid_barcode_is_stored_as_its_key(self, client, product):
        """FR-005: the card must render this, not what was typed"""
        response = client.post(
            identifiers_url(product.id),
            json={'id_type': 'GTIN', 'value': VALID_UPC},
        )

        assert response.status_code == 201
        body = response.get_json()
        assert body['success'] is True
        assert body['identifier']['value'] == VALID_GTIN_KEY
        assert body['identifier']['validation_overridden'] is False

    def test_a_bad_check_digit_is_refused(self, client, product):
        """FR-006: a mistyped barcode that silently works is worse than one that does not"""
        response = client.post(
            identifiers_url(product.id),
            json={'id_type': 'GTIN', 'value': BAD_CHECK_DIGIT},
        )

        assert response.status_code == 400
        body = response.get_json()
        assert body['success'] is False
        assert 'not a valid barcode' in body['error']

    def test_a_bad_check_digit_is_stored_on_an_explicit_override(self, client, product):
        """FR-006: kept, and the override recorded on the row rather than silent"""
        response = client.post(
            identifiers_url(product.id),
            json={'id_type': 'GTIN', 'value': BAD_CHECK_DIGIT, 'override': True},
        )

        assert response.status_code == 201
        assert response.get_json()['identifier']['validation_overridden'] is True

    def test_an_all_zero_read_is_refused(self, client, product):
        """FR-007: a scanner no-read is never a trade item"""
        response = client.post(
            identifiers_url(product.id),
            json={'id_type': 'GTIN', 'value': '00000000000000'},
        )

        assert response.status_code == 400
        assert 'zeros' in response.get_json()['error']

    def test_an_all_zero_read_is_refused_even_with_the_override(self, client, product):
        """FR-007: the one refusal the override does not reach"""
        response = client.post(
            identifiers_url(product.id),
            json={'id_type': 'GTIN', 'value': '00000000000000', 'override': True},
        )

        assert response.status_code == 400
        assert 'zeros' in response.get_json()['error']

    def test_a_value_owned_by_another_product_is_refused_by_name(self, client, service, product):
        """FR-009: the operator decides, so they have to be told which product"""
        other = service.create_product(description='Something else')
        service.add_identifier(other.id, IdentifierType.GTIN.value, VALID_UPC)

        response = client.post(
            identifiers_url(product.id),
            json={'id_type': 'GTIN', 'value': VALID_UPC},
        )

        assert response.status_code == 409
        body = response.get_json()
        assert body['success'] is False
        assert body['owning_product_id'] == other.id

    def test_a_missing_product_answers_json_under_message(self, client):
        """FR-019: raised past the route, so the key is 'message' and not 'error'"""
        response = client.post(
            identifiers_url(999999),
            json={'id_type': 'MPN', 'value': 'ACME-1'},
        )

        assert response.status_code == 404
        body = response.get_json()
        assert body['success'] is False
        assert 'error' not in body
        assert '999999' in body['message']

    def test_re_adding_the_same_value_leaves_one_row(self, client, service, product):
        """FR-010: the state asked for already holds; that is not a failure"""
        for _ in range(2):
            response = client.post(
                identifiers_url(product.id),
                json={'id_type': 'GTIN', 'value': VALID_UPC},
            )
            assert response.status_code == 201

        stored = service.get_product(product.id).identifiers
        assert [i.value for i in stored if i.id_type == 'GTIN'] == [VALID_GTIN_KEY]

    def test_an_empty_value_is_refused(self, client, product):
        response = client.post(
            identifiers_url(product.id), json={'id_type': 'MPN', 'value': '   '}
        )

        assert response.status_code == 400
        assert 'required' in response.get_json()['error']


class TestVendorScopedTypes:
    """FR-008: a vendor's item id is only meaningful within that vendor"""

    @pytest.mark.parametrize('id_type', ['VENDOR', 'DISTRIBUTOR'])
    def test_refused_without_a_vendor(self, client, product, id_type):
        response = client.post(
            identifiers_url(product.id),
            json={'id_type': id_type, 'value': 'B0ABCDEFGH'},
        )

        assert response.status_code == 400
        assert 'vendor' in response.get_json()['error']

    @pytest.mark.parametrize('id_type', ['VENDOR', 'DISTRIBUTOR'])
    def test_stored_with_a_vendor(self, client, product, id_type):
        response = client.post(
            identifiers_url(product.id),
            json={'id_type': id_type, 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'},
        )

        assert response.status_code == 201
        assert response.get_json()['identifier']['vendor'] == 'Amazon'

    def test_an_mpn_needs_no_vendor(self, client, product):
        response = client.post(
            identifiers_url(product.id), json={'id_type': 'MPN', 'value': 'ACME-1'}
        )

        assert response.status_code == 201
        assert response.get_json()['identifier']['value'] == 'ACME-1'


class TestRemoveIdentifier:
    """DELETE /api/products/<id>/identifiers/<identifier_id>"""

    @pytest.fixture
    def identifier(self, service, product):
        return service.add_identifier(product.id, IdentifierType.MPN.value, 'ACME-1')

    def test_removes_the_row(self, client, service, product, identifier):
        response = client.delete(f'{identifiers_url(product.id)}/{identifier.id}')

        assert response.status_code == 204
        remaining = service.get_product(product.id).identifiers
        assert 'ACME-1' not in [i.value for i in remaining]

    def test_removing_it_twice_answers_a_json_404(self, client, product, identifier):
        """FR-018: the second tab's removal succeeded at what it asked for.

        Before #132 this answered a bodyless DELETE with a 302 to /inventory,
        which fetch followed into a false success. The JSON 404 is what makes
        ``response.ok || response.status === 404`` a real branch.
        """
        client.delete(f'{identifiers_url(product.id)}/{identifier.id}')
        response = client.delete(f'{identifiers_url(product.id)}/{identifier.id}')

        assert response.status_code == 404
        assert response.get_json()['success'] is False

    def test_an_identifier_on_another_product_is_not_reachable(
        self, client, service, identifier
    ):
        """The product in the path owns the row, or there is no row to remove"""
        other = service.create_product(description='Something else')

        response = client.delete(f'{identifiers_url(other.id)}/{identifier.id}')

        assert response.status_code == 404

    def test_the_product_survives_losing_its_last_identifier(
        self, client, service, product, identifier
    ):
        """FR-017: identity is the product row, never one of its names"""
        client.delete(f'{identifiers_url(product.id)}/{identifier.id}')

        survivor = service.get_product(product.id)
        assert survivor is not None
        assert survivor.internal_code
        assert [i.value for i in survivor.identifiers if i.id_type != 'INTERNAL'] == []
