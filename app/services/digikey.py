"""
Read orders and part detail from DigiKey.

The only place in ``app/`` that talks to DigiKey, and it talks to nothing else:
``requests``, the standard library, ``app.models`` and ``app.exceptions``. No
Flask, no ORM, no config module. It does not know a database exists.

**Everything is parsed with ``json.loads(body, parse_float=Decimal)`` and never
with ``response.json()``.** JSON's only number type is an IEEE double, so
``"UnitPrice": 6.9`` decodes to a float under the default parser and Constitution
III has no exemption for a value in transit. This is the single easiest thing in
the feature to get wrong, and it would be invisible until a reconciliation months
later, so it is worth stating twice: **no ``.json()`` in this module.**

**Two legs, not three.** ``client_credentials`` gets a token in one round trip
with no browser, no HTTPS callback and nothing on disk. The registered OAuth
callback exists because DigiKey's portal demands one when you create an app; it
is never used.

**The account has to be named separately.** A 2-legged token identifies the
*application*, not the customer, so without ``X-DIGIKEY-Account-ID`` every order
endpoint answers ``400 Account ID must not be 0``. That is configuration missing,
not authorization refused, and it is mapped to ``ConfigurationError`` so the
operator is sent to their settings rather than to a login. Verified against the
live API on 2026-08-22; see ``specs/024-digikey-order-capture/verification.md``.

No retries, no cache, no rate-limit scheduler, no connection pooling beyond what
``requests`` does by default. The published allowance is 120 requests a minute
and 1,000 a day against a workshop that orders once a fortnight. Principle I
wants a measured problem before machinery.
"""

import json
import logging
import time
from decimal import Decimal
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from app.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ItemNotFoundError,
    RateLimitError,
    TemporaryError,
)
from app.models import DigiKeyOrder, DigiKeyOrderSummary, DigiKeyPart

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://api.digikey.com'

# DigiKey's 2-legged access token lives 10 minutes. Renewing this far ahead of
# its stated expiry keeps a request from starting with a token that dies in
# flight; the cost of being early is one extra token call every 10 minutes.
_TOKEN_RENEWAL_MARGIN_SECONDS = 30

# The 400 DigiKey returns when nothing has said which account the request is for.
_MISSING_ACCOUNT_MARKER = 'account id must not be 0'

# How far back the order listing looks by default. A backfill is a one-off catch-up
# over a workshop's whole buying history, so this is years rather than weeks --
# and it has to be sent, because **omitting the range is not "unfiltered"**: the
# endpoint's own default window is narrow enough to return one order on an
# account holding six (verification.md).
_ORDER_HISTORY_DAYS = 365 * 5


