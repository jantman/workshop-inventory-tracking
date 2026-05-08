"""Standalone Python client for the Workshop Inventory Tracking REST API.

This module is intentionally self-contained. Its only third-party
dependency is ``requests``, so the file can be copied or vendored into
other projects without pulling in any of the application's runtime
dependencies.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


__all__ = [
    'CreateItemResult',
    'UploadPhotoResult',
    'WorkshopInventoryClient',
]


@dataclass(frozen=True)
class CreateItemResult:
    """Outcome of a ``create_item`` call."""

    success: bool
    created_ja_ids: list[str]
    errors: list[dict[str, Any]]
    http_status: int
    raw: dict[str, Any]

    @property
    def message(self) -> str | None:
        return self.raw.get('message')


@dataclass(frozen=True)
class UploadPhotoResult:
    """Outcome of an ``upload_photo`` call."""

    success: bool
    photo: dict[str, Any] | None
    errors: list[dict[str, Any]]
    http_status: int
    raw: dict[str, Any]

    @property
    def message(self) -> str | None:
        return self.raw.get('message')


class WorkshopInventoryClient:
    """Client for the Workshop Inventory Tracking REST API.

    Network failures (DNS, connection refused, timeouts) raise
    ``requests.RequestException``. HTTP 4xx/5xx responses are returned
    as result objects with ``success=False`` so callers can branch on
    the outcome without catching exceptions.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()

    def create_item(self, item: dict[str, Any]) -> CreateItemResult:
        """Create one or more inventory items.

        ``item`` is a JSON-serializable dict matching the payload
        accepted by ``POST /api/inventory/items``. Use the
        ``quantity_to_create`` field (1-100) to create multiple items
        with sequential JA IDs in a single call.
        """
        response = self.session.post(
            f'{self.base_url}/api/inventory/items',
            json=item,
            timeout=self.timeout,
        )
        body = self._safe_json(response)
        return CreateItemResult(
            success=bool(body.get('success', False)),
            created_ja_ids=list(body.get('created_ja_ids') or []),
            errors=list(body.get('errors') or []),
            http_status=response.status_code,
            raw=body,
        )

    def upload_photo(
        self,
        ja_id: str,
        *,
        file_path: str | Path | None = None,
        file_data: bytes | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> UploadPhotoResult:
        """Upload a photo for the given item.

        Provide either ``file_path`` (the file is read from disk) or
        ``file_data`` together with ``filename``. ``content_type`` is
        auto-detected from the filename when not supplied.
        """
        if file_path is None and file_data is None:
            raise ValueError('Provide either file_path or file_data')
        if file_path is not None and file_data is not None:
            raise ValueError('Provide only one of file_path or file_data')

        if file_path is not None:
            path = Path(file_path)
            file_data = path.read_bytes()
            if filename is None:
                filename = path.name
        elif filename is None:
            raise ValueError('filename is required when passing file_data')

        content_type = (
            content_type
            or mimetypes.guess_type(filename)[0]
            or 'application/octet-stream'
        )

        files = {'file': (filename, file_data, content_type)}

        response = self.session.post(
            f'{self.base_url}/api/items/{ja_id}/photos',
            files=files,
            timeout=self.timeout,
        )
        body = self._safe_json(response)

        success = bool(body.get('success', False))
        errors: list[dict[str, Any]] = []
        if not success:
            err_msg = (
                body.get('error')
                or body.get('message')
                or f'HTTP {response.status_code}'
            )
            errors = [{'index': 0, 'ja_id': ja_id, 'message': err_msg}]

        return UploadPhotoResult(
            success=success,
            photo=body.get('photo') if isinstance(body.get('photo'), dict) else None,
            errors=errors,
            http_status=response.status_code,
            raw=body,
        )

    @staticmethod
    def _safe_json(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            text = (response.text or '')[:200]
            return {
                'success': False,
                'error': f'Non-JSON response (HTTP {response.status_code}): {text}',
                'created_ja_ids': [],
                'errors': [{
                    'index': 0,
                    'ja_id': None,
                    'message': text or f'HTTP {response.status_code}',
                }],
            }
        if not isinstance(data, dict):
            return {
                'success': False,
                'error': 'Non-dict JSON response',
                'created_ja_ids': [],
                'errors': [{'index': 0, 'ja_id': None, 'message': 'Non-dict JSON response'}],
            }
        return data


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Create an inventory item via the Workshop Inventory REST API.'
    )
    parser.add_argument(
        '--url',
        required=True,
        help='Base URL of the application (e.g. http://localhost:5000)',
    )
    parser.add_argument(
        '--input',
        required=True,
        help='Path to a JSON file with the item payload, or "-" for stdin.',
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=30.0,
        help='HTTP timeout in seconds (default: 30).',
    )
    args = parser.parse_args(argv)

    if args.input == '-':
        payload = json.load(sys.stdin)
    else:
        with open(args.input) as fh:
            payload = json.load(fh)

    client = WorkshopInventoryClient(args.url, timeout=args.timeout)
    result = client.create_item(payload)

    print(json.dumps({
        'success': result.success,
        'http_status': result.http_status,
        'created_ja_ids': result.created_ja_ids,
        'errors': result.errors,
    }, indent=2))

    return 0 if result.success else 1


if __name__ == '__main__':
    sys.exit(_main())
