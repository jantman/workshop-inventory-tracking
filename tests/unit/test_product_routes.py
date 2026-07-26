"""
Route/integration tests for the Product create/edit/detail pages (Story 1.3).

Uses the `client` fixture (CSRF disabled in TestConfig, so POSTs need no token).
"""

import re

import pytest

from app.exceptions import ValidationError
from app.mariadb_catalog_service import CatalogService


def _form_controls(body, ids):
    """The `<input>`/`<select>`/`<textarea>` tags carrying each of `ids`.

    Lets an assertion about a FORM CONTROL be made against that control instead
    of against the whole rendered page — which includes base.html, so a page-wide
    substring check answers questions about the navbar rather than about the
    field under test.
    """
    tags = []
    for control_id in ids:
        match = re.search(
            r'<(?:input|select|textarea)\b[^>]*\bid="%s"[^>]*>' % re.escape(control_id),
            body)
        assert match is not None, f'no form control with id="{control_id}"'
        tags.append(match.group(0))
    return tags


@pytest.mark.unit
class TestProductRoutes:

    def _make_product(self, test_storage, **kwargs):
        kwargs.setdefault('description', 'Seed product')
        return CatalogService(test_storage).create_product(**kwargs)

    def test_add_form_renders(self, client):
        resp = client.get('/products/add')
        assert resp.status_code == 200
        assert b'Add Product' in resp.data

    def test_create_with_only_description_redirects_to_detail(self, client, test_storage):
        resp = client.post('/products/add', data={'description': 'LM317 regulator'})
        assert resp.status_code == 302
        assert '/products/' in resp.headers['Location']

        # follow to the detail page
        detail = client.get(resp.headers['Location'])
        assert detail.status_code == 200
        assert b'LM317 regulator' in detail.data

        # persisted with other fields empty
        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(product_id)
        assert product.description == 'LM317 regulator'
        assert product.manufacturer is None

    def test_create_blank_description_rerenders_with_error(self, client, test_storage):
        resp = client.post('/products/add', data={'description': '   ',
                                                  'manufacturer': 'KeepMe'})
        assert resp.status_code == 200  # re-rendered form, not a redirect
        assert b'Label Description is required.' in resp.data
        assert b'KeepMe' in resp.data  # typed input preserved on re-render
        # nothing created (no product with id 1 should exist)
        assert CatalogService(test_storage).get_product(1) is None

    def test_create_overlong_field_rerenders_with_error(self, client, test_storage):
        resp = client.post('/products/add', data={'description': 'x' * 300})
        assert resp.status_code == 200
        assert b'must be 255 characters or fewer' in resp.data
        assert CatalogService(test_storage).get_product(1) is None

    def test_detail_missing_is_404(self, client):
        resp = client.get('/products/999999')
        assert resp.status_code == 404

    def test_detail_renders_fields(self, client, test_storage):
        pid = self._make_product(test_storage, description='Trimmer pot',
                                 manufacturer='Bourns', mpn='3386P')
        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        assert b'Trimmer pot' in resp.data
        assert b'Bourns' in resp.data
        assert b'3386P' in resp.data

    def test_edit_form_prefilled(self, client, test_storage):
        pid = self._make_product(test_storage, description='Editable', manufacturer='TI')
        resp = client.get(f'/products/edit/{pid}')
        assert resp.status_code == 200
        assert b'Editable' in resp.data
        assert b'TI' in resp.data

    def test_edit_missing_is_404(self, client):
        assert client.get('/products/edit/999999').status_code == 404

    def test_edit_persists_change(self, client, test_storage):
        pid = self._make_product(test_storage, description='before')
        resp = client.post(f'/products/edit/{pid}', data={'description': 'after'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/products/{pid}')

        product = CatalogService(test_storage).get_product(pid)
        assert product.description == 'after'

    def test_edit_blank_description_rerenders(self, client, test_storage):
        pid = self._make_product(test_storage, description='keep me')
        resp = client.post(f'/products/edit/{pid}',
                           data={'description': '', 'manufacturer': 'TypedNotSaved'})
        assert resp.status_code == 200
        assert b'Label Description is required.' in resp.data
        # the user's in-flight edits survive the error re-render...
        assert b'TypedNotSaved' in resp.data
        # ...but nothing was written to the database
        product = CatalogService(test_storage).get_product(pid)
        assert product.description == 'keep me'
        assert product.manufacturer is None

    def test_edit_omitted_field_left_unchanged(self, client, test_storage):
        """A POST body missing a field must not null the stored value."""
        pid = self._make_product(test_storage, description='thing', manufacturer='TI')
        resp = client.post(f'/products/edit/{pid}', data={'description': 'thing'})
        assert resp.status_code == 302
        product = CatalogService(test_storage).get_product(pid)
        assert product.manufacturer == 'TI'  # absent key != clear


@pytest.mark.unit
class TestProductPurchases:
    """Detail-page purchase history + the REST record endpoint (Story 1.4)."""

    def _seed(self, test_storage):
        from datetime import date
        from decimal import Decimal
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='LM317')
        svc.record_purchase(pid, vendor='DigiKey', order_date=date(2026, 7, 1),
                            unit_price=Decimal('1.00'))
        svc.record_purchase(pid, vendor='Mouser', order_date=date(2026, 7, 5),
                            unit_price=Decimal('1.25'))
        svc.record_purchase(pid, vendor='DigiKey', order_date=date(2026, 7, 9),
                            unit_price=Decimal('1.50'))
        return pid

    def test_detail_shows_history_and_last_paid(self, client, test_storage):
        pid = self._seed(test_storage)
        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        body = resp.data.decode()
        # all three vendors present, chronological
        assert body.index('Mouser') > body.index('DigiKey')  # first row is 2026-07-01 DigiKey
        # last paid is the most recent price
        assert '1.50' in body
        assert 'Last paid' in body

    def test_detail_no_purchases_empty_state(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='bare')
        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        assert b'No purchases recorded' in resp.data

    def test_record_purchase_endpoint_creates_201(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='widget')
        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'vendor': 'DigiKey', 'unit_price': '2.34',
                                 'quantity': 5, 'order_date': '2026-07-10'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['purchase']['vendor'] == 'DigiKey'
        assert data['purchase']['product_id'] == pid
        assert data['product_url'].endswith(f'/products/{pid}')
        # persisted
        assert len(CatalogService(test_storage).get_purchases_for_product(pid)) == 1

    def test_record_purchase_missing_product_404_object_envelope(self, client):
        resp = client.post('/api/products/999999/purchases', json={'vendor': 'X'})
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False
        # AD-13 object envelope, NOT a bare string
        assert isinstance(data['error'], dict)
        assert data['error']['code'] == 'not_found'

    def test_record_purchase_invalid_unit_price_400_field(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='widget')
        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'vendor': 'X', 'unit_price': 'not-a-number'})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['field'] == 'unit_price'
        # nothing created
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []


_PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF'


@pytest.mark.unit
class TestProductAttachments:
    """Attachment upload/serve + detail-page card (Story 1.5)."""

    def test_detail_shows_attachments_card_and_form(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='widget')
        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        body = resp.data
        assert b'Attachments' in body
        assert b'enctype="multipart/form-data"' in body
        assert b'No attachments' in body  # empty state

    def test_upload_attachment_multipart(self, client, test_storage):
        import io
        pid = CatalogService(test_storage).create_product(description='widget')
        resp = client.post(
            f'/products/{pid}/attachments',
            data={'file': (io.BytesIO(_PDF), 'datasheet.pdf')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 302
        rows = CatalogService(test_storage).get_attachments_for_product(pid)
        assert len(rows) == 1
        assert rows[0].filename == 'datasheet.pdf'

    def test_upload_no_file_flashes_and_creates_nothing(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='widget')
        resp = client.post(f'/products/{pid}/attachments', data={},
                           content_type='multipart/form-data', follow_redirects=True)
        assert resp.status_code == 200
        assert CatalogService(test_storage).get_attachments_for_product(pid) == []

    def test_upload_to_missing_product_404(self, client):
        import io
        resp = client.post('/products/999999/attachments',
                           data={'file': (io.BytesIO(_PDF), 'x.pdf')},
                           content_type='multipart/form-data')
        assert resp.status_code == 404

    def test_serve_attachment_returns_bytes_and_content_type(self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='widget')
        snap = svc.add_attachment(product_id=pid, filename='ds.pdf', content=_PDF,
                                  content_type='application/pdf')
        resp = client.get(f'/attachments/{snap["id"]}')
        assert resp.status_code == 200
        assert resp.data == _PDF
        assert resp.headers['Content-Type'] == 'application/pdf'
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_serve_missing_attachment_404(self, client):
        assert client.get('/attachments/999999').status_code == 404


@pytest.mark.unit
class TestProductCategoryPath(object):
    """The category field's FR13 path end-to-end below the browser: what the
    operator types is stored canonical, shown canonical, and prefilled
    canonical (Story 3.1)."""

    def _make_product(self, test_storage, **kwargs):
        kwargs.setdefault('description', 'Seed product')
        return CatalogService(test_storage).create_product(**kwargs)

    @pytest.mark.parametrize('typed, stored', [
        ('Electronics/Power/DC-DC Converters',
         'electronics/power/dc-dc converters'),                # the AC's case
        ('Electronics/Power/', 'electronics/power'),           # trailing slash
        ('/electronics//power/', 'electronics/power'),         # slash noise
        (' Thermal / Heat Sinks ', 'thermal/heat sinks'),      # spacing
        ('   ', None),                                         # blank -> NULL
    ])
    def test_add_form_post_persists_canonical(self, client, test_storage, typed, stored):
        resp = client.post('/products/add', data={'description': 'LM317',
                                                  'category_path': typed})
        assert resp.status_code == 302
        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(product_id)
        assert product.category_path == stored

    def test_detail_page_shows_the_canonical_path(self, client, test_storage):
        resp = client.post('/products/add', data={'description': 'LM317',
                                                  'category_path': 'Electronics/Power/'})
        detail = client.get(resp.headers['Location'])
        assert detail.status_code == 200
        assert b'electronics/power' in detail.data
        # The stored value is what the page renders — assert on the row itself
        # rather than on the whole page, which contains unrelated markup that
        # could coincidentally carry the typed spelling.
        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(product_id)
        assert product.category_path == 'electronics/power'

    def test_edit_form_prefills_the_canonical_value(self, client, test_storage):
        pid = self._make_product(test_storage, category_path='Electronics/Power/')
        form = client.get(f'/products/edit/{pid}')
        assert form.status_code == 200
        assert b'value="electronics/power"' in form.data

    def test_edit_post_persists_canonical(self, client, test_storage):
        pid = self._make_product(test_storage, category_path='seed/path')
        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'thing',
                                 'category_path': ' /Thermal/Heat Sinks '})
        assert resp.status_code == 302
        product = CatalogService(test_storage).get_product(pid)
        assert product.category_path == 'thermal/heat sinks'

    def test_edit_post_with_blank_clears_the_category(self, client, test_storage):
        pid = self._make_product(test_storage, category_path='seed/path')
        client.post(f'/products/edit/{pid}', data={'description': 'thing',
                                                   'category_path': '   '})
        assert CatalogService(test_storage).get_product(pid).category_path is None

    def test_edit_omitting_category_leaves_it_unchanged(self, client, test_storage):
        pid = self._make_product(test_storage, category_path='Electronics/Power')
        client.post(f'/products/edit/{pid}', data={'description': 'thing'})
        assert (CatalogService(test_storage).get_product(pid).category_path
                == 'electronics/power')

    def test_overlong_category_still_rejected_by_the_existing_message(
            self, client, test_storage):
        """No new user-facing validation error for shape — the route's
        pre-existing 512-character limit is untouched."""
        resp = client.post('/products/add', data={'description': 'LM317',
                                                  'category_path': 'a' * 513})
        assert resp.status_code == 200  # re-rendered form, not a redirect
        assert b'Category must be 512 characters or fewer.' in resp.data

    def test_forms_carry_the_autocomplete_wiring(self, client, test_storage):
        """The category input is wired to the shared component (FR14): a
        dropdown container plus the script that auto-initializes it."""
        pid = self._make_product(test_storage)
        for url in ('/products/add', f'/products/edit/{pid}'):
            page = client.get(url)
            assert page.status_code == 200
            assert b'id="category_path-suggestions"' in page.data
            assert b'field-autocomplete.js' in page.data