class DigiKeyClient:
    """Reads DigiKey's Order Status and Product Information APIs.

    Built once from configuration and stashed on the app, in the same shape as
    the storage backend, so a test injects a fake and no application code learns
    it is being tested.

    Raises rather than returning a status object: ``StorageResult`` is the
    storage layer's convention and this is not the storage layer.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        account_id: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
    ) -> None:
        """Hold the credentials and the account this client reads for.

        Args:
            client_id: The registered application's id.
            client_secret: Its secret. Never logged.
            account_id: The DigiKey customer account number, sent as
                ``X-DIGIKEY-Account-ID``. Not a credential, but required.
            base_url: Points at the sandbox in development and at a loopback
                fake in the E2E suite.
            timeout: Per-request, in seconds. Matches ``store_listing_images``.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_id = account_id
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip('/')
        self.timeout = timeout

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # -- Public surface ----------------------------------------------------

    def get_order(self, sales_order_number: str) -> DigiKeyOrder:
        """Read one sales order back, with its line items.

        Args:
            sales_order_number: As printed on a confirmation, or as ECIA ``1K``
                off a bag label.

        Returns:
            The order. Its ``lines`` carry the two part numbers, a description,
            a quantity and a price -- and no manufacturer, because a v4 line has
            none. Enrichment is the caller's business.

        Raises:
            ConfigurationError: Not configured, or the account id is missing.
            AuthenticationError: Credentials refused.
            ItemNotFoundError: No such order on this account -- including an
                order placed minutes ago that DigiKey cannot see yet.
            RateLimitError: Throttled.
            TemporaryError: Unreachable, erroring, or answering with nonsense.
        """
        cleaned = (sales_order_number or '').strip()
        if not cleaned:
            raise ItemNotFoundError(
                "No sales order number given", item_id=''
            )

        payload = self._get(
            f'/orderstatus/v4/salesorder/{quote(cleaned, safe="")}',
            subject=f'sales order {cleaned}',
        )
        order = DigiKeyOrder.from_payload(payload)
        if order is None:
            # A 200 that names no order. Reported as not found rather than as an
            # empty order, which would invite the operator to capture nothing.
            raise ItemNotFoundError(
                f"DigiKey returned no order for sales order {cleaned}",
                item_id=cleaned,
            )
        return order

    def list_orders(self, days: int = _ORDER_HISTORY_DAYS) -> List[DigiKeyOrderSummary]:
        """The account's recent sales orders, most recent first.

        Feature 031. Backfilling DigiKey otherwise means reading sales order
        numbers off DigiKey's website and typing them back into a screen that is
        already talking to DigiKey.

        Args:
            days: How far back to look. Sent as an explicit range because the
                endpoint's default window is narrow -- see
                ``_ORDER_HISTORY_DAYS``.

        Returns:
            One entry per **sales order**, flattened out of the nested
            ``Orders[].SalesOrders[]`` the endpoint returns, because a sales
            order is the unit :meth:`get_order` and a bag label both name. Empty
            when the account has none in the window; that is an answer, not a
            failure.

        Raises:
            The same set as :meth:`get_order`. In particular
            ConfigurationError when nothing has said which account this is.

        No paging. The published shape supports it, but a workshop that orders
        once a fortnight does not fill a page, and Principle I wants a measured
        problem before machinery.
        """
        today = date.today()
        payload = self._get(
            '/orderstatus/v4/orders'
            f'?startDate={today - timedelta(days=days)}&endDate={today}',
            subject='your DigiKey orders',
        )

        if not isinstance(payload, dict):
            raise TemporaryError(
                "DigiKey's order listing was not in the expected shape"
            )

        summaries = []
        for order in payload.get('Orders') or []:
            if not isinstance(order, dict):
                continue
            for sales_order in order.get('SalesOrders') or []:
                summary = DigiKeyOrderSummary.from_payload(sales_order)
                # None is one unreadable row, not a lost listing.
                if summary is not None:
                    summaries.append(summary)

        # Most recent first, which is the end a backfill starts from. Undated
        # entries sort last rather than crashing the comparison.
        summaries.sort(
            key=lambda s: (s.order_date is not None, s.order_date),
            reverse=True,
        )
        return summaries

    def get_part(self, part_number: str) -> DigiKeyPart:
        """Read DigiKey's detail for one part.

        Accepts a DigiKey part number or a manufacturer part number; DigiKey
        resolves either.

        Raises:
            ItemNotFoundError: DigiKey does not recognize the part number.
            (and the same set as :meth:`get_order` otherwise)
        """
        cleaned = (part_number or '').strip()
        if not cleaned:
            raise ItemNotFoundError("No part number given", item_id='')

        payload = self._get(
            f'/products/v4/search/{quote(cleaned, safe="")}/productdetails',
            subject=f'part {cleaned}',
        )
        part = DigiKeyPart.from_payload(payload)
        if part is None:
            raise ItemNotFoundError(
                f"DigiKey returned no product for {cleaned}", item_id=cleaned
            )
        return part

    # -- Token -------------------------------------------------------------

    def _token(self) -> str:
        """A live access token, fetched or reused.

        Held in memory only. There is nothing worth persisting about a
        ten-minute token, and a file would be one more secret to keep out of the
        repository.
        """
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        if not self.client_id or not self.client_secret:
            raise ConfigurationError(
                "DigiKey is not configured. Set DIGIKEY_CLIENT_ID and "
                "DIGIKEY_CLIENT_SECRET in .env.",
                config_key='DIGIKEY_CLIENT_ID',
            )

        try:
            response = requests.post(
                f'{self.base_url}/v1/oauth2/token',
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'client_credentials',
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise TemporaryError(
                f"Could not reach DigiKey to authenticate: {e}"
            ) from e

        if response.status_code in (400, 401, 403):
            # A refused token is always the credentials -- the account id plays
            # no part in this call.
            raise AuthenticationError(
                "DigiKey refused the credentials. Check DIGIKEY_CLIENT_ID and "
                "DIGIKEY_CLIENT_SECRET, and that the application is still "
                "subscribed to the Order Status and Product Information APIs."
            )
        if response.status_code != 200:
            raise TemporaryError(
                f"DigiKey returned {response.status_code} when authenticating"
            )

        try:
            body = json.loads(response.text, parse_float=Decimal)
            token = body['access_token']
            expires_in = int(body.get('expires_in') or 0)
        except (ValueError, KeyError, TypeError) as e:
            raise TemporaryError(
                f"DigiKey's token response could not be read: {e}"
            ) from e

        self._access_token = token
        self._token_expires_at = (
            time.monotonic() + max(expires_in - _TOKEN_RENEWAL_MARGIN_SECONDS, 0)
        )
        return token

    # -- Requests ----------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        """Every request carries these.

        ``X-DIGIKEY-Account-ID`` goes on all of them, not only order calls:
        DigiKey's sunset notice for ``X-DIGIKEY-Customer-Id`` lists ProductDetails
        among the endpoints that take its replacement.
        """
        if not self.account_id:
            raise ConfigurationError(
                "DIGIKEY_ACCOUNT_ID is not set. DigiKey's credentials identify "
                "the application rather than the customer, so the account "
                "number has to be given separately -- it is on any DigiKey order "
                "confirmation or invoice.",
                config_key='DIGIKEY_ACCOUNT_ID',
            )

        return {
            'Authorization': f'Bearer {self._token()}',
            'X-DIGIKEY-Client-Id': self.client_id,
            'X-DIGIKEY-Account-ID': self.account_id,
            'Accept': 'application/json',
            'X-DIGIKEY-Locale-Site': 'US',
            'X-DIGIKEY-Locale-Language': 'en',
            'X-DIGIKEY-Locale-Currency': 'USD',
        }

    def _get(self, path: str, subject: str) -> Any:
        """GET a path and return its decoded body, or raise.

        The body is read as **text** and decoded here, so that
        ``parse_float=Decimal`` applies to every response without a caller
        having to remember it.

        ``subject`` is what the operator asked for, in their words, so a 404 can
        say "no part X" rather than "no order X" for a part lookup.
        """
        url = f'{self.base_url}{path}'
        try:
            response = requests.get(
                url, headers=self._headers(), timeout=self.timeout
            )
        except requests.RequestException as e:
            raise TemporaryError(f"Could not reach DigiKey: {e}") from e

        self._raise_for_status(response, subject)

        try:
            return json.loads(response.text, parse_float=Decimal)
        except ValueError as e:
            raise TemporaryError(
                f"DigiKey's response for {subject} was not readable JSON: {e}"
            ) from e

    def _raise_for_status(self, response: requests.Response, subject: str) -> None:
        """Turn a non-200 into the exception that tells the operator what to do."""
        status = response.status_code
        if status == 200:
            return

        body = (response.text or '')[:500]

        if status == 400 and _MISSING_ACCOUNT_MARKER in body.lower():
            # Not authorization: nothing said which account. Sending the operator
            # to renew an authorization would send them somewhere useless.
            raise ConfigurationError(
                "DigiKey does not know which account to read. Check that "
                "DIGIKEY_ACCOUNT_ID is set to your DigiKey account number.",
                config_key='DIGIKEY_ACCOUNT_ID',
            )

        if status in (401, 403):
            raise AuthenticationError(
                "DigiKey refused the request. The application's authorization "
                "may need renewing, or its API subscriptions may have lapsed."
            )

        if status == 404:
            raise ItemNotFoundError(
                f"DigiKey has no {subject} for this account. An order placed in "
                f"the last few minutes may not be visible yet.",
                item_id=subject,
            )

        if status == 429:
            reset = response.headers.get('X-RateLimit-ResetTime') or \
                response.headers.get('X-RateLimit-Reset')
            when = f" Try again after {reset}." if reset else ""
            # retry_after is typed as an int on this exception and DigiKey's
            # header is a timestamp, so the time goes in the message where the
            # operator will actually read it.
            raise RateLimitError(
                f"DigiKey is throttling requests.{when}",
                service='DigiKey',
            )

        logger.warning("DigiKey lookup of %s returned %s: %s", subject, status, body)
        raise TemporaryError(
            f"DigiKey returned {status}. Try again in a moment."
        )
