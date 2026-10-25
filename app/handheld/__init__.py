"""Handheld screens blueprint (feature 068).

Task screens for a scanner handheld (Zebra TC52, 360x512 CSS px), all under
``/h/``. A fourth blueprint package beside ``main``, ``admin`` and ``product``
so the prefix comes from one place (research.md D1). The routes only read
through existing services and render; every write goes through an existing
API or service call.

Author: Jason Antman, 2026.
"""

from flask import Blueprint

bp = Blueprint('handheld', __name__, url_prefix='/h')

from app.handheld import routes  # noqa: E402,F401