@pytest.mark.unit
class TestCategoryPages(object):
    """The operator's rename path below the browser (Story 3.2, FR17): the
    listing is the tree's only visible surface, and the rename form's preview
    is the confirmation."""

    def _make_product(self, test_storage, **kwargs):
        kwargs.setdefault('description', 'Seed product')
        return CatalogService(test_storage).create_product(**kwargs)

    def _row(self, body, path):
        """The listing row for `path` alone, so a count assertion cannot be
        satisfied by an identical number in some other row."""
        marker = f'<code>{path}</code>'.encode()
        assert marker in body, f'no listing row for {path}'
        start = body.index(marker)
        return body[start:body.index(b'</tr>', start)]

    def _force_category_path(self, test_storage, product_id, value):
        """Write a raw category_path, bypassing the service's normalization.

        The only way to reproduce a legacy row that Story 3.1's backfill
        migration deliberately LEFT non-canonical (it skips any value it cannot
        normalize and prints the ids for a manual decision).
        """
        from app.database import Product
        service = CatalogService(test_storage)
        session = service.Session()
        try:
            (session.query(Product).filter(Product.id == product_id)
             .update({Product.category_path: value}))
            session.commit()
        finally:
            session.close()

    def test_listing_renders_paths_and_counts(self, client, test_storage):
        for path in ('electronics/power', 'electronics/power', 'thermal/heat'):
            self._make_product(test_storage, category_path=path)
        self._make_product(test_storage)  # no category — never listed

        resp = client.get('/products/categories')
        assert resp.status_code == 200
        assert b'electronics/power' in resp.data
        assert b'thermal/heat' in resp.data
        # Each row carries a Rename link keyed on its own path.
        assert b'/products/categories/rename?path=electronics/power' in resp.data
        # Two products are filed at electronics/power itself; thermal/heat has
        # one. Read off each path's own row, not the page as a whole.
        assert self._row(resp.data, 'electronics/power').count(b'>2<') == 2
        assert self._row(resp.data, 'thermal/heat').count(b'>1<') == 2

    def test_listing_includes_interior_nodes_no_product_is_filed_at(
            self, client, test_storage):
        """The tree is stored as its leaves, so the node FR17's own acceptance
        criterion renames may carry no product of its own — it still needs a
        row and a Rename link."""
        self._make_product(test_storage, category_path='electronics/power/dc-dc')

        resp = client.get('/products/categories')
        assert resp.status_code == 200
        # Both ancestors are listed, each with its own rename affordance.
        assert b'<code>electronics</code>' in resp.data
        assert b'<code>electronics/power</code>' in resp.data
        assert b'/products/categories/rename?path=electronics/power' in resp.data
        # Filed-here 0, but the subtree holds the one product.
        row = self._row(resp.data, 'electronics/power')
        assert b'>0<' in row and b'>1<' in row

    def test_listing_orders_by_segment_not_by_byte(self, client, test_storage):
        """`-` (0x2D) sorts below `/` (0x2F), so plain string ordering would
        wedge `electronics-old` between a parent and its child."""
        for path in ('electronics/power', 'electronics-old'):
            self._make_product(test_storage, category_path=path)

        body = client.get('/products/categories').data
        parent = body.index(b'<code>electronics</code>')
        child = body.index(b'<code>electronics/power</code>')
        sibling = body.index(b'<code>electronics-old</code>')
        assert parent < child < sibling

    def test_listing_empty_state(self, client, test_storage):
        self._make_product(test_storage)
        resp = client.get('/products/categories')
        assert resp.status_code == 200
        assert b'No categories yet' in resp.data

    def test_rename_form_previews_the_subtree(self, client, test_storage):
        self._make_product(test_storage, category_path='electronics/power')
        self._make_product(test_storage, category_path='electronics/power/dc-dc')
        self._make_product(test_storage, category_path='electronics/cables')

        resp = client.get('/products/categories/rename?path=electronics/power')
        assert resp.status_code == 200
        assert b'electronics/power/dc-dc' in resp.data
        # The sibling is outside the subtree, so it is not previewed as moving.
        assert b'electronics/cables' not in resp.data
        # Two products move, and the destination input starts empty — read off
        # the input's OWN tag: `value=""` asserted page-wide is satisfied by
        # any other empty attribute, so the test would pass with the source
        # path pre-filled.
        assert b'id="rename-total">2<' in resp.data
        start = resp.data.index(b'id="new_path"')
        new_path_tag = resp.data[start:resp.data.index(b'>', start)]
        assert b'value=""' in new_path_tag
        # Nothing was refused, so no field is marked invalid.
        assert b'is-invalid' not in resp.data

    def test_rename_form_with_an_unknown_path_redirects(self, client, test_storage):
        self._make_product(test_storage, category_path='electronics/power')
        resp = client.get('/products/categories/rename?path=nosuch')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/products/categories')

    def test_rename_post_persists_and_redirects(self, client, test_storage):
        node = self._make_product(test_storage, category_path='electronics/power')
        child = self._make_product(test_storage,
                                   category_path='electronics/power/dc-dc')

        resp = client.post('/products/categories/rename',
                           data={'old_path': 'electronics/power',
                                 'new_path': 'Electronics / PSU'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/products/categories')

        service = CatalogService(test_storage)
        assert service.get_product(node).category_path == 'electronics/psu'
        assert service.get_product(child).category_path == 'electronics/psu/dc-dc'

        # The flash names both paths and how many products moved.
        listing = client.get(resp.headers['Location'])
        assert b'electronics/psu' in listing.data
        assert b'2 product(s) updated' in listing.data

    def test_rename_post_on_a_collision_rerenders_and_changes_nothing(
            self, client, test_storage):
        node = self._make_product(test_storage, category_path='electronics/power')
        blocker = self._make_product(test_storage, category_path='electronics/psu')

        resp = client.post('/products/categories/rename',
                           data={'old_path': 'electronics/power',
                                 'new_path': 'electronics/psu'})
        assert resp.status_code == 200  # re-rendered form, not a redirect
        assert b'already exists and holds 1 product(s)' in resp.data
        assert b'value="electronics/psu"' in resp.data  # submitted value retained

        service = CatalogService(test_storage)
        assert service.get_product(node).category_path == 'electronics/power'
        assert service.get_product(blocker).category_path == 'electronics/psu'

    def test_rename_form_with_no_path_argument_says_so(self, client, test_storage):
        """`No products are filed under category ""` would name the wrong
        problem: nothing was picked."""
        self._make_product(test_storage, category_path='electronics/power')
        resp = client.get('/products/categories/rename', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Pick a category to rename' in resp.data

    def test_rename_form_marks_the_field_the_service_refused(
            self, client, test_storage):
        """A rejected SOURCE path must not paint the destination input red."""
        self._make_product(test_storage, category_path='electronics/power')

        refused_source = client.post('/products/categories/rename',
                                     data={'old_path': 'nosuch',
                                           'new_path': 'electronics/psu'})
        assert refused_source.status_code == 200
        assert b'No products are filed under' in refused_source.data
        assert b'is-invalid' not in refused_source.data

        refused_destination = client.post('/products/categories/rename',
                                          data={'old_path': 'electronics/power',
                                                'new_path': 'electronics/power'})
        assert refused_destination.status_code == 200
        assert b'is-invalid' in refused_destination.data
        assert b'id="new_path-error"' in refused_destination.data

    def test_rename_post_reports_a_backend_failure_without_a_second_error(
            self, client, test_storage, monkeypatch):
        """The generic failure branch also re-runs the preview, which would
        raise again on a dead backend — the operator must still get a page."""
        self._make_product(test_storage, category_path='electronics/power')

        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        monkeypatch.setattr(CatalogService, 'rename_category_path', _boom)
        monkeypatch.setattr(CatalogService, 'list_category_paths', _boom)

        resp = client.post('/products/categories/rename',
                           data={'old_path': 'electronics/power',
                                 'new_path': 'electronics/psu'})
        assert resp.status_code == 200
        assert b'An error occurred while renaming the category' in resp.data
        # ...and nothing the page could not establish. "No products are filed
        # under this category" / "Products affected: 0" beside a backend error
        # reads as if the operator's category had just been emptied.
        assert b'No products are filed under this category' not in resp.data
        assert b'id="rename-total">0<' not in resp.data
        assert b'id="preview-unavailable"' in resp.data

    def test_renaming_an_interior_node_carries_its_only_child(
            self, client, test_storage):
        """The epic's own scenario: products assigned UNDER a segment that
        holds none of its own."""
        child = self._make_product(test_storage,
                                   category_path='electronics/power/dc-dc')

        resp = client.post('/products/categories/rename',
                           data={'old_path': 'electronics/power',
                                 'new_path': 'electronics/psu'})
        assert resp.status_code == 302
        assert (CatalogService(test_storage).get_product(child).category_path
                == 'electronics/psu/dc-dc')

    @pytest.mark.parametrize('stored', [
        '/electronics/power',      # leading separator -> an EMPTY ancestor
        'electronics//power',      # doubled separator -> a phantom node
        'Electronics/Power',       # never lowercased
        ' electronics/power ',     # never stripped
    ])
    def test_listing_survives_a_non_canonical_legacy_path(
            self, client, test_storage, stored):
        """Story 3.1's backfill leaves any row it could not normalize exactly
        as it found it, so a stored path is NOT guaranteed canonical — and this
        page is where the operator would go looking for one. Deriving interior
        nodes from `/a/b` yields an empty ancestor that `is_descendant_path`
        refuses, 500-ing the listing itself."""
        product = self._make_product(test_storage, category_path='seed/path')
        self._force_category_path(test_storage, product, stored)

        resp = client.get('/products/categories')
        assert resp.status_code == 200
        # The bad row is still listed — hiding it would leave the operator no
        # way to find it — but it contributes no interior nodes of its own.
        assert f'<code>{stored}</code>'.encode() in resp.data

    def test_a_doubled_separator_invents_no_phantom_sibling_node(
            self, client, test_storage):
        """`ancestor_paths('a//b')` would offer a node `a/` beside the real
        `a`, with its own Rename link that normalizes back to `a` — clicking it
        would move a subtree the operator never selected."""
        self._make_product(test_storage, category_path='electronics/power')
        legacy = self._make_product(test_storage, category_path='seed/path')
        self._force_category_path(test_storage, legacy, 'electronics//old')

        resp = client.get('/products/categories')
        assert resp.status_code == 200
        assert b'<code>electronics</code>' in resp.data       # the real node
        assert b'<code>electronics/</code>' not in resp.data  # the phantom

    def test_a_non_canonical_row_offers_no_rename_link(
            self, client, test_storage):
        """The rename form normalizes whatever `?path=` it is handed, so a link
        built from a non-canonical row points at a DIFFERENT path than the row
        it sits on. The row stays listed — this page is where the operator
        finds it — but without an action it cannot perform."""
        self._make_product(test_storage, category_path='electronics/power')
        legacy = self._make_product(test_storage, category_path='seed/path')
        self._force_category_path(test_storage, legacy, 'Electronics/Power')

        resp = client.get('/products/categories')
        assert resp.status_code == 200
        row = self._row(resp.data, 'Electronics/Power')
        assert b'Not canonical' in row
        assert b'/products/categories/rename?path=' not in row
        # The canonical row beside it keeps its link.
        canonical_row = self._row(resp.data, 'electronics/power')
        assert b'Not canonical' not in canonical_row
        assert b'/products/categories/rename?path=electronics/power' in canonical_row

    def test_a_non_canonical_path_cannot_rename_its_canonical_twin(
            self, client, test_storage):
        """The failure the withheld link exists to prevent: `?path=` is
        normalized before anything is matched, so a legacy `Electronics/Power`
        resolves onto the REAL `electronics/power` — previewing, and on submit
        renaming, a category the operator never selected."""
        node = self._make_product(test_storage, category_path='electronics/power')
        legacy = self._make_product(test_storage, category_path='seed/path')
        self._force_category_path(test_storage, legacy, 'Electronics/Power')

        resp = client.get('/products/categories/rename?path=Electronics/Power',
                          follow_redirects=True)
        assert resp.status_code == 200
        assert b'is not stored in canonical form' in resp.data
        # No form was rendered at all, so the twin's subtree was never offered.
        assert b'id="rename-source"' not in resp.data
        assert (CatalogService(test_storage).get_product(node).category_path
                == 'electronics/power')

    def test_rename_preview_lists_the_interior_node_being_renamed(
            self, client, test_storage):
        """The table is headed "What Will Move" — and the node the operator
        named moves, even when no product is filed at it directly (FR17's own
        acceptance criterion renames exactly such a node)."""
        self._make_product(test_storage, category_path='electronics/power/dc-dc')

        resp = client.get('/products/categories/rename?path=electronics/power')
        assert resp.status_code == 200
        table = resp.data[resp.data.index(b'id="affected-table"'):]
        assert b'<code>electronics/power</code>' in table
        assert b'<code>electronics/power/dc-dc</code>' in table
        assert b'id="rename-total">1<' in resp.data

    def test_rename_form_reports_a_rejection_exactly_once(
            self, client, test_storage):
        """One rejection is one problem: printing the same sentence in the
        alert AND under the input reads as two."""
        self._make_product(test_storage, category_path='electronics/power')

        resp = client.post('/products/categories/rename',
                           data={'old_path': 'electronics/power',
                                 'new_path': 'electronics/power'})
        assert resp.status_code == 200
        message = b'is already this category&#39;s path'
        assert resp.data.count(message) == 1
        # The field is still marked, and still has something to describe it.
        assert b'is-invalid' in resp.data
        assert b'id="new_path-error"' in resp.data

    def test_the_navbar_offers_the_categories_page(self, client):
        """The one nav change: a second item in the existing Products dropdown."""
        resp = client.get('/products/add')
        assert resp.status_code == 200
        assert b'Manage Categories' in resp.data
        assert b'href="/products/categories"' in resp.data


@pytest.mark.unit
class TestProductTagsOnForm(object):
    """The tag field on the product add/edit forms and its rendering on the
    detail page (Story 3.3, FR16)."""

    def _make_product(self, test_storage, **kwargs):
        kwargs.setdefault('description', 'Seed product')
        return CatalogService(test_storage).create_product(**kwargs)

    def _tags(self, test_storage, product_id):
        return CatalogService(test_storage).get_tags_for_product(product_id)

    def _product_count(self, test_storage):
        """How many products exist. Proving a refused form created NOTHING by
        asking whether id 1 is absent only works while the sequence happens to
        start there, and silently stops proving anything once a test seeds a
        product first."""
        from app.database import Product
        session = CatalogService(test_storage).Session()
        try:
            return session.query(Product).count()
        finally:
            session.close()

    def test_the_form_offers_a_tags_input_wired_to_the_component(
            self, client, test_storage):
        """Wiring is by id convention alone: the input plus its sibling
        dropdown div are the whole JS contract."""
        pid = self._make_product(test_storage)
        for url in ('/products/add', f'/products/edit/{pid}'):
            page = client.get(url)
            assert page.status_code == 200
            assert b'id="tags"' in page.data
            assert b'id="tags-suggestions"' in page.data
            assert b'field-autocomplete.js' in page.data
            # The hint that the field holds a comma-separated list.
            assert b'Separate tags with commas' in page.data

    def test_add_with_tags_stores_them_and_redirects(self, client, test_storage):
        resp = client.post('/products/add',
                           data={'description': 'Heat sink',
                                 'tags': 'SSR, rectifier, ssr'})
        assert resp.status_code == 302
        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        # De-duplicated on the canonical form: two rows, not three.
        assert self._tags(test_storage, product_id) == ['rectifier', 'ssr']

        detail = client.get(resp.headers['Location'])
        assert detail.status_code == 200
        assert b'Product created successfully!' in detail.data
        assert b'rectifier' in detail.data
        assert b'ssr' in detail.data

    def test_add_without_the_tags_key_stores_none(self, client, test_storage):
        resp = client.post('/products/add', data={'description': 'Untagged'})
        assert resp.status_code == 302
        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert self._tags(test_storage, product_id) == []

    def test_add_with_an_invalid_tag_rerenders_and_creates_nothing(
            self, client, test_storage):
        """The matrix row: a 65-character tag. Validation is PURE and runs
        before any write, so no product is created."""
        from app.utils.tag import MAX_TAG_LENGTH

        before = self._product_count(test_storage)
        bad_tag = 'a' * (MAX_TAG_LENGTH + 1)
        resp = client.post('/products/add',
                           data={'description': 'Heat sink',
                                 'tags': bad_tag})
        assert resp.status_code == 200  # re-rendered form, not a redirect
        # The util's own message, rendered verbatim on the field.
        assert b'Tag is too long' in resp.data
        assert b'is-invalid' in resp.data
        assert self._product_count(test_storage) == before
        # The submitted value survives the re-render, so the operator's other
        # in-flight edits are not thrown away with the bad tag.
        start = resp.data.index(b'id="tags"')
        assert bad_tag.encode() in resp.data[start:resp.data.index(b'>', start)]

    def test_add_with_a_comma_bearing_tag_is_ordinary_typing_noise(
            self, client, test_storage):
        """A doubled/trailing separator is dropped, not refused — only the
        single-tag entry point rejects an embedded comma."""
        resp = client.post('/products/add',
                           data={'description': 'Heat sink',
                                 'tags': 'ssr,,rectifier,'})
        assert resp.status_code == 302
        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert self._tags(test_storage, product_id) == ['rectifier', 'ssr']

    def test_add_with_too_many_tags_rerenders_and_creates_nothing(
            self, client, test_storage):
        from app.utils.tag import MAX_TAGS_PER_PRODUCT

        before = self._product_count(test_storage)
        resp = client.post('/products/add',
                           data={'description': 'Heat sink',
                                 'tags': ','.join(
                                     f't{i}' for i in
                                     range(MAX_TAGS_PER_PRODUCT + 1))})
        assert resp.status_code == 200
        assert b'Too many tags' in resp.data
        assert self._product_count(test_storage) == before

    def test_edit_form_round_trips_the_stored_tags(self, client, test_storage):
        """The matrix row: a product tagged ssr and rectifier shows
        `rectifier, ssr` in the input."""
        pid = self._make_product(test_storage, description='Heat sink')
        CatalogService(test_storage).set_product_tags(pid, ['ssr', 'rectifier'])

        resp = client.get(f'/products/edit/{pid}')
        assert resp.status_code == 200
        start = resp.data.index(b'id="tags"')
        tags_tag = resp.data[start:resp.data.index(b'>', start)]
        assert b'value="rectifier, ssr"' in tags_tag

    def test_edit_form_leaves_the_input_empty_for_an_untagged_product(
            self, client, test_storage):
        pid = self._make_product(test_storage)
        resp = client.get(f'/products/edit/{pid}')
        start = resp.data.index(b'id="tags"')
        tags_tag = resp.data[start:resp.data.index(b'>', start)]
        assert b'value=""' in tags_tag

    def test_edit_replaces_the_whole_set(self, client, test_storage):
        pid = self._make_product(test_storage, description='Heat sink')
        CatalogService(test_storage).set_product_tags(pid, ['a', 'b'])

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Heat sink', 'tags': 'b, c'})
        assert resp.status_code == 302
        assert self._tags(test_storage, pid) == ['b', 'c']

    def test_edit_with_an_empty_tags_field_clears_every_tag(
            self, client, test_storage):
        pid = self._make_product(test_storage, description='Heat sink')
        CatalogService(test_storage).set_product_tags(pid, ['ssr', 'rectifier'])

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Heat sink', 'tags': ''})
        assert resp.status_code == 302
        assert self._tags(test_storage, pid) == []

    def test_edit_omitting_the_tags_key_leaves_them_alone(
            self, client, test_storage):
        """Absent means "not provided" — the existing partial-update rule."""
        pid = self._make_product(test_storage, description='Heat sink')
        CatalogService(test_storage).set_product_tags(pid, ['ssr', 'rectifier'])

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Heat sink'})
        assert resp.status_code == 302
        assert self._tags(test_storage, pid) == ['rectifier', 'ssr']

    def test_edit_with_an_invalid_tag_rerenders_and_changes_nothing(
            self, client, test_storage):
        from app.utils.tag import MAX_TAG_LENGTH

        pid = self._make_product(test_storage, description='Heat sink')
        CatalogService(test_storage).set_product_tags(pid, ['ssr'])

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Renamed',
                                 'tags': 'a' * (MAX_TAG_LENGTH + 1)})
        assert resp.status_code == 200
        assert b'Tag is too long' in resp.data
        # Neither the product nor its tags were touched.
        service = CatalogService(test_storage)
        assert service.get_product(pid).description == 'Heat sink'
        assert service.get_tags_for_product(pid) == ['ssr']

    def test_a_post_save_tag_failure_redirects_with_an_error_flash(
            self, client, test_storage, monkeypatch):
        """The product and its tags are two transactions, so an infrastructure
        failure can land between them. The operator is told the truth — the
        product saved, the tags did not — and sent to the detail page where the
        product demonstrably exists, never a form claiming the save failed."""
        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        monkeypatch.setattr(CatalogService, 'set_product_tags', _boom)

        resp = client.post('/products/add',
                           data={'description': 'Heat sink', 'tags': 'ssr'})
        assert resp.status_code == 302
        assert '/products/' in resp.headers['Location']

        monkeypatch.undo()
        detail = client.get(resp.headers['Location'])
        assert detail.status_code == 200
        assert b'the product was saved, but its tags were not' in \
            detail.data.lower()
        # The success IS flashed beside the failure, because both are true and
        # the product exists. Suppressing it made FR41's confirmed-duplicate path
        # — where the identifier is ALWAYS refused, by design — look like a save
        # that had failed outright. Never a claim the product failed.
        assert b'Product created successfully!' in detail.data
        assert b'Failed to create product' not in detail.data

    def test_a_post_save_tag_failure_on_edit_redirects_too(
            self, client, test_storage, monkeypatch):
        pid = self._make_product(test_storage, description='Heat sink')

        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        monkeypatch.setattr(CatalogService, 'set_product_tags', _boom)

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Heat sink', 'tags': 'ssr'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/products/{pid}')

        monkeypatch.undo()
        detail = client.get(resp.headers['Location'])
        assert b'the product was saved, but its tags were not' in \
            detail.data.lower()
        assert b'Product updated successfully!' not in detail.data

    @pytest.mark.parametrize('field, retryable, advice', [
        ('tags', False, b'enter different tags'),        # collation collision
        ('tags', True, b'enter its tags again'),         # concurrent-save race
        ('product_id', False, b'enter its tags again'),  # a retry could succeed
    ])
    def test_a_refused_tag_write_gets_advice_that_can_work(
            self, client, test_storage, monkeypatch, field, retryable, advice):
        """A refused tag write is not the same failure as a backend outage —
        and not every refusal on the `tags` field is the same failure either.

        `_validate_product_form` refuses everything a pure check can see, so a
        ValidationError from the service means the DATABASE refused the list.
        A collation collision is refused forever, so the operator must CHANGE a
        tag; the concurrent-save race is refused once, so the identical list
        works and demanding a change would send them chasing a conflict that no
        longer exists. Keying on the field alone cannot tell them apart, which
        is why the service marks the race `retryable`.

        No kind may say "save again": the edit form repopulates its tags from
        the database, which does not hold what the operator typed.
        """
        def _refuse(*args, **kwargs):
            error = ValidationError('nope', field=field, value='x')
            if retryable:
                error.retryable = True
            raise error

        monkeypatch.setattr(CatalogService, 'set_product_tags', _refuse)

        resp = client.post('/products/add',
                           data={'description': 'Heat sink', 'tags': 'ssr'})
        assert resp.status_code == 302

        monkeypatch.undo()
        detail = client.get(resp.headers['Location'])
        assert b'the product was saved, but its tags were not' in \
            detail.data.lower()
        assert advice in detail.data
        # Case-insensitive: the service composes half of this sentence, and
        # its half starts a sentence ("Save them again.").
        assert b'save again' not in detail.data.lower()
        assert b'save them again' not in detail.data.lower()

    def test_detail_renders_tags_as_filter_links(self, client, test_storage):
        pid = self._make_product(test_storage, description='Heat sink')
        CatalogService(test_storage).set_product_tags(pid, ['ssr', 'heat sink'])

        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        assert b'/products/tags/filter?tag=ssr' in resp.data
        # A canonical tag may contain spaces, hence the query parameter.
        assert b'/products/tags/filter?tag=heat+sink' in resp.data

    def test_detail_shows_the_fallback_for_an_untagged_product(
            self, client, test_storage):
        pid = self._make_product(test_storage)
        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        start = resp.data.index(b'id="product-tags"')
        cell = resp.data[start:resp.data.index(b'</dd>', start)]
        assert '—'.encode() in cell
        assert b'/products/tags/filter' not in cell


