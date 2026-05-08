"""Unit tests for the standalone API client at app/api_client.py.

HTTP is mocked at the session level so tests run without a server and
without depending on any of the application's runtime modules.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

import pytest
import requests

from app.api_client import (
    CreateItemResult,
    UploadPhotoResult,
    WorkshopInventoryClient,
)


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
