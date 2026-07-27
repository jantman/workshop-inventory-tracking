"""
Route/integration tests for the Product create/edit/detail pages (Story 1.3).

Uses the `client` fixture (CSRF disabled in TestConfig, so POSTs need no token).
"""

import html
import re
from pathlib import Path

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


def _input_value(body, control_id):
    """The value the named `<input>` would SUBMIT, entities decoded.

    Asserting a stored value "is in the page" proves nothing about a ROUND-TRIP:
    the edit page also renders the product's description in its title, so a
    page-wide substring check passes whether or not the input was populated.

    Decoded because Jinja escapes `&`, `<` and `"` on the way out and the
    browser decodes them on the way back in. Comparing the raw attribute text
    against a stored value would report `Fluke &amp; Co` as a mangled
    round-trip, and — worse, in `_rendered_edit_form` — would re-post the
    escaped form and call the result lossless.
    """
    tag = _form_controls(body, [control_id])[0]
    # Anchored on whitespace, not `\b`: a word boundary also matches inside a
    # hyphenated attribute name, so `data-value="…"` rendered before the real
    # one would be returned in its place.
    match = re.search(r'\svalue="([^"]*)"', tag)
    assert match is not None, \
        f'the control id="{control_id}" carries no value attribute'
    return html.unescape(match.group(1))


def _textarea_value(body, control_id):
    """Same, for `notes` — a `<textarea>` carries its value as content, so
    `_input_value` would find no value attribute at all."""
    match = re.search(
        r'<textarea\b[^>]*\bid="%s"[^>]*>(.*?)</textarea>' % re.escape(control_id),
        body, re.S)
    assert match is not None, f'no textarea with id="{control_id}"'
    return html.unescape(match.group(1))


def _shown_keyed_errors(body):
    """Every message rendered by a field's OWN feedback block, and only those.

    `d-block` is what makes one of these visible — Bootstrap keeps a bare
    `invalid-feedback` hidden — and it is added by the same `{% if %}` that
    chooses the message, so matching on it is what separates a rendered error
    from a slot sitting there empty.

    That distinction is load-bearing rather than fussy. `description`'s block is
    the one that always renders, with `A Label Description is required.` as its
    placeholder — which CONTAINS the validator's `Label Description is
    required.`. A bare `in body` check for that message therefore passes on a
    page carrying no error at all, so the assertion meant to catch a deleted
    feedback block could not catch it for the one required field on the form.
    """
    return [html.unescape(m.strip()) for m in re.findall(
        r'<div class="invalid-feedback d-block">(.*?)</div>', body, re.S)]