@pytest.mark.unit
class TestTagPages(object):
    """The operator's tag retrieval path below the browser (Story 3.3,
    FR16): the listing is the vocabulary's only visible surface, and the
    filter page is FR16's answer."""

    def _make_product(self, test_storage, tags=None, **kwargs):
        kwargs.setdefault('description', 'Seed product')
        service = CatalogService(test_storage)
        product_id = service.create_product(**kwargs)
        if tags:
            service.set_product_tags(product_id, tags)
        return product_id

    def _row(self, body, tag):
        """The listing row for `tag` alone, so a count assertion cannot be
        satisfied by an identical number in some other row."""
        marker = f'<code>{tag}</code>'.encode()
        assert marker in body, f'no listing row for {tag}'
        start = body.index(marker)
        return body[start:body.index(b'</tr>', start)]

    def test_listing_renders_tags_and_counts(self, client, test_storage):
        self._make_product(test_storage, tags=['ssr'])
        self._make_product(test_storage, tags=['ssr'])
        self._make_product(test_storage, tags=['rectifier'])
        self._make_product(test_storage)  # untagged — never listed

        resp = client.get('/products/tags')
        assert resp.status_code == 200
        # Each row carries a link keyed on its own tag.
        assert b'/products/tags/filter?tag=ssr' in resp.data
        # Two products carry ssr; one carries rectifier. Read off each tag's
        # own row, not the page as a whole.
        assert b'>2<' in self._row(resp.data, 'ssr')
        assert b'>1<' in self._row(resp.data, 'rectifier')

    def test_listing_empty_state(self, client, test_storage):
        """A fresh install offers no tags — the vocabulary accretes from use."""
        self._make_product(test_storage)
        resp = client.get('/products/tags')
        assert resp.status_code == 200
        assert b'No tags yet' in resp.data
        assert b'accretes purely from use' in resp.data

    def test_filter_returns_exactly_the_tagged_products(self, client, test_storage):
        """THE acceptance criterion (FR16): three heat sinks at
        thermal/heat-sinks with two tagged ssr and one rectifier, plus a fourth
        ssr product filed elsewhere — the filter crosses the tree."""
        self._make_product(test_storage, description='Heat sink A',
                           category_path='thermal/heat-sinks', tags=['ssr'])
        self._make_product(test_storage, description='Heat sink B',
                           category_path='thermal/heat-sinks', tags=['ssr'])
        self._make_product(test_storage, description='Heat sink C',
                           category_path='thermal/heat-sinks',
                           tags=['rectifier'])
        outsider = self._make_product(test_storage, description='Relay module',
                                      category_path='electronics/relays',
                                      tags=['ssr'])

        resp = client.get('/products/tags/filter?tag=ssr')
        assert resp.status_code == 200
        assert b'Heat sink A' in resp.data
        assert b'Heat sink B' in resp.data
        assert b'Relay module' in resp.data
        # The rectifier product is NOT listed, whatever its category.
        assert b'Heat sink C' not in resp.data
        # Each row links to its own detail page.
        assert f'/products/{outsider}"'.encode() in resp.data

    def test_filter_normalizes_its_argument(self, client, test_storage):
        self._make_product(test_storage, description='Heat sink A', tags=['ssr'])
        resp = client.get('/products/tags/filter?tag=++SSR+')
        assert resp.status_code == 200
        assert b'Heat sink A' in resp.data

    def test_filter_on_an_unused_tag_renders_a_named_empty_state(
            self, client, test_storage):
        """An empty result is an answer, not an error."""
        self._make_product(test_storage, description='Heat sink A', tags=['ssr'])

        resp = client.get('/products/tags/filter?tag=nosuchtag')
        assert resp.status_code == 200
        assert b'id="tag-empty-state"' in resp.data
        assert b'nosuchtag' in resp.data
        assert b'Heat sink A' not in resp.data

    @pytest.mark.parametrize('query', [
        '',                     # ?tag= present but blank
        '?tag=',                # ditto, spelled out
        '?tag=+++',             # whitespace only
    ])
    def test_filter_with_no_tag_redirects_asking_for_one(
            self, client, test_storage, query):
        self._make_product(test_storage, tags=['ssr'])

        resp = client.get(f'/products/tags/filter{query}')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/products/tags')

        listing = client.get(resp.headers['Location'])
        assert b'Pick a tag to filter by' in listing.data

    @pytest.mark.parametrize('query', [
        '?tag=' + 'a' * 200,    # over-length: unstorable, so unmatchable
        '?tag=a%2Cb',           # comma-bearing: likewise
    ])
    def test_filter_with_an_unusable_tag_names_that_problem(
            self, client, test_storage, query):
        """A truncated or hand-edited link is a different problem from an
        absent one: telling someone who supplied a tag to "pick a tag" reports
        the wrong thing about a URL they can see contains one."""
        self._make_product(test_storage, tags=['ssr'])

        resp = client.get(f'/products/tags/filter{query}')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/products/tags')

        listing = client.get(resp.headers['Location'])
        assert b'not a usable tag' in listing.data
        assert b'Pick a tag to filter by' not in listing.data

    def test_the_navbar_offers_the_tags_page(self, client):
        """The only nav change: a third item in the Products dropdown."""
        resp = client.get('/products/add')
        assert resp.status_code == 200
        assert b'Browse Tags' in resp.data
        assert b'href="/products/tags"' in resp.data


