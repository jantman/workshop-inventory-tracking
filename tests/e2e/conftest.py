"""Fixtures shared across the e2e suite.

``image_host`` lives here rather than in one test module because four modules
need it. Importing a pytest fixture from another test module works -- injection
finds it either way -- but it reads to every linter as an unused import that is
then shadowed by each test's parameter, which buries real findings under dozens
of F401/F811s. A conftest is where pytest expects a shared fixture to be.
"""

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class _QuietHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler without a line of stderr per request"""

    def log_message(self, fmt, *args):
        # Named `fmt` rather than the stdlib's `format`, which shadows the
        # builtin. BaseHTTPRequestHandler calls this positionally, so the
        # override still matches.
        pass


@pytest.fixture
def image_host():
    """An origin the *application* can really fetch image bytes from.

    ``page.route`` is no help for images, because it is the application that
    fetches them and not the browser -- so their addresses have to name an
    origin the test controls and the server can actually reach.

    Threaded, and deliberately so. Chromium opens speculative connections and
    leaves them idle; a single-threaded HTTPServer blocks inside one of those
    reading a request that never arrives, and ``shutdown()`` then waits forever
    for a loop that cannot come back round. The suite hangs rather than fails,
    which is the worst failure mode a fixture has.
    """
    handler = partial(_QuietHandler, directory=str(FIXTURES / "images"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{server.server_port}"

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
