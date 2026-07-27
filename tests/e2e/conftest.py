"""
Shared helpers for the e2e scan tests.

`SCAN_INPUT`, `unstored_gtin` and `simulate_wedge_scan` live here rather than in
`tests/e2e/test_wedge_scan.py` so that the modules using them depend on shared
infrastructure instead of on each other. The dependency direction is the point:
a helper reached through a sibling test module is hostage to that module's
lifetime, so renaming or reorganizing anything in it breaks a file that does
not appear in the diff.

These are plain module-level functions, not fixtures: `SCAN_INPUT` has ~30
usages and turning `simulate_wedge_scan` into a fixture would churn every call
site for no isolation gain.
"""

import json
import random
import urllib.request


SCAN_INPUT = '#scan-input'


def _gtin13(body):
    """`body` (12 digits) plus its GS1 mod-10 check digit."""
    total = sum((3 if i % 2 == 0 else 1) * int(digit)
                for i, digit in enumerate(reversed(body)))
    return f'{body}{(10 - total % 10) % 10}'


def unstored_gtin(live_server):
    """A check-digit-valid GTIN-13 that demonstrably no product carries.

    `clear_test_data()` truncates the catalog tables, so a test starts with an
    empty catalog — but "empty at setup" is not "empty here". Callers reach
    this helper mid-test, after their OWN products have landed, and it is what
    the catalog holds at the moment of the call that decides where a vector
    routes.

    The absence is therefore CHECKED rather than assumed. `POST /api/scan` is
    read-only, so asking the running server where a candidate routes costs one
    lookup and writes nothing — and the answer is proof, from the very code path
    under test, of where this vector goes. A purely random vector would only ever
    be a probability argument.

    The accepted answer is `create`, not merely "not `product`". Every caller
    waits for `/products/add`, and a candidate whose digits happen to appear in
    some other product's text routes to `search` instead — a page that never
    becomes the create form, so the wait would time out rather than fail with
    anything that names the cause.
    """
    for _ in range(20):
        candidate = _gtin13(f'{random.randrange(10 ** 12):012d}')
        request = urllib.request.Request(
            f'{live_server.url}/api/scan',
            data=json.dumps({'raw': candidate}).encode('utf-8'),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10) as response:
            if json.load(response).get('outcome') == 'create':
                return candidate
    raise AssertionError('no unclaimed GTIN found in 20 attempts')


def simulate_wedge_scan(page, text):
    """Simulate a keyboard-wedge scanner: keystrokes then Enter.

    Modeled on tests/e2e/test_move_items.py's simulate_barcode_scan - a wedge
    is indistinguishable from fast typing, which is the whole point of FR35.
    """
    scan_input = page.locator(SCAN_INPUT)
    scan_input.fill('')
    scan_input.focus()
    scan_input.type(text)
    scan_input.press('Enter')
