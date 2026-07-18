"""Unit tests for the standalone API client at app/api_client.py.

HTTP is mocked at the session level so tests run without a server and
without depending on any of the application's runtime modules.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import requests

from app.api_client import (
    CreateItemResult,
    FieldSuggestionsResult,
    SUGGESTABLE_FIELDS,
    TaxonomyResult,
    UploadPhotoResult,
    WorkshopInventoryClient,
)


def _sample_taxonomy() -> list[dict]:
    """A minimal but representative nested taxonomy tree."""
    return [
        {
            'id': 1,
            'name': 'Steel',
            'level': 1,
            'active': True,
            'notes': '',
            'sort_order': 0,
            'children': [
                {
                    'id': 5,
                    'name': 'Alloy Steel',
                    'level': 2,
                    'parent': 'Steel',
                    'active': True,
                    'notes': '',
                    'sort_order': 0,
                    'children': [
                        {
                            'id': 9,
                            'name': '4140',
                            'level': 3,
                            'parent': 'Alloy Steel',
                            'active': True,
                            'aliases': ['41400'],
                            'notes': '',
                            'sort_order': 0,
                        }
                    ],
                }
            ],
        }
    ]


def _mock_response(status_code: int, json_body: dict | list | None,
                   text: str | None = None) -> MagicMock:
    """Build a MagicMock that quacks like a requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    if json_body is not None:
        resp.json.return_value = json_body
        resp.text = json.dumps(json_body)
    else:
        resp.json.side_effect = ValueError('not json')
        resp.text = text or ''
    return resp


@pytest.fixture
def session():
    """A MagicMock session whose .post() can be programmed per test."""
    return MagicMock(spec=requests.Session)


@pytest.fixture
def client(session):
    return WorkshopInventoryClient('http://example.test', session=session)


class TestCreateItem:
    def test_single_success(self, client, session):
        session.post.return_value = _mock_response(200, {
            'success': True,
            'created_ja_ids': ['JA000001'],
            'errors': [],
            'message': 'Item added successfully',
        })

        result = client.create_item({'ja_id': 'JA000001', 'item_type': 'Bar'})

        assert isinstance(result, CreateItemResult)
        assert result.success is True
        assert result.created_ja_ids == ['JA000001']
        assert result.errors == []
        assert result.http_status == 200
        assert result.message == 'Item added successfully'

        session.post.assert_called_once()
        call_args = session.post.call_args
        assert call_args.args[0] == 'http://example.test/api/inventory/items'
        assert call_args.kwargs['json'] == {'ja_id': 'JA000001', 'item_type': 'Bar'}
        assert call_args.kwargs['timeout'] == 30.0

    def test_bulk_success(self, client, session):
        session.post.return_value = _mock_response(200, {
            'success': True,
            'created_ja_ids': ['JA000001', 'JA000002', 'JA000003'],
            'errors': [],
        })

        result = client.create_item({'item_type': 'Bar', 'quantity_to_create': 3})

        assert result.success is True
        assert result.created_ja_ids == ['JA000001', 'JA000002', 'JA000003']

    def test_validation_error_400(self, client, session):
        session.post.return_value = _mock_response(400, {
            'success': False,
            'created_ja_ids': [],
            'errors': [{'index': 0, 'ja_id': None, 'message': 'Missing required fields: location'}],
            'error': 'Missing required fields: location',
        })

        result = client.create_item({})

        assert result.success is False
        assert result.http_status == 400
        assert result.created_ja_ids == []
        assert len(result.errors) == 1
        assert 'location' in result.errors[0]['message']

    def test_partial_success_207(self, client, session):
        session.post.return_value = _mock_response(207, {
            'success': False,
            'created_ja_ids': ['JA000001', 'JA000003'],
            'errors': [{'index': 1, 'ja_id': 'JA000002', 'message': 'Active item already exists'}],
            'error': 'Created 2 of 3 items. Some items failed.',
        })

        result = client.create_item({'item_type': 'Bar', 'quantity_to_create': 3})

        assert result.success is False
        assert result.http_status == 207
        assert len(result.created_ja_ids) == 2
        assert len(result.errors) == 1

    def test_connection_error_propagates(self, client, session):
        session.post.side_effect = requests.ConnectionError('connection refused')

        with pytest.raises(requests.ConnectionError):
            client.create_item({'ja_id': 'JA000001'})

    def test_timeout_propagates(self, client, session):
        session.post.side_effect = requests.Timeout('timed out')

        with pytest.raises(requests.Timeout):
            client.create_item({'ja_id': 'JA000001'})

    def test_non_json_response_returns_failure(self, client, session):
        session.post.return_value = _mock_response(502, None, text='Bad Gateway')

        result = client.create_item({'ja_id': 'JA000001'})

        assert result.success is False
        assert result.http_status == 502
        assert len(result.errors) == 1
        assert 'Bad Gateway' in result.errors[0]['message']

    def test_non_dict_json_response(self, client, session):
        session.post.return_value = _mock_response(200, ['unexpected', 'array'])

        result = client.create_item({'ja_id': 'JA000001'})

        assert result.success is False
        assert result.http_status == 200
        assert result.errors[0]['message'] == 'Non-dict JSON response'

    def test_base_url_trailing_slash_normalized(self, session):
        client = WorkshopInventoryClient('http://example.test/', session=session)
        session.post.return_value = _mock_response(200, {
            'success': True, 'created_ja_ids': ['JA000001'], 'errors': []
        })

        client.create_item({'ja_id': 'JA000001'})

        assert session.post.call_args.args[0] == 'http://example.test/api/inventory/items'

    def test_http_error_always_reports_failure_even_if_body_claims_success(self, client, session):
        # If the server ever lies about success on an error status, the
        # client must still report failure based on the HTTP code.
        session.post.return_value = _mock_response(500, {
            'success': True,
            'created_ja_ids': [],
            'errors': [],
        })

        result = client.create_item({'ja_id': 'JA000001'})

        assert result.success is False
        assert result.http_status == 500
        assert len(result.errors) >= 1

    def test_custom_timeout_propagates(self, session):
        client = WorkshopInventoryClient('http://example.test', timeout=5.0, session=session)
        session.post.return_value = _mock_response(200, {
            'success': True, 'created_ja_ids': ['JA000001'], 'errors': []
        })

        client.create_item({'ja_id': 'JA000001'})

        assert session.post.call_args.kwargs['timeout'] == 5.0


