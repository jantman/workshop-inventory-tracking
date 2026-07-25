"""
Route/integration tests for the Product create/edit/detail pages (Story 1.3).

Uses the `client` fixture (CSRF disabled in TestConfig, so POSTs need no token).
"""

import pytest

from app.exceptions import ValidationError
from app.mariadb_catalog_service import CatalogService


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
        # Never a success flash beside it, and never a claim the product failed.
        assert b'Product created successfully!' not in detail.data
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
