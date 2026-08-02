"""Product catalogue blueprint.

A third blueprint package alongside ``main`` and ``admin``. The catalogue's
routes live here rather than in app/main/routes.py, which is already ~2900 lines
and would not stay readable with a dozen more surfaces bolted on.
"""

from flask import Blueprint

bp = Blueprint('product', __name__)

from app.product import routes  # noqa: E402,F401  (registers the routes)