# ---------------------------------------------------------------------------
# Story 4.5: the three landings a routed scan can point at (FR39/FR40/FR41).
# All additions below are OPTIONAL fields on shipped forms — every Story 1.3
# test above stays green untouched.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProductAddPrefill:
    """`/products/add` reads its pre-fill from `request.args` (FR39/FR40)."""

    def test_every_whitelisted_arg_reaches_the_rendered_form(self, client):
        """The scan hands the form values; the form shows them."""
        resp = client.get('/products/add?description=Scanned+thing'
                          '&manufacturer=Yageo&mpn=RC0805-10K'
                          '&category_path=electronics&tags=smd&notes=from+a+scan'
                          '&identifier_type=GTIN&identifier_value=00012345678905'
                          '&quantity=25&order_number=PO-4471'
                          '&vendor=DigiKey&vendor_sku=296-1234-ND')
        assert resp.status_code == 200
        body = resp.data.decode()
        for value in ('Scanned thing', 'Yageo', 'RC0805-10K', 'electronics',
                      'smd', 'from a scan', '00012345678905', '25', 'PO-4471',
                      'DigiKey', '296-1234-ND'):
            assert value in body, value

    def test_prefilled_values_stay_editable(self, client):
        """FR39 says "every pre-filled value stays editable", so the identifier
        arrives in an ordinary input, not as text or a hidden field.

        Scoped to the pre-filled controls themselves rather than to the whole
        rendered page: `readonly`/`disabled` anywhere in base.html's navbar
        would otherwise fail this test for a reason that has nothing to do with
        the scan pre-fill, and passing it would prove nothing about the inputs.
        """
        resp = client.get('/products/add?identifier_type=GTIN'
                          '&identifier_value=00012345678905&mpn=RC0805'
                          '&quantity=25&order_number=PO-1')
        body = resp.data.decode()
        assert 'id="identifier_value"' in body
        assert 'name="identifier_value"' in body
        assert 'type="hidden"' not in body.split('id="identifier_value"')[0][-200:]

        for tag in _form_controls(body, ('identifier_value', 'identifier_type',
                                         'mpn', 'quantity', 'order_number',
                                         'description')):
            assert 'readonly' not in tag, tag
            assert 'disabled' not in tag, tag

    def test_the_identifier_block_is_absent_without_a_scanned_identifier(self, client):
        """A hand-driven create form is unchanged: no identifier block at all."""
        resp = client.get('/products/add')
        assert resp.status_code == 200
        assert b'id="scanned-identifier"' not in resp.data
        assert b'id="duplicate-warning"' not in resp.data

    def test_internal_is_not_an_offerable_identifier_type(self, client):
        """`add_identifier` refuses INTERNAL — that row is derived from
        `products.internal_id`, so offering it would only ever fail."""
        resp = client.get('/products/add?identifier_type=GTIN&identifier_value=1')
        body = resp.data.decode()
        assert '<option value="GTIN"' in body
        assert '<option value="MPN"' in body
        assert '<option value="INTERNAL"' not in body

    def test_unknown_args_are_ignored(self, client):
        """A fixed whitelist, not `request.args` wholesale: the form round-trips
        whatever it is handed, so an unbounded read would let any query string
        put arbitrary keys in front of the operator."""
        resp = client.get('/products/add?internal_id=SNEAKY&attributes=nope'
                          '&csrf_token=forged&confirm_duplicate=yes')
        body = resp.data.decode()
        assert 'SNEAKY' not in body
        assert 'nope' not in body
        assert 'forged' not in body

    def test_a_prefilled_value_is_judged_on_post_not_truncated_on_get(self, client):
        """Values are taken as given; length is `_validate_product_form`'s call."""
        long_mpn = 'M' * 300
        resp = client.get(f'/products/add?mpn={long_mpn}')
        assert long_mpn in resp.data.decode()

        posted = client.post('/products/add',
                             data={'description': 'x', 'mpn': long_mpn})
        assert posted.status_code == 200
        assert b'must be 255 characters or fewer' in posted.data


