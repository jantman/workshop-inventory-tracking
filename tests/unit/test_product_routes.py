"""
Route/integration tests for the Product create/edit/detail pages (Story 1.3).

Uses the `client` fixture (CSRF disabled in TestConfig, so POSTs need no token).
"""

import pytest

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