class TestUploadPhoto:
    def test_success_from_file_path(self, client, session, tmp_path):
        photo_path = tmp_path / 'sample.jpg'
        photo_path.write_bytes(b'\xff\xd8\xff\xe0fake-jpeg-data')

        session.post.return_value = _mock_response(200, {
            'success': True,
            'photo': {'id': 42, 'filename': 'sample.jpg'},
            'message': 'Photo sample.jpg uploaded successfully',
        })

        result = client.upload_photo('JA000001', file_path=str(photo_path))

        assert isinstance(result, UploadPhotoResult)
        assert result.success is True
        assert result.photo == {'id': 42, 'filename': 'sample.jpg'}
        assert result.errors == []
        assert result.http_status == 200

        call_args = session.post.call_args
        assert call_args.args[0] == 'http://example.test/api/items/JA000001/photos'
        files = call_args.kwargs['files']
        assert 'file' in files
        sent_filename, sent_data, sent_content_type = files['file']
        assert sent_filename == 'sample.jpg'
        assert sent_data == b'\xff\xd8\xff\xe0fake-jpeg-data'
        assert sent_content_type == 'image/jpeg'

    def test_success_from_file_data(self, client, session):
        session.post.return_value = _mock_response(200, {
            'success': True,
            'photo': {'id': 7},
        })

        result = client.upload_photo(
            'JA000001',
            file_data=b'PNG-bytes',
            filename='manual.png',
        )

        assert result.success is True
        files = session.post.call_args.kwargs['files']
        sent_filename, sent_data, sent_content_type = files['file']
        assert sent_filename == 'manual.png'
        assert sent_data == b'PNG-bytes'
        assert sent_content_type == 'image/png'

    def test_explicit_content_type_overrides_guess(self, client, session):
        session.post.return_value = _mock_response(200, {'success': True, 'photo': {}})

        client.upload_photo(
            'JA000001',
            file_data=b'data',
            filename='thing.jpg',
            content_type='application/x-custom',
        )

        files = session.post.call_args.kwargs['files']
        assert files['file'][2] == 'application/x-custom'

    def test_unknown_extension_defaults_to_octet_stream(self, client, session):
        session.post.return_value = _mock_response(200, {'success': True, 'photo': {}})

        client.upload_photo('JA000001', file_data=b'x', filename='no-ext')

        files = session.post.call_args.kwargs['files']
        assert files['file'][2] == 'application/octet-stream'

    def test_neither_path_nor_data_raises(self, client):
        with pytest.raises(ValueError, match='file_path or file_data'):
            client.upload_photo('JA000001')

    def test_both_path_and_data_raises(self, client, tmp_path):
        photo = tmp_path / 'p.jpg'
        photo.write_bytes(b'x')
        with pytest.raises(ValueError, match='only one of'):
            client.upload_photo('JA000001', file_path=str(photo), file_data=b'y')

    def test_file_data_without_filename_raises(self, client):
        with pytest.raises(ValueError, match='filename is required'):
            client.upload_photo('JA000001', file_data=b'data')

    def test_failure_response_normalized(self, client, session):
        session.post.return_value = _mock_response(400, {
            'success': False,
            'error': 'No file provided',
        })

        result = client.upload_photo('JA000001', file_data=b'x', filename='x.jpg')

        assert result.success is False
        assert result.http_status == 400
        assert len(result.errors) == 1
        assert result.errors[0]['ja_id'] == 'JA000001'
        assert 'No file provided' in result.errors[0]['message']

    def test_http_error_always_reports_failure_even_if_body_claims_success(self, client, session):
        session.post.return_value = _mock_response(500, {
            'success': True,
            'photo': {'id': 1},
        })

        result = client.upload_photo('JA000001', file_data=b'x', filename='x.jpg')

        assert result.success is False
        assert result.http_status == 500
        assert len(result.errors) >= 1

    def test_server_error_500(self, client, session):
        session.post.return_value = _mock_response(500, {
            'success': False,
            'error': 'Photo upload failed: storage exhausted',
        })

        result = client.upload_photo('JA000001', file_data=b'x', filename='x.jpg')

        assert result.success is False
        assert result.http_status == 500
        assert 'storage exhausted' in result.errors[0]['message']


