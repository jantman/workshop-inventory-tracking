"""MCP server blueprint (feature 070).

Serves the Model Context Protocol's Streamable HTTP transport at ``POST /mcp``,
stateless and with plain JSON responses, so an AI assistant can look up and
change inventory items and products. Every tool calls the same service or
route-level helper the web operation it mirrors uses
(specs/070-mcp-server/research.md R4).

Author: Jason Antman, 2026.
"""

from flask import Blueprint

bp = Blueprint('mcp', __name__)

from app.mcp import routes  # noqa: E402,F401