@pytest.mark.unit
class TestScannedIdentifierAttach:
    """Saving a scanned create form attaches the identifier (FR40)."""

    def test_identifier_is_attached_on_save(self, client, test_storage):
        resp = client.post('/products/add', data={
            'description': 'Scanned part',
            'identifier_type': 'GTIN',
            'identifier_value': '9506000134352',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        gtins = [r for r in rows if r.identifier_type == 'GTIN']
        assert len(gtins) == 1
        # Normalized to the canonical 14-digit key by the service (AD-7).
        assert gtins[0].value == '09506000134352'

    def test_a_blank_identifier_attaches_nothing(self, client, test_storage):
        resp = client.post('/products/add', data={
            'description': 'Hand-typed part',
            'identifier_type': 'GTIN',
            'identifier_value': '   ',
        })
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        assert [r for r in rows if r.identifier_type == 'GTIN'] == []

    def test_a_uniqueness_collision_flashes_and_still_lands_on_the_product(
            self, client, test_storage):
        """`uq_product_identifiers_type_value_scope` makes a GTIN globally
        unique, so "create a duplicate anyway" and "attach the scanned GTIN to
        it" are mutually exclusive at the schema level.

        The Product is created and the operator lands on it — telling them the
        save failed while the Product exists is the failure mode
        `_apply_product_tags` was already written to avoid.
        """
        svc = CatalogService(test_storage)
        first = svc.create_product(description='Original')
        svc.add_identifier(first, identifier_type='GTIN', value='9506000134352')

        resp = client.post('/products/add', data={
            'description': 'A separate product',
            'identifier_type': 'GTIN',
            'identifier_value': '9506000134352',
            'duplicate_of': str(first),
            'confirm_duplicate': 'yes',
        }, follow_redirects=True)

        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'A separate product' in body            # landed on the NEW product
        assert 'already exists on product' in body     # flashed, not raised
        # The identifier stayed with the original: nothing was moved.
        original_rows = svc.get_identifiers_for_product(first)
        assert any(r.value == '09506000134352' for r in original_rows)

    @pytest.mark.parametrize('identifier_type', ['NOT_A_TYPE', 'INTERNAL',
                                                 'gtin'])
    def test_an_invalid_identifier_type_is_refused_before_the_write(
            self, client, test_storage, identifier_type):
        """Judged on the form, not after the commit.

        `add_identifier` runs after `create_product` has committed and is
        deliberately non-fatal, so a type it refuses there costs a product that
        exists with its identifier thrown away — and no surface exists anywhere
        to add one back. Every check makeable from the form alone belongs in
        front of the write. `INTERNAL` is the case that matters: it is a real
        enum member, so only the choice list rejects it.
        """
        resp = client.post('/products/add', data={
            'description': 'Odd type',
            'identifier_type': identifier_type,
            'identifier_value': 'ABC',
        })
        assert resp.status_code == 200          # re-rendered, not redirected
        assert b'Choose a valid identifier type.' in resp.data
        assert CatalogService(test_storage).search_products('Odd type') == []

    def test_an_over_long_identifier_value_is_refused_before_the_write(
            self, client, test_storage):
        """`product_identifiers.value` is VARCHAR(255). Same reasoning: the
        column refusing it after the commit costs the identifier silently."""
        resp = client.post('/products/add', data={
            'description': 'Long identifier',
            'identifier_type': 'MPN',
            'identifier_value': 'X' * 256,
        })
        assert resp.status_code == 200
        assert b'255 characters or fewer' in resp.data
        assert CatalogService(test_storage).search_products('Long identifier') == []


@pytest.mark.unit
class TestFirstReceiptOnCreate:
    """The create form's optional first receipt (FR39)."""

    def _created_id(self, resp):
        return int(resp.headers['Location'].rstrip('/').split('/')[-1])

    def test_a_receipt_field_records_one_purchase(self, client, test_storage):
        resp = client.post('/products/add', data={
            'description': 'Received part',
            'quantity': '5',
            'order_number': 'PO-1',
        })
        assert resp.status_code == 302
        pid = self._created_id(resp)

        purchases = CatalogService(test_storage).get_purchases_for_product(pid)
        assert len(purchases) == 1
        assert purchases[0].quantity == 5
        assert purchases[0].order_number == 'PO-1'

    def test_all_four_receipt_fields_are_carried(self, client, test_storage):
        resp = client.post('/products/add', data={
            'description': 'Received part',
            'quantity': '2', 'order_number': 'PO-2',
            'vendor': 'DigiKey', 'vendor_sku': '296-1234-ND',
        })
        pid = self._created_id(resp)
        purchase = CatalogService(test_storage).get_purchases_for_product(pid)[0]
        assert (purchase.vendor, purchase.vendor_sku) == ('DigiKey', '296-1234-ND')

    def test_no_receipt_field_records_nothing(self, client, test_storage):
        """The Story 1.3 create path is untouched: blank throughout writes no
        Purchase and costs no transaction."""
        resp = client.post('/products/add', data={
            'description': 'Just a product',
            'quantity': '', 'order_number': '', 'vendor': '', 'vendor_sku': '',
        })
        pid = self._created_id(resp)
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('quantity', ['abc', '0', '-3', '2.5'])
    def test_an_unusable_quantity_rerenders_and_writes_nothing(
            self, client, test_storage, quantity):
        """Owned by `_validate_product_form`, so no caller can bypass it."""
        resp = client.post('/products/add',
                           data={'description': 'Nope', 'quantity': quantity})
        assert resp.status_code == 200
        assert b'whole number greater than zero' in resp.data
        assert CatalogService(test_storage).get_product(1) is None

    @pytest.mark.parametrize('field', ['vendor', 'vendor_sku', 'order_number'])
    def test_an_overlong_receipt_field_rerenders_with_its_own_message(
            self, client, test_storage, field):
        """Bounded against the Purchase columns, not the Product ones."""
        resp = client.post('/products/add',
                           data={'description': 'Nope', field: 'x' * 300})
        assert resp.status_code == 200
        assert b'must be 255 characters or fewer' in resp.data
        assert CatalogService(test_storage).get_product(1) is None


@pytest.mark.unit
class TestDuplicateConfirmation:
    """FR41: creating a second Product for a scan that already matched requires
    an explicit confirmation, and it is never possible to reach the write
    without one."""

    def test_unchecked_rerenders_and_writes_nothing(self, client, test_storage):
        svc = CatalogService(test_storage)
        existing = svc.create_product(description='Original')

        resp = client.post('/products/add', data={
            'description': 'Would-be duplicate',
            'duplicate_of': str(existing),
        })
        assert resp.status_code == 200                 # re-render, not a redirect
        assert b'create a separate product' in resp.data
        assert svc.get_product(existing + 1) is None   # nothing written

    def test_checked_creates_the_product(self, client, test_storage):
        svc = CatalogService(test_storage)
        existing = svc.create_product(description='Original')

        resp = client.post('/products/add', data={
            'description': 'Deliberate duplicate',
            'duplicate_of': str(existing),
            'confirm_duplicate': 'yes',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert svc.get_product(pid).description == 'Deliberate duplicate'

    @pytest.mark.parametrize('confirm', ['no', 'on', 'true', '1', ''])
    def test_only_the_exact_confirmation_value_passes(
            self, client, test_storage, confirm):
        """A checkbox that submits something else is not a confirmation."""
        svc = CatalogService(test_storage)
        existing = svc.create_product(description='Original')

        resp = client.post('/products/add', data={
            'description': 'Would-be duplicate',
            'duplicate_of': str(existing),
            'confirm_duplicate': confirm,
        })
        assert resp.status_code == 200
        assert svc.get_product(existing + 1) is None

    def test_the_form_renders_the_warning_and_the_checkbox(self, client, test_storage):
        existing = CatalogService(test_storage).create_product(description='Original')
        resp = client.get(f'/products/add?duplicate_of={existing}'
                          f'&identifier_type=GTIN&identifier_value=09506000134352')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'id="duplicate-warning"' in body
        assert 'name="confirm_duplicate"' in body
        assert 'name="duplicate_of"' in body
        # The banner says plainly where the scanned identifier ends up.
        assert 'stays with that product' in body

    def test_the_gate_does_not_leak_into_the_edit_form(self, client, test_storage):
        """`_validate_product_form` is shared, but the edit form never carries
        `duplicate_of`, so nothing about editing changes."""
        pid = CatalogService(test_storage).create_product(description='before')
        resp = client.post(f'/products/edit/{pid}', data={'description': 'after'})
        assert resp.status_code == 302


@pytest.mark.unit
class TestSearchPageIsNotADeadEnd:
    """This page is a SCAN DESTINATION, so it may not answer with an error page.

    `api_scan` maps a resolver failure to the AD-13 JSON envelope precisely so a
    scan never lands on an HTML 500. The same broken database one step later —
    after the client has navigated and the scan text is gone from the field —
    would have produced exactly that.
    """

    def test_a_failing_search_flashes_instead_of_500ing(
            self, client, test_storage, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError('database down')

        monkeypatch.setattr(CatalogService, 'search_products', _boom)

        resp = client.get('/products/search?q=WIDGET&description=WIDGET')
        assert resp.status_code == 200
        assert b'Search is unavailable' in resp.data
        # And the escape hatch the scan arrived with still works.
        assert b'search-create-product' in resp.data


@pytest.mark.unit
class TestProductSearchPage:
    """`/products/search` — the landing an ambiguous scan needs (AD-17)."""

    def test_the_internal_id_is_shown_because_it_is_searched(
            self, client, test_storage):
        """A scan that fell through to this page is often looking for exactly the
        internal id, and it is one of the columns the match can have come from —
        a row listed with no visible reason it is there is not a result."""
        CatalogService(test_storage).create_product(description='WIDGET alpha')

        resp = client.get('/products/search?q=WIDGET')
        assert resp.status_code == 200
        assert b'Internal ID' in resp.data

    def test_hits_are_rendered_as_links(self, client, test_storage):
        svc = CatalogService(test_storage)
        first = svc.create_product(description='WIDGET alpha', manufacturer='Acme')
        second = svc.create_product(description='WIDGET beta', mpn='W-2')

        resp = client.get('/products/search?q=WIDGET')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'WIDGET alpha' in body and 'WIDGET beta' in body
        assert f'/products/{first}' in body and f'/products/{second}' in body
        assert 'Acme' in body and 'W-2' in body

    def test_no_hits_renders_the_empty_state(self, client, test_storage):
        CatalogService(test_storage).create_product(description='something else')
        resp = client.get('/products/search?q=NOTHINGMATCHESTHIS')
        assert resp.status_code == 200
        assert b'id="search-empty-state"' in resp.data
        assert b'No products match' in resp.data

    def test_a_blank_query_renders_the_empty_state_without_querying(
            self, client, test_storage, monkeypatch):
        """`search_products` would answer `[]` anyway; not asking says so more
        plainly, and keeps a bookmarked bare URL from scanning the table."""
        calls = []
        monkeypatch.setattr(CatalogService, 'search_products',
                            lambda self, *a, **k: calls.append(a) or [])

        resp = client.get('/products/search?q=%20%20')
        assert resp.status_code == 200
        assert b'id="search-empty-state"' in resp.data
        assert calls == []

    def test_the_create_link_carries_the_scans_prefill(self, client):
        """A search landing never dead-ends either: "Create a new product" keeps
        the identifier the scan carried."""
        resp = client.get('/products/search?q=00012345678905'
                          '&identifier_type=GTIN&identifier_value=00012345678905')
        body = resp.data.decode()
        assert 'id="search-create-product"' in body
        assert 'identifier_type=GTIN' in body
        assert 'identifier_value=00012345678905' in body

    def test_the_page_issues_only_search_products(self, client, test_storage,
                                                  monkeypatch):
        """AD-17: no second search implementation, no filter/ranking/paging
        argument. The call is positional-query-only."""
        seen = []
        original = CatalogService.search_products

        def _spy(self, query, filters=None, **kwargs):
            seen.append((query, filters, kwargs))
            return original(self, query, filters, **kwargs)

        monkeypatch.setattr(CatalogService, 'search_products', _spy)
        assert client.get('/products/search?q=abc').status_code == 200
        assert seen == [('abc', None, {})]


@pytest.mark.unit
class TestPurchaseAddForm:
    """`/products/<id>/purchases/add` — where a matched scan's banner lands."""

    def test_the_detail_page_links_to_it_without_a_scan(self, client, test_storage):
        """The banner was the ONLY link to this form, so an operator who reached
        a product by browsing or by search could not record a purchase at all —
        and two flashed messages that say to "add the purchase from the product
        page" named a control that was not there."""
        pid = CatalogService(test_storage).create_product(description='Reel')

        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        assert f'/products/{pid}/purchases/add'.encode() in resp.data
        assert b'id="add-purchase"' in resp.data

    def test_form_prefills_from_the_query_string(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='Reel')
        resp = client.get(f'/products/{pid}/purchases/add'
                          '?vendor=DigiKey&vendor_sku=296-1234-ND&quantity=100'
                          '&order_number=PO-9&unit_price=1.25'
                          '&order_date=2026-07-01&received_date=2026-07-05'
                          '&source_url=https://example.invalid/x')
        assert resp.status_code == 200
        body = resp.data.decode()
        for value in ('DigiKey', '296-1234-ND', '100', 'PO-9', '1.25',
                      '2026-07-01', '2026-07-05', 'https://example.invalid/x'):
            assert value in body, value

    def test_unknown_product_is_404(self, client):
        assert client.get('/products/999999/purchases/add').status_code == 404
        assert client.post('/products/999999/purchases/add',
                           data={'vendor': 'X'}).status_code == 404

    def test_success_records_and_redirects_to_the_detail_page(self, client, test_storage):
        from decimal import Decimal
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Reel')

        resp = client.post(f'/products/{pid}/purchases/add', data={
            'vendor': 'DigiKey', 'vendor_sku': '296-1234-ND', 'quantity': '100',
            'unit_price': '1.25', 'order_number': 'PO-9',
            'order_date': '2026-07-01', 'received_date': '2026-07-05',
            'source_url': 'https://example.invalid/x',
        })
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/products/{pid}')

        purchases = svc.get_purchases_for_product(pid)
        assert len(purchases) == 1
        assert purchases[0].vendor == 'DigiKey'
        assert purchases[0].quantity == 100
        assert purchases[0].unit_price == Decimal('1.25')
        assert purchases[0].order_date.isoformat() == '2026-07-01'

    @pytest.mark.parametrize('field, value, fragment', [
        ('quantity', 'abc', b'whole number'),
        ('unit_price', 'not-a-number', b'decimal number'),
        ('order_date', '07/01/2026', b'ISO date'),
        ('received_date', 'tomorrow', b'ISO date'),
    ])
    def test_a_bad_value_rerenders_with_a_field_error_and_writes_nothing(
            self, client, test_storage, field, value, fragment):
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Reel')

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'vendor': 'DigiKey', field: value})
        assert resp.status_code == 200
        assert fragment in resp.data
        assert b'DigiKey' in resp.data           # the typed input survives
        assert svc.get_purchases_for_product(pid) == []

    def test_an_empty_form_records_a_bare_purchase(self, client, test_storage):
        """Every Purchase business column is nullable (backfill-forward, FR61),
        and `record_purchase` defaults a missing order_date to today."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Reel')

        resp = client.post(f'/products/{pid}/purchases/add', data={})
        assert resp.status_code == 302
        assert len(svc.get_purchases_for_product(pid)) == 1

    def test_the_json_endpoint_is_untouched(self, client, test_storage):
        """The HTML form is a second entry point, not a replacement: the JSON
        route keeps its own contract."""
        pid = CatalogService(test_storage).create_product(description='Reel')
        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'vendor': 'DigiKey', 'unit_price': '2.34'})
        assert resp.status_code == 201
        assert resp.get_json()['purchase']['vendor'] == 'DigiKey'


@pytest.mark.unit
class TestScanArrivalBanner:
    """The detail page's scan banner (FR41)."""

    def test_absent_without_scan_kind(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='Plain')
        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        assert b'id="scan-banner"' not in resp.data

    def test_present_with_both_links_when_a_scan_arrived(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='Matched')
        resp = client.get(f'/products/{pid}?scan_kind=gtin&scan_type=GTIN'
                          '&scan_value=09506000134352')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'id="scan-banner"' in body
        assert f'/products/{pid}/purchases/add' in body
        assert 'duplicate_of=' in body
        assert '09506000134352' in body

    def test_the_purchase_link_carries_the_receipt_prefill(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='Matched')
        resp = client.get(f'/products/{pid}?scan_kind=ecia&quantity=100'
                          '&order_number=PO-9&vendor_sku=296-1234-ND')
        body = resp.data.decode()
        assert 'quantity=100' in body
        assert 'order_number=PO-9' in body
        assert '296-1234-ND' in body

    def test_the_duplicate_link_reaches_a_gated_create_form(self, client, test_storage):
        """End to end: the banner's second link opens a form that refuses to
        write until the operator confirms (FR41)."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Matched')

        import re
        from urllib.parse import parse_qs

        detail = client.get(f'/products/{pid}?scan_kind=gtin&scan_type=GTIN'
                            '&scan_value=09506000134352')
        body = detail.data.decode()

        # Follow the href the ROUTE built rather than reconstructing it here —
        # the template computes no URL, which is precisely what this asserts.
        match = re.search(r'href="([^"]*)"[^>]*id="scan-banner-create"', body)
        assert match is not None, 'the banner must offer the duplicate link'
        create_url = match.group(1).replace('&amp;', '&')

        form = client.get(create_url)
        assert form.status_code == 200
        assert b'id="duplicate-warning"' in form.data

        # ...and that form refuses to write until it is confirmed.
        refused = client.post('/products/add', data={
            'description': 'Would-be duplicate',
            **{k: v[0] for k, v in parse_qs(create_url.split('?', 1)[1]).items()},
        })
        assert refused.status_code == 200
        assert svc.get_product(pid + 1) is None


@pytest.mark.unit
class TestPrefillCannotBreakTheForm:
    """A pre-fill arrives from a URL, so every value in it is hand-editable."""

    @pytest.mark.parametrize('value', ['abc', '1;2', '-1', '1.0', '', ' ',
                                       '٥', '1_0',
                                       # All-digits is not the same test as
                                       # "could be a product id": both of these
                                       # made the warning block assert that this
                                       # scan matched a product while linking to
                                       # one that cannot exist.
                                       '0', '9' * 60])
    def test_a_non_numeric_duplicate_of_renders_no_block_instead_of_500ing(
            self, client, value):
        """`duplicate_of` feeds `url_for('main.product_detail', product_id=…)`,
        whose `int` converter raises `ValueError` on anything else. Anything
        that cannot name a product is not a duplicate claim, so it is dropped
        and the block simply does not render."""
        resp = client.get(f'/products/add?duplicate_of={value}')
        assert resp.status_code == 200
        assert b'id="duplicate-warning"' not in resp.data

    def test_a_non_numeric_duplicate_of_also_survives_a_post_rerender(
            self, client, test_storage):
        """The POST re-render reads `request.form`, not the whitelist, so the
        same value must not reach `url_for` from there either."""
        resp = client.post('/products/add',
                           data={'description': '', 'duplicate_of': 'abc'})
        assert resp.status_code == 200
        assert b'id="duplicate-warning"' not in resp.data
        assert CatalogService(test_storage).get_product(1) is None

    def test_a_numeric_duplicate_of_still_renders(self, client, test_storage):
        existing = CatalogService(test_storage).create_product(description='Original')
        resp = client.get(f'/products/add?duplicate_of={existing}')
        assert b'id="duplicate-warning"' in resp.data


@pytest.mark.unit
class TestDuplicateConfirmationRoundTrips:
    """The one control guarding a destructive-by-accident write (FR41)."""

    def test_the_checkbox_is_rechecked_after_an_unrelated_error(
            self, client, test_storage):
        """Every sibling field round-trips through `form_data`. An operator who
        confirmed and then tripped a DIFFERENT validation error must not be
        silently returned to the unconfirmed state — they would tick it twice
        for one intent, or (worse) not notice it had been cleared."""
        existing = CatalogService(test_storage).create_product(description='Original')

        resp = client.post('/products/add', data={
            'description': '',                      # the unrelated error
            'duplicate_of': str(existing),
            'confirm_duplicate': 'yes',
        })
        assert resp.status_code == 200
        body = resp.data.decode()
        checkbox = re.search(r'<input[^>]*id="confirm_duplicate"[^>]*>', body)
        assert checkbox is not None
        assert 'checked' in checkbox.group(0)
        # ...and the gate itself did not fire, because it WAS confirmed.
        assert b'create a separate product anyway.' in resp.data
        assert 'Confirm below' not in body

    def test_an_unconfirmed_rerender_is_not_checked(self, client, test_storage):
        existing = CatalogService(test_storage).create_product(description='Original')
        resp = client.post('/products/add', data={
            'description': 'Would-be duplicate', 'duplicate_of': str(existing)})
        checkbox = re.search(r'<input[^>]*id="confirm_duplicate"[^>]*>',
                             resp.data.decode())
        assert 'checked' not in checkbox.group(0)


@pytest.mark.unit
class TestScannedIdentifierTyping:
    """The type decides how the value is stored, so it is never guessed."""

    def test_a_value_without_a_type_is_a_field_error_not_a_silent_gtin(
            self, client, test_storage):
        """An unselected `<select>` used to render with no `selected` option, so
        the browser picked the first declared enum member and a non-GTIN value
        was GTIN-typed and check-digit-normalized."""
        resp = client.post('/products/add', data={
            'description': 'Scanned part', 'identifier_value': 'ABC-123'})

        assert resp.status_code == 200
        assert b'Choose the type of the scanned identifier' in resp.data
        assert CatalogService(test_storage).get_product(1) is None

    def test_the_select_offers_an_empty_option_first(self, client):
        resp = client.get('/products/add?identifier_value=ABC-123')
        body = resp.data.decode()
        assert '<option value=""' in body
        # ...and it is the selected one, so no type is pre-chosen for the operator.
        assert re.search(r'<option value=""[^>]*selected', body)

    def test_a_type_that_arrived_on_the_url_is_still_preselected(self, client):
        resp = client.get('/products/add?identifier_type=GTIN'
                          '&identifier_value=00012345678905')
        body = resp.data.decode()
        assert '<option value="GTIN" selected>' in body
        assert not re.search(r'<option value=""[^>]*selected', body)

    def test_a_blank_value_needs_no_type(self, client, test_storage):
        resp = client.post('/products/add', data={
            'description': 'Hand-typed', 'identifier_value': '   ',
            'identifier_type': ''})
        assert resp.status_code == 302

    def test_the_receipt_vendor_does_not_become_the_identifier_scope(
            self, client, test_storage):
        """`add_identifier` takes `vendor` as the identifier's `vendor_scope`
        for a vendor-scoped type. Passing the receipt block's Vendor input into
        it couples two inputs the form presents as unrelated, with nothing in
        the UI saying so — and it decides the row's uniqueness namespace."""
        svc = CatalogService(test_storage)
        resp = client.post('/products/add', data={
            'description': 'Scanned part',
            'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND',
            'vendor': 'DigiKey',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in svc.get_identifiers_for_product(pid)
                if r.identifier_type == 'VENDOR_SKU']
        assert len(rows) == 1
        assert rows[0].vendor_scope == ''
        # The vendor still reached the place the form said it would.
        assert svc.get_purchases_for_product(pid)[0].vendor == 'DigiKey'


@pytest.mark.unit
class TestQuantityIsTheRuleTheMessageStates:
    """`int()` is not "a whole number": `int('1_0')` is 10, `int('٥')` is 5."""

    @pytest.mark.parametrize('quantity', ['1_0', '٥', '+5', ' 5 5', '5.0',
                                          '1e3', '0x10'])
    def test_a_value_int_would_have_accepted_or_mangled_is_refused(
            self, client, test_storage, quantity):
        resp = client.post('/products/add',
                           data={'description': 'Nope', 'quantity': quantity})
        assert resp.status_code == 200
        assert b'whole number greater than zero' in resp.data
        assert CatalogService(test_storage).get_purchases_for_product(1) == []

    def test_an_overflowing_quantity_is_refused_before_the_column_sees_it(
            self, client, test_storage):
        """`Purchase.quantity` is a 32-bit INTEGER; a longer digit string parses
        in Python and then fails (or wraps) at the database."""
        resp = client.post('/products/add',
                           data={'description': 'Nope', 'quantity': '9' * 12})
        assert resp.status_code == 200
        assert b'whole number greater than zero' in resp.data

    def test_the_largest_valid_quantity_is_accepted(self, client, test_storage):
        resp = client.post('/products/add',
                           data={'description': 'Big receipt', 'quantity': '2147483647'})
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert CatalogService(test_storage).get_purchases_for_product(
            pid)[0].quantity == 2147483647


@pytest.mark.unit
class TestPurchaseFormRefusesWhatTheColumnCannotHold:
    """`record_purchase` validates nothing, so this form is the only gate."""

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    @pytest.mark.parametrize('price', ['NaN', 'nan', 'Infinity', '-Infinity',
                                       'sNaN'])
    def test_a_non_finite_price_is_refused_not_stored_as_null(
            self, client, test_storage, price):
        """`Decimal('NaN')` raises neither `InvalidOperation` nor `ValueError`,
        so an unchecked parse answered "Purchase recorded." and stored NULL — a
        silently discarded price."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'unit_price': price})
        assert resp.status_code == 200
        assert b'decimal number' in resp.data
        assert svc.get_purchases_for_product(pid) == []

    def test_a_negative_price_is_refused(self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'unit_price': '-1.00'})
        assert resp.status_code == 200
        assert b'must not be negative' in resp.data
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('price', ['100000000', '1E+30', '99999999999.99'])
    def test_a_price_past_the_column_is_refused_with_a_field_message(
            self, client, test_storage, price):
        """`Purchase.unit_price` is `Numeric(10, 2)` — eight digits before the
        point. MariaDB refuses more outright, so `record_purchase` returns None
        and the operator gets the generic "Failed to record the purchase" naming
        no field; SQLite widens the column instead and stores a number that was
        never storable. Both are the failure mode the length limits on the text
        columns exist to prevent, on the one column that had no bound."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'unit_price': price})
        assert resp.status_code == 200
        assert b'must be less than 100000000' in resp.data
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('price', ['0.005', '1.234', '1e-30'])
    def test_a_price_finer_than_the_column_is_refused_rather_than_rounded(
            self, client, test_storage, price):
        """The column keeps two decimal places, so a third is silently rounded
        away: `0.005` answered "Purchase recorded." while storing `0.01`, and
        `1e-30` while storing `0.00`. A price the operator did not type is worse
        than a refusal they can act on."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'unit_price': price})
        assert resp.status_code == 200
        assert b'at most two decimal places' in resp.data
        assert svc.get_purchases_for_product(pid) == []

    def test_a_two_decimal_price_at_the_column_edge_is_accepted(
            self, client, test_storage):
        """The bound is exclusive on the value the column cannot hold, not on
        the largest one it can."""
        from decimal import Decimal
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'unit_price': '99999999.99'})
        assert resp.status_code == 302
        assert svc.get_purchases_for_product(pid)[0].unit_price == \
            Decimal('99999999.99')

    @pytest.mark.parametrize('quantity', ['0', '-3', '1_0', '٥', '2.5'])
    def test_a_non_positive_or_non_ascii_quantity_is_refused(
            self, client, test_storage, quantity):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'quantity': quantity})
        assert resp.status_code == 200
        assert b'whole number' in resp.data
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('field, limit, label', [
        ('vendor', 255, b'Vendor must be 255'),
        ('vendor_sku', 255, b'Vendor SKU must be 255'),
        ('order_number', 255, b'Order Number must be 255'),
        ('source_url', 1024, b'Source URL must be 1024'),
    ])
    def test_an_overlong_value_gets_a_field_message_not_a_backend_failure(
            self, client, test_storage, field, limit, label):
        """`product_add` bounds its copies of the same three columns; without
        the same rule here an over-long value reached MariaDB and came back as
        the generic "Failed to record the purchase", naming no field."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={field: 'x' * (limit + 1)})
        assert resp.status_code == 200
        assert label in resp.data
        assert b'characters or fewer' in resp.data
        assert svc.get_purchases_for_product(pid) == []

    def test_a_value_exactly_at_the_limit_is_accepted(self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'vendor': 'x' * 255})
        assert resp.status_code == 302
        assert len(svc.get_purchases_for_product(pid)) == 1


@pytest.mark.unit
class TestFirstReceiptFailureIsNeverFatal:
    """Everything after `create_product` commits is non-fatal, by construction."""

    def test_a_raising_record_purchase_still_lands_on_the_new_product(
            self, client, test_storage, monkeypatch):
        """`record_purchase` promises not to raise, but this runs AFTER the
        Product committed. Unguarded, a broken promise reaches `product_add`'s
        outer handler, which flashes "An error occurred while creating the
        product" and re-renders the form with `duplicate_of` still set — the
        exact "the save failed while the Product exists" lie the surrounding
        comments exist to prevent, whose natural resubmit creates the second
        product FR41 is meant to stop.

        Injected, because no input can make `record_purchase` raise — the same
        justification `test_a_failing_resolution_is_the_ad13_envelope` gives.
        """
        def _boom(self, product_id, **kwargs):
            raise RuntimeError('the database went away')

        monkeypatch.setattr(CatalogService, 'record_purchase', _boom)

        resp = client.post('/products/add', data={
            'description': 'Received part', 'quantity': '5'},
            follow_redirects=True)

        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Received part' in body                     # landed ON the product
        assert 'first receipt was not recorded' in body    # flashed, not raised
        assert 'An error occurred while creating' not in body

    def test_the_identifier_still_gets_attached_when_the_receipt_fails(
            self, client, test_storage, monkeypatch):
        """Collected rather than returned early: one failing follow-up must not
        silently skip the next."""
        def _boom(self, product_id, **kwargs):
            raise RuntimeError('the database went away')

        monkeypatch.setattr(CatalogService, 'record_purchase', _boom)

        resp = client.post('/products/add', data={
            'description': 'Received part', 'quantity': '5',
            'identifier_type': 'GTIN', 'identifier_value': '9506000134352'})
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        assert any(r.value == '09506000134352' for r in rows)


@pytest.mark.unit
class TestScanBannerArgsAreValidated:
    """The detail page's banner args are hand-editable query-string values."""

    @pytest.mark.parametrize('args', [
        'scan_kind=not-a-kind',
        'scan_kind=GTIN',                            # right value, wrong case
        'scan_kind=<script>alert(1)</script>',
        'scan_kind=gtin&scan_type=NOT_A_TYPE',
        'scan_kind=gtin&scan_type=gtin',             # right value, wrong case
        'scan_kind=gtin&scan_type=INTERNAL',         # a type add_identifier refuses
    ])
    def test_an_invalid_discriminator_suppresses_the_banner(
            self, client, test_storage, args):
        """Otherwise any URL can assert that an arbitrary scan of an arbitrary
        type matched this product, and put that bogus type on the create link
        where it becomes the `identifier_type` a save then tries to attach."""
        pid = CatalogService(test_storage).create_product(description='Plain')

        resp = client.get(f'/products/{pid}?{args}&scan_value=09506000134352')
        assert resp.status_code == 200
        assert b'id="scan-banner"' not in resp.data

    @pytest.mark.parametrize('kind', ['internal', 'gtin', 'ecia', 'free_text'])
    def test_every_real_scan_kind_still_renders(self, client, test_storage, kind):
        pid = CatalogService(test_storage).create_product(description='Matched')
        resp = client.get(f'/products/{pid}?scan_kind={kind}')
        assert b'id="scan-banner"' in resp.data

    def test_the_duplicate_link_carries_the_mpn(self, client, test_storage):
        """FR39 names the MPN first; without it the duplicate-create link opens
        blank on the one field the operator just scanned off the label."""
        pid = CatalogService(test_storage).create_product(description='Matched')

        resp = client.get(f'/products/{pid}?scan_kind=ecia&mpn=RC0805-10K'
                          '&quantity=100&order_number=PO-9')
        body = resp.data.decode()
        create = re.search(r'href="([^"]*)"[^>]*id="scan-banner-create"', body)
        assert create is not None
        assert 'mpn=RC0805-10K' in create.group(1)

        # ...and NOT onto the purchase link, which has no such column.
        purchase = re.search(r'href="([^"]*)"[^>]*id="scan-banner-purchase"', body)
        assert 'mpn=' not in purchase.group(1)

        # End to end: the create form opens with the MPN in it.
        form = client.get(create.group(1).replace('&amp;', '&'))
        assert b'value="RC0805-10K"' in form.data


@pytest.mark.unit
class TestSearchPageKeepsTheScan:
    """Refining the query is the most natural next action on a results page."""

    def test_the_search_form_forwards_the_prefill_as_hidden_inputs(
            self, client, test_storage):
        """A form carrying only `q` throws the scan away, so the create escape
        hatch on the refined page opens blank on exactly that scan."""
        resp = client.get('/products/search?q=RC0805'
                          '&identifier_type=GTIN&identifier_value=00012345678905'
                          '&mpn=RC0805-10K&quantity=25&order_number=PO-9')
        body = resp.data.decode()
        for name, value in (('identifier_type', 'GTIN'),
                            ('identifier_value', '00012345678905'),
                            ('mpn', 'RC0805-10K'),
                            ('quantity', '25'),
                            ('order_number', 'PO-9')):
            assert re.search(
                r'<input type="hidden" name="%s" value="%s">' % (name, value),
                body), name
        # `q` is the visible input; a hidden copy would submit it twice.
        assert '<input type="hidden" name="q"' not in body

    def test_a_refined_search_still_reaches_a_prefilled_create_form(
            self, client, test_storage):
        """The property those hidden inputs exist for, asserted end to end."""
        CatalogService(test_storage).create_product(description='RC0805 reel')

        first = client.get('/products/search?q=RC0805'
                           '&identifier_type=GTIN&identifier_value=00012345678905')
        assert first.status_code == 200

        # What the browser would submit: the visible q plus every hidden input.
        refined = client.get('/products/search?q=RC0805+reel'
                             '&identifier_type=GTIN&identifier_value=00012345678905')
        body = refined.data.decode()
        create = re.search(r'href="([^"]*)"[^>]*id="search-create-product"', body)
        assert create is not None

        form = client.get(create.group(1).replace('&amp;', '&'))
        assert b'value="00012345678905"' in form.data


@pytest.mark.unit
class TestADigitRunIsNeverA500:
    """`int()` is not total over digit strings, and every path that parses one
    here is reachable from a query string or a paste.

    CPython refuses to parse a decimal string longer than
    `sys.int_info.str_digits_check_threshold` (4300) and raises `ValueError`
    rather than returning a value. `_positive_int_string` had already proved the
    string was all-ASCII-digits by then, so the raise landed in whatever the
    caller was — including a GET that has no handler at all.
    """

    HUGE = '9' * 4301

    def test_the_prefill_path_survives_it(self, client):
        """`duplicate_of` is parsed on GET, outside `product_add`'s try."""
        resp = client.get(f'/products/add?duplicate_of={self.HUGE}')
        assert resp.status_code == 200
        # Not a product id, so the duplicate block is simply not rendered.
        assert b'confirm_duplicate' not in resp.data

    def test_the_create_form_refuses_it_by_field(self, client):
        resp = client.post('/products/add',
                           data={'description': 'A part', 'quantity': self.HUGE})
        assert resp.status_code == 200
        assert b'Quantity must be a whole number' in resp.data

    def test_the_purchase_form_refuses_it_by_field(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='Part')

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'quantity': self.HUGE})
        assert resp.status_code == 200
        assert b'Quantity must be a whole number' in resp.data
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []

    def test_leading_zeros_still_mean_what_they_meant(self, client, test_storage):
        """The bound is on the magnitude, not on the typing."""
        pid = CatalogService(test_storage).create_product(description='Part')

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'quantity': '0000000007'}, follow_redirects=True)
        assert resp.status_code == 200
        purchases = CatalogService(test_storage).get_purchases_for_product(pid)
        assert [p.quantity for p in purchases] == [7]


