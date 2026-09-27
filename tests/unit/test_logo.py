"""
The application's logo is declared, served, shown, and sized (053, issue #169).

The master is ``app/static/img/logo.svg``; the favicon and the extension icons
are rasters rendered from it and checked in. These tests pin the places that
use it, so a template edit that drops the ``<link rel="icon">`` or brings back
the borrowed ``bi-tools`` glyph fails here rather than in a browser tab.
"""

import json
import re
from pathlib import Path

import pytest
from flask import url_for
from PIL import Image

REPO_ROOT = Path(__file__).parents[2]
MANIFEST = REPO_ROOT / 'extension' / 'manifest.json'
FAVICON = REPO_ROOT / 'app' / 'static' / 'img' / 'favicon.ico'


def _home(client):
    response = client.get('/')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _icon_links(html):
    return re.findall(r'<link rel="icon"[^>]*>', html)


def _href(tag):
    return re.search(r'href="([^"]+)"', tag).group(1)


@pytest.mark.unit
class TestTheTabShowsTheLogo:
    """US1: every page declares a favicon, and it is served."""

    def test_the_page_declares_the_svg_and_the_ico(self, client):
        links = _icon_links(_home(client))

        assert len(links) == 2, links
        assert 'type="image/svg+xml"' in links[0]
        assert _href(links[0]).endswith('/static/img/logo.svg')
        assert _href(links[1]).endswith('/static/img/favicon.ico')

    def test_every_declared_icon_is_served(self, client):
        for link in _icon_links(_home(client)):
            response = client.get(_href(link))
            assert response.status_code == 200, link
            assert response.data

    def test_the_root_favicon_path_is_the_logo(self, client):
        """For requests that never read a page's ``<head>``."""
        response = client.get('/favicon.ico')

        assert response.status_code == 200
        assert response.data == FAVICON.read_bytes()


@pytest.mark.unit
class TestTheExtensionIconIsTheLogo:
    """US2: each icon the manifest declares is a PNG of its declared size."""

    def test_every_declared_icon_is_its_declared_size(self):
        manifest = json.loads(MANIFEST.read_text())
        declared = {**manifest['icons'], **manifest['action']['default_icon']}

        assert set(declared) == {'16', '48', '128'}
        for size, name in declared.items():
            with Image.open(MANIFEST.parent / name) as image:
                assert image.format == 'PNG', name
                assert image.size == (int(size), int(size)), name


@pytest.mark.unit
class TestTheNavbarShowsTheLogo:
    """US3: the brand and the home banner carry the logo, not a stock glyph."""

    def test_the_navbar_brand_is_the_logo_and_still_links_home(self, app, client):
        brand = re.search(
            r'<a class="navbar-brand" href="([^"]+)">(.*?)</a>',
            _home(client),
            re.DOTALL,
        )

        assert brand, 'no navbar brand'
        with app.test_request_context():
            assert brand.group(1) == url_for('main.index')
        assert re.search(r'<img src="[^"]*/static/img/logo\.svg" class="brand-logo"', brand.group(2))
        assert 'Workshop Inventory' in brand.group(2)
        assert 'bi-tools' not in brand.group(2)

    def test_the_home_banner_heading_is_the_logo(self, client):
        heading = re.search(r'<h1 class="display-4">(.*?)</h1>', _home(client), re.DOTALL)

        assert heading, 'no banner heading'
        assert 'class="brand-logo"' in heading.group(1)
        assert 'bi-tools' not in heading.group(1)