class TestSession:
    def test_supplies_default_session_when_none(self):
        c = WorkshopInventoryClient('http://example.test')
        assert isinstance(c.session, requests.Session)

    def test_uses_provided_session(self):
        s = requests.Session()
        c = WorkshopInventoryClient('http://example.test', session=s)
        assert c.session is s


class TestGetFieldSuggestions:
    def test_success_no_query(self, client, session):
        session.get.return_value = _mock_response(200, {
            'success': True,
            'field': 'vendor',
            'suggestions': ['Acme', 'McMaster-Carr'],
        })

        result = client.get_field_suggestions('vendor')

        assert isinstance(result, FieldSuggestionsResult)
        assert result.success is True
        assert result.field == 'vendor'
        assert result.suggestions == ['Acme', 'McMaster-Carr']
        assert result.errors == []
        assert result.http_status == 200

        call_args = session.get.call_args
        assert call_args.args[0] == (
            'http://example.test/api/inventory/field-suggestions/vendor'
        )
        # Limit always sent; no q/location when not provided.
        assert call_args.kwargs['params'] == {'limit': 10}

    def test_success_with_query_and_limit(self, client, session):
        session.get.return_value = _mock_response(200, {
            'success': True,
            'field': 'vendor',
            'suggestions': ['McMaster-Carr'],
        })

        result = client.get_field_suggestions('vendor', query='mc', limit=5)

        assert result.success is True
        assert result.suggestions == ['McMaster-Carr']
        params = session.get.call_args.kwargs['params']
        assert params == {'q': 'mc', 'limit': 5}

    def test_sub_location_with_location_filter(self, client, session):
        session.get.return_value = _mock_response(200, {
            'success': True,
            'field': 'sub_location',
            'suggestions': ['Top', 'Bottom'],
        })

        result = client.get_field_suggestions(
            'sub_location', location='Shelf A'
        )

        assert result.success is True
        params = session.get.call_args.kwargs['params']
        assert params['location'] == 'Shelf A'

    def test_unknown_field_returns_failure(self, client, session):
        session.get.return_value = _mock_response(400, {
            'success': False,
            'error': "Unsupported field for suggestions: 'material'",
        })

        result = client.get_field_suggestions('material')

        assert result.success is False
        assert result.http_status == 400
        assert result.suggestions == []
        assert len(result.errors) == 1
        assert 'material' in result.errors[0]['message']

    def test_http_error_always_reports_failure(self, client, session):
        session.get.return_value = _mock_response(500, {
            'success': True,
            'field': 'vendor',
            'suggestions': ['ignored'],
        })

        result = client.get_field_suggestions('vendor')

        assert result.success is False
        assert result.http_status == 500
        assert result.suggestions == []

    def test_non_json_response_returns_failure(self, client, session):
        session.get.return_value = _mock_response(502, None, text='Bad Gateway')

        result = client.get_field_suggestions('vendor')

        assert result.success is False
        assert result.http_status == 502
        assert result.suggestions == []

    def test_connection_error_propagates(self, client, session):
        session.get.side_effect = requests.ConnectionError('refused')
        with pytest.raises(requests.ConnectionError):
            client.get_field_suggestions('vendor')

    def test_empty_query_not_sent(self, client, session):
        session.get.return_value = _mock_response(200, {
            'success': True, 'field': 'vendor', 'suggestions': []
        })
        client.get_field_suggestions('vendor', query='')
        params = session.get.call_args.kwargs['params']
        assert 'q' not in params

    def test_non_int_limit_falls_back_to_default(self, client, session):
        # Client contract: only network failures raise. A non-int
        # limit must not raise locally — it falls back to the default
        # so the server's HTTP error path is what callers see.
        session.get.return_value = _mock_response(200, {
            'success': True, 'field': 'vendor', 'suggestions': []
        })
        client.get_field_suggestions('vendor', limit='oops')
        assert session.get.call_args.kwargs['params']['limit'] == 10

        session.get.reset_mock()
        session.get.return_value = _mock_response(200, {
            'success': True, 'field': 'vendor', 'suggestions': []
        })
        client.get_field_suggestions('vendor', limit=None)
        assert session.get.call_args.kwargs['params']['limit'] == 10

    def test_suggestable_fields_constant_exposed(self):
        assert 'thread_size' in SUGGESTABLE_FIELDS
        assert 'sub_location' in SUGGESTABLE_FIELDS
        assert 'vendor' in SUGGESTABLE_FIELDS
        assert 'location' in SUGGESTABLE_FIELDS
        assert 'purchase_location' in SUGGESTABLE_FIELDS
        assert 'material' not in SUGGESTABLE_FIELDS

    def test_field_path_segment_is_url_encoded_in_endpoint(self, client, session):
        # Server only ever sees whitelisted simple identifiers in
        # practice, but the client must still construct the URL safely
        # if a caller passes garbage. Spaces become %20, special chars
        # are percent-encoded.
        session.get.return_value = _mock_response(400, {
            'success': False, 'error': 'Unsupported field'
        })
        client.get_field_suggestions('not a field')
        url = session.get.call_args.args[0]
        assert (
            url
            == 'http://example.test/api/inventory/field-suggestions/not%20a%20field'
        )

        session.get.reset_mock()
        session.get.return_value = _mock_response(400, {
            'success': False, 'error': 'Unsupported field'
        })
        client.get_field_suggestions('a/b?c')
        url = session.get.call_args.args[0]
        # Slash, query-marker, and other reserved chars must be encoded.
        assert (
            url
            == 'http://example.test/api/inventory/field-suggestions/a%2Fb%3Fc'
        )