@pytest.mark.unit
class TestNoErrorRendersNowhere:
    """A validation error on a field the template does not render is a silent
    200 that writes nothing and says nothing.

    `add.html` renders the Scanned Identifier card — and both of its
    `invalid-feedback` blocks — only when `identifier_value` is set, so every
    identifier rule has to be gated on the same condition.
    """

    def test_a_bogus_type_beside_no_value_does_not_block_the_save(
            self, client, test_storage):
        resp = client.post('/products/add',
                           data={'description': 'A part',
                                 'identifier_type': 'NOT_A_TYPE',
                                 'identifier_value': ''})

        assert resp.status_code == 302, 'the save was refused with no visible reason'
        products = CatalogService(test_storage).search_products('A part')
        assert [p.description for p in products] == ['A part']

    def test_a_bogus_type_beside_a_value_is_still_refused_visibly(self, client):
        resp = client.post('/products/add',
                           data={'description': 'A part',
                                 'identifier_type': 'NOT_A_TYPE',
                                 'identifier_value': '00012345678905'})

        assert resp.status_code == 200
        assert b'Choose a valid identifier type.' in resp.data


@pytest.mark.unit
class TestAFailedSearchClaimsNothing:
    """"No products match X" is a positive claim about the catalog, and a
    search that did not run cannot make it."""

    def test_the_empty_state_does_not_assert_the_catalog_is_empty(
            self, client, test_storage, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError('database down')

        monkeypatch.setattr(CatalogService, 'search_products', _boom)

        body = client.get('/products/search?q=WIDGET').data.decode()
        assert 'The search did not run' in body
        assert 'No products match' not in body

    def test_a_search_that_ran_and_found_nothing_still_says_so(self, client):
        body = client.get('/products/search?q=NOTHING-MATCHES-THIS').data.decode()
        assert 'No products match' in body


@pytest.mark.unit
class TestDuplicateOfMustNameAProduct:
    """Shape is not existence: `_valid_duplicate_of` proves the value COULD be
    an id, which is not the same as its naming one."""

    def test_an_unknown_product_id_renders_no_duplicate_claim(
            self, client, test_storage):
        resp = client.get('/products/add?duplicate_of=999999')

        assert resp.status_code == 200
        body = resp.data.decode()
        # No warning asserting a match, no gate demanding confirmation of one.
        assert 'confirm_duplicate' not in body
        assert '/products/999999' not in body

    def test_a_real_product_id_still_renders_it(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='The original')

        body = client.get(f'/products/add?duplicate_of={pid}').data.decode()
        assert 'confirm_duplicate' in body
        assert f'/products/{pid}' in body


@pytest.mark.unit
class TestATypedSearchStillReachesAUsableCreateForm:
    """Only a SCANNED search carries a pre-fill; a typed one carried nothing."""

    def test_the_create_link_carries_the_typed_query(self, client):
        body = client.get('/products/search?q=blue+widget').data.decode()
        create = re.search(r'href="([^"]*)"[^>]*id="search-create-product"', body)
        assert create is not None

        form = client.get(create.group(1).replace('&amp;', '&'))
        # `description` is the one REQUIRED field on the create form.
        assert b'value="blue widget"' in form.data

    def test_a_scanned_search_keeps_the_scan_mapping(self, client):
        """A `gtin` fall-through deliberately leaves `description` blank — the
        identifier is what that scan says — so the fallback must not fire."""
        body = client.get('/products/search?q=012345678905'
                          '&identifier_type=GTIN'
                          '&identifier_value=00012345678905').data.decode()
        create = re.search(r'href="([^"]*)"[^>]*id="search-create-product"', body)
        assert 'description=' not in create.group(1)


@pytest.mark.unit
class TestThePurchaseFormIsNeverA500:
    """The other landing a matched scan reaches by one click."""

    def test_a_raising_record_purchase_is_a_flash_not_an_error_page(
            self, client, test_storage, monkeypatch):
        pid = CatalogService(test_storage).create_product(description='Part')

        def _boom(*args, **kwargs):
            raise RuntimeError('database down')

        monkeypatch.setattr(CatalogService, 'record_purchase', _boom)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'quantity': '5'})
        assert resp.status_code == 200
        assert b'Failed to record the purchase' in resp.data


@pytest.mark.unit
class TestTheSearchPageRendersNothingItCannotShow:
    """`q` stays byte-identical for the SEARCH; it is scrubbed for display."""

    def test_control_characters_are_not_echoed_into_the_markup(self, client):
        body = client.get('/products/search?q=SEP%1FARATED').data.decode()

        assert '\x1f' not in body
        assert 'SEP ARATED' in body

    def test_the_search_itself_still_runs_on_the_raw_text(
            self, client, test_storage):
        """The exemption exists so the page shows what `hit_count` counted."""
        CatalogService(test_storage).create_product(description='SEP\x1fARATED part')

        body = client.get('/products/search?q=SEP%1FARATED').data.decode()
        assert 'part' in body
        assert 'No products match' not in body
