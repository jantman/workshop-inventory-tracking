"""End-to-end tests for the standalone WorkshopInventoryClient.

These tests run against the live test server (no browser) to verify
the client correctly speaks the real HTTP API.
"""

from __future__ import annotations

import io
import os
import tempfile

import pytest
import requests
from PIL import Image

from app.api_client import WorkshopInventoryClient


@pytest.fixture
def sample_image_path():
    """Create a small JPEG on disk and clean it up after the test."""
    image = Image.new('RGB', (100, 100), color='red')
    fh = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    image.save(fh.name, format='JPEG', quality=85)
    fh.close()
    try:
        yield fh.name
    finally:
        try:
            os.unlink(fh.name)
        except OSError:
            pass


@pytest.fixture
def client(live_server):
    return WorkshopInventoryClient(live_server.url, timeout=15.0)


@pytest.mark.e2e
class TestApiClientCreateItem:
    def test_create_single_item(self, client, live_server):
        result = client.create_item({
            'item_type': 'Bar',
            'shape': 'Round',
            'material': 'Steel',
            'location': 'API Shelf',
            'length': 100,
            'width': 25,
            'active': True,
        })

        assert result.success is True, result.errors
        assert result.http_status == 200
        # Server allocated the JA ID. We don't assume a specific value
        # since the live test server's state isn't guaranteed empty.
        assert len(result.created_ja_ids) == 1
        ja_id = result.created_ja_ids[0]
        assert ja_id.startswith('JA') and len(ja_id) == 8

        # Verify the item is reachable through the existing read API.
        verify = requests.get(f'{live_server.url}/api/items/{ja_id}', timeout=10)
        assert verify.status_code == 200
        body = verify.json()
        assert body.get('success') is True
        assert body['item']['ja_id'] == ja_id
        assert body['item']['material'] == 'Steel'

    def test_create_bulk_items(self, client, live_server):
        result = client.create_item({
            'item_type': 'Bar',
            'shape': 'Round',
            'material': 'Steel',
            'location': 'Bulk Bay',
            'length': 50,
            'width': 10,
            'active': True,
            'quantity_to_create': 3,
        })

        assert result.success is True, result.errors
        assert result.http_status == 200
        assert len(result.created_ja_ids) == 3
        for ja_id in result.created_ja_ids:
            verify = requests.get(f'{live_server.url}/api/items/{ja_id}', timeout=10)
            assert verify.status_code == 200, f'{ja_id} not reachable'

    def test_validation_error_returns_structured_failure(self, client):
        result = client.create_item({
            'item_type': 'Bar',
            'shape': 'Round',
            'material': 'Steel',
            # location omitted → 400
            'active': True,
        })

        assert result.success is False
        assert result.http_status == 400
        assert result.created_ja_ids == []
        assert len(result.errors) == 1
        assert 'location' in result.errors[0]['message']

    def test_ja_id_in_request_is_rejected(self, client):
        # The server is the sole allocator; sending ja_id from JSON
        # is treated as an unknown field and yields 400.
        result = client.create_item({
            'ja_id': 'JA000999',
            'item_type': 'Bar',
            'shape': 'Round',
            'material': 'Steel',
            'location': 'API Shelf',
            'active': True,
        })

        assert result.success is False
        assert result.http_status == 400
        assert any('ja_id' in err.get('message', '') for err in result.errors)


@pytest.mark.e2e
class TestApiClientUploadPhoto:
    def test_upload_photo_for_existing_item(self, client, live_server, sample_image_path):
        create_result = client.create_item({
            'item_type': 'Bar',
            'shape': 'Round',
            'material': 'Steel',
            'location': 'Photo Shelf',
            'length': 100,
            'width': 25,
            'active': True,
        })
        assert create_result.success is True, create_result.errors
        ja_id = create_result.created_ja_ids[0]

        upload_result = client.upload_photo(ja_id, file_path=sample_image_path)

        assert upload_result.success is True, upload_result.errors
        assert upload_result.http_status == 200
        assert upload_result.photo is not None
        assert 'id' in upload_result.photo

        # Verify via the read endpoint
        photos_resp = requests.get(f'{live_server.url}/api/items/{ja_id}/photos', timeout=10)
        assert photos_resp.status_code == 200
        photos_body = photos_resp.json()
        assert photos_body.get('success') is True
        assert len(photos_body.get('photos', [])) >= 1

    def test_upload_photo_from_bytes(self, client, live_server):
        create_result = client.create_item({
            'item_type': 'Bar',
            'shape': 'Round',
            'material': 'Steel',
            'location': 'Bytes Shelf',
            'length': 50,
            'width': 12,
            'active': True,
        })
        assert create_result.success is True, create_result.errors
        ja_id = create_result.created_ja_ids[0]

        buf = io.BytesIO()
        Image.new('RGB', (60, 60), color='green').save(buf, format='JPEG')

        upload_result = client.upload_photo(
            ja_id,
            file_data=buf.getvalue(),
            filename='from-bytes.jpg',
        )

        assert upload_result.success is True, upload_result.errors
        assert upload_result.photo is not None