class TestGetTaxonomy:
    def test_success(self, client, session):
        session.get.return_value = _mock_response(200, {
            'success': True,
            'taxonomy': _sample_taxonomy(),
        })

        result = client.get_taxonomy()

        assert isinstance(result, TaxonomyResult)
        assert result.success is True
        assert result.http_status == 200
        assert result.errors == []
        assert len(result.taxonomy) == 1
        category = result.taxonomy[0]
        assert category['name'] == 'Steel'
        assert category['level'] == 1
        family = category['children'][0]
        assert family['name'] == 'Alloy Steel'
        assert family['parent'] == 'Steel'
        material = family['children'][0]
        assert material['name'] == '4140'
        assert material['aliases'] == ['41400']

        call_args = session.get.call_args
        assert call_args.args[0] == 'http://example.test/api/taxonomy'
        # include_inactive omitted by default.
        assert call_args.kwargs['params'] == {}

    def test_include_inactive_param_sent(self, client, session):
        session.get.return_value = _mock_response(200, {
            'success': True, 'taxonomy': [],
        })

        client.get_taxonomy(include_inactive=True)

        params = session.get.call_args.kwargs['params']
        assert params == {'include_inactive': 'true'}

    def test_empty_taxonomy(self, client, session):
        session.get.return_value = _mock_response(200, {
            'success': True, 'taxonomy': [],
        })

        result = client.get_taxonomy()

        assert result.success is True
        assert result.taxonomy == []
        assert result.errors == []

    def test_http_error_always_reports_failure(self, client, session):
        session.get.return_value = _mock_response(500, {
            'success': True,
            'taxonomy': _sample_taxonomy(),
        })

        result = client.get_taxonomy()

        assert result.success is False
        assert result.http_status == 500
        assert result.taxonomy == []
        assert len(result.errors) == 1

    def test_server_error_body_normalized(self, client, session):
        session.get.return_value = _mock_response(500, {
            'success': False,
            'error': 'Failed to get materials taxonomy',
        })

        result = client.get_taxonomy()

        assert result.success is False
        assert result.http_status == 500
        assert result.taxonomy == []
        assert result.errors[0]['message'] == 'Failed to get materials taxonomy'

    def test_non_json_response_returns_failure(self, client, session):
        session.get.return_value = _mock_response(502, None, text='Bad Gateway')

        result = client.get_taxonomy()

        assert result.success is False
        assert result.http_status == 502
        assert result.taxonomy == []

    def test_non_list_taxonomy_coerced_to_empty(self, client, session):
        session.get.return_value = _mock_response(200, {
            'success': True, 'taxonomy': 'not-a-list',
        })

        result = client.get_taxonomy()

        assert result.success is True
        assert result.taxonomy == []

    def test_connection_error_propagates(self, client, session):
        session.get.side_effect = requests.ConnectionError('refused')
        with pytest.raises(requests.ConnectionError):
            client.get_taxonomy()
