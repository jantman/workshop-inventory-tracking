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
from urllib.parse import quote

import requests


__all__ = [
    'CreateItemResult',
    'FieldSuggestionsResult',
    'SUGGESTABLE_FIELDS',
    'UploadPhotoResult',
    'WorkshopInventoryClient',
]


# Whitelist matching the server's
# `InventoryService.FIELD_SUGGESTION_COLUMNS`. Used purely as
# documentation for callers; the server is the source of truth and
# rejects unknown values with HTTP 400.
SUGGESTABLE_FIELDS = (
    'thread_size',
    'purchase_location',
    'vendor',
    'location',
    'sub_location',
)


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
class FieldSuggestionsResult:
    """Outcome of a ``get_field_suggestions`` call."""

    success: bool
    field: str
    suggestions: list[str]
    errors: list[dict[str, Any]]
    http_status: int
    raw: dict[str, Any]


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

        ``item`` is a JSON-serializable dict POSTed verbatim to
        ``/api/inventory/items``. Unknown top-level keys are rejected
        by the server with a 400.

        **JA IDs are allocated by the server.** Do not pass a ``ja_id``
        field; doing so is treated as an unknown field and returns 400.
        Read the allocated ID(s) back from
        ``result.created_ja_ids``. For bulk creation, IDs are assigned
        sequentially starting at the next free ID.

        **Required fields**

        - ``item_type`` (str): one of ``"Bar"``, ``"Plate"``,
          ``"Sheet"``, ``"Tube"``, ``"Threaded Rod"``, ``"Angle"``,
          ``"Channel"``.
        - ``shape`` (str): one of ``"Rectangular"``, ``"Round"``,
          ``"Square"``, ``"Hex"``.
        - ``material`` (str): material name. Validated against the
          configured materials taxonomy when one is present (e.g.
          ``"Steel"``, ``"4140"``, ``"6061-T6"``, ``"316"``).
        - ``location`` (str): physical location label, free-form.

        **Optional dimension fields** (str or number; inches except
        ``weight`` in pounds; strings may be decimal ``"12.5"``, simple
        fraction ``"3/4"``, or mixed number ``"1 1/2"``):

        - ``length``, ``width``, ``thickness``, ``wall_thickness``,
          ``weight``.

        **Optional threading fields**

        - ``thread_series`` (str): one of ``"UNC"``, ``"UNF"``,
          ``"UNEF"``, ``"UNS"``, ``"Metric"``, ``"BSW"``, ``"BSF"``,
          ``"NPT"``, ``"Acme"``, ``"Trapezoidal"``, ``"Square"``,
          ``"Buttress"``, ``"Custom"``, ``"Other"``. Case-insensitive.
          The literal ``"None"`` is treated as not provided.
        - ``thread_handedness`` (str): ``"RH"`` (default) or ``"LH"``.
        - ``thread_size`` (str): designation, e.g. ``"1/4-20"``,
          ``"M10x1.5"``.

        **Optional metadata fields** (all str unless noted):

        - ``sub_location``: sub-location within ``location``.
        - ``purchase_date``: ``YYYY-MM-DD``, ``MM/DD/YYYY``, or
          ``MM.DD.YYYY``. Unparseable values are silently stored as
          null.
        - ``purchase_price`` (str or number).
        - ``purchase_location``, ``vendor``, ``vendor_part_number``,
          ``notes``.

        **Optional flags** (boolean only — strings rejected):

        - ``active`` (bool): defaults to ``False`` if omitted, matching
          the HTML form's unchecked-checkbox semantics. Pass ``True``
          to create an active item.
        - ``precision`` (bool): defaults to ``False``.

        **Bulk creation**

        - ``quantity_to_create`` (int, 1-100, default 1): when greater
          than 1, the server allocates that many items with sequential
          JA IDs starting at the next free ID. The other fields are
          applied to every created item.

        **Returned ``CreateItemResult``**

        - ``success`` (bool): ``True`` only when every requested item
          was created. Any HTTP 4xx/5xx forces ``False`` regardless of
          body content. 207 Multi-Status (partial bulk success) reports
          ``False`` here, with both ``created_ja_ids`` and ``errors``
          populated.
        - ``created_ja_ids`` (list[str]): JA IDs that persisted.
        - ``errors`` (list[dict]): each entry is
          ``{"index": <1-based attempt position; 0 for single>,
          "ja_id": <attempted JA ID, may be None>, "message": "..."}``.
        - ``http_status`` (int): the raw HTTP status code (200 / 207 /
          400 / 500).
        - ``raw`` (dict): the parsed JSON response body, for callers
          that need fields beyond the documented surface.

        **Errors that bubble up as exceptions**

        Network failures (connection refused, DNS, TLS, timeout, etc.)
        propagate as ``requests.RequestException`` subclasses. HTTP
        errors do *not* raise — they come back as a result with
        ``success=False`` so callers can branch without try/except.
        """
        response = self.session.post(
            f'{self.base_url}/api/inventory/items',
            json=item,
            timeout=self.timeout,
        )
        body = self._safe_json(response)
        # An HTTP error always means failure regardless of what the body
        # claims; only successful (1xx/2xx/3xx) responses defer to the
        # body's success field. 207 partial-success carries success=false
        # in the body, so this still reports it correctly.
        if response.status_code >= 400:
            success = False
        else:
            success = bool(body.get('success', False))
        errors = list(body.get('errors') or [])
        if not success and not errors:
            err_msg = body.get('error') or body.get('message') or f'HTTP {response.status_code}'
            errors = [{
                'index': 0,
                'ja_id': item.get('ja_id') if isinstance(item, dict) else None,
                'message': err_msg,
            }]
        return CreateItemResult(
            success=success,
            created_ja_ids=list(body.get('created_ja_ids') or []),
            errors=errors,
            http_status=response.status_code,
            raw=body,
        )

    def get_field_suggestions(
        self,
        field: str,
        *,
        query: str | None = None,
        limit: int = 10,
        location: str | None = None,
    ) -> FieldSuggestionsResult:
        """Fetch autocomplete suggestions for a free-form item field.

        Calls ``GET /api/inventory/field-suggestions/<field>`` and
        returns distinct values currently recorded in the database for
        that field, ordered exact match → starts-with → contains, each
        tier alphabetized.

        **Arguments**

        - ``field`` (str): one of ``"thread_size"``,
          ``"purchase_location"``, ``"vendor"``, ``"location"``,
          ``"sub_location"``. The server returns 400 for any other
          value; the client surfaces that as ``success=False`` rather
          than raising. ``SUGGESTABLE_FIELDS`` is exported for
          reference.
        - ``query`` (str, optional): case-insensitive substring filter.
          When omitted, the server returns distinct values in
          case-insensitive alphabetical order up to ``limit``.
        - ``limit`` (int, default 10): maximum number of suggestions.
          Server clamps to ``[1, 50]``. Non-int values are coerced to
          the default of 10 rather than raising — the client only
          raises for network failures.
        - ``location`` (str, optional): only meaningful when
          ``field == "sub_location"``. Restricts results to
          sub-locations recorded under the given location
          (case-insensitive).

        **Returned ``FieldSuggestionsResult``**

        - ``success`` (bool): ``True`` only on 2xx with
          ``"success": true`` in the body.
        - ``field`` (str): the field that was queried; echoed back from
          the server on success, otherwise the value the caller passed.
        - ``suggestions`` (list[str]): the returned values. Empty list
          on failure.
        - ``errors`` (list[dict]): single-entry list on failure of the
          shape ``{"index": 0, "ja_id": None, "message": "..."}``.
        - ``http_status`` (int): the raw HTTP status code.
        - ``raw`` (dict): the parsed JSON response body.

        **Network errors**

        Network failures (connection refused, DNS, TLS, timeout)
        propagate as ``requests.RequestException`` subclasses. HTTP
        errors land as ``success=False`` rather than raising.
        """
        # Tolerate non-int limit by falling back to the default.
        # The contract is: only network failures raise; everything
        # else surfaces via success=False or server-side clamping.
        try:
            limit_value = int(limit)
        except (TypeError, ValueError):
            limit_value = 10
        params: dict[str, Any] = {'limit': limit_value}
        if query is not None and query != '':
            params['q'] = query
        if location is not None and location != '':
            params['location'] = location

        # URL-encode the field path segment defensively. Production
        # callers will pass plain identifiers from SUGGESTABLE_FIELDS,
        # but a value containing spaces or reserved characters must
        # not produce a malformed request URL.
        encoded_field = quote(str(field), safe='')

        response = self.session.get(
            f'{self.base_url}/api/inventory/field-suggestions/{encoded_field}',
            params=params,
            timeout=self.timeout,
        )
        body = self._safe_json(response)

        if response.status_code >= 400:
            success = False
        else:
            success = bool(body.get('success', False))

        suggestions: list[str] = []
        if success:
            raw_suggestions = body.get('suggestions') or []
            if isinstance(raw_suggestions, list):
                suggestions = [str(s) for s in raw_suggestions]

        errors: list[dict[str, Any]] = []
        if not success:
            err_msg = (
                body.get('error')
                or body.get('message')
                or f'HTTP {response.status_code}'
            )
            errors = [{'index': 0, 'ja_id': None, 'message': err_msg}]

        return FieldSuggestionsResult(
            success=success,
            field=str(body.get('field') or field),
            suggestions=suggestions,
            errors=errors,
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

        POSTs a ``multipart/form-data`` request to
        ``/api/items/<ja_id>/photos`` with the file in the ``file``
        field.

        **Arguments**

        - ``ja_id`` (str): canonical-form JA ID of the item that owns
          the photo (e.g. ``"JA000123"``). The item must already exist;
          the server returns 400 / 500 otherwise.
        - ``file_path`` (str or Path, optional): path to a file to
          upload. Mutually exclusive with ``file_data``.
        - ``file_data`` (bytes, optional): the raw file bytes to
          upload. When supplied, ``filename`` is required. Mutually
          exclusive with ``file_path``.
        - ``filename`` (str, optional): the name to send to the server.
          Required when ``file_data`` is supplied. Defaults to the
          basename of ``file_path`` otherwise.
        - ``content_type`` (str, optional): the MIME type to send. When
          omitted it is guessed from ``filename`` via
          ``mimetypes.guess_type`` and falls back to
          ``application/octet-stream``. The server accepts standard
          image content types (e.g. ``image/jpeg``, ``image/png``,
          ``image/webp``) and ``application/pdf``.

        **Returned ``UploadPhotoResult``**

        - ``success`` (bool): ``True`` only on a 2xx response with
          ``"success": true`` in the body. Any HTTP 4xx/5xx forces
          ``False`` regardless of body content.
        - ``photo`` (dict | None): the server's representation of the
          stored photo on success — typically includes ``id``,
          ``filename``, ``content_type``, ``file_size``, ``thumbnail``,
          and timestamps. ``None`` on failure.
        - ``errors`` (list[dict]): on failure, a single entry of the
          form ``{"index": 0, "ja_id": <ja_id>, "message": "..."}``.
          Empty on success.
        - ``http_status`` (int): the raw HTTP status code.
        - ``raw`` (dict): the parsed JSON response body.

        **Argument-validation errors raised by the client itself**

        - ``ValueError`` if neither ``file_path`` nor ``file_data`` is
          given, if both are given, or if ``file_data`` is given
          without ``filename``.

        **Network errors**

        Network failures propagate as ``requests.RequestException``
        subclasses (same as ``create_item``).
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

        # HTTP error → never report success, regardless of body content.
        if response.status_code >= 400:
            success = False
        else:
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