def _rendered_edit_form(body):
    """The edit form as a POST body: every control it rendered, with the value
    it rendered. What a client that re-posts the page it was handed would send.
    """
    data = {name: _input_value(body, name)
            for name in ('description', 'manufacturer', 'mpn', 'category_path',
                         'tags')}
    data['notes'] = _textarea_value(body, 'notes')
    return data


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

    def test_create_blank_description_rerenders_with_error(self, client, product_ids):
        resp = client.post('/products/add', data={'description': '   ',
                                                  'manufacturer': 'KeepMe'})
        assert resp.status_code == 200  # re-rendered form, not a redirect
        assert b'Label Description is required.' in resp.data
        assert b'KeepMe' in resp.data  # typed input preserved on re-render
        assert product_ids() == set()  # nothing created

    def test_create_overlong_field_rerenders_with_error(self, client, product_ids):
        resp = client.post('/products/add', data={'description': 'x' * 300})
        assert resp.status_code == 200
        assert b'must be 255 characters or fewer' in resp.data
        assert product_ids() == set()

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

    def test_create_stores_padded_identifier_fields_trimmed(self, client, test_storage):
        """Padding typed or pasted into the form does not reach the column (DW-7).

        The route deliberately hands `request.form` values to the service
        untouched — the service owns the trim, and a second strip here would be
        a duplicate rule that can drift — so this is the assertion that the
        end-to-end form path actually gets the benefit of it. Padding is a
        realistic form input rather than a contrived one: a part number pasted
        from a datasheet or a distributor's page routinely carries a leading or
        trailing space, and the operator cannot see it in the field.
        """
        resp = client.post('/products/add', data={'description': 'RES 10K 0805 1%',
                                                  'mpn': ' RC0805-10K ',
                                                  'manufacturer': ' TI '})
        assert resp.status_code == 302

        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(product_id)
        assert product.mpn == 'RC0805-10K'
        assert product.manufacturer == 'TI'

    def test_edit_stores_padded_identifier_fields_trimmed(self, client, test_storage):
        """The same through the edit form, which reaches the other writer.

        `product_edit` builds a partial `update_fields` dict and calls
        `update_product`, a different service method with its own cleaning loop
        than the one `product_add` calls, so a create-side assertion says
        nothing about this path. Read back through `get_product` rather than off
        the redirect target's HTML: the detail page would render a padded value
        and a trimmed one indistinguishably.
        """
        pid = self._make_product(test_storage, description='before', mpn='OLD-1')
        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'before',
                                 'mpn': ' RC0805-10K ',
                                 'manufacturer': ' TI '})
        assert resp.status_code == 302

        product = CatalogService(test_storage).get_product(pid)
        assert product.mpn == 'RC0805-10K'
        assert product.manufacturer == 'TI'


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

    def _product_count(self, test_storage):
        """How many products exist — the only way to say a refused form wrote
        NOTHING, rather than that it did not redirect."""
        from app.database import Product
        session = CatalogService(test_storage).Session()
        try:
            return session.query(Product).count()
        finally:
            session.close()

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

    def test_overlong_category_is_refused_with_the_utils_own_message(
            self, client, test_storage):
        """The route renders `app/utils/category.py`'s message verbatim rather
        than restating the limit — there is one rule, and it names the length it
        measured."""
        resp = client.post('/products/add', data={'description': 'LM317',
                                                  'category_path': 'a' * 513})
        assert resp.status_code == 200  # re-rendered form, not a redirect
        assert b'Category path is too long: 513 characters (max 512).' in resp.data
        # The plain over-length case is the one an operator meets, so it is
        # also where "refused before any write" has to be proved.
        assert self._product_count(test_storage) == 0

    def test_category_at_the_limit_is_accepted(self, client, test_storage):
        """512 characters is what the column holds, so it is stored, not
        refused — the boundary belongs to the accepting side."""
        value = 'a' * 512
        resp = client.post('/products/add', data={'description': 'LM317',
                                                  'category_path': value})
        assert resp.status_code == 302
        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert CatalogService(test_storage).get_product(product_id).category_path == value

    @pytest.mark.parametrize('typed_count, stored_length, accepted', [
        (256, 512, True),    # exactly the limit once stored
        (257, 514, False),   # one typed character past it
    ])
    def test_the_512_cut_is_made_on_the_stored_length(
            self, client, test_storage, typed_count, stored_length, accepted):
        """Where the accept/reject cut actually falls.

        `'a' * 512` proves nothing about WHICH length is measured, because a
        canonical ASCII path has only one: raw and stored are the same number,
        so it passes identically under either rule. These two land the STORED
        length on 512 and just past it while the typed length stays around
        half that — far inside a raw-character rule, which would therefore
        accept both. Only a rule reading the stored value separates them.
        """
        typed = 'İ' * typed_count
        assert len(typed) < 512  # a raw rule sees no difference between these

        resp = client.post('/products/add', data={'description': 'LM317',
                                                  'category_path': typed})
        if accepted:
            assert resp.status_code == 302
            product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
            stored = CatalogService(test_storage).get_product(product_id).category_path
            assert stored == typed.lower()
            assert len(stored) == stored_length
        else:
            assert resp.status_code == 200
            assert (f'Category path is too long: {stored_length} characters '
                    f'(max 512).') in resp.data.decode()
            assert self._product_count(test_storage) == 0

    def test_a_category_that_lowercases_longer_is_refused_on_add(
            self, client, test_storage):
        """Normalization is not always a shortening: `'İ'.lower()` is two
        characters, so 300 typed characters are 600 stored ones.

        Measuring what was typed accepted this and left the service — which
        never raises — to fail the write into a generic flash. The limit is on
        the value that would be STORED, and it is reported before any write."""
        resp = client.post('/products/add', data={'description': 'LM317',
                                                  'category_path': 'İ' * 300})
        assert resp.status_code == 200
        assert 'Category path is too long: 600 characters (max 512).' in \
            resp.data.decode()
        assert b'An error occurred' not in resp.data
        assert self._product_count(test_storage) == 0

    def test_a_category_that_lowercases_longer_is_refused_on_edit(
            self, client, test_storage):
        """Both forms share `_validate_product_form`, so the edit route refuses
        the same value the same way and leaves the stored path alone."""
        pid = self._make_product(test_storage, category_path='seed/path')
        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'thing',
                                 'category_path': 'İ' * 300})
        assert resp.status_code == 200
        assert 'Category path is too long: 600 characters (max 512).' in \
            resp.data.decode()
        product = CatalogService(test_storage).get_product(pid)
        assert product.category_path == 'seed/path'
        assert product.description == 'Seed product'

    def test_over_length_raw_that_normalizes_to_fit_is_accepted(
            self, client, test_storage):
        """The symmetric case: separator and whitespace noise that normalizes
        away never reaches the column, so it cannot exceed the column's limit.
        Judging the typed length refused this path over a bound the value it
        would have stored does not come close to."""
        canonical = 'thermal/heat sinks/extruded'
        typed = ' / ' * 100 + canonical.upper() + ' / ' * 100
        assert len(typed) > 512  # the raw value alone would have been refused

        resp = client.post('/products/add', data={'description': 'LM317',
                                                  'category_path': typed})
        assert resp.status_code == 302
        product_id = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert (CatalogService(test_storage).get_product(product_id).category_path
                == canonical)

    def test_neither_form_caps_the_category_input(self, client, test_storage):
        """A `maxlength` here would be the raw-length rule again, moved into the
        browser — where it truncates a legal path in silence. The fields whose
        limits ARE on the raw value keep theirs."""
        pid = self._make_product(test_storage)
        for url in ('/products/add', f'/products/edit/{pid}'):
            page = client.get(url)
            assert page.status_code == 200
            body = page.data.decode()
            # Asked of the control, not of the page: every one of these forms
            # renders several bounded inputs, so `'maxlength' not in body`
            # would be answered by any of them.
            category, description, manufacturer, mpn = _form_controls(
                body, ('category_path', 'description', 'manufacturer', 'mpn'))
            assert 'maxlength' not in category, f'{url} caps the category input'
            for field, tag in (('description', description),
                               ('manufacturer', manufacturer), ('mpn', mpn)):
                assert 'maxlength="255"' in tag, \
                    f'{url} dropped the {field} cap, which IS a raw-length rule'

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

    def test_the_destination_input_is_not_capped(self, client, test_storage):
        """The rename destination is judged by the same rule the product form's
        Category is: on the path as STORED. A cap on what is typed would cut a
        legal destination short in silence, so the input carries none."""
        self._make_product(test_storage, category_path='electronics/power')

        resp = client.get('/products/categories/rename?path=electronics/power')
        new_path_tag, = _form_controls(resp.data.decode(), ['new_path'])
        assert 'maxlength' not in new_path_tag

    def test_a_destination_that_normalizes_to_fit_is_renamed(
            self, client, test_storage):
        """Separator and whitespace noise never reaches the column, so a
        destination far past the limit as typed still fits once stored — which
        is only reachable now that nothing cuts the input off."""
        node = self._make_product(test_storage, category_path='electronics/power')
        typed = ' / ' * 100 + 'Electronics / PSU' + ' / ' * 100
        assert len(typed) > 512

        resp = client.post('/products/categories/rename',
                           data={'old_path': 'electronics/power',
                                 'new_path': typed})
        assert resp.status_code == 302
        assert (CatalogService(test_storage).get_product(node).category_path
                == 'electronics/psu')

    def test_a_destination_that_lowercases_longer_is_refused_on_the_field(
            self, client, test_storage):
        """The other direction, and the reason the cap could not have stayed:
        300 typed characters are 600 stored ones, so the refusal can only come
        from the server — beside the field, with nothing written."""
        node = self._make_product(test_storage, category_path='electronics/power')

        resp = client.post('/products/categories/rename',
                           data={'old_path': 'electronics/power',
                                 'new_path': 'İ' * 300})
        assert resp.status_code == 200
        assert 'Category path is too long: 600 characters (max 512).' in \
            resp.data.decode()
        assert b'id="new_path-error"' in resp.data
        assert (CatalogService(test_storage).get_product(node).category_path
                == 'electronics/power')

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
        """Inverted for DW-30: the success IS flashed beside the failure.

        This test used to assert the opposite, and the two forms therefore told
        different stories about the identical outcome — a committed row whose
        follow-up write failed read as a partial success on `product_add` and as
        an outright failure here. `update_product` had already committed by the
        time `set_product_tags` was reached, so withholding the success flash
        left the operator with only "the tags were not saved" and no word on the
        edit that had in fact landed. Same order as the sibling above: the
        success first, unconditionally, then the collected failures."""
        pid = self._make_product(test_storage, description='Heat sink')

        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        monkeypatch.setattr(CatalogService, 'set_product_tags', _boom)

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Renamed', 'tags': 'ssr'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/products/{pid}')

        monkeypatch.undo()
        detail = client.get(resp.headers['Location'])
        assert b'the product was saved, but its tags were not' in \
            detail.data.lower()
        assert b'Product updated successfully!' in detail.data
        assert b'Failed to update product' not in detail.data
        # And the edit really did land, which is what the success flash claims.
        assert CatalogService(test_storage).get_product(pid).description == 'Renamed'

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
                          '&identifier_vendor=Adafruit'
                          '&quantity=25&order_number=PO-4471'
                          '&vendor=DigiKey&vendor_sku=296-1234-ND')
        assert resp.status_code == 200
        body = resp.data.decode()
        for value in ('Scanned thing', 'Yageo', 'RC0805-10K', 'electronics',
                      'smd', 'from a scan', '00012345678905', '25', 'PO-4471',
                      'DigiKey', '296-1234-ND'):
            assert value in body, value
        # DW-20: the identifier block's own vendor scope pre-fills like the two
        # fields beside it. Asserted on the control rather than on the page,
        # because the receipt block renders a Vendor input too — a page-wide
        # substring check could not tell the two apart.
        assert _input_value(body, 'identifier_vendor') == 'Adafruit'

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
                          '&identifier_vendor=DigiKey'
                          '&quantity=25&order_number=PO-1')
        body = resp.data.decode()
        assert 'id="identifier_value"' in body
        assert 'name="identifier_value"' in body
        assert 'type="hidden"' not in body.split('id="identifier_value"')[0][-200:]

        for tag in _form_controls(body, ('identifier_value', 'identifier_type',
                                         'identifier_vendor',
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
class TestGtinCheckDigitRefusedBeforeTheWrite:
    """The fourth purely-checkable identifier fault, moved in front of the
    commit (DW-23).

    A GTIN `app/utils/gtin.py` refuses used to be judged only inside
    `add_identifier`, which runs AFTER `create_product` has committed and is
    deliberately non-fatal: the POST redirected, the product existed, the
    identifier was thrown away and the operator got an advisory flash on a page
    with no way to add one back. Its three siblings — blank type, unknown type,
    over-long value — were already moved; these tests pin the fourth, and every
    way it must NOT fire.

    Reachable only by hand: `classify()` types a value `GTIN` only once its
    check digit has validated, so no scan can pre-fill a value this refuses.
    """

    def test_a_bad_check_digit_is_refused_with_nothing_written(
            self, client, product_ids):
        resp = client.post('/products/add', data={
            'description': 'Mis-scanned part',
            'identifier_type': 'GTIN',
            'identifier_value': '012345678900',
        })

        assert resp.status_code == 200          # re-rendered, not redirected
        assert product_ids() == set()           # and nothing at all was created

        body = resp.data.decode()
        # Quoted from the pure util verbatim — the route adds a pointer, it does
        # not restate the rule — and the pointer carries the service's recovery
        # clause word for word, so both sides name the same remedy. Only the
        # verb differs: here the type is still a `<select>` to change.
        assert _shown_keyed_errors(body) == [
            "GTIN check digit is invalid: expected 5, got 0 in '012345678900'. "
            'Choose the GTIN_UNVALIDATED type to keep the value exactly as '
            'entered, without check-digit validation.']
        # ...rendered on the Scanned Identifier card, beside the value it is
        # about. That card renders only when `identifier_value` is set, so a
        # message keyed here is only visible when the value is too.
        assert 'id="scanned-identifier"' in body
        assert 'is-invalid' in _form_controls(body, ['identifier_value'])[0]
        # The message names an action, so the control that performs it has to be
        # on the page it renders on: the type the operator is told to choose is
        # an option of the re-rendered `<select>`, and the type they submitted
        # is still the selected one to change FROM.
        assert '<option value="GTIN_UNVALIDATED"' in body
        assert '<option value="GTIN" selected>' in body
        # The submitted values survive the re-render, so the operator can fix
        # the digit they mistyped rather than retype the whole value.
        assert _input_value(body, 'identifier_value') == '012345678900'
        assert _input_value(body, 'description') == 'Mis-scanned part'

    @pytest.mark.parametrize('identifier_value, message', [
        # `normalize_gtin` raises ONE error for non-digits, wrong lengths and a
        # failed check digit, and the route catches it whole — narrowing to the
        # check digit would mean re-listing the other two rules in the route.
        ('ABC-123', "GTIN must contain only digits: 'ABC-123'."),
        ('12345', "GTIN must be 8, 12, 13, or 14 digits, got 5: '12345'."),
        # `str.isdigit()` is true for non-ASCII digits, so the util requires
        # ASCII on purpose: an Arabic-Indic twin of a real GTIN must not become
        # a key that cannot be compared with the plain digits everything else
        # stores. The route inherits that, and gets it for free by not
        # re-deriving the rule.
        ('٠١٢٣٤٥٦٧٨٩٠٥',
         "GTIN must contain only digits: '٠١٢٣٤٥٦٧٨٩٠٥'."),
    ])
    def test_every_way_the_util_refuses_a_gtin_is_refused_here(
            self, client, product_ids, identifier_value, message):
        resp = client.post('/products/add', data={
            'description': 'Mis-scanned part',
            'identifier_type': 'GTIN',
            'identifier_value': identifier_value,
        })

        assert resp.status_code == 200
        assert product_ids() == set()
        assert _shown_keyed_errors(resp.data.decode()) == [
            f'{message} Choose the GTIN_UNVALIDATED type to keep the value '
            f'exactly as entered, without check-digit validation.']

    def test_a_valid_gtin_still_saves_and_is_still_normalized_by_the_service(
            self, client, test_storage):
        """The form's call is PURE: it discards the canonical key and leaves the
        write-time normalization where it was (AD-4)."""
        resp = client.post('/products/add', data={
            'description': 'Good scan',
            'identifier_type': 'GTIN',
            'identifier_value': '012345678905',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        assert [r.value for r in rows if r.identifier_type == 'GTIN'] == \
            ['00012345678905']

    def test_the_quarantine_type_still_takes_the_value_as_scanned(
            self, client, test_storage):
        """`GTIN_UNVALIDATED` exists to hold exactly what this rule refuses, and
        it is on the same `<select>` the message points at — so the rule fires
        on the exact, case-sensitive `GTIN` only."""
        resp = client.post('/products/add', data={
            'description': 'Quarantined scan',
            'identifier_type': 'GTIN_UNVALIDATED',
            'identifier_value': '012345678900',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        assert [r.value for r in rows
                if r.identifier_type == 'GTIN_UNVALIDATED'] == ['012345678900']

    def test_a_non_gtin_type_is_not_check_digit_judged(self, client, test_storage):
        """An MPN that happens to be twelve digits is not a GTIN, and the one
        branch `add_identifier` normalizes is the one branch this judges."""
        resp = client.post('/products/add', data={
            'description': 'Digit-shaped MPN',
            'identifier_type': 'MPN',
            'identifier_value': '012345678900',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        assert [r.value for r in rows if r.identifier_type == 'MPN'] == \
            ['012345678900']

    def test_a_blank_value_is_not_a_gtin_to_judge(self, client, test_storage):
        """Gated on a non-blank VALUE like every sibling rule: `add.html`
        renders the card, and therefore both feedback blocks, only when
        `identifier_value` is set, so an error keyed beside a blank value would
        be a silent 200 that wrote nothing."""
        resp = client.post('/products/add', data={
            'description': 'No scan at all',
            'identifier_type': 'GTIN',
            'identifier_value': '',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        assert [r for r in rows if r.identifier_type == 'GTIN'] == []

    def test_an_over_long_value_still_reports_the_column_rule_alone(
            self, client, product_ids):
        """First-writer-wins, the file's convention: a 256-digit value is both
        too long for `product_identifiers.value` and not a GTIN, and the column
        it cannot be stored in is the more useful of the two things to say."""
        resp = client.post('/products/add', data={
            'description': 'Long scan',
            'identifier_type': 'GTIN',
            'identifier_value': '0' * 256,
        })

        assert resp.status_code == 200
        assert product_ids() == set()
        assert _shown_keyed_errors(resp.data.decode()) == [
            'Identifier must be 255 characters or fewer.']

    def test_the_edit_route_gains_no_identifier_validation(
            self, client, test_storage):
        """`product_edit` renders no Scanned Identifier card and writes no
        identifier, so it may not refuse a write over one (DW-13, DW-29). The
        rule lives in `_validate_product_create_form`, not the shared half."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='before')
        identifiers_before = sorted((i.identifier_type, i.value)
                                    for i in svc.get_identifiers_for_product(pid))

        resp = client.post(f'/products/edit/{pid}', data={
            'description': 'after',
            'identifier_type': 'GTIN',
            'identifier_value': '012345678900',
        })

        assert resp.status_code == 302, 'the edit was refused with no visible reason'
        assert svc.get_product(pid).description == 'after'
        # Ignored in BOTH directions: not refused, and not written either.
        assert sorted((i.identifier_type, i.value)
                      for i in svc.get_identifiers_for_product(pid)) == \
            identifiers_before


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
            self, client, product_ids, quantity):
        """Owned by `_validate_product_create_form`, which every route that can
        write a Purchase from this block goes through. Deliberately NOT shared
        with `product_edit`, which renders no quantity input and writes no
        Purchase — see `TestTheEditFormOnlyEnforcesWhatItRenders`."""
        resp = client.post('/products/add',
                           data={'description': 'Nope', 'quantity': quantity})
        assert resp.status_code == 200
        assert b'whole number greater than zero' in resp.data
        assert product_ids() == set()

    @pytest.mark.parametrize('field', ['vendor', 'vendor_sku', 'order_number'])
    def test_an_overlong_receipt_field_rerenders_with_its_own_message(
            self, client, product_ids, field):
        """Bounded against the Purchase columns, not the Product ones."""
        resp = client.post('/products/add',
                           data={'description': 'Nope', field: 'x' * 300})
        assert resp.status_code == 200
        assert b'must be 255 characters or fewer' in resp.data
        assert product_ids() == set()


@pytest.mark.unit
class TestDuplicateConfirmation:
    """FR41: creating a second Product for a scan that already matched requires
    an explicit confirmation, and it is never possible to reach the write
    without one."""

    def test_unchecked_rerenders_and_writes_nothing(self, client, test_storage,
                                                    product_ids):
        svc = CatalogService(test_storage)
        existing = svc.create_product(description='Original')

        resp = client.post('/products/add', data={
            'description': 'Would-be duplicate',
            'duplicate_of': str(existing),
        })
        assert resp.status_code == 200                 # re-render, not a redirect
        assert b'create a separate product' in resp.data
        assert product_ids() == {existing}             # nothing written

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
            self, client, test_storage, product_ids, confirm):
        """A checkbox that submits something else is not a confirmation."""
        svc = CatalogService(test_storage)
        existing = svc.create_product(description='Original')

        resp = client.post('/products/add', data={
            'description': 'Would-be duplicate',
            'duplicate_of': str(existing),
            'confirm_duplicate': confirm,
        })
        assert resp.status_code == 200
        assert product_ids() == {existing}

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
        """`_validate_product_form` is shared and keeps the gate, but the edit
        form never SUBMITS `duplicate_of`, so an ordinary edit is untouched by
        it. A hand-crafted POST that does carry the key is a different case,
        pinned by `TestTheSharedGateIsVisibleOnBothForms`."""
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

    def test_the_duplicate_link_reaches_a_gated_create_form(self, client, test_storage,
                                                            product_ids):
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
        assert product_ids() == {pid}


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
            self, client, product_ids):
        """The POST re-render reads `request.form`, not the whitelist, so the
        same value must not reach `url_for` from there either."""
        resp = client.post('/products/add',
                           data={'description': '', 'duplicate_of': 'abc'})
        assert resp.status_code == 200
        assert b'id="duplicate-warning"' not in resp.data
        assert product_ids() == set()

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
            self, client, product_ids):
        """An unselected `<select>` used to render with no `selected` option, so
        the browser picked the first declared enum member and a non-GTIN value
        was GTIN-typed and check-digit-normalized."""
        resp = client.post('/products/add', data={
            'description': 'Scanned part', 'identifier_value': 'ABC-123'})

        assert resp.status_code == 200
        assert b'Choose the type of the scanned identifier' in resp.data
        assert product_ids() == set()

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
        for a vendor-scoped type, and the scope decides the row's uniqueness
        namespace — so it comes from the identifier block's own input and from
        nothing else. The receipt block's Vendor is a different fact about a
        different table, and coupling the two would let a purchase rewrite an
        identity nothing on the form said it touched (DW-20)."""
        svc = CatalogService(test_storage)
        resp = client.post('/products/add', data={
            'description': 'Scanned part',
            'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND',
            'identifier_vendor': 'DigiKey',
            'vendor': 'Mouser',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in svc.get_identifiers_for_product(pid)
                if r.identifier_type == 'VENDOR_SKU']
        assert len(rows) == 1
        assert rows[0].vendor_scope == 'DigiKey'
        # ...and the receipt vendor still reached the only place the form said
        # it would: the Purchase.
        assert svc.get_purchases_for_product(pid)[0].vendor == 'Mouser'


@pytest.mark.unit
class TestScannedIdentifierVendorScope:
    """The create form's own vendor-scope input (DW-20).

    `vendor_scope` is not decoration: `''` is the sentinel meaning GLOBAL
    (AD-9), so a VENDOR_SKU/ASIN/FNSKU saved without one is stored in the wrong
    namespace and the NEXT vendor's identical SKU collides with it on
    `uq_product_identifiers_type_value_scope` instead of coexisting beside it.
    The form offered all three types with no control saying which vendor they
    belonged to, and passed no `vendor` at all. These tests defend the input,
    the refusal that guards it, and — in both directions — its independence from
    the First Receipt block's Vendor, which is a fact about a Purchase and must
    never decide an identifier's identity.
    """

    def test_a_vendor_scoped_type_without_a_scope_is_refused_before_the_write(
            self, client, product_ids):
        """Refused in front of `create_product` like every other identifier
        rule: `_attach_scanned_identifier` runs post-commit and is non-fatal, so
        a refusal there would be a product that exists with its identifier
        thrown away and no surface anywhere to add one back."""
        resp = client.post('/products/add', data={
            'description': 'Amazon part',
            'identifier_type': 'ASIN',
            'identifier_value': 'B00X',
        })

        assert resp.status_code == 200
        assert product_ids() == set()

        body = resp.data.decode()
        # Names the type the operator chose, not the whole vendor-scoped set:
        # they have one row in front of them, and reciting three types makes
        # them work out which one they are looking at.
        assert _shown_keyed_errors(body) == [
            'ASIN identifiers are unique per vendor, so Vendor Scope is '
            "required. It is this identifier's own vendor, not the First "
            "Receipt block's Vendor."]
        # ...rendered on the Scanned Identifier card, beside the control it is
        # about. That card renders only when `identifier_value` is set, so a
        # message keyed here is only visible when the field is too.
        assert 'id="scanned-identifier"' in body
        assert 'is-invalid' in _form_controls(body, ['identifier_vendor'])[0]

    def test_a_blank_scope_is_never_borrowed_from_the_receipt_vendor(
            self, client, product_ids):
        """The independence runs both ways. A receipt Vendor beside a blank
        scope is still a refusal — filling one field in from the other would
        scope the identifier to whoever this particular purchase came from, and
        the operator would never see that it had happened."""
        resp = client.post('/products/add', data={
            'description': 'DigiKey part',
            'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND',
            'vendor': 'DigiKey',
            'identifier_vendor': '   ',
        })

        assert resp.status_code == 200
        assert product_ids() == set()
        # Through `_shown_keyed_errors` like every sibling here, not a page-wide
        # substring: the helper exists because `in body` proves only that the
        # text is somewhere on the page, not that a field's own feedback block
        # rendered it — and asserting the whole list also proves nothing ELSE
        # was refused, i.e. that the receipt Vendor was not what stopped it.
        assert _shown_keyed_errors(resp.data.decode()) == [
            'VENDOR_SKU identifiers are unique per vendor, so Vendor Scope is '
            "required. It is this identifier's own vendor, not the First "
            "Receipt block's Vendor."]

    @pytest.mark.parametrize('identifier_type', ['ASIN', 'FNSKU', 'VENDOR_SKU'])
    def test_every_vendor_scoped_type_round_trips_its_scope(
            self, client, test_storage, identifier_type):
        """All three, not just the one the bug was reported against — the rule
        reads `VENDOR_SCOPED_IDENTIFIER_TYPES` rather than naming a type, so a
        member falling out of that frozenset is the failure to catch."""
        resp = client.post('/products/add', data={
            'description': f'{identifier_type} part',
            'identifier_type': identifier_type,
            'identifier_value': 'ABC-123',
            'identifier_vendor': 'DigiKey',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in CatalogService(test_storage).get_identifiers_for_product(pid)
                if r.identifier_type == identifier_type]
        assert [r.vendor_scope for r in rows] == ['DigiKey']

    def test_the_stored_scope_is_trimmed(self, client, test_storage):
        """Surrounding space decides namespace identity — `' DigiKey'` and
        `'DigiKey'` are two scopes, so the same SKU would coexist with itself.
        The trim happens on both sides of the call; this pins the result."""
        resp = client.post('/products/add', data={
            'description': 'Padded scope',
            'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND',
            'identifier_vendor': '  DigiKey  ',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in CatalogService(test_storage).get_identifiers_for_product(pid)
                if r.identifier_type == 'VENDOR_SKU']
        assert [r.vendor_scope for r in rows] == ['DigiKey']

    def test_a_scope_of_exactly_the_limit_is_accepted(self, client, test_storage):
        """The boundary the refusal above does not prove: 256 being refused is
        equally consistent with an off-by-one that also refuses 255, which the
        column holds."""
        scope = 'V' * 255
        resp = client.post('/products/add', data={
            'description': 'Exactly at the limit',
            'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND',
            'identifier_vendor': scope,
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in CatalogService(test_storage).get_identifiers_for_product(pid)
                if r.identifier_type == 'VENDOR_SKU']
        assert [r.vendor_scope for r in rows] == [scope]

    @pytest.mark.parametrize('identifier_type', ['', 'NOT_A_TYPE'])
    def test_an_unusable_type_leaves_the_scope_rules_unfired(
            self, client, product_ids, identifier_type):
        """First-writer-wins, and the type is the earlier writer. A blank or
        unrecognised type is already a field error of its own; adding a Vendor
        Scope demand beside it would ask the operator to fill in a box whose
        requirement nothing on the page can yet be sure of."""
        resp = client.post('/products/add', data={
            'description': 'Untyped',
            'identifier_type': identifier_type,
            'identifier_value': '296-1234-ND',
        })

        assert resp.status_code == 200
        assert product_ids() == set()
        # Across EVERY rendered message, not just the first: a Vendor Scope
        # demand emitted second is exactly the regression above, and looking at
        # `[0]` alone would let it through.
        assert not any('Vendor Scope' in m
                       for m in _shown_keyed_errors(resp.data.decode()))

    def test_the_duplicate_path_can_attach_under_a_different_scope(
            self, client, test_storage):
        """The duplicate card USED to promise the attach could not happen at
        all, which stopped being true the moment a scope existed: the same
        VENDOR_SKU under a different vendor is a different key, so it attaches.
        Both captions now state the rule instead of predicting the outcome."""
        svc = CatalogService(test_storage)
        first = client.post('/products/add', data={
            'description': 'DigiKey reel', 'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND', 'identifier_vendor': 'DigiKey'})
        first_pid = int(first.headers['Location'].rstrip('/').split('/')[-1])

        resp = client.post('/products/add', data={
            'description': 'Mouser reel', 'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND', 'identifier_vendor': 'Mouser',
            'duplicate_of': str(first_pid), 'confirm_duplicate': 'yes'})
        assert resp.status_code == 302
        second_pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in svc.get_identifiers_for_product(second_pid)
                if r.identifier_type == 'VENDOR_SKU']
        assert [r.vendor_scope for r in rows] == ['Mouser']

    def test_the_duplicate_card_no_longer_promises_a_failure_it_cannot_keep(
            self, client, test_storage):
        """The caption is read by an operator deciding whether to bother
        supplying a scope, so it must not tell them the save is doomed when a
        distinct scope makes it succeed."""
        resp = client.post('/products/add', data={
            'description': 'First', 'identifier_type': 'GTIN',
            'identifier_value': '00012345678905'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        body = client.get(f'/products/add?duplicate_of={pid}'
                          '&identifier_type=VENDOR_SKU'
                          '&identifier_value=296-1234-ND').data.decode()
        # Whitespace-normalised: the caption is wrapped in the template, so a
        # raw substring check would be asserting where the line breaks fall.
        card = ' '.join(body.split('id="scanned-identifier"')[1]
                        .split('id="first-receipt"')[0].split())
        assert 'unique across the whole catalog' not in card
        assert 'unique within its scope' in card
        assert 'Vendor Scope that product does not hold it under' in card

    def test_the_duplicate_card_offers_no_scope_escape_for_a_global_type(
            self, client, test_storage):
        """GTIN is the ONLY type any scan puts on the duplicate-create link
        (`_scan_banner_args`), and `add_identifier` discards `vendor` for it —
        so the vendor-scoped wording, rendered unconditionally, told every
        operator who can actually reach this page to fill in a box that cannot
        change the outcome. The caption branches on the chosen type instead."""
        resp = client.post('/products/add', data={
            'description': 'First', 'identifier_type': 'GTIN',
            'identifier_value': '00012345678905'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        body = client.get(f'/products/add?duplicate_of={pid}'
                          '&identifier_type=GTIN'
                          '&identifier_value=00012345678905').data.decode()
        caption = ' '.join(body.split('id="scanned-identifier"')[1]
                           .split('id="first-receipt"')[0]
                           .split('<div class="form-text">')[-1].split())
        assert 'unique across the whole catalog' in caption
        # ...and no longer sends them to the Vendor Scope box for a way out.
        assert 'Vendor Scope' not in caption

        # ...and the caption is telling the truth: a scope supplied anyway is
        # discarded, and the attach still fails.
        again = client.post('/products/add', data={
            'description': 'Second', 'identifier_type': 'GTIN',
            'identifier_value': '00012345678905',
            'identifier_vendor': 'AVendorNoOneElseHolds',
            'duplicate_of': str(pid), 'confirm_duplicate': 'yes'})
        assert again.status_code == 302
        second_pid = int(again.headers['Location'].rstrip('/').split('/')[-1])
        rows = [r for r in CatalogService(test_storage).get_identifiers_for_product(second_pid)
                if r.identifier_type == 'GTIN']
        assert rows == []

    def test_the_same_scope_still_collides(self, client, test_storage):
        """The negative half of the whole thesis. `two vendors coexist` alone is
        also satisfied by a scope that is unique per REQUEST — a product id, a
        timestamp — which would destroy uniqueness outright while leaving every
        other test in this class green. The same value under the same scope must
        still be refused."""
        svc = CatalogService(test_storage)
        pids = []
        for description in ('First', 'Second'):
            resp = client.post('/products/add', data={
                'description': description,
                'identifier_type': 'VENDOR_SKU',
                'identifier_value': '296-1234-ND',
                'identifier_vendor': 'DigiKey',
            })
            assert resp.status_code == 302
            pids.append(int(resp.headers['Location'].rstrip('/').split('/')[-1]))

        held = [[r.vendor_scope for r in svc.get_identifiers_for_product(pid)
                 if r.identifier_type == 'VENDOR_SKU'] for pid in pids]
        assert held == [['DigiKey'], []]

    @pytest.mark.parametrize('identifier_type', ['MPN', 'GTIN_UNVALIDATED'])
    def test_an_offered_global_type_still_saves_with_no_scope(
            self, client, test_storage, identifier_type):
        """The membership test read the other way round. Every offered type
        that is NOT vendor-scoped must still save with the box empty — a rule
        widened to all of them would make the box mandatory for a scan that
        cannot know a vendor, and only these types would notice."""
        resp = client.post('/products/add', data={
            'description': f'{identifier_type} part',
            'identifier_type': identifier_type,
            'identifier_value': 'RC0805-10K',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in CatalogService(test_storage).get_identifiers_for_product(pid)
                if r.identifier_type == identifier_type]
        assert [r.vendor_scope for r in rows] == ['']

    def test_a_globally_scoped_type_still_stores_an_empty_scope(
            self, client, test_storage):
        """`add_identifier` ignores `vendor` for a globally-scoped type, so a
        scope typed beside a GTIN is silently dropped rather than made a second
        form rule the service does not have. The help text documents it; this
        pins that the form did not invent one."""
        resp = client.post('/products/add', data={
            'description': 'Global part',
            'identifier_type': 'GTIN',
            'identifier_value': '00012345678905',
            'identifier_vendor': 'DigiKey',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in CatalogService(test_storage).get_identifiers_for_product(pid)
                if r.identifier_type == 'GTIN']
        assert [r.vendor_scope for r in rows] == ['']

    def test_an_over_long_scope_is_refused_before_the_write(
            self, client, product_ids):
        """`product_identifiers.vendor_scope` is VARCHAR(255). `add_identifier`
        refuses an over-long one too, but only after `create_product` has
        committed, and the attach helper turns that refusal into an advisory
        flash — so the product would exist with its identifier discarded and no
        surface anywhere to add one back."""
        resp = client.post('/products/add', data={
            'description': 'Long scope',
            'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND',
            'identifier_vendor': 'V' * 256,
        })

        assert resp.status_code == 200
        assert product_ids() == set()
        assert _shown_keyed_errors(resp.data.decode()) == [
            'Vendor Scope must be 255 characters or fewer.']

    def test_a_global_type_ignores_an_over_long_scope_rather_than_refusing_it(
            self, client, test_storage):
        """"Ignored" has to mean ignored. `add_identifier` discards `vendor`
        for a globally-scoped type before it ever measures it, so a length rule
        that fired here would refuse a save over a value nothing was going to
        store — the form contradicting the caption on its own field."""
        resp = client.post('/products/add', data={
            'description': 'Global part',
            'identifier_type': 'GTIN',
            'identifier_value': '00012345678905',
            'identifier_vendor': 'V' * 256,
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = [r for r in CatalogService(test_storage).get_identifiers_for_product(pid)
                if r.identifier_type == 'GTIN']
        assert [r.vendor_scope for r in rows] == ['']

    def test_two_vendors_identical_skus_both_persist(self, client, test_storage):
        """The bug itself, in one assertion. With every VENDOR_SKU stored
        globally scoped, the second product's identical SKU hit the uniqueness
        constraint and was dropped behind an advisory flash."""
        svc = CatalogService(test_storage)
        scopes = []
        for vendor in ('DigiKey', 'Mouser'):
            resp = client.post('/products/add', data={
                'description': f'{vendor} reel',
                'identifier_type': 'VENDOR_SKU',
                'identifier_value': '296-1234-ND',
                'identifier_vendor': vendor,
            })
            assert resp.status_code == 302
            pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
            rows = [r for r in svc.get_identifiers_for_product(pid)
                    if r.identifier_type == 'VENDOR_SKU']
            assert len(rows) == 1, f'{vendor} lost its identifier'
            scopes.append(rows[0].vendor_scope)
        assert scopes == ['DigiKey', 'Mouser']

    def test_a_blank_identifier_value_leaves_the_scope_rule_unfired(
            self, client, test_storage):
        """Gated on a non-blank VALUE like every identifier rule beside it: the
        card holding this field's message slot renders only when there is one,
        so an error raised here would be a silent 200 that wrote nothing."""
        resp = client.post('/products/add', data={
            'description': 'Hand-typed',
            'identifier_value': '   ',
            'identifier_type': 'VENDOR_SKU',
            'identifier_vendor': '',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        assert [r for r in rows if r.identifier_type == 'VENDOR_SKU'] == []

    def test_the_scope_input_renders_inside_the_identifier_card(self, client):
        """Inside the card, not beside the receipt block: the card, the name and
        the help text are three independent signals that this is not the
        Purchase's Vendor, so no later reader has to infer it."""
        resp = client.get('/products/add?identifier_value=296-1234-ND'
                          '&identifier_type=VENDOR_SKU')
        body = resp.data.decode()
        card = body.split('id="scanned-identifier"')[1].split('id="first-receipt"')[0]

        assert 'id="identifier_vendor"' in card
        assert 'name="identifier_vendor"' in card
        # Named from the route's list rather than hand-listed in Jinja, in the
        # declaration order the enum gives.
        assert 'Required for ASIN, FNSKU, VENDOR_SKU' in card
        # ...and the help text says outright which Vendor this is NOT, so the
        # distinction does not rest on the field name alone.
        assert re.search(r"not</strong>\s+the First Receipt block's Vendor", card)

    def test_the_scope_input_is_absent_without_a_scanned_identifier(self, client):
        """The hand-driven create form is unchanged — no card, and therefore no
        vendor-scope input and no rule that could fire on it."""
        resp = client.get('/products/add')
        assert resp.status_code == 200
        assert b'id="identifier_vendor"' not in resp.data
        # ...while the receipt block's own Vendor is untouched by any of this.
        assert b'id="vendor"' in resp.data

    def test_a_scope_from_the_url_prefills_and_stays_editable(self, client):
        resp = client.get('/products/add?identifier_value=296-1234-ND'
                          '&identifier_type=VENDOR_SKU&identifier_vendor=DigiKey')
        body = resp.data.decode()
        assert _input_value(body, 'identifier_vendor') == 'DigiKey'
        tag, = _form_controls(body, ['identifier_vendor'])
        assert 'readonly' not in tag
        assert 'disabled' not in tag

    def test_a_scope_survives_a_rerender_caused_by_another_field(self, client):
        """An operator who typed the scope and then tripped an UNRELATED
        refusal must not be quietly returned to a blank one — re-submitting the
        page as handed back would then store the identifier globally scoped,
        which is the exact bug this field exists to close."""
        resp = client.post('/products/add', data={
            'description': '',
            'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND',
            'identifier_vendor': 'DigiKey',
        })
        assert resp.status_code == 200
        assert _input_value(resp.data.decode(), 'identifier_vendor') == 'DigiKey'


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
class TestRecordPurchaseEndpointHoldsTheSameColumnBounds:
    """`api_record_purchase` writes the same `purchases` columns as the HTML
    form, through a `record_purchase` that validates nothing. For `unit_price`
    and the four text columns — the columns DW-12 and DW-25 name — every value
    `TestPurchaseFormRefusesWhatTheColumnCannotHold` refuses is refused here
    too, as the AD-13 envelope rather than a re-render, and every value it
    accepts is accepted here. `quantity` is NOT one of those columns: the two
    entry points still parse it differently by design (see
    `_parse_purchase_form`), so nothing here claims parity for it.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def _post(self, client, pid, body):
        return client.post(f'/api/products/{pid}/purchases', json=body)

    def _refusal(self, resp, field, fragment):
        """Assert the AD-13 refusal shape and return nothing else worth saying."""
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'invalid_field'
        assert data['error']['field'] == field
        assert fragment in data['error']['message']

    @pytest.mark.parametrize('price', ['2.34', 2.34])
    def test_a_valid_price_is_accepted_as_a_string_or_a_json_number(
            self, client, test_storage, price):
        """Both are the shipped contract, and the reason the parse goes through
        `Decimal(str(...))` rather than `Decimal(...)`."""
        from decimal import Decimal
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {'unit_price': price})
        assert resp.status_code == 201
        assert svc.get_purchases_for_product(pid)[0].unit_price == Decimal('2.34')

    def test_a_two_decimal_price_at_the_column_edge_is_accepted(
            self, client, test_storage):
        from decimal import Decimal
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {'unit_price': '99999999.99'})
        assert resp.status_code == 201
        assert svc.get_purchases_for_product(pid)[0].unit_price == \
            Decimal('99999999.99')

    @pytest.mark.parametrize('price', ['NaN', 'nan', 'sNaN', 'Infinity',
                                       '-Infinity'])
    def test_a_non_finite_price_is_refused_not_answered_201_with_a_null(
            self, client, test_storage, price):
        """DW-12: these raise neither `InvalidOperation` nor `ValueError`, so
        the unguarded parse answered 201 while storing NULL."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'unit_price': price}),
                      'unit_price', 'decimal number')
        assert svc.get_purchases_for_product(pid) == []

    def test_an_unparseable_price_is_still_refused(self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'unit_price': 'not-a-number'}),
                      'unit_price', 'decimal number')
        assert svc.get_purchases_for_product(pid) == []

    def test_a_negative_price_is_refused(self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'unit_price': '-1.00'}),
                      'unit_price', 'must not be negative')
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('price', ['100000000', '1E+30', '99999999999.99'])
    def test_a_price_past_the_column_is_refused(self, client, test_storage, price):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'unit_price': price}),
                      'unit_price', 'less than 100000000')
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('price', ['0.005', '1.234', '1e-30'])
    def test_a_price_finer_than_the_column_is_refused_rather_than_rounded(
            self, client, test_storage, price):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'unit_price': price}),
                      'unit_price', 'at most two decimal places')
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('body', [{}, {'unit_price': None},
                                      {'unit_price': ''}])
    def test_an_absent_or_empty_price_still_records_a_null(
            self, client, test_storage, body):
        """No price is not a bad price; unchanged behavior. The bodies are
        POSTed as written — `{}` in particular, since a body carrying no key at
        all is the one most likely to catch a `body.get` assumption."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, body)
        assert resp.status_code == 201
        assert svc.get_purchases_for_product(pid)[0].unit_price is None

    @pytest.mark.parametrize('field, limit, label', [
        ('vendor', 255, 'Vendor must be 255'),
        ('vendor_sku', 255, 'Vendor SKU must be 255'),
        ('order_number', 255, 'Order Number must be 255'),
        ('source_url', 1024, 'Source URL must be 1024'),
    ])
    def test_an_overlong_value_names_its_field_instead_of_failing_the_write(
            self, client, test_storage, field, limit, label):
        """DW-25: over-long values reached the column and came back as the
        generic 500 "Failed to record purchase", naming no field."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {field: 'x' * (limit + 1)})
        self._refusal(resp, field, 'characters or fewer')
        assert label in resp.get_json()['error']['message']
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('field, limit', [('vendor', 255),
                                              ('vendor_sku', 255),
                                              ('order_number', 255),
                                              ('source_url', 1024)])
    def test_a_value_exactly_at_the_limit_is_accepted(
            self, client, test_storage, field, limit):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {field: 'x' * limit})
        assert resp.status_code == 201
        assert len(svc.get_purchases_for_product(pid)) == 1

    @pytest.mark.parametrize('field, limit', [('vendor', 255),
                                              ('source_url', 1024)])
    def test_padding_is_not_counted_because_it_is_not_stored(
            self, client, test_storage, field, limit):
        """The service trims every text field before the write (`_clean`), and
        the form strips before measuring, so a padded value the column can hold
        must not be refused here — that would be a NEW disagreement between the
        two entry points, on the columns this change exists to reconcile."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {field: '  ' + 'x' * limit + '  '})
        assert resp.status_code == 201
        assert getattr(svc.get_purchases_for_product(pid)[0], field) == 'x' * limit

    def test_a_whitespace_only_price_means_no_price_as_it_does_on_the_form(
            self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {'unit_price': '   '})
        assert resp.status_code == 201
        assert svc.get_purchases_for_product(pid)[0].unit_price is None

    def test_a_json_float_carrying_binary_repr_noise_is_refused(
            self, client, test_storage):
        """`0.1 + 0.2` is `0.30000000000000004`, whose `str()` has seventeen
        significant digits. The scale rule refuses it rather than storing a
        rounded price the caller never sent: JSON numbers stay supported, but
        the caller sends the two decimal places it means."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'unit_price': 0.1 + 0.2}),
                      'unit_price', 'at most two decimal places')
        assert svc.get_purchases_for_product(pid) == []

    def test_a_non_string_value_is_not_the_length_rules_business(
            self, client, test_storage):
        """The one deliberate non-change: the rule counts characters, so a JSON
        number is left to whatever the write path already did with it rather
        than newly refused as over-long."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {'vendor': 5})
        assert resp.status_code == 201
        assert len(svc.get_purchases_for_product(pid)) == 1


# The verdict on a `unit_price`, as ONE list. The classes above spell out each
# rule and why it exists; this table exists so the two entry points cannot drift
# apart without a test failing, which two hand-copied per-route lists could not
# catch — the same reason the routes share `_purchase_unit_price`.
# `(raw value, None if it must be accepted else the message fragment)`.
_UNIT_PRICE_VERDICTS = [
    ('2.34', None),
    ('0', None),
    ('0.00', None),
    ('+2.34', None),      # `Decimal` takes a leading sign; both sides must.
    ('  2.34  ', None),   # both strip before parsing, so padding is not a price
    ('99999999.99', None),
    # Passes the `>= 100000000` ceiling as typed and quantizes PAST the column;
    # refused by the scale rule rather than the magnitude one. Pinned here
    # because the two bounds cover that gap only together.
    ('99999999.995', 'at most two decimal places'),
    ('NaN', 'decimal number'),
    ('nan', 'decimal number'),
    ('sNaN', 'decimal number'),
    ('Infinity', 'decimal number'),
    ('-Infinity', 'decimal number'),
    ('not-a-number', 'decimal number'),
    ('-1.00', 'must not be negative'),
    ('100000000', 'less than 100000000'),
    ('1E+30', 'less than 100000000'),
    ('99999999999.99', 'less than 100000000'),
    ('0.005', 'at most two decimal places'),
    ('1.234', 'at most two decimal places'),
    ('1e-30', 'at most two decimal places'),
]


@pytest.mark.unit
@pytest.mark.parametrize('price, fragment', _UNIT_PRICE_VERDICTS)
class TestBothPurchaseEntryPointsAgreeOnUnitPrice:
    """DW-12/DW-25's acceptance criterion, stated as a property: a value one
    entry point accepts the other accepts, and a value one refuses the other
    refuses with the same reason. Only the SHAPE of the refusal differs — a
    re-rendered field message versus the AD-13 envelope.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def test_the_html_form(self, client, test_storage, price, fragment):
        from decimal import Decimal
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'unit_price': price})
        if fragment is None:
            assert resp.status_code == 302
            assert svc.get_purchases_for_product(pid)[0].unit_price == \
                Decimal(price)
        else:
            assert resp.status_code == 200
            assert fragment.encode() in resp.data
            assert svc.get_purchases_for_product(pid) == []

    def test_the_json_endpoint(self, client, test_storage, price, fragment):
        from decimal import Decimal
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'unit_price': price})
        if fragment is None:
            assert resp.status_code == 201
            assert svc.get_purchases_for_product(pid)[0].unit_price == \
                Decimal(price)
        else:
            assert resp.status_code == 400
            error = resp.get_json()['error']
            assert error['code'] == 'invalid_field'
            assert error['field'] == 'unit_price'
            assert fragment in error['message']
            assert svc.get_purchases_for_product(pid) == []


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


@pytest.mark.unit
class TestTheEditFormOnlyEnforcesWhatItRenders:
    """`product_edit` may not refuse a write over a field it neither renders nor
    reads (DW-13, DW-29).

    The first-receipt block (`quantity`, `vendor`, `vendor_sku`,
    `order_number`) and the scanned-identifier card (`identifier_type`,
    `identifier_value`) exist on `add.html` alone; `product_edit` writes none of
    them and `edit.html` has no input and no `invalid-feedback` block for any of
    them. While those rules lived in the shared validator, a POST carrying one
    earned a 200 that wrote nothing and said nothing anywhere on the page.
    """

    def _make_product(self, test_storage, **kwargs):
        kwargs.setdefault('description', 'Seed product')
        return CatalogService(test_storage).create_product(**kwargs)

    @pytest.mark.parametrize('extra', [
        {'quantity': '0'},                    # the create form's whole-number rule
        {'quantity': 'abc'},
        {'vendor': 'x' * 300},                # the Purchase column bounds
        {'vendor_sku': 'x' * 300},
        {'order_number': 'x' * 300},
        {'identifier_type': 'NOT_A_TYPE', 'identifier_value': 'x' * 300},
    ])
    def test_an_add_only_field_is_ignored_rather_than_refused(
            self, client, test_storage, extra):
        pid = self._make_product(test_storage, description='before')
        svc = CatalogService(test_storage)
        # Not `== []`: `create_product` mints the product's own INTERNAL
        # identifier, so the property is that this POST added nothing to what
        # was already there. Compared by value because ProductIdentifier
        # carries no `__eq__` — two reads of the same row are not `==`.
        def _identifiers():
            return sorted((i.identifier_type, i.value)
                          for i in svc.get_identifiers_for_product(pid))

        identifiers_before = _identifiers()

        data = {'description': 'after'}
        data.update(extra)
        resp = client.post(f'/products/edit/{pid}', data=data)

        assert resp.status_code == 302, 'the edit was refused with no visible reason'
        assert resp.headers['Location'].endswith(f'/products/{pid}')
        # The one field this form does render was written; the rest are inert.
        # "Ignored" has to mean ignored in BOTH directions — scoping the rules
        # out of this route must not be mistaken for wiring the fields in, so
        # the absence of a Purchase and of a new identifier is asserted rather
        # than inferred from the redirect.
        assert svc.get_product(pid).description == 'after'
        assert svc.get_purchases_for_product(pid) == []
        assert _identifiers() == identifiers_before

    def test_no_add_only_input_appears_on_the_edit_form(self, client, test_storage):
        """The scoping fix is "stop validating them", never "start rendering
        them": those fields belong to the create form's blocks."""
        pid = self._make_product(test_storage)
        body = client.get(f'/products/edit/{pid}').data.decode()

        for name in ('quantity', 'vendor', 'vendor_sku', 'order_number',
                     'identifier_type', 'identifier_value'):
            assert f'name="{name}"' not in body

    @pytest.mark.parametrize('extra, message', [
        ({'quantity': '0'}, b'whole number greater than zero'),
        ({'vendor': 'x' * 300}, b'must be 255 characters or fewer'),
        ({'identifier_type': 'NOT_A_TYPE',
          'identifier_value': '00012345678905'}, b'Choose a valid identifier type.'),
    ])
    def test_the_same_rules_still_bite_on_the_create_form(
            self, client, product_ids, extra, message):
        """Moving them out of the shared validator must not weaken them where
        they belong — same rules, same messages, nothing created."""
        data = {'description': 'A part'}
        data.update(extra)
        resp = client.post('/products/add', data=data)

        assert resp.status_code == 200
        assert message in resp.data
        assert product_ids() == set()


@pytest.mark.unit
class TestTheSharedGateIsVisibleOnBothForms:
    """The FR41 duplicate gate stays in the SHARED validator, so `edit.html`
    needs somewhere to render an error key it has no field for.

    Scoping the gate to `product_add` would be a real hole — the write it guards
    is reachable by POSTing anywhere the validator runs — so the edit template
    grows an unkeyed fallback instead. That makes "an error renders nowhere"
    unreachable on this form for every present and future shared rule, which is
    the invariant `TestNoErrorRendersNowhere` already pins on the add side.
    """

    def test_an_unconfirmed_duplicate_is_refused_visibly_on_the_edit_form(
            self, client, test_storage):
        svc = CatalogService(test_storage)
        other = svc.create_product(description='Original')
        pid = svc.create_product(description='before')

        resp = client.post(f'/products/edit/{pid}', data={
            'description': 'after',
            'duplicate_of': str(other),
        })

        assert resp.status_code == 200
        # The gate's own message, not a generic "something went wrong".
        assert b'create a separate product' in resp.data
        assert svc.get_product(pid).description == 'before'  # nothing written

    def test_the_fallback_renders_a_key_the_form_has_no_field_for(
            self, client, test_storage, monkeypatch):
        """Structural, not `confirm_duplicate`-specific: any key the shared
        validator gains later must surface without a template change."""
        from app.main import routes

        pid = CatalogService(test_storage).create_product(description='before')
        monkeypatch.setattr(
            routes, '_validate_product_form',
            lambda form_data: {'a_field_this_form_lacks': 'Invented rule fired.'})

        resp = client.post(f'/products/edit/{pid}', data={'description': 'after'})

        assert resp.status_code == 200
        assert b'Invented rule fired.' in resp.data
        assert b'id="form-error-a_field_this_form_lacks"' in resp.data

    def test_a_keyed_error_is_not_duplicated_by_the_fallback(
            self, client, test_storage):
        """A field WITH an invalid-feedback block still renders there once —
        the fallback is for orphans only, not a second copy of every message."""
        pid = CatalogService(test_storage).create_product(description='before')

        resp = client.post(f'/products/edit/{pid}', data={'description': ''})

        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'id="form-error-description"' not in body
        # Counted over the SHOWN feedback blocks, not the whole page: the
        # description slot's hidden placeholder contains this message verbatim,
        # so `body.count(...) == 1` is true of every render of this template
        # and would have proved nothing about duplication either way.
        assert _shown_keyed_errors(body).count('Label Description is required.') == 1

    # One list, read by the test below and by the template-agreement test after
    # it, so "every keyed field is covered" is checked rather than assumed.
    KEYED_FIELD_CASES = [
        ('description', {'description': ''}, 'Label Description is required.'),
        ('manufacturer', {'manufacturer': 'x' * 300},
         'Manufacturer must be 255 characters or fewer.'),
        ('mpn', {'mpn': 'x' * 300}, 'MPN must be 255 characters or fewer.'),
        ('category_path', {'category_path': 'x' * 600},
         'Category path is too long: 600 characters (max 512).'),
        # Whole message, not a prefix: these are compared against a feedback
        # block's entire contents now, and a prefix would have let a truncated
        # or mangled message pass for a rendered one.
        ('tags', {'tags': 'x' * 100}, 'Tag is too long: 100 characters (max 64).'),
    ]

    @pytest.mark.parametrize('field, extra, message', KEYED_FIELD_CASES)
    def test_every_field_the_fallback_skips_still_has_its_own_slot(
            self, client, test_storage, field, extra, message):
        """`keyed_error_fields` is template knowledge hand-copied into a Jinja
        list, and nothing about the copy is checked by the copy.

        Delete or rename one `invalid-feedback` block below and the fallback
        goes on skipping that key, so the error it names renders NOWHERE — the
        exact silent 200 this whole block exists to make unreachable, restored
        by a one-line template edit. So every name on that list is exercised
        here from both sides: the message must appear, and it must NOT have
        come from the fallback.

        Asserted against the SHOWN feedback blocks rather than the page text,
        because `description`'s slot always renders and its placeholder holds
        the very message this row looks for — an `in body` check passed there
        whether or not the error was rendered at all."""
        pid = CatalogService(test_storage).create_product(description='before')

        data = {'description': 'after'}
        data.update(extra)
        resp = client.post(f'/products/edit/{pid}', data=data)

        assert resp.status_code == 200
        body = resp.data.decode()
        assert message in _shown_keyed_errors(body), \
            f'the {field} error rendered in no feedback block of its own'
        assert f'id="form-error-{field}"' not in body, \
            f'{field} lost its own message slot and fell through to the fallback'

    def test_the_parametrized_names_are_the_templates_own_list(self):
        """The check above only covers names someone remembered to add HERE, so
        by itself it is one hand-copy pinned by a second hand-copy: add a field
        to `keyed_error_fields` without giving it a feedback block and the
        fallback starts skipping a key that now renders nowhere, with nothing
        failing. Reading the template's list closes that direction — the two
        copies must name the same fields or this fails."""
        template = (Path(__file__).resolve().parents[2]
                    / 'app' / 'templates' / 'product' / 'edit.html').read_text()
        match = re.search(r'set keyed_error_fields = \[(.*?)\]', template, re.S)
        assert match is not None, \
            'edit.html no longer sets keyed_error_fields — the fallback changed shape'
        in_template = set(re.findall(r"'([^']+)'", match.group(1)))

        assert in_template == {case[0] for case in self.KEYED_FIELD_CASES}


@pytest.mark.unit
class TestTheEditRerenderCarriesStoredValues:
    """A failure re-render merges the SUBMITTED values over the STORED ones.

    `edit.html` renders `value="{{ form_data.get('<field>', '') }}"`, so handing
    it the raw submitted mapping made every field the client did not send render
    blank. A non-browser client that POSTs one field and then re-posts the form
    it was handed thereby cleared every optional field it never sent (DW-52) —
    the exact opposite of the partial-update rule the route applies to the
    write.
    """

    # Deliberately carries `&`, `<` and `"` — the three characters Jinja escapes
    # on the way out. A round-trip that is lossless only for alphanumerics is
    # not the property this change exists to guarantee, and every one of these
    # is ordinary typing in a manufacturer or a note.
    _MANUFACTURER = 'Fluke & Co "Test" <div>'

    def _seed(self, test_storage):
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Heat sink',
                                 manufacturer=self._MANUFACTURER,
                                 mpn='LM317', category_path='electronics',
                                 notes='bench stock')
        svc.set_product_tags(pid, ['ssr', 'rectifier'])
        return pid

    def test_a_partial_post_rerenders_the_stored_values(self, client, test_storage):
        """The matrix row: only `description` is sent, and every other control
        comes back holding what a GET would have shown."""
        pid = self._seed(test_storage)

        resp = client.post(f'/products/edit/{pid}', data={'description': ''})
        assert resp.status_code == 200
        assert b'Label Description is required.' in resp.data

        body = resp.data.decode()
        assert _input_value(body, 'manufacturer') == self._MANUFACTURER
        assert _input_value(body, 'mpn') == 'LM317'
        assert _input_value(body, 'category_path') == 'electronics'
        assert _input_value(body, 'tags') == 'rectifier, ssr'
        assert _textarea_value(body, 'notes') == 'bench stock'
        # Submitted still beats stored for the key that WAS sent.
        assert _input_value(body, 'description') == ''

    def test_an_explicit_clear_survives_the_merge(self, client, test_storage):
        """A key present-but-empty is a deliberate clear, not an omission, and
        must not be overwritten by the stored value it is clearing."""
        pid = self._seed(test_storage)

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': '', 'manufacturer': ''})
        assert resp.status_code == 200

        body = resp.data.decode()
        assert _input_value(body, 'manufacturer') == ''
        assert _input_value(body, 'mpn') == 'LM317'  # omitted, so still stored

    def test_an_explicit_tag_clear_survives_the_merge_and_then_lands(
            self, client, test_storage):
        """`tags` is the field where the merge is most dangerous, because it is
        the one whose absence is read by `_form_tags` rather than by the
        `field in form_data` loop, and because a stored value put back into the
        input would turn "clear every tag" into "keep them" on the re-post."""
        pid = self._seed(test_storage)

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': '', 'tags': ''})
        assert resp.status_code == 200
        assert _input_value(resp.data.decode(), 'tags') == ''

        repost = _rendered_edit_form(resp.data.decode())
        repost['description'] = 'Heat sink'
        assert client.post(f'/products/edit/{pid}', data=repost).status_code == 302
        assert CatalogService(test_storage).get_tags_for_product(pid) == []

    def test_reposting_the_rerendered_form_clears_nothing(self, client, test_storage):
        """The whole point of the merge: the round-trip is lossless. Post one
        field, correct the error in the page you were handed, post it back
        verbatim — and nothing you never typed is gone."""
        pid = self._seed(test_storage)

        first = client.post(f'/products/edit/{pid}', data={'description': ''})
        assert first.status_code == 200

        repost = _rendered_edit_form(first.data.decode())
        repost['description'] = 'Heat sink'
        second = client.post(f'/products/edit/{pid}', data=repost)
        assert second.status_code == 302

        svc = CatalogService(test_storage)
        product = svc.get_product(pid)
        assert (product.manufacturer, product.mpn) == (self._MANUFACTURER, 'LM317')
        assert product.category_path == 'electronics'
        assert product.notes == 'bench stock'
        assert svc.get_tags_for_product(pid) == ['rectifier', 'ssr']

    def test_a_backend_failure_rerender_shows_no_stored_value_as_blank(
            self, client, test_storage, monkeypatch):
        """`update_product` returning false re-renders the same form, so it
        needs the same merge — otherwise a transient backend failure is how the
        operator's next save wipes the fields it blanked."""
        pid = self._seed(test_storage)
        monkeypatch.setattr(CatalogService, 'update_product',
                            lambda *args, **kwargs: False)

        resp = client.post(f'/products/edit/{pid}', data={'description': 'Renamed'})
        assert resp.status_code == 200
        assert b'Failed to update product' in resp.data

        body = resp.data.decode()
        assert _input_value(body, 'manufacturer') == self._MANUFACTURER
        assert _input_value(body, 'description') == 'Renamed'

    def test_the_outer_exception_rerender_gets_the_merge_too(
            self, client, test_storage, monkeypatch):
        """The third re-render site. An unexpected exception is exactly when
        the operator is most likely to just resubmit the page they were given.
        """
        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        pid = self._seed(test_storage)
        monkeypatch.setattr(CatalogService, 'update_product', _boom)

        resp = client.post(f'/products/edit/{pid}', data={'description': 'Renamed'})
        assert resp.status_code == 200
        assert b'An error occurred while updating the product' in resp.data
        assert _input_value(resp.data.decode(), 'manufacturer') == self._MANUFACTURER

    def test_an_unreadable_baseline_degrades_instead_of_500ing(
            self, client, test_storage, monkeypatch):
        """Reading the stored values is the one service call the POST path did
        not make before the merge existed. It serves a DISPLAY concern, so it
        may not be the reason this page starts answering with an error page —
        every other failure here is a flash and a re-render. A baseline that
        cannot be read falls back to the submitted values alone: worse than the
        merge, still a form.

        And it SAYS so. The degraded page shows every omitted field blank, and
        blank is this form's own spelling of "clear this", so a re-post of the
        page as handed would wipe them. Degrading quietly would have turned a
        transient read failure into data loss on the operator's next save."""
        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        pid = self._seed(test_storage)
        monkeypatch.setattr(CatalogService, 'get_tags_for_product', _boom)

        resp = client.post(f'/products/edit/{pid}', data={'description': ''})

        assert resp.status_code == 200
        assert b'Label Description is required.' in resp.data
        # Degraded, not merged — and emphatically not a 500.
        assert _input_value(resp.data.decode(), 'manufacturer') == ''
        assert b'may not actually be empty' in resp.data

    def test_a_successful_save_never_reads_the_baseline(
            self, client, test_storage, monkeypatch):
        """The merge serves the FAILURE re-renders only, and a save that works
        is the common case. Reading the baseline eagerly spent a query on every
        edit and, worse, would have raised the degraded-baseline warning on a
        page the operator was never shown."""
        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        pid = self._seed(test_storage)
        monkeypatch.setattr(CatalogService, 'get_tags_for_product', _boom)

        resp = client.post(f'/products/edit/{pid}', data={'description': 'Renamed'})
        assert resp.status_code == 302

        monkeypatch.undo()
        detail = client.get(resp.headers['Location'])
        assert b'may not actually be empty' not in detail.data
        assert b'Product updated successfully!' in detail.data

    def test_the_merge_does_not_leak_into_the_write(self, client, test_storage):
        """Only the RENDER mapping is merged. If the merged mapping reached
        `update_product`, every stored value would arrive as a present key and
        the partial-update rule this merge exists to protect would be gone —
        which is unobservable on a successful save except by clearing a field
        the POST omits and checking it survived."""
        pid = self._seed(test_storage)

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Heat sink', 'manufacturer': ''})
        assert resp.status_code == 302

        svc = CatalogService(test_storage)
        product = svc.get_product(pid)
        assert product.manufacturer is None      # present-but-empty clears
        assert product.mpn == 'LM317'            # absent leaves alone
        assert svc.get_tags_for_product(pid) == ['rectifier', 'ssr']


@pytest.mark.unit
class TestACommittedEditWithAFailedFollowupTellsBothTruths:
    """DW-30: `update_product` and `set_product_tags` are two transactions, so a
    failure can land between them — and the row exists either way."""

    def test_the_success_is_flashed_before_the_failure(
            self, client, test_storage, monkeypatch):
        """Order is the message: the edit landed, and then one follow-up did
        not. Reversed, the page opens by telling the operator something broke
        and only afterwards that the save worked."""
        pid = CatalogService(test_storage).create_product(description='Heat sink')

        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        monkeypatch.setattr(CatalogService, 'set_product_tags', _boom)
        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Renamed', 'tags': 'ssr'})
        assert resp.status_code == 302

        monkeypatch.undo()
        body = client.get(resp.headers['Location']).data.decode()
        assert body.index('Product updated successfully!') < \
            body.lower().index('the product was saved, but its tags were not')

    def test_a_clean_edit_still_flashes_only_the_success(
            self, client, test_storage):
        """The unconditional flash must not turn into an unconditional pair."""
        pid = CatalogService(test_storage).create_product(description='Heat sink')

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Renamed', 'tags': 'ssr'})
        detail = client.get(resp.headers['Location'])
        assert b'Product updated successfully!' in detail.data
        assert b'tags were not' not in detail.data
