"""
Route/integration tests for the Product create/edit/detail pages (Story 1.3).

Uses the `client` fixture (CSRF disabled in TestConfig, so POSTs need no token).
"""

import html
import math
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from app.exceptions import ValidationError
from app.main.routes import (_purchase_unit_price, _RECEIPT_FIELDS,
                             _RECEIPT_TRIGGER_FIELDS, _record_first_receipt)
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


def _select_options(body, control_id):
    """The named `<select>`'s options, as `[(value, label, is_selected)]`.

    A `<select>` carries neither its choices nor its state the way an `<input>`
    does — the value lives on each `<option>` and the state is a bare `selected`
    attribute on one of them — so `_input_value` cannot read one at all. It
    would find no `value="…"` on the `<select>` tag and fail its own assertion,
    which is why Story 5.3's control needed this pair of helpers rather than a
    line in the tuple below.
    """
    match = re.search(
        r'<select\b[^>]*\bid="%s"[^>]*>(.*?)</select>' % re.escape(control_id),
        body, re.S)
    assert match is not None, f'no select with id="{control_id}"'
    options = []
    for tag, label in re.findall(r'(<option\b[^>]*>)(.*?)</option>',
                                 match.group(1), re.S):
        value = re.search(r'\svalue="([^"]*)"', tag)
        assert value is not None, f'an option of id="{control_id}" has no value'
        options.append((html.unescape(value.group(1)),
                        html.unescape(label.strip()),
                        re.search(r'\sselected\b', tag) is not None))
    return options


def _select_value(body, control_id):
    """The value the named `<select>` would SUBMIT.

    The selected option's value — or, when nothing is marked selected, the
    FIRST option's, because that is what a browser submits. Faithfulness there
    is the point: a template bug that marks nothing selected does not render an
    empty control, it silently submits the first choice, and a helper that
    returned None for that case would let `_rendered_edit_form` below report a
    re-post that never happened.
    """
    options = _select_options(body, control_id)
    assert options, f'the select id="{control_id}" renders no options'
    for value, _label, selected in options:
        if selected:
            return value
    return options[0][0]


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


def _checkbox_is_checked(body, control_id):
    """Whether the named checkbox rendered ticked.

    A checkbox carries its state as the bare `checked` attribute, not as a
    value, so `_input_value` cannot read one — and its SUBMITTED form is the
    other way round again: a browser omits an unticked box from the POST body
    entirely rather than sending it false. `_rendered_edit_form` below relies on
    both halves of that.
    """
    tag = _form_controls(body, [control_id])[0]
    return re.search(r'\schecked\b', tag) is not None


def _rendered_edit_form(body):
    """The edit form as a POST body: every control it rendered, with the value
    it rendered. What a client that re-posts the page it was handed would send.
    """
    data = {name: _input_value(body, name)
            for name in ('description', 'manufacturer', 'mpn', 'category_path',
                         'tags',
                         # Story 5.1. Listed here for the reason the helper
                         # exists: a client re-posting the page it was handed
                         # must round-trip these too, and `quantity_on_hand` is
                         # the one field where a rendering bug (`or ''` over a
                         # tracked 0) silently untracks the product on that
                         # re-post. Story 5.2's `reorder_threshold` has the same
                         # falsy-zero hazard and the same consequence on a
                         # re-post: a threshold of 0 rendered blank comes back
                         # as "no threshold".
                         'quantity_on_hand', 'reorder_threshold',
                         'location', 'sub_location')}
    data['notes'] = _textarea_value(body, 'notes')
    # Story 5.3, read through `_select_value` because `_input_value` cannot see
    # a `<select>`'s state. Unconditional, and that is faithful rather than
    # convenient: this control has no unticked/empty form, so a browser posts it
    # on EVERY save. Its presence in this dict is precisely what makes the
    # re-post regression below a real test — the service must decide from the
    # VALUE, not from the key, whether an assertion was made.
    data['stock_status'] = _select_value(body, 'stock_status')
    # Story 5.1's recount checkbox, submitted the way a browser submits one:
    # present only when ticked. Faithfulness matters more here than anywhere
    # else in this helper — a key sent unconditionally would make every
    # re-post of the rendered form a recount, which is precisely the behaviour
    # the re-stamp rule exists to forbid.
    if _checkbox_is_checked(body, 'quantity_recounted'):
        data['quantity_recounted'] = 'on'
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


@pytest.mark.unit
class TestTagRenamePage(object):
    """The rename-and-merge page below the browser (DW-48, FR16): the listing
    is where the counts live, so it is where the action belongs, and the form's
    preview is the confirmation."""

    def _make_product(self, test_storage, tags=None, **kwargs):
        kwargs.setdefault('description', 'Seed product')
        service = CatalogService(test_storage)
        product_id = service.create_product(**kwargs)
        if tags:
            service.set_product_tags(product_id, tags)
        return product_id

    def _row(self, body, tag):
        """The listing row for `tag` alone, so an action assertion cannot be
        satisfied by a link sitting in some other row."""
        marker = f'<code>{tag}</code>'.encode()
        assert marker in body, f'no listing row for {tag}'
        start = body.index(marker)
        return body[start:body.index(b'</tr>', start)]

    def test_every_listing_row_offers_both_actions(self, client, test_storage):
        """Both, on every row: there is no non-canonical carve-out here the way
        there is on the categories page. `product_tags` shipped empty and every
        writer of it normalizes before writing — `set_product_tags`, and the
        rename this very link leads to — so a stored tag IS canonical whichever
        one wrote it."""
        self._make_product(test_storage, tags=['ssr'])
        self._make_product(test_storage, tags=['heat sink'])

        resp = client.get('/products/tags')
        assert resp.status_code == 200
        for tag, query in (('ssr', b'tag=ssr'), ('heat sink', b'tag=heat+sink')):
            row = self._row(resp.data, tag)
            assert b'View products' in row
            assert b'Rename' in row
            assert b'/products/tags/rename?' + query in row
            assert b'/products/tags/filter?' + query in row

    def test_the_form_previews_the_tag_and_its_count(self, client, test_storage):
        self._make_product(test_storage, tags=['ssr'])
        self._make_product(test_storage, tags=['ssr'])
        self._make_product(test_storage, tags=['rectifier'])

        resp = client.get('/products/tags/rename?tag=ssr')
        assert resp.status_code == 200
        assert b'id="rename-source">ssr<' in resp.data
        # Two products carry ssr; the third tag is none of this page's business.
        assert b'id="rename-total">2<' in resp.data
        # The merge rule is stated up front, because the GET cannot know the
        # destination and so cannot enumerate what a merge would do.
        assert b'the two are merged' in resp.data
        # The destination input starts empty — read off the input's OWN tag, so
        # a page-wide `value=""` in some other element cannot satisfy it.
        start = resp.data.index(b'id="new_tag"')
        assert b'value=""' in resp.data[start:resp.data.index(b'>', start)]
        # Nothing was refused, so no field is marked invalid.
        assert b'is-invalid' not in resp.data

    def test_the_form_normalizes_its_argument(self, client, test_storage):
        """`?tag=` goes through the same util the product form does, so a
        padded or upper-cased link still resolves onto the stored tag."""
        self._make_product(test_storage, tags=['ssr'])

        resp = client.get('/products/tags/rename?tag=++SSR+')
        assert resp.status_code == 200
        assert b'id="rename-source">ssr<' in resp.data

    def test_the_form_with_an_unused_tag_redirects(self, client, test_storage):
        self._make_product(test_storage, tags=['ssr'])

        resp = client.get('/products/tags/rename?tag=nosuchtag',
                          follow_redirects=True)
        assert resp.status_code == 200
        assert b'No products carry tag &#34;nosuchtag&#34;' in resp.data
        # No form was rendered, so nothing could be submitted against it.
        assert b'id="rename-source"' not in resp.data

    @pytest.mark.parametrize('query', [
        'a,b',              # the separator: no stored tag can contain it
        'x' * 200,          # past the 64-character limit
    ])
    def test_the_form_names_an_unusable_tag_as_unusable(self, client,
                                                        test_storage, query):
        """A value no tag could ever BE is a different problem from a tag
        nothing happens to carry.

        Both resolve to zero products, but "No products carry tag "a,b"" sends
        someone who followed a truncated or hand-edited link looking for a tag
        that disappeared, when the link is what mangled it. The sibling
        `tag_filter` route draws this distinction for the same input class, in
        the same words.
        """
        self._make_product(test_storage, tags=['ssr'])

        resp = client.get(f'/products/tags/rename?tag={query}',
                          follow_redirects=True)
        assert resp.status_code == 200
        assert b'not a usable tag' in resp.data
        assert b'No products carry tag' not in resp.data
        assert b'id="rename-source"' not in resp.data

    @pytest.mark.parametrize('query', [
        '',                     # no ?tag= at all
        '?tag=',                # present but blank
        '?tag=+++',             # whitespace only
    ])
    def test_the_form_with_no_tag_says_so(self, client, test_storage, query):
        """`No products carry tag ""` would name the wrong problem: nothing was
        picked."""
        self._make_product(test_storage, tags=['ssr'])

        resp = client.get(f'/products/tags/rename{query}',
                          follow_redirects=True)
        assert resp.status_code == 200
        assert b'Pick a tag to rename' in resp.data

    def test_post_renames_and_reports_what_happened(self, client, test_storage):
        first = self._make_product(test_storage, tags=['ssr'])
        second = self._make_product(test_storage, tags=['ssr'])

        resp = client.post('/products/tags/rename',
                           data={'old_tag': 'ssr', 'new_tag': ' Relay '})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/products/tags')

        service = CatalogService(test_storage)
        assert service.get_tags_for_product(first) == ['relay']
        assert service.get_tags_for_product(second) == ['relay']

        # The flash names both CANONICAL forms and the count.
        listing = client.get(resp.headers['Location'])
        assert b'Renamed tag &#34;ssr&#34; to &#34;relay&#34;' in listing.data
        assert b'2 product(s) updated' in listing.data
        # Nothing merged, so the page does not claim anything did.
        assert b'merged into it' not in listing.data

    def test_post_onto_an_existing_tag_merges_and_says_so(self, client,
                                                          test_storage):
        """The merge is reported SEPARATELY: a merged product ends up with one
        new-tag row where it carried two tags, so a single "N updated" would
        overstate what the listing then shows against the destination."""
        moved = self._make_product(test_storage, tags=['ssr'])
        merged = self._make_product(test_storage, tags=['ssr', 'relay'])

        resp = client.post('/products/tags/rename',
                           data={'old_tag': 'ssr', 'new_tag': 'relay'})
        assert resp.status_code == 302

        service = CatalogService(test_storage)
        assert service.get_tags_for_product(moved) == ['relay']
        # One relay, and no product lost an unrelated tag.
        assert service.get_tags_for_product(merged) == ['relay']

        listing = client.get(resp.headers['Location'])
        assert b'1 product(s) updated' in listing.data
        assert b'1 product(s) already carried &#34;relay&#34;' in listing.data
        # And the vocabulary followed: only the destination is left.
        assert b'<code>ssr</code>' not in listing.data
        assert b'<code>relay</code>' in listing.data

    def test_a_pure_merge_does_not_report_zero_updated(self, client,
                                                       test_storage):
        """When EVERY carrying product already holds the destination, nothing
        was rewritten — and the rename sentence is wrong twice over.

        It would lead with "0 product(s) updated" and then be contradicted by a
        second sentence reporting products that plainly did change. The whole
        operation was a merge, so it is described as one.
        """
        first = self._make_product(test_storage, tags=['ssr', 'relay'])
        second = self._make_product(test_storage, tags=['ssr', 'relay'])

        resp = client.post('/products/tags/rename',
                           data={'old_tag': 'ssr', 'new_tag': 'relay'})
        assert resp.status_code == 302

        service = CatalogService(test_storage)
        assert service.get_tags_for_product(first) == ['relay']
        assert service.get_tags_for_product(second) == ['relay']

        listing = client.get(resp.headers['Location'])
        assert b'Merged tag &#34;ssr&#34; into &#34;relay&#34;' in listing.data
        assert b'2 product(s)' in listing.data
        # Neither the zero nor the sentence that contradicts it.
        assert b'0 product(s) updated' not in listing.data
        assert b'Renamed tag' not in listing.data

    def test_post_on_a_refusal_rerenders_and_changes_nothing(self, client,
                                                             test_storage):
        pid = self._make_product(test_storage, tags=['ssr'])

        resp = client.post('/products/tags/rename',
                           data={'old_tag': 'ssr', 'new_tag': ' SSR '})
        assert resp.status_code == 200  # re-rendered form, not a redirect
        assert b'is already this tag' in resp.data
        # The typed destination is retained, exactly as submitted.
        assert _input_value(resp.data.decode(), 'new_tag') == ' SSR '
        assert CatalogService(test_storage).get_tags_for_product(pid) == ['ssr']

    @pytest.mark.parametrize('old_tag, expected', [
        ('nosuchtag', b'No products carry tag'),   # carried by no product
        ('', b'Select a tag to rename'),           # blank
        ('a,b', b'separator between tags'),        # unusable: cannot be a tag
        ('x' * 200, b'too long'),                  # unusable: over-length
    ])
    def test_a_refused_source_goes_back_to_the_listing(self, client,
                                                       test_storage, old_tag,
                                                       expected):
        """A refusal naming the SOURCE must not re-render the form.

        `old_tag` is a HIDDEN input, so the re-rendered page would offer
        nothing to correct: submitting it again reproduces the identical
        refusal forever and the only way off the page is Cancel. Every one of
        these is a property of a value the form does not let the operator
        touch, so it goes back to the listing with the reason — the same answer
        the GET guard already gives for the same three inputs.
        """
        pid = self._make_product(test_storage, tags=['ssr'])

        resp = client.post('/products/tags/rename',
                           data={'old_tag': old_tag, 'new_tag': 'relay'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/products/tags')

        listing = client.get(resp.headers['Location'])
        assert expected in listing.data
        # No form came back, so there is no dead end to resubmit — and the
        # page cannot state the problem a second time under "Products
        # affected" either.
        assert b'id="rename-source"' not in listing.data
        assert b'No products carry this tag' not in listing.data
        assert CatalogService(test_storage).get_tags_for_product(pid) == ['ssr']

    def test_a_refused_destination_marks_that_field(self, client,
                                                    test_storage):
        """The other half: a destination refusal IS actionable, so the form
        comes back with the field the service named painted invalid."""
        self._make_product(test_storage, tags=['ssr'])

        resp = client.post('/products/tags/rename',
                           data={'old_tag': 'ssr', 'new_tag': 'a,b'})
        assert resp.status_code == 200
        assert b'is-invalid' in resp.data
        assert b'id="new_tag-error"' in resp.data
        # The REASON has to be reachable from the input, not just a pointer to
        # it: the feedback slot deliberately does not restate the message, so
        # the alert carrying it is named first in `aria-describedby` — without
        # that, a screen reader on the invalid field announces "see the message
        # at the top of the page" and nothing else.
        assert b'aria-describedby="rename-error new_tag-error"' in resp.data
        assert b'id="rename-error"' in resp.data

    def test_a_retryable_refusal_does_not_paint_the_destination_invalid(
            self, client, test_storage, monkeypatch):
        """The concurrent-writer race is refused on `new_tag`, but the typed
        destination was never the problem.

        The identical submission succeeds once the racing transaction is done,
        so marking the input would render the race identically to a permanent
        collation collision and tell the operator to change a value that is
        fine. The field alone cannot tell the two apart, which is why the
        service marks the race `retryable` — and why this route consumes it,
        the way `_apply_product_tags` already does.
        """
        self._make_product(test_storage, tags=['ssr'])

        def _race(*args, **kwargs):
            error = ValidationError(
                "Another change added 'relay' to one of these products at the "
                'same time, so nothing was renamed.',
                field='new_tag', value='relay')
            error.retryable = True
            raise error

        monkeypatch.setattr(CatalogService, 'rename_tag', _race)

        resp = client.post('/products/tags/rename',
                           data={'old_tag': 'ssr', 'new_tag': 'relay'})
        assert resp.status_code == 200
        # The reason is stated, and the typed value is kept for the retry.
        assert b'at the same time' in resp.data
        assert _input_value(resp.data.decode(), 'new_tag') == 'relay'
        # ...but nothing is marked wrong, because nothing is.
        assert b'is-invalid' not in resp.data
        assert b'id="new_tag-error"' not in resp.data

    def test_a_rejection_is_reported_exactly_once(self, client, test_storage):
        """One rejection is one problem: printing the same sentence in the
        alert AND under the input reads as two."""
        self._make_product(test_storage, tags=['ssr'])

        resp = client.post('/products/tags/rename',
                           data={'old_tag': 'ssr', 'new_tag': 'ssr'})
        assert resp.status_code == 200
        assert resp.data.count(b'is already this tag') == 1
        # The field is still marked, and still has something to describe it.
        assert b'is-invalid' in resp.data
        assert b'id="new_tag-error"' in resp.data

    def test_post_reports_a_backend_failure_without_a_second_error(
            self, client, test_storage, monkeypatch):
        """The generic failure branch also re-runs the preview, which would
        raise again on a dead backend — the operator must still get a page,
        and must not be told something the page could not establish."""
        self._make_product(test_storage, tags=['ssr'])

        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        monkeypatch.setattr(CatalogService, 'rename_tag', _boom)
        monkeypatch.setattr(CatalogService, 'list_tags', _boom)

        resp = client.post('/products/tags/rename',
                           data={'old_tag': 'ssr', 'new_tag': 'relay'})
        assert resp.status_code == 200
        assert b'An error occurred while renaming the tag' in resp.data
        # "No products carry this tag" / "Products affected: 0" beside a
        # backend error reads as if the operator's tag had just been emptied.
        assert b'No products carry this tag' not in resp.data
        assert b'id="rename-total">0<' not in resp.data
        assert b'id="preview-unavailable"' in resp.data

    def test_the_destination_input_is_not_capped(self, client, test_storage):
        """The 64-character limit is on the NORMALIZED tag, and normalization
        trims and collapses whitespace — so a cap on what is typed would refuse
        padding the server would have thrown away. The server is the only
        enforcer."""
        self._make_product(test_storage, tags=['ssr'])

        resp = client.get('/products/tags/rename?tag=ssr')
        new_tag_tag, = _form_controls(resp.data.decode(), ['new_tag'])
        assert 'maxlength' not in new_tag_tag
        # And no autocomplete either: an existing destination is LEGAL here, so
        # offering the vocabulary would invite an accidental merge.
        assert 'autocomplete="off"' in new_tag_tag


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
class TestAPrefilledFormIsSavedBack:
    """The round trip `TestProductAddPrefill` above stops one step short of:
    GET the form the way a scan opens it, then POST back exactly what the
    operator would have — the pre-filled values untouched plus the one field
    they had to type.

    DW-27 lived in that gap. Every test above either GETs a pre-filled form and
    never submits it, or POSTs a form built by hand; nothing submitted a
    SCAN-shaped one, so nothing saw that a part-number-only ECIA label
    (`1P`+`P`, no `Q`, no `K`) put its `P` record into `vendor_sku` and thereby
    recorded a Purchase the operator never entered.

    The query string used is the one a scan of that envelope produces,
    verbatim: `?mpn=ABC-123&vendor_sku=XYZ-999`. Its producer is
    `POST /api/scan` -> `_scan_destination`, which is where to look if this
    literal ever needs re-deriving.
    """

    PREFILL = '/products/add?mpn=ABC-123&vendor_sku=XYZ-999'

    def _prefilled_form_values(self, client):
        """GET the scan-routed form and return what its inputs would submit.

        The values are READ BACK OUT of the rendered page rather than restated
        as literals, which is the whole point of going through the GET: a
        pre-fill that arrived double-escaped, truncated or under another name
        would then be what the POST carries, and the round trip would fail here
        instead of passing on values the browser would never have sent.

        The WHOLE receipt block is read and returned, blanks included, because a
        browser submits every control it renders — and because reading only the
        populated ones would hollow out the test below. That test asserts an
        ABSENCE of Purchases; a helper that neither read nor posted `quantity`
        would go on asserting an empty history even if a later pre-fill change
        armed that field, passing over precisely the regression it exists to
        catch. The equality below is what fails instead, and it is the unit-test
        counterpart of the `#quantity`/`#order_number` emptiness the e2e checks.
        """
        resp = client.get(self.PREFILL)
        assert resp.status_code == 200
        body = resp.data.decode()
        values = {name: _input_value(body, name)
                  for name in ('mpn',) + _RECEIPT_FIELDS}
        assert values == {'mpn': 'ABC-123', 'vendor_sku': 'XYZ-999',
                          'quantity': '', 'order_number': '',
                          'vendor': '', 'unit_price': ''}
        return values

    def test_a_scanned_part_number_saved_with_a_description_records_no_purchase(
            self, client, test_storage):
        """The DW-27 repro. The operator scanned to CATALOGUE a part, not to
        receive one: the only non-blank receipt field is the vendor SKU the scan
        supplied, so the Product exists and its FR20/FR21 history is empty."""
        data = self._prefilled_form_values(client)
        data['description'] = 'Scanned part'

        resp = client.post('/products/add', data=data)
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        svc = CatalogService(test_storage)
        assert svc.get_product(pid) is not None
        assert svc.get_purchases_for_product(pid) == []

    def test_the_same_form_with_a_typed_quantity_records_one_purchase(
            self, client, test_storage):
        """...and the receiving case still works, carrying the scanned SKU with
        it. This is why the narrowing is a change to the TRIGGER and not to the
        read set: the vendor SKU nobody typed is still worth storing once
        something says a shipment actually arrived."""
        data = self._prefilled_form_values(client)
        data['description'] = 'Scanned part'
        data['quantity'] = '42'

        resp = client.post('/products/add', data=data)
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        purchases = CatalogService(test_storage).get_purchases_for_product(pid)
        assert len(purchases) == 1
        assert purchases[0].quantity == 42
        assert purchases[0].vendor_sku == 'XYZ-999'


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

    Reachable only by hand: `classify()` types a value `GTIN` only once
    `normalize_gtin` has accepted it, so no scan can pre-fill a value this
    refuses. The gate is that whole acceptance, not the check digit alone —
    the all-zero row below is refused by a rule mod-10 would have passed.
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
        # The wedge no-read, hand-entered. It passes mod-10, so only the util's
        # all-zero rule keeps it out — and the route inherits that too, which is
        # the point: this row exists so the write-path consequence is pinned
        # rather than left a silent side effect of a change to gtin.py.
        ('00000000', "GTIN must not be all zeros: '00000000'."),
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

    def test_the_quarantine_type_also_takes_the_wedge_no_read(
            self, client, test_storage):
        """The all-zero refusal's message points at the same `<select>`, so the
        escape hatch has to actually hold the value it was offered for."""
        resp = client.post('/products/add', data={
            'description': 'Quarantined no-read',
            'identifier_type': 'GTIN_UNVALIDATED',
            'identifier_value': '00000000',
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        rows = CatalogService(test_storage).get_identifiers_for_product(pid)
        assert [r.value for r in rows
                if r.identifier_type == 'GTIN_UNVALIDATED'] == ['00000000']

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


# DW-22: the prices `_purchase_unit_price` refuses, with the message it gives
# for each. Shared by the create form's own refusal test and by the parity class
# below, so the two surfaces are asked about the SAME values — a list restated
# per surface could only drift, which is the divergence sharing the helper
# removed in the first place.
#
# It is a SUPERSET of every value the two pre-existing per-surface classes ask
# about in isolation — `TestPurchaseFormRefusesWhatTheColumnCannotHold` and
# `TestRecordPurchaseEndpointHoldsTheSameColumnBounds` — so the parity class
# below cannot pass on a narrower set than either surface is held to alone.
# Keep it that way when either of those lists grows.
_UNSTORABLE_PRICES = [
    ('abc', 'Unit Price must be a decimal number.'),
    ('1,25', 'Unit Price must be a decimal number.'),
    ('$1.25', 'Unit Price must be a decimal number.'),
    # Parseable but non-finite: the same refusal, because an unchecked parse
    # would report success and store NULL. `-Infinity` is refused as "not a
    # number" rather than as negative — `is_finite()` is checked first — so it
    # also pins that ordering. `nan` is here beside `NaN` because `Decimal` is
    # case-insensitive about it and both older lists ask about the lowercase
    # spelling.
    ('NaN', 'Unit Price must be a decimal number.'),
    ('nan', 'Unit Price must be a decimal number.'),
    ('sNaN', 'Unit Price must be a decimal number.'),
    ('Infinity', 'Unit Price must be a decimal number.'),
    ('-Infinity', 'Unit Price must be a decimal number.'),
    ('-1.00', 'Unit Price must not be negative.'),
    # `-0` is ACCEPTED (it is not negative) and stored as `Decimal('0.00')`;
    # this is the nearest value that is negative, so it pins that the sign is
    # dropped from a zero and nowhere else.
    ('-0.001', 'Unit Price must not be negative.'),
    ('1.234', 'Unit Price must have at most two decimal places.'),
    ('0.005', 'Unit Price must have at most two decimal places.'),
    ('1e-30', 'Unit Price must have at most two decimal places.'),
    # Past the eight digits `Numeric(10, 2)` holds. `99999999.995` is caught by
    # the SCALE rule, not the ceiling — it is below 100000000 as typed.
    ('100000000', 'Unit Price must be less than 100000000.'),
    ('99999999999.99', 'Unit Price must be less than 100000000.'),
    ('1E+30', 'Unit Price must be less than 100000000.'),
    ('99999999.995', 'Unit Price must have at most two decimal places.'),
]


@pytest.mark.unit
class TestFirstReceiptOnCreate:
    """The create form's optional first receipt (FR39)."""

    def _created_id(self, resp):
        return int(resp.headers['Location'].rstrip('/').split('/')[-1])

    def test_the_trigger_fields_record_one_purchase(self, client, test_storage):
        """Named for the trigger rather than for "a receipt field": since DW-27
        three of the five record nothing on their own, and only these two do."""
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

    def test_all_five_receipt_fields_are_carried(self, client, test_storage):
        resp = client.post('/products/add', data={
            'description': 'Received part',
            'quantity': '2', 'order_number': 'PO-2',
            'vendor': 'DigiKey', 'vendor_sku': '296-1234-ND',
            'unit_price': '1.25',
        })
        pid = self._created_id(resp)
        purchase = CatalogService(test_storage).get_purchases_for_product(pid)[0]
        assert (purchase.vendor, purchase.vendor_sku) == ('DigiKey', '296-1234-ND')
        assert purchase.quantity == 2
        # DW-22: the whole point — the arrival is priced by the create form, so
        # no second Purchase is needed and FR20/FR21's history stays one row.
        assert purchase.unit_price == Decimal('1.25')

    def test_no_receipt_field_records_nothing(self, client, test_storage):
        """The Story 1.3 create path is untouched: blank throughout writes no
        Purchase and costs no transaction."""
        resp = client.post('/products/add', data={
            'description': 'Just a product',
            'quantity': '', 'order_number': '', 'vendor': '', 'vendor_sku': '',
            'unit_price': '',
        })
        pid = self._created_id(resp)
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []

    def test_an_order_number_alone_records_one_purchase(self, client, test_storage):
        """The other half of the DW-27 trigger. An order number with nothing
        beside it is still a receipt — it names a shipment — so it records the
        one Purchase, with every other column NULL."""
        resp = client.post('/products/add', data={
            'description': 'Ordered part',
            'order_number': 'PO-1',
            'quantity': '', 'vendor': '', 'vendor_sku': '', 'unit_price': '',
        })
        assert resp.status_code == 302
        pid = self._created_id(resp)

        purchases = CatalogService(test_storage).get_purchases_for_product(pid)
        assert len(purchases) == 1
        assert purchases[0].order_number == 'PO-1'
        # Every other column NULL, asserted rather than implied: a partial
        # receipt must not acquire a default the operator never supplied. The
        # price-alone test this replaced carried the same guard.
        assert purchases[0].quantity is None
        assert purchases[0].vendor is None
        assert purchases[0].unit_price is None

    @pytest.mark.parametrize('field, value', [
        ('unit_price', '0.50'),
        ('vendor', 'DigiKey'),
        ('vendor_sku', 'XYZ-999'),
    ])
    def test_a_non_trigger_field_alone_records_nothing(
            self, client, test_storage, field, value):
        """DW-27: these three are READ when a receipt is triggered and are not
        triggers themselves, so each one alone creates the Product and no
        Purchase at all.

        `vendor_sku` is the case the bug was filed over — a distributor scan
        pre-fills it from the label's `P` record, so triggering on it booked a
        receipt dated today that the operator never entered. `vendor` is out for
        a different reason — nothing pre-fills it, but naming who sells the part
        is not saying a shipment came — and a lone price (DW-22's trigger,
        removed here) is likewise a fact about the product.

        Deliberately NOT an error: a scan fills `vendor_sku` in, so refusing the
        shape would hand the operator a message about a field they never typed.
        The value is dropped and the block's help text is what says so.
        """
        resp = client.post('/products/add', data={
            'description': 'Not a receipt',
            'quantity': '', 'order_number': '', 'vendor': '', 'vendor_sku': '',
            'unit_price': '',
            field: value,
        })
        assert resp.status_code == 302
        pid = self._created_id(resp)
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []

    def test_all_three_non_triggers_together_still_record_nothing(
            self, client, test_storage):
        """The shape the parametrize above cannot reach, and the one the manual
        promises about in as many words: "no matter what the other three hold".

        Equivalent to any one of them alone under today's `any()`, which is the
        reason to pin it separately — the promise the documentation makes is
        about the COMBINATION, so a future guard that special-cased "a full
        vendor/price/SKU set surely means a receipt" would falsify the manual
        while every single-field test above stayed green. It is also the
        realistic forgetting: who sold it, what it cost and their part number
        all typed, and no quantity. Dropped silently rather than refused; the
        silence itself is on the ledger as DW-194.
        """
        resp = client.post('/products/add', data={
            'description': 'Not a receipt either',
            'vendor': 'DigiKey', 'unit_price': '12.50',
            'vendor_sku': '296-1234-ND',
            'quantity': '', 'order_number': '',
        })
        assert resp.status_code == 302
        pid = self._created_id(resp)
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []

    def test_the_trigger_is_a_subset_of_what_is_read(self):
        """DW-27 split one tuple into two, and containment is the cheap half of
        keeping the split safe: `_record_first_receipt` subscripts a dict built
        from the READ set, so a name that triggers without being read raises
        `KeyError` on every create POST — caught by `product_add` into "An error
        occurred while creating the product" over a Product that has already
        committed, which is the save-looks-failed resubmit FR41 exists to
        prevent. This assertion is what makes that a red test rather than a
        traceback an operator finds.

        It is only the cheap half. `_record_first_receipt` consumes the read set
        through hardcoded keys rather than by iterating it, so membership here
        does NOT prove a given name is passed to `record_purchase` — what proves
        that, per field, is the behavioural tests above and in
        `test_all_five_receipt_fields_are_carried`. Do not read this assertion
        as covering more than it says.

        The exact contents are pinned beside it so narrowing or widening the
        trigger stays a decision someone makes rather than a line someone slips
        in; `unit_price` in particular was a trigger for one day (DW-22) and is
        deliberately not one now.
        """
        assert set(_RECEIPT_TRIGGER_FIELDS) <= set(_RECEIPT_FIELDS)
        assert _RECEIPT_TRIGGER_FIELDS == ('quantity', 'order_number')

    @pytest.mark.parametrize('blank', ['', '   '])
    def test_a_blank_price_beside_a_trigger_is_not_an_error(
            self, client, test_storage, blank):
        """A blank stores NULL, exactly as it does on `purchase_add`. Whitespace
        is a blank too — both sites `.strip()`, so a stray space is neither a
        refusal nor a value, and the Purchase is the one the quantity asked for.

        The quantity is what changed here, not the assertion: DW-27 took the
        trigger away from the price and from the vendor beside it, so this needs
        a real trigger to still be about the price at all."""
        resp = client.post('/products/add', data={
            'description': 'Unpriced part',
            'quantity': '3', 'vendor': 'DigiKey', 'unit_price': blank,
        })
        assert resp.status_code == 302
        pid = self._created_id(resp)

        purchase = CatalogService(test_storage).get_purchases_for_product(pid)[0]
        assert purchase.unit_price is None
        assert purchase.vendor == 'DigiKey'

    @pytest.mark.parametrize('field', ['unit_price', 'quantity', 'order_number'])
    def test_whitespace_alone_is_not_a_trigger(self, client, test_storage, field):
        """A space typed into one field and nothing else is not a receipt, so
        the Story 1.3 path still costs no Purchase. Covered on BOTH triggers as
        well as on the price because the two kinds now differ: whitespace in a
        trigger field is the one place the `.strip()` is what stands between a
        blank form and a spurious Purchase, so neither trigger may be the one
        that goes untested."""
        resp = client.post('/products/add', data={
            'description': 'Just a product', field: '   ',
        })
        assert resp.status_code == 302
        pid = self._created_id(resp)
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []

    def test_the_price_input_renders_inside_the_first_receipt_card(self, client):
        """On GET, not merely on a re-render: the field has to be OFFERED, and
        offered in the block whose help text describes it. Sliced on the card's
        own id rather than searched page-wide, because an input with the right
        name somewhere else on the form would satisfy every other assertion here
        while putting the price outside the receipt it prices."""
        body = client.get('/products/add').data.decode()
        # Bounded at the bottom by the card's own help text — the last thing
        # inside it — so the slice is the block's controls and nothing after it.
        # Both markers are asserted first: splitting on a string the page no
        # longer contains would otherwise fail with a bare `IndexError`, or
        # silently widen the slice to the whole rest of the page.
        assert 'id="first-receipt"' in body
        assert 'A Quantity or an Order Number records one purchase' in body
        card = body.split('id="first-receipt"')[1] \
                   .split('A Quantity or an Order Number records one purchase')[0]

        control, = _form_controls(card, ['unit_price'])
        assert 'name="unit_price"' in control
        assert 'readonly' not in control and 'disabled' not in control
        # Against the slice, not the page: the whole point of slicing is that a
        # same-named control outside the card must not satisfy these.
        assert _input_value(card, 'unit_price') == ''

    def test_a_url_borne_price_does_not_prefill_the_block(self, client):
        """`unit_price` is deliberately absent from `_PRODUCT_PREFILL_ARGS`:
        nothing in the app emits a price into a query string, so the whitelist
        does not widen for it. Pinned so adding it stays a decision someone
        makes rather than a line someone slips in — the sibling receipt fields
        DO pre-fill, which is exactly what makes the omission easy to misread as
        an oversight."""
        body = client.get('/products/add?unit_price=1.25&quantity=3').data.decode()

        assert _input_value(body, 'quantity') == '3'
        assert _input_value(body, 'unit_price') == ''

    @pytest.mark.parametrize('price, message', _UNSTORABLE_PRICES)
    def test_an_unstorable_price_rerenders_and_writes_nothing(
            self, client, product_ids, price, message):
        """Judged before `create_product` commits, and with
        `_purchase_unit_price`'s own message — the same helper `purchase_add`
        and `api_record_purchase` apply, so all three agree about this column.

        Asserted through `_shown_keyed_errors` rather than page-wide, because
        the message has to reach the operator BESIDE the box they typed in: a
        rule keyed on a name the template gives no `invalid-feedback` slot
        renders nowhere at all, and a page-wide substring cannot tell the two
        apart. Whole-list equality also proves nothing ELSE was refused."""
        resp = client.post('/products/add',
                           data={'description': 'Nope', 'unit_price': price})
        assert resp.status_code == 200
        body = resp.data.decode()
        assert _shown_keyed_errors(body) == [message]
        assert 'is-invalid' in _form_controls(body, ['unit_price'])[0]
        assert product_ids() == set()

    def test_the_boundary_price_the_column_holds_is_stored(
            self, client, test_storage):
        """The quantity is the DW-27 trigger and nothing more: without one the
        price would now be dropped rather than stored, so the boundary this test
        is about could not be asserted at all."""
        resp = client.post('/products/add', data={
            'description': 'Expensive part', 'quantity': '1',
            'unit_price': '99999999.99',
        })
        assert resp.status_code == 302
        pid = self._created_id(resp)

        purchase = CatalogService(test_storage).get_purchases_for_product(pid)[0]
        assert purchase.unit_price == Decimal('99999999.99')

    def test_a_refused_price_is_still_in_the_input_on_the_rerender(
            self, client, product_ids):
        """The typed value round-trips through `form_data` like every sibling
        field, so the operator corrects a price rather than retyping it."""
        resp = client.post('/products/add',
                           data={'description': '', 'unit_price': '1.234'})
        assert resp.status_code == 200
        assert product_ids() == set()
        control, = _form_controls(resp.data.decode(), ['unit_price'])
        assert 'value="1.234"' in control

    def test_a_good_price_survives_a_bounce_on_another_field(
            self, client, product_ids):
        """The commoner half of the round-trip, and the one that costs the
        operator something: the price was fine and the form came back for a
        DIFFERENT reason. The test above only proves a REFUSED price is
        re-rendered — a `form_data` lookup dropped from the price input alone
        would still pass it, because that input carries `is-invalid` on exactly
        the submissions it covers. Here the price is the one field with nothing
        wrong with it, so losing it is pure retyping."""
        resp = client.post('/products/add',
                           data={'description': '', 'unit_price': '1.25'})
        assert resp.status_code == 200
        assert product_ids() == set()
        body = resp.data.decode()
        # The price itself was not what was refused.
        assert _shown_keyed_errors(body) == ['Label Description is required.']
        assert _input_value(body, 'unit_price') == '1.25'

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
class TestTheFirstReceiptTriggersOnWhatSurvivesTheParse:
    """`_record_first_receipt` called DIRECTLY — the only way to reach this rule.

    Every HTTP path into the helper goes through `_validate_product_create_form`
    first, and that refuses `quantity='abc'` with a field message before
    `product_add` commits anything, so the class above cannot post the case this
    one is about; a route test that tried would be asserting the VALIDATOR's
    behaviour under a name claiming the receipt's. The rule is still worth
    pinning here rather than dismissing as unreachable: the helper is a second
    gate in front of `record_purchase`, it runs AFTER the Product has committed
    and deliberately non-fatally, and `product_add` is not the only caller it
    could ever have. What the guard stands between is an unusable trigger and a
    Purchase carrying nothing but the `order_date` the service defaults to
    today — a row indistinguishable from a receipt someone meant.

    The decline is silent (`None`, no message) in every case here, matching what
    a form with no receipt at all does. Returning a message would put an error
    in front of an operator over a field a scan may have filled in for them,
    which is the trade DW-27 already made in the other direction.
    """

    def _receipt(self, app, test_storage, form_data):
        """Run one receipt against a fresh Product; return `(result, purchases)`.

        Inside an app context because the helper's failure path logs through
        `current_app` — nothing here is expected to take that path, and a test
        that did would otherwise fail with a context error naming neither the
        receipt nor the reason.
        """
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Reel')
        with app.app_context():
            result = _record_first_receipt(svc, pid, form_data)
        return result, svc.get_purchases_for_product(pid)

    def test_an_unusable_quantity_alone_records_nothing(self, app, test_storage):
        """The hole this closed: `'abc'` is non-blank, so a trigger tested on the
        raw string fired, and then `_positive_int_string` returned None — one
        Purchase with a NULL quantity, a NULL everything-else and today's date,
        reported as a success. There is nothing in that row for the trigger to
        have meant, so there is no receipt."""
        result, purchases = self._receipt(app, test_storage, {'quantity': 'abc'})

        assert result is None
        assert purchases == []

    def test_an_unusable_quantity_beside_a_real_trigger_still_records(
            self, app, test_storage):
        """The other trigger survives its own parse — `order_number` has none,
        its stripped string IS its parsed form — so the receipt is real and the
        quantity is simply the column it could not fill. Parsing before the
        guard must not become "any unusable field cancels the receipt": the
        Purchase the operator meant is still written."""
        result, purchases = self._receipt(app, test_storage, {
            'quantity': 'abc', 'order_number': 'PO-1',
        })

        assert result is None
        assert len(purchases) == 1
        assert purchases[0].quantity is None
        assert purchases[0].order_number == 'PO-1'

    def test_an_unusable_quantity_beside_a_non_trigger_records_nothing(
            self, app, test_storage):
        """A vendor is not a trigger (DW-27) and an unusable quantity is no
        longer one, so the two together are still not a receipt. Worth its own
        case because it is the shape where something WAS typed: the guard has to
        be about the trigger fields' parsed values and not about whether the
        form carried anything at all."""
        result, purchases = self._receipt(app, test_storage, {
            'quantity': 'abc', 'vendor': 'Acme',
        })

        assert result is None
        assert purchases == []

    def test_a_usable_quantity_alone_still_records_the_receipt(
            self, app, test_storage):
        """The control, and the half of the change that must NOT have moved:
        parsing earlier changes which values trigger, not what a trigger does."""
        result, purchases = self._receipt(app, test_storage, {'quantity': '2'})

        assert result is None
        assert len(purchases) == 1
        assert purchases[0].quantity == 2

    @pytest.mark.parametrize('quantity', [
        # A quantity `_positive_int_string` refuses for being a NUMBER it will
        # not take rather than for not being one. `'0'` is the interesting one:
        # it reads as a quantity, and "zero of them turned up" is not a receipt.
        # It does NOT arrive from a scan — `_ecia_prefill` puts a label's `Q`
        # into the field only when `_positive_int_string` already accepts it, so
        # a `Q 0` record is dropped a step earlier — which is why it is pinned
        # here, against the guard, rather than left to that gate. Over
        # `_MAX_INT32` is the other end of the same rule.
        '0',
        '-1',
        '2147483648',
    ])
    def test_a_quantity_the_rule_refuses_is_not_a_trigger_either(
            self, app, test_storage, quantity):
        """The guard must follow `_positive_int_string`'s verdict and not its own
        idea of "looks like a number". These are the values where testing the
        parsed result by TRUTHINESS and testing it for having parsed could come
        apart — `'0'` reads as a number, parses to None, and is falsy besides."""
        result, purchases = self._receipt(app, test_storage,
                                          {'quantity': quantity})

        assert result is None
        assert purchases == []


@pytest.mark.unit
class TestTheFirstReceiptPriceMatchesThePurchaseForm:
    """DW-22 added a THIRD entry point writing `purchases.unit_price`, and the
    property that matters is not that the create form has some price rule but
    that it has the SAME one: an operator who is refused a price on one surface
    and accepted on the other has been told two different things about one
    column. `_purchase_unit_price` is what makes that true — this asks the two
    HTML surfaces the same questions and compares their answers, so a future
    copy of the rule into either route fails here rather than in production.

    `api_record_purchase` is the third surface and is already pinned against the
    purchase form by `TestRecordPurchaseEndpointHoldsTheSameColumnBounds`, so
    the agreement is transitive and is not restated here.
    """

    def _create_form_errors(self, client, price):
        """Every message the create form renders beside a field for `price`."""
        resp = client.post('/products/add',
                           data={'description': 'Priced part',
                                 'unit_price': price})
        assert resp.status_code == 200
        return _shown_keyed_errors(resp.data.decode())

    def _purchase_form_errors(self, client, test_storage, price):
        """The same, from `purchase_add` against a product that already exists."""
        pid = CatalogService(test_storage).create_product(description='Reel')
        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'unit_price': price})
        assert resp.status_code == 200
        return _shown_keyed_errors(resp.data.decode())

    @pytest.mark.parametrize('price, message', _UNSTORABLE_PRICES)
    def test_both_forms_refuse_the_same_price_with_the_same_message(
            self, client, test_storage, price, message):
        assert self._create_form_errors(client, price) == [message]
        assert self._purchase_form_errors(client, test_storage, price) == [message]

    @pytest.mark.parametrize('price, stored', [
        ('1.25', Decimal('1.25')),
        ('0', Decimal('0')),
        ('99999999.99', Decimal('99999999.99')),
        # `Decimal` is lenient about both of these and neither entry point
        # tightens it (recorded in the ledger against `_purchase_unit_price`),
        # so the create form must be lenient in exactly the same way rather
        # than accidentally stricter.
        ('1_0', Decimal('10')),
        ('1E+2', Decimal('100')),
    ])
    def test_both_forms_accept_and_store_the_same_price(
            self, client, test_storage, price, stored):
        """The create form carries a `quantity` and the purchase form does not,
        and that asymmetry is the DW-27 trigger rule rather than anything about
        the price: only the create form makes a Purchase conditional at all, and
        without a trigger there would be no stored price on that side to compare.
        What is asserted — that the two surfaces store the same value — is
        unchanged."""
        svc = CatalogService(test_storage)

        created = client.post('/products/add',
                              data={'description': 'Priced part',
                                    'quantity': '1',
                                    'unit_price': price})
        assert created.status_code == 302
        new_id = int(created.headers['Location'].rstrip('/').split('/')[-1])

        existing_id = svc.create_product(description='Reel')
        recorded = client.post(f'/products/{existing_id}/purchases/add',
                               data={'unit_price': price})
        assert recorded.status_code == 302

        # Counted, not just indexed: this is the test that exercises the widest
        # set of accepted values, so a create path that ever wrote the receipt
        # twice would otherwise pass it on `[0]` alone.
        created_purchases = svc.get_purchases_for_product(new_id)
        recorded_purchases = svc.get_purchases_for_product(existing_id)
        assert len(created_purchases) == len(recorded_purchases) == 1
        assert created_purchases[0].unit_price == stored
        assert recorded_purchases[0].unit_price == stored


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
        identity nothing on the form said it touched (DW-20).

        The `quantity` is there because DW-27 stopped a lone receipt Vendor from
        recording anything: the trigger, not the assertion, is what changed. The
        vendor still has to reach the Purchase and only the Purchase, and now
        there is a Purchase for it to reach.
        """
        svc = CatalogService(test_storage)
        resp = client.post('/products/add', data={
            'description': 'Scanned part',
            'identifier_type': 'VENDOR_SKU',
            'identifier_value': '296-1234-ND',
            'identifier_vendor': 'DigiKey',
            'vendor': 'Mouser',
            'quantity': '1',
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
    `_parse_purchase_form`), so nothing here claims parity for it. What they DO
    now agree on is that column's 32-bit bound, applied to the parsed int on
    this side and to the raw digit string on the form's — see
    `TestRecordPurchaseEndpointBoundsQuantityToTheColumn` (DW-86) for this
    endpoint's `quantity` rules, and
    `TestBothPurchaseEntryPointsAgreeOnQuantityBounds` for the agreement itself,
    which is a table rather than a claim precisely because the two write the
    bound as separate expressions and could otherwise drift apart.
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


@pytest.mark.unit
class TestRecordPurchaseEndpointBoundsQuantityToTheColumn:
    """DW-86: `quantity` was the last column on this endpoint with no bound at
    all. `Purchase.quantity` is an INTEGER, which MariaDB stores in 32 bits, and
    a bare `int()` produced values it cannot hold: `2147483648` and up failed the
    write and came back as the generic `server_error` 500 naming no field — the
    DW-25 symptom every other column here had already lost — while `0` and `-3`
    were stored exactly as typed and a JSON `1e400`, which `json.loads` decodes
    to `float('inf')`, raised `OverflowError` straight past a catch that named
    only `TypeError` and `ValueError`.

    Every assertion below is about what the ROUTE answers, never about the write
    failing, and that is deliberate: this suite runs on SQLite, which widens
    INTEGER silently and stores whatever it is handed. A backend that refuses an
    over-wide value would make some of these pass for the wrong reason, and the
    one this suite actually uses would make them pass for no reason at all.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def _post(self, client, pid, body):
        return client.post(f'/api/products/{pid}/purchases', json=body)

    def _refusal(self, resp, fragment):
        """Assert the AD-13 refusal shape for a `quantity` rule and nothing more."""
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'invalid_field'
        assert data['error']['field'] == 'quantity'
        assert fragment in data['error']['message']

    @pytest.mark.parametrize('quantity, stored', [(5, 5), (1, 1),
                                                  (2147483647, 2147483647),
                                                  ('5', 5)])
    def test_a_storable_quantity_is_accepted_as_an_int_or_a_digit_string(
            self, client, test_storage, quantity, stored):
        """The shipped contract, including the exact edge: the bound is
        inclusive on the largest value the column can hold, and both the JSON
        int and the string that spells it are accepted. The string is the reason
        the form's `_positive_int_string` is NOT reused here — it takes a string
        and this contract takes either, so the parsers stay separate and only
        the column's bound is shared."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {'quantity': quantity})
        assert resp.status_code == 201
        assert svc.get_purchases_for_product(pid)[0].quantity == stored

    @pytest.mark.parametrize('quantity', [2147483648, 100000000000000000000])
    def test_a_quantity_past_the_column_names_its_field_instead_of_failing_the_write(
            self, client, test_storage, quantity):
        """The 500 DW-86 names. `2147483648` is one past the column and the
        twenty-digit value is far past it; neither is storable, and before this
        both reached the write and returned `server_error` with no field for the
        caller to act on."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'quantity': quantity}),
                      'no more than 2147483647')
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('literal', ['1e400', 'Infinity', '-Infinity',
                                         'NaN'])
    def test_a_non_finite_json_number_is_refused_rather_than_raised(
            self, client, test_storage, literal):
        """`1e400` has no Python float, so `json.loads` gives `float('inf')` and
        `int(inf)` raises `OverflowError` — which is neither a `TypeError` nor a
        `ValueError`, so it escaped the parse catch entirely and became a 500.

        `Infinity`, `-Infinity` and `NaN` are the same hole reached by the
        spelling a client is likelier to send: Python's encoder EMITS those
        three for the non-finite floats, and its decoder accepts them by
        default, so a client that round-trips a `float('inf')` through
        `json.dumps` sends `Infinity` and not `1e400`. The first two raise
        `OverflowError` like `1e400`; `NaN` raises `ValueError` and was already
        caught. All four are unparseable quantities and answer as that field.

        Posted as raw bodies rather than through `json=`: none of these is a
        literal `json.dumps` produces from a value this test could pass, so the
        only way to ask the question is to send the bytes a client would send."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases',
                           data='{"quantity": ' + literal + '}',
                           content_type='application/json')
        self._refusal(resp, 'must be an integer')
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('quantity', [0, -3])
    def test_a_non_positive_quantity_is_refused_rather_than_stored_as_typed(
            self, client, test_storage, quantity):
        """No backend was ever going to object to these — they fit the column
        perfectly — so they were recorded as purchases of zero and of minus
        three items. The form has always refused them; this is the half of the
        bound that is about meaning rather than width."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'quantity': quantity}),
                      'greater than 0')
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('quantity', ['abc', [1], {}])
    def test_an_unparseable_quantity_is_still_refused_the_same_way(
            self, client, test_storage, quantity):
        """Unchanged behavior, pinned because the parse catch grew a third
        exception: a value `int()` cannot read at all must still be the
        `invalid_field` refusal it already was, not a new code. Both halves of
        the ORIGINAL catch are represented — `'abc'` raises `ValueError`, the
        list and the dict raise `TypeError` — so widening it to `OverflowError`
        cannot be shown to have narrowed it."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'quantity': quantity}),
                      'must be an integer')
        assert svc.get_purchases_for_product(pid) == []

    def test_a_digit_string_python_cannot_parse_is_still_a_quantity_refusal(
            self, client, test_storage):
        """The STRING half of CPython's integer-parse cap, and the half this
        endpoint's contract is the reason for: it accepts `"5"` as well as `5`,
        so a caller can send an over-long value as a string. Then the object is
        well-formed, `get_json` returns a `dict`, and `int()` raises
        `ValueError` like any other unreadable quantity — so this one IS named
        against `quantity`, unlike the same digits sent as a bare literal, which
        never becomes a `dict` at all and is answered by the body-shape guard
        (see `TestRecordPurchaseEndpointRefusesABodyThatIsNotAnObject`).

        The length is read from `sys.get_int_max_str_digits()` rather than
        written as 4300, because the cap is per-process settable
        (`PYTHONINTMAXSTRDIGITS`, `-X int_max_str_digits`) and a hard-coded
        boundary would be an assertion about the environment."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        oversized = '9' * (sys.get_int_max_str_digits() + 1)
        self._refusal(self._post(client, pid, {'quantity': oversized}),
                      'must be an integer')
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('body', [{'vendor': 'X'}, {'quantity': None},
                                      {'quantity': ''}])
    def test_an_absent_or_empty_quantity_still_records_a_null(
            self, client, test_storage, body):
        """No quantity is not a bad quantity, and the new bound must not read
        `None` as "not greater than zero" — which is why it is guarded by
        `quantity is not None` rather than folded into the comparison."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, body)
        assert resp.status_code == 201
        assert svc.get_purchases_for_product(pid)[0].quantity is None

    @pytest.mark.parametrize('quantity, stored', [(3.7, 3), (True, 1)])
    def test_a_coercible_quantity_is_still_taken_as_int_reads_it(
            self, client, test_storage, quantity, stored):
        """Pinned as a DELIBERATE non-change, not as an endorsement. `int()`
        truncates `3.7` to 3 and reads `True` as 1, and both still answer 201 and
        store that number. This is `int()`'s coercion lenience — the exact
        counterpart of `Decimal`'s on `unit_price`, which accepts `'1_0'` as 10
        and `'٥'` as 5 (DW-89) — and it is left alone on purpose: refusing a
        value that is not a whole number is a new business rule about what a
        client may send, not the column bound DW-86 closes. The endpoint's
        message says only what is enforced here for exactly that reason, rather
        than borrowing the form's "whole number" sentence.
        """
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = self._post(client, pid, {'quantity': quantity})
        assert resp.status_code == 201
        assert svc.get_purchases_for_product(pid)[0].quantity == stored

    @pytest.mark.parametrize('quantity', [False, 0.5, 0.999])
    def test_a_value_that_truncates_to_zero_is_refused_as_the_zero_it_became(
            self, client, test_storage, quantity):
        """Where the kept coercion and the new bound meet, and the only place
        this change moves a value that is not out of range. `int()` reads
        `False` as 0 and truncates any fraction under 1 to 0, and the bound
        judges what `int()` returned, so all three are now refused where they
        were stored as 0 before — a purchase of zero items either way, so the
        refusal is the same one `{'quantity': 0}` gets.

        The message is the honest cost of parsing before bounding: `0.5` is told
        it must be greater than 0 when it already was. Diagnosing it separately
        would mean a "whole number" rule, which is exactly what this endpoint
        does not have — `3.7` must still store 3."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(self._post(client, pid, {'quantity': quantity}),
                      'greater than 0')
        assert svc.get_purchases_for_product(pid) == []


@pytest.mark.unit
class TestRecordPurchaseEndpointRefusesABodyThatIsNotAnObject:
    """DW-90: `request.get_json(silent=True) or {}` left a JSON array, string or
    number exactly as decoded, so the first `body.get(...)` raised
    `AttributeError` and the caller got a generic 500 instead of the AD-13
    envelope this endpoint honors everywhere else. Every OTHER way of failing to
    send an object — no body, a literal `null`, bytes that are not JSON, a good
    object with the wrong content type — took the falsy branch instead and
    recorded a purchase nobody had asked for, dated today.

    The refusal names no field, and that is the shape being asserted as much as
    the status: AD-13's `field` identifies a JSON key, and a body that is not an
    object has no key to name, so `error` must carry `code` and `message` and
    nothing else. All of them share one message, on the same reasoning as
    `_purchase_unit_price`'s single "decimal number" string: it states the
    requirement, not the diagnosis, because `silent=True` hands the route the
    same `None` for all of them.

    This endpoint refuses where its sibling `api_scan` coerces a non-dict body
    to `{}`. The difference is what an empty body MEANS: there, `raw` is
    required and its absence is already a refusal, so coercion only picks the
    message; here every field is optional and `{}` is a valid request, so
    coercion would answer 201 and write a row.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def _refusal(self, resp):
        """Assert the AD-13 body-shape refusal: `invalid_request`, no `field`."""
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        error = data['error']
        assert error['code'] == 'invalid_request'
        assert 'field' not in error
        assert 'JSON object' in error['message']

    @pytest.mark.parametrize('raw', ['[1, 2]', '"hello"', '5'])
    def test_a_non_object_json_body_is_refused_not_dereferenced(
            self, client, test_storage, raw):
        """The three DW-90 named: each decodes to something without a `.get`,
        which is where the `AttributeError` 500 came from. Posted as raw bytes
        rather than through `json=` so the literal on the wire is the one named
        here.

        All three are truthy, so all three survived `or {}` unchanged and
        reached the `.get`. The falsy non-objects — which `or {}` rewrote into a
        valid empty request instead, and which are the reason the expression
        could not be kept in front of this check — are the next test down."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases', data=raw,
                           content_type='application/json')
        self._refusal(resp)
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('raw', ['[]', '0', 'null'])
    def test_a_falsy_body_is_refused_rather_than_read_as_an_empty_request(
            self, client, test_storage, raw):
        """The values that did NOT 500 and are the more interesting half: `or
        {}` turned each of them into a valid empty request and recorded a
        purchase. `null` belongs here rather than with the three above — it
        decodes to `None`, which never reached a `.get` — and `[]` and `0` are
        why the shipped `or {}` could not be kept in front of the guard: `[] or
        {}` and `0 or {}` are both `{}`, so two of the very bodies being refused
        would have been rewritten into a valid one before `isinstance` ever saw
        them."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases', data=raw,
                           content_type='application/json')
        self._refusal(resp)
        assert svc.get_purchases_for_product(pid) == []

    def test_a_request_with_no_body_at_all_is_refused_not_recorded(
            self, client, test_storage):
        """The behavior change this closes rather than merely stops crashing:
        `get_json(silent=True)` returned None, `or {}` made it an empty request,
        and the endpoint answered 201 with a purchase dated today. A POST that
        says nothing is not a purchase."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(client.post(f'/api/products/{pid}/purchases'))
        assert svc.get_purchases_for_product(pid) == []

    def test_an_unparseable_body_is_refused_not_recorded(
            self, client, test_storage):
        """Same 201-with-a-row as the empty body, from a client that meant to
        send JSON and got the bytes wrong — the case where silently recording a
        row is least defensible."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases', data='{oops',
                           content_type='application/json')
        self._refusal(resp)
        assert svc.get_purchases_for_product(pid) == []

    def test_an_integer_literal_python_cannot_parse_is_refused_here(
            self, client, test_storage):
        """A well-formed object that is nonetheless refused for its SHAPE, and
        the one arrival worth naming: CPython will not parse an integer literal
        longer than `sys.get_int_max_str_digits()`, so `json` raises inside
        `get_json` and the body never becomes a `dict` at all. The caller is
        told the body must be an object, which is a true requirement and a poor
        diagnosis; the alternative is a second decode purely to describe an
        over-long number. One digit fewer still reaches the `quantity` bound and
        is named as that field — the boundary is CPython's, not this route's,
        and it is the same cap `_positive_int_string` documents for the form.

        The two lengths are derived from `sys.get_int_max_str_digits()` rather
        than written as 4301 and 4300: that cap is 4300 only by default and is
        per-process settable (`PYTHONINTMAXSTRDIGITS`, `-X int_max_str_digits`),
        so hard-coding it would assert something about the environment instead
        of about the route. (The form helper's comment calls this constant
        `sys.int_info.str_digits_check_threshold`, which is a different number
        entirely — 640, the floor the setter accepts.)"""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)
        limit = sys.get_int_max_str_digits()

        self._refusal(client.post(f'/api/products/{pid}/purchases',
                                  data='{"quantity": ' + '9' * (limit + 1) + '}',
                                  content_type='application/json'))
        assert svc.get_purchases_for_product(pid) == []

        resp = client.post(f'/api/products/{pid}/purchases',
                           data='{"quantity": ' + '9' * limit + '}',
                           content_type='application/json')
        assert resp.status_code == 400
        error = resp.get_json()['error']
        assert error['code'] == 'invalid_field'
        assert error['field'] == 'quantity'
        assert 'no more than 2147483647' in error['message']
        assert svc.get_purchases_for_product(pid) == []

    @pytest.mark.parametrize('kwargs', [
        {'data': '{"quantity": 5}', 'content_type': 'text/plain'},
        {'data': '{"quantity": 5}'},
        {'data': {'quantity': '5'}},
    ])
    def test_an_object_sent_as_the_wrong_media_type_is_refused_not_dropped(
            self, client, test_storage, kwargs):
        """`get_json` reads only a JSON content type, so these bodies — two of
        them a perfectly good object, one of them a form encoding — decoded to
        `None` and answered 201 with every value silently discarded. Refusing
        them is the point of the guard as much as the array is: a client whose
        request was ignored is worse off than one that was told no.

        This is why the message names `application/json` rather than only the
        object shape: for these three the shape was never the problem."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        self._refusal(client.post(f'/api/products/{pid}/purchases', **kwargs))
        assert svc.get_purchases_for_product(pid) == []

    def test_an_empty_object_still_records_a_purchase(
            self, client, test_storage):
        """The case the guard must NOT catch, and the reason it tests
        `isinstance(body, dict)` rather than truthiness: `{}` is falsy and is a
        perfectly valid request, since every field of a purchase is optional.
        Note what it stores — nothing the caller sent, but not an all-null row
        either: `record_purchase` fills `order_date` with today."""
        from datetime import date
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        today = date.today()
        resp = client.post(f'/api/products/{pid}/purchases', json={})
        assert resp.status_code == 201
        purchases = svc.get_purchases_for_product(pid)
        assert len(purchases) == 1
        assert purchases[0].vendor is None
        assert purchases[0].quantity is None
        assert purchases[0].unit_price is None
        # Both sides of a midnight crossing, as `_DATE_ORDER_VERDICTS` does.
        assert purchases[0].order_date in (today, date.today())


# The verdict on a `unit_price`, as ONE list. The classes above spell out each
# rule and why it exists; this table exists so the two entry points cannot drift
# apart without a test failing, which two hand-copied per-route lists could not
# catch — the same reason the routes share `_purchase_unit_price`.
#
# `(raw value, the Decimal it must STORE if it is accepted, else the message
# fragment it must be refused with)`. The accepted half spells out the stored
# value rather than saying only "accepted" because the two questions are not the
# same one: `-0`, `0E+5` and `0.00E-99999999999999999` are all accepted and all
# have to arrive in the column as the one `Decimal('0.00')`, and a test that
# only asked "was it accepted" — or compared with `==`, which every spelling of
# a number passes — could not tell that apart from storing what was typed.
# Which SPELLING actually leaves the route is a question no suite reading
# through SQLite can answer (see `_assert_stored`); the accepted column states
# it anyway, and `TestAnAcceptedUnitPriceIsNormalizedBeforeItIsStored` is where
# it is checked.
_UNIT_PRICE_VERDICTS = [
    ('2.34', Decimal('2.34')),
    ('0', Decimal('0.00')),
    ('0.00', Decimal('0.00')),
    # `Decimal` takes a leading sign; both sides must.
    ('+2.34', Decimal('2.34')),
    # both strip before parsing, so padding is not a price
    ('  2.34  ', Decimal('2.34')),
    ('99999999.99', Decimal('99999999.99')),
    # Spellings `Decimal` keeps and a DECIMAL literal need not take, which is
    # why the helper returns the quantized value rather than the value as typed:
    # the driver renders the object with `str()`, so `Decimal('1E+7')` reaches
    # MariaDB as `'1E+7'` and `Decimal('0.00E-99999999999999999')` as
    # `'0E-100000000000000001'`, which it refuses outright. `-0` is here as a value
    # rather than as a refusal on purpose — it is not negative, so the negative
    # rule never sees it, and dropping its sign is the decision that makes it a
    # zero instead of a `Decimal('-0.00')` in the column.
    ('-0', Decimal('0.00')),
    ('0E+5', Decimal('0.00')),
    ('0.00E-99999999999999999', Decimal('0.00')),
    ('1E+7', Decimal('10000000.00')),
    # The un-normalized spelling a real client actually sends, and the one the
    # exponent rows above are not: the scale rule is NUMERIC (`price` equals its
    # own quantize), so trailing zeros pass it, and `str(Decimal('2.3400'))`
    # keeps all four places. A JSON client that formats currency to four
    # decimals is accepted — correctly — and used to store a spelling nobody
    # chose. MariaDB takes that one, so this row is about the normalization
    # being uniform rather than about a literal being refused.
    ('2.3400', Decimal('2.34')),
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
    # The neighbour of the `-0` row above, and the reason that row is not a
    # licence to accept anything spelled with a minus: `Decimal('-0.001') < 0`
    # is True, so the negative rule fires before the scale rule ever sees it.
    ('-0.001', 'must not be negative'),
    ('100000000', 'less than 100000000'),
    ('1E+30', 'less than 100000000'),
    ('99999999999.99', 'less than 100000000'),
    ('0.005', 'at most two decimal places'),
    ('1.234', 'at most two decimal places'),
    ('1e-30', 'at most two decimal places'),
]


# The accepted half of the table above, for the suites that are about what a
# price BECOMES rather than about whether it is taken. Derived rather than
# restated so it cannot fall behind the table it is drawn from — a new accepted
# row is a new case in every suite below without anyone remembering to add it.
_STORABLE_PRICES = [(raw, verdict) for raw, verdict in _UNIT_PRICE_VERDICTS
                    if isinstance(verdict, Decimal)]


@pytest.mark.unit
class TestTheUnitPriceVerdictTableIsWellFormed:
    """One statement about the TABLE, asked once rather than per case.

    The accepted half used to be spelled `None` and is now spelled "a
    `Decimal`", while the suites below branch on `isinstance(verdict, Decimal)`.
    A row written any third way — the old `None`, a `float`, an accepted value
    quoted as `'2.34'` — is not a syntax error and not a caught mistake: it
    silently takes the REFUSAL branch and fails somewhere inside a route
    assertion, blaming the code for what is a typo here. `_STORABLE_PRICES` is
    derived from the same predicate, so such a row also quietly drops out of
    every normalization suite.
    """

    def test_every_row_is_a_stored_decimal_or_a_refusal_fragment(self):
        for raw, verdict in _UNIT_PRICE_VERDICTS:
            assert isinstance(verdict, (Decimal, str)), \
                f'the `_UNIT_PRICE_VERDICTS` row for {raw!r} is ' \
                f'{verdict!r}: a row is a Decimal (accepted, and the value ' \
                f'stored) or a message fragment (refused), never anything else'


@pytest.mark.unit
@pytest.mark.parametrize('price, verdict', _UNIT_PRICE_VERDICTS)
class TestBothPurchaseEntryPointsAgreeOnUnitPrice:
    """DW-12/DW-25's acceptance criterion, stated as a property: a value one
    entry point accepts the other accepts, and a value one refuses the other
    refuses with the same reason. Only the SHAPE of the refusal differs — a
    re-rendered field message versus the AD-13 envelope.
    """

    def _product(self, test_storage):
        # The table's own well-formedness is asserted once, above, rather than
        # from in here: a malformed row misroutes into the refusal branch below,
        # and that is a statement about the table and not about either route.
        return CatalogService(test_storage).create_product(description='Reel')

    def _assert_stored(self, svc, pid, verdict):
        """The accepted half: the two entry points hold the SAME number.

        Compared on `str()` and not on `==` so the assertion states the claim
        that is actually being made — the driver renders a `Decimal` with
        `str()`, and `Decimal('-0.00')`, `Decimal('1E+7')` and
        `Decimal('10000000.00')` all compare equal to the number they mean while
        spelling it three ways. What this tier can PROVE is narrower than what
        it states, and deliberately so: SQLite stores `Numeric(10, 2)` as a
        float and rebuilds it with `'%.2f'`, so the column hands back the
        two-place form whatever went in, sign included. The spelling is pinned
        one level down, on the helper's own return
        (`TestAnAcceptedUnitPriceIsNormalizedBeforeItIsStored`), and against a
        real DECIMAL column in the integration tier.
        """
        assert str(svc.get_purchases_for_product(pid)[0].unit_price) == \
            str(verdict)

    def test_the_html_form(self, client, test_storage, price, verdict):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'unit_price': price})
        if isinstance(verdict, Decimal):
            assert resp.status_code == 302
            self._assert_stored(svc, pid, verdict)
        else:
            assert resp.status_code == 200
            assert verdict.encode() in resp.data
            assert svc.get_purchases_for_product(pid) == []

    def test_the_json_endpoint(self, client, test_storage, price, verdict):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'unit_price': price})
        if isinstance(verdict, Decimal):
            assert resp.status_code == 201
            self._assert_stored(svc, pid, verdict)
        else:
            assert resp.status_code == 400
            error = resp.get_json()['error']
            assert error['code'] == 'invalid_field'
            assert error['field'] == 'unit_price'
            assert verdict in error['message']
            assert svc.get_purchases_for_product(pid) == []


@pytest.mark.unit
@pytest.mark.parametrize('price, expected', _STORABLE_PRICES)
class TestAnAcceptedUnitPriceIsNormalizedBeforeItIsStored:
    """The claim the table's accepted column makes, asserted where SQLite cannot
    erase it: on `_purchase_unit_price`'s own return value.

    Every route-level suite reads its purchases back through SQLite, which
    stores `Numeric(10, 2)` as a float and rebuilds it with `'%.2f'`. That
    column returns the two-place form no matter what went in — `Decimal('-0')`,
    `Decimal('1E+7')` and `Decimal('0E-100000000000000001')` all come back as
    the number they mean, correctly spelled — so NO test that goes through
    storage can tell "the helper normalized it" from "the readback did". The
    helper's return is the last place the difference is visible in this tier,
    which is why it is asserted directly here rather than through a route.

    That the difference matters at all is the integration tier's subject
    (`tests/integration/test_purchase_unit_price_decimal.py`): MariaDB is handed
    `str()` of whatever `Decimal` the route produced, and it refuses
    `'0E-100000000000000001'` — the spelling of a zero that reached the driver
    unquantized — as a literal, losing the whole receipt.
    """

    def test_the_helper_returns_the_two_place_form(self, price, expected):
        value, message = _purchase_unit_price(price)
        assert message is None, f'{price!r} was refused: {message}'
        # `str()` for the reason given on `_assert_stored` above — and here it
        # is the whole point rather than a precaution, since `==` holds for
        # every spelling by construction.
        assert str(value) == str(expected)

    def test_the_returned_spelling_is_one_a_decimal_literal_takes(
            self, price, expected):
        """The property the specific expectations above are instances of, and
        the one that actually matters to MariaDB: no exponent, no sign, exactly
        two places after the point. The test above compares against a value
        someone wrote down by hand, so its failure can only show two unequal
        strings; this one names the rule being broken, which is what a reader of
        the failure needs. It is the same reason `_purchase_unit_price` states
        the rule in its docstring instead of leaving it to be read off the
        table."""
        value, _ = _purchase_unit_price(price)
        assert re.fullmatch(r'\d+\.\d\d', str(value)), \
            f'{price!r} came back as {str(value)!r}, which is not a DECIMAL literal'


@pytest.mark.unit
class TestANegativeZeroPriceIsEchoedAsAZero:
    """The one place dropping `-0`'s sign is visible to somebody.

    MariaDB stores `Decimal('-0.00')` as `0.00` either way, so the column never
    showed the difference and neither does SQLite. The JSON endpoint does:
    `Purchase.to_dict` renders the column with `float()`, and `float()` keeps a
    negative zero — so before the sign was dropped, a client that sent
    `unit_price: "-0"` got `-0.0` back in the 201 body it is meant to trust as
    what was recorded. Pinned here because it is the whole observable
    consequence of that decision, and nothing else in this file would notice if
    it were reverted.
    """

    def test_the_creation_response_carries_an_unsigned_zero(
            self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='Reel')

        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'unit_price': '-0'})

        assert resp.status_code == 201
        echoed = resp.get_json()['purchase']['unit_price']
        assert echoed == 0
        # `==` cannot tell `-0.0` from `0.0`; `copysign` is what asks the
        # question this test is named for.
        assert math.copysign(1, echoed) == 1, \
            f'the 201 body echoed {echoed!r}, a negative zero'


@pytest.mark.unit
@pytest.mark.parametrize('price, expected', _STORABLE_PRICES)
class TestTheCreateFormStoresTheSameNormalizedPrice:
    """The THIRD writer of this column, held to the same table as the two above.

    `product_add`'s first receipt reaches `record_purchase` by its own path —
    `_record_first_receipt`, after the Product has committed — so "both entry
    points agree" is not a statement about it, and the acceptance criterion is
    about all three. What this adds is that every value the other two take is
    taken HERE too and reaches the column as the same number: a create form that
    grew a price rule of its own would refuse one of these rows, or store a
    different number, while both classes above stayed green. Parametrized over
    the derived accepted list so the three suites can only ever be asked about
    the same values.

    The NUMBER is what this tier can hold it to, not the spelling — the readback
    is through SQLite, which stores `Numeric(10, 2)` as a float and rebuilds it
    with `'%.2f'`, so the column re-spells whatever went in (see `_assert_stored`
    above). Removing the helper's `quantize` would leave every case here green.
    The spelling is pinned on the helper's own return, one class up, and against
    a real DECIMAL column in the integration tier; what this class is for is that
    the third entry point is asked the same question at all.
    """

    def test_the_first_receipt_block(self, client, test_storage, price, expected):
        # The quantity is the DW-27 trigger and nothing more: a price alone is
        # not a receipt, so without one there would be no row to look at.
        resp = client.post('/products/add', data={
            'description': 'Priced part', 'quantity': '1', 'unit_price': price,
        })
        assert resp.status_code == 302
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        purchase = CatalogService(test_storage).get_purchases_for_product(pid)[0]
        assert str(purchase.unit_price) == str(expected)


# The verdict on ONE purchase date's FORMAT, as one list — the anti-drift device
# this pair never had while the two entry points parsed their dates separately.
# It is what closes DW-88 (`date.fromisoformat` accepts most of ISO 8601, so
# `'2026-W01-1'` recorded a purchase in 2025 through a message that says only
# `YYYY-MM-DD` is taken) and DW-191 (the form stripped and the endpoint did not,
# so `' 2026-01-01 '` was a stored row one way and a 400 the other). Both are now
# one rule in `_purchase_date`, and this table is the whole statement of it.
#
# `(value, verdict)`, where the verdict is one of:
#   'stored'  -- accepted; the column holds `date.fromisoformat(value.strip())`
#   'absent'  -- accepted as NO date, which is not the same as accepted: the
#                column stays NULL (`received_date`) or is filled with today by
#                the service (`order_date`, DW-192)
#   'refused' -- the one message, `'<Label> must be an ISO date (YYYY-MM-DD).'`
#
# Every row runs against BOTH date columns and BOTH entry points (the class
# below crosses this table with the field name), because the rule is the columns'
# and not one column's. The one row that cannot: a value that is not a string.
# An HTML form field is always a string — Werkzeug decodes the body into `str` —
# so the JSON integer `20260101` has no form spelling at all, and the form half
# skips it explicitly rather than the table quietly omitting the case that used
# to be `str()`-coerced and stored as a date the caller never spelled.
#
# The matrix's last row — a malformed date that is ALSO out of order — is not
# here because it is about two fields at once; it lives in
# `TestAMalformedDateIsNeverAlsoCalledOutOfOrder`, which pins it on both sides.
_DATE_FORMAT_VERDICTS = [
    ('2026-01-01', 'stored'),
    # DW-191: padded on both sides now, and stripped to the same day.
    (' 2026-01-01 ', 'stored'),
    # Years below 1000 round-trip through `date.isoformat()` and were always
    # accepted; pinned so the round-trip rule is not mistaken for a range rule.
    # This suite runs on SQLite, but the row is not green only because of that:
    # MariaDB's `1000-01-01` floor is the range its `DATE` type is DOCUMENTED to
    # support and not one it enforces, and 11.8 under `STRICT_TRANS_TABLES`
    # stores `'0999-01-01'` without error or warning. So there is no production
    # failure hiding behind this row.
    ('0999-01-01', 'stored'),
    ('9999-12-31', 'stored'),
    # The three spellings of "no date given". None of them is a refusal.
    (None, 'absent'),
    ('', 'absent'),
    ('   ', 'absent'),
    # DW-88: these three PARSE and are still refused, because they print back as
    # a different string than they were given — the round-trip comparison is the
    # grammar rule, and these are the only rows that exercise it. The week date
    # is the one that changed a stored value: it is 2025-12-29.
    ('2026-W01-1', 'refused'),
    ('2026-W01', 'refused'),
    ('20260101', 'refused'),
    # A JSON number, refused rather than `str()`-coerced — the one row with no
    # form spelling at all, for the reason given above.
    (20260101, 'refused'),
    # These never parsed on either side and must stay refused — they are caught
    # by the `except`, NOT by the round-trip comparison, so they would all stay
    # green if it were deleted. `strptime` would have taken the first two, which
    # is why the check is not `strptime`.
    ('2026-1-1', 'refused'),
    ('٢٠٢٦-٠١-٠١', 'refused'),
    ('2026-01-01T00:00:00', 'refused'),
    ('2026-02-30', 'refused'),
    ('nope', 'refused'),
    ('07/01/2026', 'refused'),
]

# Restated here rather than imported from `_PURCHASE_DATE_LABELS`: the label is
# half of what the refusal promises, and a test that read the mapping under test
# would agree with any relabelling, including one that swapped the two.
_DATE_FORMAT_LABELS = {'order_date': 'Order Date',
                       'received_date': 'Received Date'}


@pytest.mark.unit
@pytest.mark.parametrize('field', ['order_date', 'received_date'])
@pytest.mark.parametrize('value, verdict', _DATE_FORMAT_VERDICTS)
class TestBothPurchaseEntryPointsAgreeOnDateFormat:
    """DW-88/DW-191 as a property: a date one entry point accepts the other
    accepts and stores as the same day, and a date one refuses the other refuses
    with the same message against the same field. Only the SHAPE of the refusal
    differs — a re-rendered field message versus the AD-13 envelope, where the
    human-labelled sentence is reused verbatim because `error.field` already
    carries the machine name.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def _message(self, field):
        return f'{_DATE_FORMAT_LABELS[field]} must be an ISO date (YYYY-MM-DD).'

    def _assert_stored(self, svc, pid, field, value, verdict, today):
        """The two accepted verdicts, which differ in what lands in the column:
        a `'stored'` date is the STRIPPED value, and an `'absent'` one leaves
        `received_date` NULL while the service fills `order_date` with today.

        `today` is read by the caller BEFORE the POST and both sides of a
        midnight crossing are allowed, as in `_DATE_ORDER_VERDICTS`: recomputing
        `date.today()` here would fail the absent-`order_date` rows on any run
        that straddles it.
        """
        from datetime import date
        purchases = svc.get_purchases_for_product(pid)
        assert len(purchases) == 1
        stored = getattr(purchases[0], field)
        if verdict == 'stored':
            assert stored == date.fromisoformat(value.strip())
        elif field == 'received_date':
            assert stored is None
        else:
            assert stored in (today, date.today())

    def test_the_html_form(self, client, test_storage, field, value, verdict):
        from datetime import date
        if not isinstance(value, str) and value is not None:
            pytest.skip('a form field is always a string, so a JSON number has '
                        'no spelling here; the JSON half below carries the row')
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        # `None` is spelled on a form by not submitting the field at all — the
        # request Werkzeug turns back into `form.get(name) is None`.
        data = {} if value is None else {field: value}
        today = date.today()
        resp = client.post(f'/products/{pid}/purchases/add', data=data)

        if verdict == 'refused':
            assert resp.status_code == 200
            body = resp.data.decode()
            assert self._message(field) in body
            # Against the CONTROL, not the page: both date fields render an
            # identical `invalid-feedback` slot, so a page-wide substring check
            # would stay green if the message were filed under the other one.
            other = ('received_date' if field == 'order_date'
                     else 'order_date')
            assert 'is-invalid' in _form_controls(body, [field])[0]
            assert 'is-invalid' not in _form_controls(body, [other])[0]
            assert svc.get_purchases_for_product(pid) == []
            return

        assert resp.status_code == 302
        self._assert_stored(svc, pid, field, value, verdict, today)

    def test_the_json_endpoint(self, client, test_storage, field, value,
                               verdict):
        from datetime import date
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        today = date.today()
        resp = client.post(f'/api/products/{pid}/purchases',
                           json={field: value})

        if verdict == 'refused':
            assert resp.status_code == 400
            error = resp.get_json()['error']
            assert error['code'] == 'invalid_field'
            # The MACHINE name in `field`, the HUMAN-labelled sentence in
            # `message` — the same string the form renders, byte for byte.
            assert error['field'] == field
            assert error['message'] == self._message(field)
            assert svc.get_purchases_for_product(pid) == []
            return

        assert resp.status_code == 201
        self._assert_stored(svc, pid, field, value, verdict, today)


@pytest.mark.unit
class TestTheJsonEndpointJudgesTheDatesInMappingOrder:
    """Which date a body with TWO bad dates is refused for. The table above
    cannot say: it sends one bad date at a time, so it stays green whichever
    order the endpoint judges them in.

    The endpoint answers with the FIRST failure and iterates
    `_PURCHASE_DATE_LABELS`, so the answer is that mapping's insertion order —
    `order_date`. That is what the boundary comment in `api_record_purchase`
    claims, and without this it is a claim a reordering of the mapping literal
    would silently falsify.

    The form is the deliberate contrast: it collects rather than
    short-circuits, so the same pair comes back with BOTH messages on their own
    controls. Nothing is stored either way.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def test_the_json_endpoint_names_order_date(self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'order_date': 'nope',
                                 'received_date': 'also nope'})

        assert resp.status_code == 400
        error = resp.get_json()['error']
        assert error['code'] == 'invalid_field'
        assert error['field'] == 'order_date'
        assert error['message'] == 'Order Date must be an ISO date (YYYY-MM-DD).'
        assert svc.get_purchases_for_product(pid) == []

    def test_the_html_form_reports_both(self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'order_date': 'nope',
                                 'received_date': 'also nope'})

        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Order Date must be an ISO date (YYYY-MM-DD).' in body
        assert 'Received Date must be an ISO date (YYYY-MM-DD).' in body
        assert 'is-invalid' in _form_controls(body, ['order_date'])[0]
        assert 'is-invalid' in _form_controls(body, ['received_date'])[0]
        assert svc.get_purchases_for_product(pid) == []


# The verdict on a purchase's date PAIR, as ONE list, for the same reason
# `_UNIT_PRICE_VERDICTS` is one list: the rule has one definition
# (`_purchase_date_order_error`) and the two entry points must not drift apart
# from it. Unlike the price rules this one is not a column bound — no column can
# say "received on or after ordered" — so this table is the whole specification
# of it. `(order_date, received_date, None if accepted else the fragment)`.
#
# A padded pair IS pinned here now, as `_UNIT_PRICE_VERDICTS` pins one: both
# entry points reach these dates through `_purchase_date`, which strips before
# it parses, so `' 2026-01-01 '` is the same day to both (DW-191, with DW-88).
# The row belongs to THIS table and not only to `_DATE_FORMAT_VERDICTS` because
# it claims something that table cannot: the strip happens before the comparison,
# so a padded pair is judged by the ORDERING rule as the two dates it spells
# rather than dying as a format error on one side first.
_DATE_ORDER_VERDICTS = [
    ('2026-01-01', '2026-01-05', None),
    (' 2026-01-01 ', ' 2026-01-05 ', None),
    # Equal dates pass: the rule is "must not precede", not "must follow".
    ('2026-01-01', '2026-01-01', None),
    ('2026-01-05', '2026-01-01', 'must not be earlier than'),
    # The other half of that claim: a padded pair that IS out of order is
    # refused by this rule and not by a format error, which is only true if the
    # strip runs first.
    (' 2026-01-05 ', ' 2026-01-01 ', 'must not be earlier than'),
    # The three partial cases, deliberately untouched by DW-24. The second is
    # the interesting one: the service defaults the missing `order_date` to
    # today, so the stored row DOES have received before order — and is still
    # accepted, because refusing it is a wider rule than the one decided.
    ('2026-01-05', '', None),
    ('', '2020-01-01', None),
    ('', '', None),
    # The same partial case spelled with padding, which is where the new absence
    # rule and this one meet: `'   '` is "no date" to `_purchase_date` on BOTH
    # sides now (the endpoint used to answer 400 for it), so this row stores a
    # purchase whose `order_date` the service fills with today and whose
    # `received_date` is six years earlier — accepted, for the reason the
    # unpadded row above it is.
    ('   ', '2020-01-01', None),
]


@pytest.mark.unit
@pytest.mark.parametrize('order_date, received_date, fragment',
                         _DATE_ORDER_VERDICTS)
class TestBothPurchaseEntryPointsAgreeOnDateOrder:
    """DW-24 as a property: a date pair one entry point accepts the other
    accepts, and a pair one refuses the other refuses with the same message
    against the same field, `received_date`. Only the SHAPE of the refusal
    differs — a re-rendered field message versus the AD-13 envelope. The claim
    is about the ORDERING rule; the format rule underneath it is shared too now
    (`_purchase_date`, DW-88/DW-191), which is what lets the padded rows in the
    table be about ordering rather than about a parse the two sides disagree on.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def _assert_stored(self, svc, pid, order_date, received_date, today):
        """An accepted pair is stored as the day it spells, except a blank
        `order_date`, which `record_purchase` fills with today.

        The comparison strips, because the ROUTES strip: a padded row is stored
        as `2026-01-01`, and `date.fromisoformat(' 2026-01-01 ')` raises. That
        is also why a blank is tested with `.strip()` — `'   '` is "no date" to
        `_purchase_date` and must be "no date" to this assertion too.

        `today` is read by the caller BEFORE the POST and both sides of a
        midnight crossing are allowed: recomputing `date.today()` here would
        fail the blank-`order_date` rows on any run that straddles it.

        `or ''` before the strip so a `None` row — how `_DATE_FORMAT_VERDICTS`
        thirty lines above spells absence, and the spelling someone extending
        this table will reach for — fails as a readable assertion rather than as
        an `AttributeError` inside this helper.
        """
        from datetime import date
        purchases = svc.get_purchases_for_product(pid)
        assert len(purchases) == 1
        if (order_date or '').strip():
            assert purchases[0].order_date == \
                date.fromisoformat(order_date.strip())
        else:
            assert purchases[0].order_date in (today, date.today())
        assert purchases[0].received_date == (
            date.fromisoformat(received_date.strip())
            if (received_date or '').strip() else None)

    def test_the_html_form(self, client, test_storage, order_date,
                           received_date, fragment):
        from datetime import date
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        today = date.today()
        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'order_date': order_date,
                                 'received_date': received_date})
        if fragment is None:
            assert resp.status_code == 302
            self._assert_stored(svc, pid, order_date, received_date, today)
        else:
            assert resp.status_code == 200
            # Against the CONTROL, not the page: the form gives `order_date` an
            # identical `invalid-feedback` slot, so a page-wide substring check
            # would stay green if the message were filed under the wrong field —
            # which is half of what this class claims.
            body = resp.data.decode()
            assert fragment in body
            assert 'is-invalid' in _form_controls(body, ['received_date'])[0]
            assert 'is-invalid' not in _form_controls(body, ['order_date'])[0]
            assert svc.get_purchases_for_product(pid) == []

    def test_the_json_endpoint(self, client, test_storage, order_date,
                               received_date, fragment):
        from datetime import date
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        today = date.today()
        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'order_date': order_date,
                                 'received_date': received_date})
        if fragment is None:
            assert resp.status_code == 201
            self._assert_stored(svc, pid, order_date, received_date, today)
        else:
            assert resp.status_code == 400
            error = resp.get_json()['error']
            assert error['code'] == 'invalid_field'
            assert error['field'] == 'received_date'
            assert fragment in error['message']
            assert svc.get_purchases_for_product(pid) == []


@pytest.mark.unit
class TestAMalformedDateIsNeverAlsoCalledOutOfOrder:
    """`_purchase_date_order_error` compares two parsed `date`s, so a date that
    never parsed cannot reach it — the form leaves it `None` and the endpoint
    has already returned. That is why the check sits after the parsing on both
    sides, and this is what holds it there: move it earlier and a typo in
    `order_date` starts also accusing `received_date`.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def test_the_html_form_reports_only_the_format_error(
            self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'order_date': 'nope',
                                 'received_date': '2026-01-01'})
        assert resp.status_code == 200
        assert b'Order Date must be an ISO date' in resp.data
        assert b'must not be earlier than' not in resp.data
        assert svc.get_purchases_for_product(pid) == []

    def test_the_html_form_does_not_clobber_the_received_date_message(
            self, client, test_storage):
        """The collision case: both messages are filed under the SAME key,
        `errors['received_date']`, so an ordering check that ran on an unparsed
        date would overwrite the format message with one about a comparison
        that never happened."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'order_date': '2026-01-05',
                                 'received_date': 'nope'})
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Received Date must be an ISO date' in body
        assert 'must not be earlier than' not in body
        assert 'is-invalid' in _form_controls(body, ['received_date'])[0]
        assert svc.get_purchases_for_product(pid) == []

    def test_the_json_endpoint_reports_only_the_format_error(
            self, client, test_storage):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'order_date': 'nope',
                                 'received_date': '2026-01-01'})
        assert resp.status_code == 400
        error = resp.get_json()['error']
        assert error['field'] == 'order_date'
        assert 'ISO date' in error['message']
        assert 'must not be earlier than' not in error['message']
        assert svc.get_purchases_for_product(pid) == []

    def test_the_json_endpoint_refuses_the_unparsed_received_date_first(
            self, client, test_storage):
        """The endpoint's counterpart to the collision above: the format
        failure returns before the ordering check is ever reached, so the one
        `field` AD-13 carries names the date that is actually unreadable."""
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'order_date': '2026-01-05',
                                 'received_date': 'nope'})
        assert resp.status_code == 400
        error = resp.get_json()['error']
        assert error['field'] == 'received_date'
        assert 'ISO date' in error['message']
        assert 'must not be earlier than' not in error['message']
        assert svc.get_purchases_for_product(pid) == []


# The verdict on a `quantity`, as ONE list — the same anti-drift device as
# `_UNIT_PRICE_VERDICTS`, and needed MORE here, because the two entry points do
# not share a helper for this column. The form runs `_positive_int_string` and
# the endpoint bounds what `int()` returned, so the 32-bit rule is written twice
# in two spellings (`parsed <= 0 or parsed > _MAX_INT32` against
# `not 0 < quantity <= _MAX_INT32`) and only `_MAX_INT32` itself is shared. A
# claim that they agree is therefore only worth what this table pins.
#
# Only the VERDICT is shared, not the message: the form promises a whole number
# and the endpoint does not (`3.7` stores 3 there, DW-86/DW-89), so the two
# sentences must differ and each side asserts its own in full, below. Neither
# side varies its wording by WHICH half of the bound was broken — one sentence
# states the whole rule — so a per-row fragment could only ever repeat the
# ceiling, and a table keyed on `'2147483647'` would still pass if either side
# stopped mentioning the lower bound at all. Hence: the row carries the verdict,
# and the message is pinned whole against the constants below.
#
# For the same reason the table holds only bound-relevant values: `'٥'`, `'1_0'`
# and `3.7` are exactly where the two still disagree, by design.
_FORM_QUANTITY_REFUSAL = ('Quantity must be a whole number greater than zero '
                          'and no more than 2147483647.')
_JSON_QUANTITY_REFUSAL = 'quantity must be greater than 0 and no more than 2147483647'

_QUANTITY_BOUND_VERDICTS = [
    (1, True),
    (5, True),
    (2147483647, True),   # the largest the INTEGER column holds
    (2147483648, False),   # one past it
    (100000000000000000000, False),
    (0, False),
    (-3, False),
]


@pytest.mark.unit
@pytest.mark.parametrize('quantity, storable', _QUANTITY_BOUND_VERDICTS)
class TestBothPurchaseEntryPointsAgreeOnQuantityBounds:
    """DW-86 as a property: a quantity one entry point stores the other stores,
    and one that cannot go in the column is refused by both against the field
    `quantity` — as a re-rendered field message on the form and as the AD-13
    envelope on the endpoint. This is the whole of the parity claimed for this
    column; the PARSERS still differ, deliberately, which is why the sibling
    class's docstring disclaims the rest of it.
    """

    def _product(self, test_storage):
        return CatalogService(test_storage).create_product(description='Reel')

    def test_the_html_form(self, client, test_storage, quantity, storable):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        # A form field is always a string; that difference is the reason the
        # two parsers cannot be shared, and the reason this is a table.
        resp = client.post(f'/products/{pid}/purchases/add',
                           data={'quantity': str(quantity)})
        if storable:
            assert resp.status_code == 302
            assert svc.get_purchases_for_product(pid)[0].quantity == quantity
        else:
            assert resp.status_code == 200
            # The whole sentence, so a message that dropped either half of the
            # rule fails here rather than passing on the ceiling alone.
            assert _FORM_QUANTITY_REFUSAL in resp.data.decode()
            assert svc.get_purchases_for_product(pid) == []

    def test_the_json_endpoint(self, client, test_storage, quantity, storable):
        svc = CatalogService(test_storage)
        pid = self._product(test_storage)

        resp = client.post(f'/api/products/{pid}/purchases',
                           json={'quantity': quantity})
        if storable:
            assert resp.status_code == 201
            assert svc.get_purchases_for_product(pid)[0].quantity == quantity
        else:
            assert resp.status_code == 400
            error = resp.get_json()['error']
            assert error['code'] == 'invalid_field'
            assert error['field'] == 'quantity'
            assert error['message'] == _JSON_QUANTITY_REFUSAL
            assert svc.get_purchases_for_product(pid) == []


@pytest.mark.unit
@pytest.mark.parametrize('field, body, fragment', [
    ('vendor', {'vendor': 'v' * 256}, '255 characters or fewer'),
    ('unit_price', {'unit_price': '-1.00'}, 'must not be negative'),
    ('quantity', {'quantity': 'abc'}, 'must be an integer'),
])
class TestTheDateOrderRuleIsJudgedLastOnTheJsonEndpoint:
    """The endpoint is first-failure-wins and its block comment says the
    cross-field date rule is judged LAST of all — not merely after the two date
    formats. Nothing else pinned that: the call can be hoisted above the
    `_PURCHASE_FIELD_LIMITS` loop, the price rule or the `quantity` parse and
    the rest of the suite stays green, at which point a body with an
    out-of-order pair stops naming the field the caller must actually fix. The
    HTML side needs no counterpart — it accumulates every error rather than
    choosing one.
    """

    def test_another_bad_field_is_named_before_the_out_of_order_pair(
            self, client, test_storage, field, body, fragment):
        svc = CatalogService(test_storage)
        pid = CatalogService(test_storage).create_product(description='Reel')

        resp = client.post(f'/api/products/{pid}/purchases',
                           json=dict(body, order_date='2026-01-05',
                                     received_date='2026-01-01'))
        assert resp.status_code == 400
        error = resp.get_json()['error']
        assert error['field'] == field
        assert fragment in error['message']
        assert 'must not be earlier than' not in error['message']
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
    `order_number`, `unit_price`) and the scanned-identifier card
    (`identifier_type`, `identifier_value`) exist on `add.html` alone;
    `product_edit` writes none of them and `edit.html` has no input and no
    `invalid-feedback` block for any of them. While those rules lived in the
    shared validator, a POST carrying one earned a 200 that wrote nothing and
    said nothing anywhere on the page.
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
        {'unit_price': 'abc'},                # the Purchase price rule (DW-22)
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
                     'unit_price', 'identifier_type', 'identifier_value'):
            assert f'name="{name}"' not in body

    @pytest.mark.parametrize('extra, message', [
        ({'quantity': '0'}, b'whole number greater than zero'),
        ({'vendor': 'x' * 300}, b'must be 255 characters or fewer'),
        ({'unit_price': 'abc'}, b'Unit Price must be a decimal number.'),
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
        # Story 5.1 — all three keyed by the SHARED validator, so all three
        # must have a slot on the edit form as well as on the create one.
        ('quantity_on_hand', {'quantity_on_hand': '-1'},
         'Quantity On Hand must be a whole number of zero or more and no more '
         'than 2147483647. Leave it blank to stop tracking the quantity.'),
        # Story 5.2, keyed by the same shared validator and so subject to the
        # same requirement: a slot on both forms, not just on the create one.
        ('reorder_threshold', {'reorder_threshold': '-1'},
         'Reorder Threshold must be a whole number of zero or more and no more '
         'than 2147483647. Leave it blank for no threshold.'),
        # Story 5.3, keyed by the same shared validator. The rendered `<select>`
        # cannot produce a value this rule refuses, which is exactly why the
        # slot has to exist on both templates: the submissions that DO reach it
        # are hand-built or truncated ones, and a refusal with nowhere to render
        # would be a silent 200 over a field the operator can see.
        ('stock_status', {'stock_status': 'bogus'},
         'Stock Status must be one of unknown, ok, low, out.'),
        ('location', {'location': 'x' * 101},
         'Location must be 100 characters or fewer.'),
        ('sub_location', {'sub_location': 'x' * 101},
         'Sub-Location must be 100 characters or fewer.'),
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
        transient read failure into data loss on the operator's next save.

        Story 5.3's Stock Status `<select>` is the one control on the page the
        degradation does NOT reach, and this test pins that rather than taking
        the route's word for it. The select has no empty state to fall back to,
        so a degraded `Not set` would look filled rather than blank — the worst
        failure shape on the form. It does not happen: the selected option is
        decided from `product.stock_status`, read off the row this route loaded
        BEFORE the failing call, so the degraded page still shows the STORED
        status and re-posting the page as handed re-posts what is already
        stored. Assert the rendered selection, because a fallback quietly
        re-pointed at the failed baseline would still pass a text-only check
        while silently reintroducing the wipe."""
        def _boom(*args, **kwargs):
            raise RuntimeError('backend down')

        pid = self._seed(test_storage)
        CatalogService(test_storage).update_product(pid, stock_status='low')
        monkeypatch.setattr(CatalogService, 'get_tags_for_product', _boom)

        resp = client.post(f'/products/edit/{pid}', data={'description': ''})

        assert resp.status_code == 200
        assert b'Label Description is required.' in resp.data
        # Degraded, not merged — and emphatically not a 500.
        body = resp.data.decode()
        assert _input_value(body, 'manufacturer') == ''
        assert b'a field shown empty below may not actually be empty' in resp.data
        # ...and the select is not among the degraded controls.
        assert _select_value(body, 'stock_status') == 'low'

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


# --- Story 5.1: tri-state quantity and location through the forms -----------


def _detail_field(body, element_id):
    """The rendered text of the detail page's `<dd id="...">`, whitespace
    collapsed — the `<dd>` spans several template lines, so a raw comparison
    would be asserting about the indentation."""
    match = re.search(r'<dd\b[^>]*\bid="%s"[^>]*>(.*?)</dd>' % re.escape(element_id),
                      body, re.S)
    assert match is not None, f'no <dd id="{element_id}"> on the page'
    text = re.sub(r'<[^>]+>', '', match.group(1))
    return html.unescape(' '.join(text.split()))


def _backdate_stamp(test_storage, product_id, when):
    """Force `quantity_verified_at` to `when`, bypassing the service.

    Written directly on purpose: the service's whole contract is that it stamps
    NOW, so there is no supported way to assert a count in the past — and every
    assertion about an age, or about a stamp that must NOT move, needs a stored
    value old enough to be unmistakable.
    """
    from sqlalchemy.orm import sessionmaker
    from app.database import Product

    Session = sessionmaker(bind=test_storage.engine)
    session = Session()
    try:
        session.query(Product).filter(Product.id == product_id).update(
            {'quantity_verified_at': when})
        session.commit()
    finally:
        session.close()
    return when


@pytest.mark.unit
class TestProductStockForms:
    """The three new controls on BOTH forms, and the write they produce.

    Add/edit parity is not decoration here: the rule that judges these fields
    lives in the shared validator, so a control missing from one template would
    be a rule that template's operator could never satisfy.
    """

    @pytest.mark.parametrize('url_factory', [
        lambda pid: '/products/add',
        lambda pid: f'/products/edit/{pid}',
    ], ids=['add', 'edit'])
    def test_both_forms_render_the_three_controls(
            self, client, test_storage, url_factory):
        pid = CatalogService(test_storage).create_product(description='Seed')
        body = client.get(url_factory(pid)).data.decode()
        tags = _form_controls(body, ['quantity_on_hand', 'location',
                                     'sub_location'])
        assert 'maxlength="10"' in tags[0]
        assert 'maxlength="100"' in tags[1]
        assert 'maxlength="100"' in tags[2]
        # The ids field-autocomplete.js auto-initializes, so the markup alone
        # wires the dropdowns — that is why this story needed no JS change.
        assert 'id="location-suggestions"' in body
        assert 'id="sub_location-suggestions"' in body
        # The blank-means-untracked meaning has to be ON the form: it is the one
        # thing about this field a reader cannot guess from its label.
        assert 'not tracked' in body

    def test_the_recount_checkbox_is_on_the_edit_form_only(
            self, client, test_storage):
        """The single deliberate exception to add/edit parity (Story 5.1).

        On a create there is no stored count to re-confirm — every non-blank
        quantity is a first assertion and always stamps — so the control would
        be a switch with nothing behind it, and `product_add` reads no such key.
        """
        pid = CatalogService(test_storage).create_product(description='Seed')

        edit_body = client.get(f'/products/edit/{pid}').data.decode()
        checkbox = _form_controls(edit_body, ['quantity_recounted'])[0]
        assert 'type="checkbox"' in checkbox
        assert not _checkbox_is_checked(edit_body, 'quantity_recounted')

        add_body = client.get('/products/add').data.decode()
        assert 'quantity_recounted' not in add_body

    def test_create_with_only_a_description_is_untracked(
            self, client, test_storage):
        resp = client.post('/products/add', data={'description': 'Bare'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(pid)
        assert product.quantity_on_hand is None
        assert product.quantity_verified_at is None
        assert product.location is None

    def test_create_carries_the_three_fields(self, client, test_storage):
        resp = client.post('/products/add', data={
            'description': 'Stocked', 'quantity_on_hand': '4',
            'location': 'Bin 7', 'sub_location': 'Left tray'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at is not None
        assert product.location == 'Bin 7'
        assert product.sub_location == 'Left tray'

    def test_a_recount_key_on_create_changes_nothing(self, client,
                                                     test_storage):
        """The I/O matrix's create row: the flag is identical to its absence
        here, because a create always stamps a non-blank quantity anyway."""
        resp = client.post('/products/add', data={
            'description': 'Flagged create', 'quantity_on_hand': '4',
            'quantity_recounted': 'on'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at is not None

    def test_the_new_fields_never_record_a_purchase(self, client, test_storage):
        """`quantity_on_hand` is a PRODUCT column and shares a page with the
        first-receipt `quantity`, which is a Purchase column. The two must stay
        entirely separate: a stock count is not a shipment, so nothing here may
        reach `_RECEIPT_TRIGGER_FIELDS`."""
        from app.main.routes import _RECEIPT_FIELDS, _RECEIPT_TRIGGER_FIELDS

        for name in ('quantity_on_hand', 'location', 'sub_location',
                     'quantity_recounted'):
            assert name not in _RECEIPT_TRIGGER_FIELDS
            assert name not in _RECEIPT_FIELDS

        resp = client.post('/products/add', data={
            'description': 'No receipt here', 'quantity_on_hand': '4',
            'location': 'Bin 7'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []

    def test_edit_asserts_zero_then_n_then_untracks(self, client, test_storage):
        """The three states walked in order, through the form each time."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Walked')

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'quantity_on_hand': '0'})
        product = svc.get_product(pid)
        assert product.quantity_on_hand == 0
        assert product.quantity_verified_at is not None

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'quantity_on_hand': '4'})
        assert svc.get_product(pid).quantity_on_hand == 4

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'quantity_on_hand': ''})
        product = svc.get_product(pid)
        assert product.quantity_on_hand is None
        assert product.quantity_verified_at is None

    def test_a_post_without_the_key_leaves_the_quantity_alone(
            self, client, test_storage):
        """The partial-update rule: absent is not blank. A non-browser client
        that PATCHes one field must not untrack the product."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Untouched', quantity_on_hand='4')
        stamp = svc.get_product(pid).quantity_verified_at

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Renamed'})
        assert resp.status_code == 302
        product = svc.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == stamp

    def test_reposting_the_rendered_edit_form_keeps_a_tracked_zero(
            self, client, test_storage):
        """The bug a `{{ x or '' }}` in the template would cause: 0 is falsy, so
        a naive render blanks the field, and this form reads blank as
        "stop tracking". A client that changes nothing would untrack every
        product sitting at zero."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Empty bin', quantity_on_hand='0',
                                 location='Bin 7', sub_location='Left tray')

        body = client.get(f'/products/edit/{pid}').data.decode()
        assert _input_value(body, 'quantity_on_hand') == '0'
        client.post(f'/products/edit/{pid}', data=_rendered_edit_form(body))

        product = svc.get_product(pid)
        assert product.quantity_on_hand == 0
        assert product.location == 'Bin 7'
        assert product.sub_location == 'Left tray'

    @pytest.mark.parametrize('bad', ['-1', '2.5', '1_0', '٥', 'abc',
                                     '2147483648'],
                             ids=['negative', 'decimal', 'underscore',
                                  'non_ascii_numeral', 'letters', 'over_int32'])
    def test_a_bad_quantity_rerenders_with_a_keyed_error_and_writes_nothing(
            self, client, test_storage, bad):
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Guarded', quantity_on_hand='4')

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Guarded',
                                 'quantity_on_hand': bad})
        assert resp.status_code == 200
        body = resp.data.decode()
        assert any(m.startswith('Quantity On Hand must be')
                   for m in _shown_keyed_errors(body)), body
        # The message must hang off the FIELD, not off the unkeyed fallback.
        assert 'id="form-error-quantity_on_hand"' not in body
        assert svc.get_product(pid).quantity_on_hand == 4  # nothing written

    def test_the_bad_quantity_also_refuses_a_create(self, client, product_ids):
        resp = client.post('/products/add',
                           data={'description': 'Guarded', 'quantity_on_hand': '-1'})
        assert resp.status_code == 200
        assert any(m.startswith('Quantity On Hand must be')
                   for m in _shown_keyed_errors(resp.data.decode()))
        assert product_ids() == set()

    @pytest.mark.parametrize('field, message', [
        ('location', 'Location must be 100 characters or fewer.'),
        ('sub_location', 'Sub-Location must be 100 characters or fewer.'),
    ])
    def test_an_overlong_location_rerenders_with_a_keyed_error(
            self, client, test_storage, field, message):
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Guarded', location='Bin 7')

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Guarded', field: 'x' * 101})
        assert resp.status_code == 200
        assert message in _shown_keyed_errors(resp.data.decode())
        assert svc.get_product(pid).location == 'Bin 7'  # nothing written

    def test_a_refused_submit_round_trips_the_typed_values(
            self, client, test_storage):
        """The typed-but-refused values come back on the re-render, so a single
        bad field does not cost the operator the other two — the recount tick
        included, since re-ticking a box the operator already ticked is how a
        refused submit would silently become a non-recount."""
        pid = CatalogService(test_storage).create_product(description='Guarded')
        resp = client.post(f'/products/edit/{pid}', data={
            'description': 'Guarded', 'quantity_on_hand': 'abc',
            'location': 'Bin 7', 'sub_location': 'Left tray',
            'quantity_recounted': 'on'})
        body = resp.data.decode()
        assert _input_value(body, 'quantity_on_hand') == 'abc'
        assert _input_value(body, 'location') == 'Bin 7'
        assert _input_value(body, 'sub_location') == 'Left tray'
        assert _checkbox_is_checked(body, 'quantity_recounted')

    def test_an_unticked_box_does_not_round_trip_as_ticked(
            self, client, test_storage):
        """The other half, and the one that would be a real defect: a re-render
        that ticked the box for an operator who did not would turn their next
        save into a recount they never asked for."""
        pid = CatalogService(test_storage).create_product(description='Guarded')
        resp = client.post(f'/products/edit/{pid}', data={
            'description': 'Guarded', 'quantity_on_hand': 'abc'})
        assert not _checkbox_is_checked(resp.data.decode(),
                                        'quantity_recounted')


@pytest.mark.unit
class TestTheVerificationStampOnlyMovesOnAnAssertion:
    """The defect the re-stamp rule exists to prevent, exercised through the
    real form rather than through the service.

    The edit template renders `quantity_on_hand` pre-filled, so every browser
    save re-posts the key — which is why key presence cannot be the assertion
    trigger. These tests re-post the form EXACTLY as it was rendered, changing
    one thing at a time, and compare the stored stamp for EQUALITY against the
    datetime captured before the call: a `>=` or an identity check would pass
    whether or not the stamp moved and could not fail.
    """

    def test_editing_only_the_description_does_not_move_the_stamp(
            self, client, test_storage):
        """The whole point of FR25: the age shown is the age of the COUNT, so
        fixing a typo three months later must leave the count reading three
        months old."""
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Typo', quantity_on_hand='4')
        old = _backdate_stamp(test_storage, pid,
                              datetime.now() - timedelta(days=95))

        body = client.get(f'/products/edit/{pid}').data.decode()
        data = _rendered_edit_form(body)
        assert data['quantity_on_hand'] == '4'
        assert 'quantity_recounted' not in data
        data['description'] = 'Typo fixed'

        resp = client.post(f'/products/edit/{pid}', data=data)
        assert resp.status_code == 302

        product = svc.get_product(pid)
        assert product.description == 'Typo fixed'
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == old

        text = _detail_field(client.get(f'/products/{pid}').data.decode(),
                             'product-quantity')
        assert text == 'In stock: 4 (counted 3 months ago)'

    def test_the_same_round_trip_with_the_box_ticked_moves_the_stamp(
            self, client, test_storage):
        """The one case a value comparison cannot see, and the reason the box
        exists: the operator counted again and got the same number."""
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Recounted', quantity_on_hand='4')
        old = _backdate_stamp(test_storage, pid,
                              datetime.now() - timedelta(days=95))

        body = client.get(f'/products/edit/{pid}').data.decode()
        data = _rendered_edit_form(body)
        data['quantity_recounted'] = 'on'

        resp = client.post(f'/products/edit/{pid}', data=data)
        assert resp.status_code == 302

        product = svc.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at > old

        text = _detail_field(client.get(f'/products/{pid}').data.decode(),
                             'product-quantity')
        assert text == 'In stock: 4 (counted just now)'

    def test_an_empty_recount_key_is_not_a_recount(
            self, client, test_storage):
        """A browser omits an unticked checkbox, but a JS serializer that posts
        every control sends `quantity_recounted=` for it. Presence alone would
        read that as "I counted it again" and refresh a date nobody earned —
        and it would disagree with `edit.html`, which re-renders the box UNTICKED
        for exactly the same body.
        """
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Serialized',
                                 quantity_on_hand='4')
        old = _backdate_stamp(test_storage, pid,
                              datetime.now() - timedelta(days=95))

        data = _rendered_edit_form(
            client.get(f'/products/edit/{pid}').data.decode())
        data['quantity_recounted'] = ''

        assert client.post(f'/products/edit/{pid}',
                           data=data).status_code == 302
        assert svc.get_product(pid).quantity_verified_at == old

    def test_a_whitespace_recount_leaves_the_box_unticked_on_re_render(
            self, client, test_storage):
        """The route reads `quantity_recounted='   '` as NOT a recount, because
        its test strips. `edit.html` must apply the SAME test: reading that body
        as truthy would re-render the box ticked, and the operator's next save
        of the form they were handed would then refresh a verification date this
        save had just correctly refused to touch.
        """
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Whitespace', quantity_on_hand='4')
        old = _backdate_stamp(test_storage, pid,
                              datetime.now() - timedelta(days=95))

        data = _rendered_edit_form(
            client.get(f'/products/edit/{pid}').data.decode())
        data['quantity_recounted'] = '   '
        # Forced down the re-render path, which is where the disagreement shows.
        data['description'] = ''

        html = client.post(f'/products/edit/{pid}', data=data).data.decode()
        assert svc.get_product(pid).quantity_verified_at == old

        box = re.search(r'<input[^>]*name="quantity_recounted"[^>]*>', html)
        assert box is not None
        assert 'checked' not in box.group(0)

    def test_a_stamp_without_a_count_shows_no_age(self, client, test_storage):
        """The write contract moves the two columns together, so this row is one
        only a restored backup or a hand-run UPDATE can produce. The page must
        still not read `Not tracked (counted 3 months ago)` — an age for a count
        the same line says does not exist.
        """
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Orphaned stamp')
        _backdate_stamp(test_storage, pid,
                        datetime.now() - timedelta(days=95))

        text = _detail_field(client.get(f'/products/{pid}').data.decode(),
                             'product-quantity')
        assert text == 'Not tracked'

    def test_a_changed_quantity_moves_the_stamp_without_the_box(
            self, client, test_storage):
        """A different number speaks for itself — the box is for the unchanged
        case only, and requiring it for a changed one would make every ordinary
        count silently keep the old date."""
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Changed', quantity_on_hand='4')
        old = _backdate_stamp(test_storage, pid,
                              datetime.now() - timedelta(days=95))

        body = client.get(f'/products/edit/{pid}').data.decode()
        data = _rendered_edit_form(body)
        data['quantity_on_hand'] = '5'

        assert client.post(f'/products/edit/{pid}',
                           data=data).status_code == 302
        product = svc.get_product(pid)
        assert product.quantity_on_hand == 5
        assert product.quantity_verified_at > old

    def test_ticking_the_box_while_clearing_the_quantity_untracks(
            self, client, test_storage):
        """A recount that finds the product untracked is an untrack, not a
        verification: the flag is ignored and both columns go to NULL."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Untrack', quantity_on_hand='4')

        assert client.post(f'/products/edit/{pid}', data={
            'description': 'Untrack', 'quantity_on_hand': '',
            'quantity_recounted': 'on'}).status_code == 302

        product = svc.get_product(pid)
        assert product.quantity_on_hand is None
        assert product.quantity_verified_at is None

    def test_the_box_alone_with_no_quantity_key_changes_nothing(
            self, client, test_storage):
        """A non-browser client that sends only the flag has asserted nothing:
        there is no submitted count for it to qualify."""
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Flag alone', quantity_on_hand='4')
        old = _backdate_stamp(test_storage, pid,
                              datetime.now() - timedelta(days=95))

        assert client.post(f'/products/edit/{pid}', data={
            'description': 'Flag alone',
            'quantity_recounted': 'on'}).status_code == 302

        product = svc.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == old

    def test_a_tracked_quantity_with_no_stamp_is_repaired(
            self, client, test_storage):
        """A state the write contract otherwise makes impossible. Left alone it
        would render a count with no age at all, forever."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Ageless', quantity_on_hand='4')
        _backdate_stamp(test_storage, pid, None)

        body = client.get(f'/products/edit/{pid}').data.decode()
        assert client.post(f'/products/edit/{pid}',
                           data=_rendered_edit_form(body)).status_code == 302

        assert svc.get_product(pid).quantity_verified_at is not None


@pytest.mark.unit
class TestProductDetailQuantityDisplay:
    """FR23/FR24/FR25 on the page: three distinct literals plus an age."""

    def test_untracked_reads_not_tracked_and_shows_no_age(
            self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='Bare')
        body = client.get(f'/products/{pid}').data.decode()
        assert _detail_field(body, 'product-quantity') == 'Not tracked'
        assert 'counted' not in body
        assert _detail_field(body, 'product-location') == '—'

    def test_zero_reads_in_stock_zero_not_a_dash(self, client, test_storage):
        """The reading FR24 forbids losing: a tracked zero must not collapse
        into the same `—` an absent field uses, and must not read as untracked."""
        pid = CatalogService(test_storage).create_product(
            description='Empty bin', quantity_on_hand='0')
        text = _detail_field(client.get(f'/products/{pid}').data.decode(),
                             'product-quantity')
        assert text.startswith('In stock: 0')
        assert 'Not tracked' not in text

    def test_n_reads_in_stock_n_with_an_age(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(
            description='Stocked', quantity_on_hand='4')
        text = _detail_field(client.get(f'/products/{pid}').data.decode(),
                             'product-quantity')
        assert text.startswith('In stock: 4')
        assert '(counted just now)' in text

    def test_the_age_reflects_the_stored_stamp(self, client, test_storage):
        """Stale, not silently corrected: the page states how old the count is."""
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Stale', quantity_on_hand='4')
        _backdate_stamp(test_storage, pid,
                        datetime.now() - timedelta(days=95))

        text = _detail_field(client.get(f'/products/{pid}').data.decode(),
                             'product-quantity')
        assert text == 'In stock: 4 (counted 3 months ago)'

    def test_the_location_pair_renders_joined(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(
            description='Shelved', location='Bin 7', sub_location='Left tray')
        body = client.get(f'/products/{pid}').data.decode()
        assert _detail_field(body, 'product-location') == 'Bin 7 / Left tray'

    def test_receiving_a_purchase_changes_neither_column(
            self, client, test_storage):
        """FR25's hard boundary: a receipt is not a count. Exercised through the
        real purchase form, because that is the path an operator takes."""
        from datetime import date

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Received', quantity_on_hand='4')
        before = svc.get_product(pid)

        resp = client.post(f'/products/{pid}/purchases/add', data={
            'vendor': 'Mouser', 'quantity': '10',
            'order_date': date(2026, 7, 1).isoformat(),
            'received_date': date(2026, 7, 9).isoformat()})
        assert resp.status_code == 302
        assert len(svc.get_purchases_for_product(pid)) == 1

        after = svc.get_product(pid)
        assert after.quantity_on_hand == before.quantity_on_hand == 4
        assert after.quantity_verified_at == before.quantity_verified_at
        text = _detail_field(client.get(f'/products/{pid}').data.decode(),
                             'product-quantity')
        assert text.startswith('In stock: 4')


# --- Story 5.2: the reorder threshold and the derived signal ----------------


@pytest.mark.unit
class TestProductReorderThresholdForms:
    """FR26's control on BOTH forms, and the write it produces.

    Parity is not decoration: the rule that judges this field lives in the
    SHARED validator, so a control missing from one template would be a rule
    that template's operator could never satisfy.
    """

    @pytest.mark.parametrize('url_factory', [
        lambda pid: '/products/add',
        lambda pid: f'/products/edit/{pid}',
    ], ids=['add', 'edit'])
    def test_both_forms_render_the_control_identically(
            self, client, test_storage, url_factory):
        pid = CatalogService(test_storage).create_product(description='Seed')
        body = client.get(url_factory(pid)).data.decode()
        tag = _form_controls(body, ['reorder_threshold'])[0]
        assert 'name="reorder_threshold"' in tag
        # Same cap as Quantity On Hand: both columns are the same 32-bit
        # integer, so a limit either side did not share would let one form
        # accept what the other refused.
        assert 'maxlength="10"' in tag
        # The card is still the Story 5.1 one, at the same anchor, with its
        # suggestion divs intact — the regrid must not have moved anything.
        assert 'id="stock-and-location"' in body
        assert 'id="location-suggestions"' in body
        assert 'id="sub_location-suggestions"' in body
        # What blank means has to be ON the form: it is the one thing about this
        # field a reader cannot guess from its label.
        assert 'blank</strong> for no threshold' in body

    def test_create_with_only_a_description_has_no_threshold(
            self, client, test_storage):
        resp = client.post('/products/add', data={'description': 'Bare'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert CatalogService(test_storage).get_product(pid).reorder_threshold \
            is None

    def test_create_carries_a_typed_threshold(self, client, test_storage):
        resp = client.post('/products/add', data={
            'description': 'Watched', 'reorder_threshold': '3'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert CatalogService(test_storage).get_product(pid).reorder_threshold \
            == 3

    def test_a_threshold_round_trips_through_the_edit_form(
            self, client, test_storage):
        """Typed on create, offered back on edit, shown on the detail page —
        the whole loop, because a value that stores but does not render back is
        a value the operator cannot revise."""
        resp = client.post('/products/add', data={
            'description': 'Watched', 'reorder_threshold': '3'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        body = client.get(f'/products/edit/{pid}').data.decode()
        assert _input_value(body, 'reorder_threshold') == '3'
        assert _detail_field(client.get(f'/products/{pid}').data.decode(),
                             'product-reorder-threshold') == '3'

    def test_a_zero_threshold_round_trips_rather_than_rendering_blank(
            self, client, test_storage):
        """The falsy-zero hazard on the form side: `{{ x or '' }}` would render
        a deliberate `0` as an empty box, which this form reads as "no
        threshold" — so an operator who merely re-saved the page would lose the
        strictest threshold there is."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Zero rule', reorder_threshold='0')

        body = client.get(f'/products/edit/{pid}').data.decode()
        assert _input_value(body, 'reorder_threshold') == '0'

        client.post(f'/products/edit/{pid}', data=_rendered_edit_form(body))
        assert svc.get_product(pid).reorder_threshold == 0

    def test_edit_sets_then_clears_the_threshold(self, client, test_storage):
        """Set, then blank. Clearing must leave the quantity columns exactly
        where they were — captured first, so the assertion can fail."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Walked', quantity_on_hand='4')
        stamp = svc.get_product(pid).quantity_verified_at

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'reorder_threshold': '3'})
        assert svc.get_product(pid).reorder_threshold == 3

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'reorder_threshold': ''})
        product = svc.get_product(pid)
        assert product.reorder_threshold is None
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == stamp

    def test_a_post_without_the_key_leaves_the_threshold_alone(
            self, client, test_storage):
        """The partial-update rule: absent is not blank. A non-browser client
        that PATCHes one field must not drop the threshold."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Untouched',
                                 reorder_threshold='3')

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Renamed'})
        assert resp.status_code == 302
        assert svc.get_product(pid).reorder_threshold == 3

    def test_reposting_the_rendered_edit_form_keeps_the_threshold(
            self, client, test_storage):
        """The re-post regression, taken verbatim from what the page rendered
        and with only the description changed — the shape of every real browser
        save. Anything the form fails to round-trip is lost here rather than at
        the moment the operator notices."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Watched', quantity_on_hand='4',
                                 reorder_threshold='3')

        body = client.get(f'/products/edit/{pid}').data.decode()
        data = _rendered_edit_form(body)
        assert data['reorder_threshold'] == '3'
        data['description'] = 'Watched (renamed)'

        assert client.post(f'/products/edit/{pid}',
                           data=data).status_code == 302
        product = svc.get_product(pid)
        assert product.description == 'Watched (renamed)'
        assert product.reorder_threshold == 3
        assert product.quantity_on_hand == 4

    def test_leading_zeros_store_the_magnitude(self, client, test_storage):
        """`007` is seven. The bound is on what the number IS, not on how it was
        typed."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Padded')
        client.post(f'/products/edit/{pid}', data={'description': 'Padded',
                                                   'reorder_threshold': '007'})
        assert svc.get_product(pid).reorder_threshold == 7

    def test_a_very_long_zero_string_is_the_zero_it_names(
            self, client, test_storage):
        """`int()` is not total over digit strings — CPython refuses one longer
        than 4300 — so a pathological pad must not reach it unstripped and turn
        a valid `0` into an HTML 500. The shared validator strips first, which
        is the whole reason its bound is on the magnitude."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Padded to death')
        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Padded to death',
                                 'reorder_threshold': '0' * 5000})
        assert resp.status_code == 302
        assert svc.get_product(pid).reorder_threshold == 0

    @pytest.mark.parametrize('bad', ['-1', '2.5', '1_0', '٥', 'abc',
                                     '2147483648'],
                             ids=['negative', 'decimal', 'underscore',
                                  'non_ascii_numeral', 'letters', 'over_int32'])
    def test_a_bad_threshold_rerenders_with_a_keyed_error_and_writes_nothing(
            self, client, test_storage, bad):
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Guarded', reorder_threshold='3')

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Guarded',
                                 'reorder_threshold': bad})
        assert resp.status_code == 200
        body = resp.data.decode()
        assert any(m.startswith('Reorder Threshold must be')
                   for m in _shown_keyed_errors(body)), body
        # The message must hang off the FIELD, not off edit.html's unkeyed
        # fallback block — which is what `keyed_error_fields` decides.
        assert 'id="form-error-reorder_threshold"' not in body
        assert svc.get_product(pid).reorder_threshold == 3  # nothing written

    def test_the_bad_threshold_also_refuses_a_create(self, client,
                                                     product_ids):
        resp = client.post('/products/add', data={'description': 'Guarded',
                                                  'reorder_threshold': '-1'})
        assert resp.status_code == 200
        assert any(m.startswith('Reorder Threshold must be')
                   for m in _shown_keyed_errors(resp.data.decode()))
        assert product_ids() == set()

    def test_a_refused_submit_round_trips_the_typed_threshold(
            self, client, test_storage):
        """One bad field must not cost the operator the value they typed into
        another — including this one when it is not the bad field."""
        pid = CatalogService(test_storage).create_product(description='Guarded')
        resp = client.post(f'/products/edit/{pid}', data={
            'description': 'Guarded', 'quantity_on_hand': 'abc',
            'reorder_threshold': '3'})
        assert _input_value(resp.data.decode(), 'reorder_threshold') == '3'

    def test_the_threshold_never_records_a_purchase(self, client,
                                                    test_storage):
        """It is a PRODUCT column and shares a page with the first-receipt
        block. Nothing on the purchase path may write it, so it may not reach
        either receipt tuple."""
        from app.main.routes import _RECEIPT_FIELDS, _RECEIPT_TRIGGER_FIELDS

        assert 'reorder_threshold' not in _RECEIPT_TRIGGER_FIELDS
        assert 'reorder_threshold' not in _RECEIPT_FIELDS

        resp = client.post('/products/add', data={
            'description': 'No receipt here', 'reorder_threshold': '3'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []

    def test_receiving_a_purchase_changes_neither_the_threshold_nor_the_count(
            self, client, test_storage):
        """The I/O matrix's receipt row, through the real purchase form."""
        from datetime import date

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Received', quantity_on_hand='4',
                                 reorder_threshold='3')
        before = svc.get_product(pid)

        resp = client.post(f'/products/{pid}/purchases/add', data={
            'vendor': 'Mouser', 'quantity': '10',
            'order_date': date(2026, 7, 1).isoformat(),
            'received_date': date(2026, 7, 9).isoformat()})
        assert resp.status_code == 302

        after = svc.get_product(pid)
        assert after.reorder_threshold == before.reorder_threshold == 3
        assert after.quantity_on_hand == before.quantity_on_hand == 4
        assert after.quantity_verified_at == before.quantity_verified_at


@pytest.mark.unit
class TestProductDetailReorderSignal:
    """FR26/FR30 on the page: the stored threshold, and the derived signal.

    The signal is read off `Product.is_effective_low` — the route writes no
    comparison and neither does the template (AD-6) — so what these tests pin is
    that the page reports what that one predicate says, in the states where a
    hand-written copy of the rule would have gone wrong.
    """

    def _detail(self, client, pid):
        return client.get(f'/products/{pid}').data.decode()

    def test_a_product_below_its_threshold_reads_low(self, client,
                                                     test_storage):
        pid = CatalogService(test_storage).create_product(
            description='Running out', quantity_on_hand='2',
            reorder_threshold='3')
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-reorder-threshold') == '3'
        assert _detail_field(body, 'product-effective-low') == 'Low stock'

    def test_a_product_exactly_at_its_threshold_reads_low(self, client,
                                                          test_storage):
        """The comparison is `<=`: the threshold is the point at which to
        reorder, not the point below it."""
        pid = CatalogService(test_storage).create_product(
            description='At the line', quantity_on_hand='3',
            reorder_threshold='3')
        assert _detail_field(self._detail(client, pid),
                             'product-effective-low') == 'Low stock'

    def test_a_product_above_its_threshold_reads_no_signal(self, client,
                                                           test_storage):
        pid = CatalogService(test_storage).create_product(
            description='Well stocked', quantity_on_hand='4',
            reorder_threshold='3')
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-reorder-threshold') == '3'
        assert _detail_field(body, 'product-effective-low') == '—'

    def test_a_zero_threshold_renders_as_zero_not_as_a_dash(self, client,
                                                            test_storage):
        """The reading a `or '—'` in the template would lose: a deliberate `0`
        is the strictest threshold there is, and rendering it as the same dash
        an unset one uses reverses what it says."""
        pid = CatalogService(test_storage).create_product(
            description='Zero rule', reorder_threshold='0')
        assert _detail_field(self._detail(client, pid),
                             'product-reorder-threshold') == '0'

    def test_a_zero_threshold_signals_only_once_the_count_reaches_zero(
            self, client, test_storage):
        svc = CatalogService(test_storage)
        empty = svc.create_product(description='Empty', quantity_on_hand='0',
                                   reorder_threshold='0')
        stocked = svc.create_product(description='One left',
                                     quantity_on_hand='1',
                                     reorder_threshold='0')
        assert _detail_field(self._detail(client, empty),
                             'product-effective-low') == 'Low stock'
        assert _detail_field(self._detail(client, stocked),
                             'product-effective-low') == '—'

    def test_no_threshold_never_signals_however_empty(self, client,
                                                      test_storage):
        """FR30: with no threshold set the branch is false however the quantity
        reads. "None on hand" is not the same claim as "below the point I said I
        wanted to reorder at" — the operator never named one."""
        pid = CatalogService(test_storage).create_product(
            description='No rule', quantity_on_hand='0')
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-reorder-threshold') == '—'
        assert _detail_field(body, 'product-effective-low') == '—'

    def test_an_untracked_product_with_a_threshold_never_signals(
            self, client, test_storage):
        """A threshold with nothing to compare against says nothing. It is still
        SHOWN, because the operator set it and will want it back the day they
        start counting."""
        pid = CatalogService(test_storage).create_product(
            description='Rule, no count', reorder_threshold='3')
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-quantity') == 'Not tracked'
        assert _detail_field(body, 'product-reorder-threshold') == '3'
        assert _detail_field(body, 'product-effective-low') == '—'

    def test_a_bare_product_shows_both_rows_empty(self, client, test_storage):
        pid = CatalogService(test_storage).create_product(description='Bare')
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-reorder-threshold') == '—'
        assert _detail_field(body, 'product-effective-low') == '—'

    def test_the_signal_follows_its_inputs_across_edits_writing_nothing(
            self, client, test_storage):
        """Derived at read, so it changes the moment the inputs do and with no
        write of its own — the `updated_at` check is what makes "no write" an
        assertion rather than an assumption."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Crossing', quantity_on_hand='2',
                                 reorder_threshold='3')
        assert _detail_field(self._detail(client, pid),
                             'product-effective-low') == 'Low stock'

        touched_at = svc.get_product(pid).updated_at
        # Drawing the page again is not an edit.
        self._detail(client, pid)
        assert svc.get_product(pid).updated_at == touched_at

        client.post(f'/products/edit/{pid}', data={'description': 'Crossing',
                                                   'quantity_on_hand': '4'})
        assert _detail_field(self._detail(client, pid),
                             'product-effective-low') == '—'

        client.post(f'/products/edit/{pid}', data={'description': 'Crossing',
                                                   'reorder_threshold': ''})
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-reorder-threshold') == '—'
        assert _detail_field(body, 'product-effective-low') == '—'

    def test_the_new_rows_do_not_intrude_on_the_quantity_row(
            self, client, test_storage):
        """`#product-quantity`'s rendered text is pinned character for character
        by the Story 5.1 tests, so the new rows must sit BESIDE it rather than
        inside it."""
        pid = CatalogService(test_storage).create_product(
            description='Running out', quantity_on_hand='2',
            reorder_threshold='3')
        text = _detail_field(self._detail(client, pid), 'product-quantity')
        assert text == 'In stock: 2 (counted just now)'

    def test_each_row_carries_the_label_the_manual_promises(self, client,
                                                            test_storage):
        """One concept wears four names here — the property `is_effective_low`,
        the id `product-effective-low`, the label "Reorder signal" and the badge
        "Low stock" — and every other assertion in this file locates by id. So
        the two `<dt>` texts, the only names the operator and
        `docs/user-manual.md` actually share, are pinned to the values beside
        them: swapped labels would leave the whole suite green while the page
        told the operator its threshold was its signal."""
        pid = CatalogService(test_storage).create_product(
            description='Running out', quantity_on_hand='2',
            reorder_threshold='3')
        body = self._detail(client, pid)
        for label, element_id in (('Reorder threshold',
                                   'product-reorder-threshold'),
                                  ('Reorder signal', 'product-effective-low'),
                                  # Story 5.3's row, pinned for the same
                                  # reason: `Stock status` is the name the
                                  # manual and the operator share, and it sits
                                  # one row away from `Reorder signal`, which
                                  # it now feeds — swapped labels would leave
                                  # the page claiming the derived signal was
                                  # the stored assertion.
                                  ('Stock status', 'product-stock-status')):
            pattern = (r'<dt\b[^>]*>\s*%s\s*</dt>\s*<dd\b[^>]*\bid="%s"'
                       % (re.escape(label), re.escape(element_id)))
            assert re.search(pattern, body), (
                f'no <dt>{label}</dt> immediately before '
                f'<dd id="{element_id}">')


# --- Story 5.3: the manual stock status through the forms and the page ------


def _backdate_status_stamp(test_storage, product_id, when):
    """Force `stock_status_at` to `when`, bypassing the service.

    The sibling of `_backdate_stamp` above, written directly for the same
    reason: the service only ever stamps NOW, so there is no supported way to
    assert a status in the past — and every assertion about a displayed age, or
    about a date that must NOT move, needs a stored value old enough to be
    unmistakable in the rendered words.
    """
    from sqlalchemy.orm import sessionmaker
    from app.database import Product

    Session = sessionmaker(bind=test_storage.engine)
    session = Session()
    try:
        session.query(Product).filter(Product.id == product_id).update(
            {'stock_status_at': when})
        session.commit()
    finally:
        session.close()
    return when


# The four options both forms must offer, in order, as `(value, label)`. Spelled
# out here rather than imported from the route for the reason every list in this
# file is: importing the mapping under test would make the assertion true by
# construction, and the LABELS are half the contract — they are the only names
# the operator and `docs/user-manual.md` share.
_STOCK_STATUS_OPTIONS = [
    ('unknown', 'Not set'),
    ('ok', 'OK'),
    ('low', 'Low'),
    ('out', 'Out of stock'),
]


@pytest.mark.unit
class TestProductStockStatusForms:
    """FR28/FR29's control on BOTH forms, and the write it produces.

    Parity is not decoration: the rule that judges this field lives in the
    SHARED validator, so a control missing from one template would be a rule
    that template's operator could never satisfy. The option LIST is part of the
    parity — a form offering three choices where the other offers four would let
    a value be set on one page and be unreachable on the other.
    """

    @pytest.mark.parametrize('url_factory', [
        lambda pid: '/products/add',
        lambda pid: f'/products/edit/{pid}',
    ], ids=['add', 'edit'])
    def test_both_forms_render_the_same_control_and_option_list(
            self, client, test_storage, url_factory):
        pid = CatalogService(test_storage).create_product(description='Seed')
        body = client.get(url_factory(pid)).data.decode()

        tag = _form_controls(body, ['stock_status'])[0]
        assert '<select' in tag
        assert 'name="stock_status"' in tag

        options = _select_options(body, 'stock_status')
        assert [(value, label) for value, label, _ in options] == \
            _STOCK_STATUS_OPTIONS
        # No empty first option, unlike the scanned-identifier type select: this
        # field has a real default and `Not set` IS it, so a blank option would
        # be a second spelling of the same state — and the server refuses a
        # blank rather than accepting one.
        assert all(value for value, _label, _selected in options)

        # The card is still the Story 5.1 one, at the same anchor, with its
        # suggestion divs intact — the fifth control must not have moved
        # anything.
        assert 'id="stock-and-location"' in body
        assert 'id="location-suggestions"' in body
        assert 'id="sub_location-suggestions"' in body

        # The row break, which both templates' grid comments call the thing that
        # leaves the 576–767 px band behaving as it did before a FIFTH control
        # joined four that paired evenly. Without it the status cell pairs with
        # `location` and every later cell shifts, which no other assertion here
        # would notice — the ids above all survive a reflow. Asserted by
        # POSITION, between the status control and the location one, because a
        # `w-100` anywhere else in the card is not the break this needs.
        after_status = body.index('name="stock_status"')
        assert 0 < body.index('<div class="w-100"></div>', after_status) \
            < body.index('id="location"', after_status), (
                'the w-100 row break is not between the stock status control '
                'and the location one; the 576-767px pairings have moved')

        # What the field means has to be ON the form: that it is only ever what
        # the operator said, and what the date beside it is the date OF.
        assert 'only ever what you said' in body
        assert '<em>changed</em>' in body

    @pytest.mark.parametrize('url_factory', [
        lambda pid: '/products/add',
        lambda pid: f'/products/edit/{pid}',
    ], ids=['add', 'edit'])
    def test_both_forms_default_to_not_set(self, client, test_storage,
                                           url_factory):
        """A fresh product has no assertion, and the control has to SAY so
        rather than leaving the browser to pick. Nothing selected renders
        identically to `Not set` selected and submits the same value — until an
        option is inserted above it, at which point a form that never marked its
        default starts silently asserting whatever now sits first."""
        pid = CatalogService(test_storage).create_product(description='Seed')
        body = client.get(url_factory(pid)).data.decode()

        selected = [value for value, _label, is_selected
                    in _select_options(body, 'stock_status') if is_selected]
        assert selected == ['unknown']

    def test_create_with_only_a_description_has_no_assertion(self, client,
                                                             test_storage):
        resp = client.post('/products/add', data={'description': 'Bare'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(pid)
        assert product.stock_status == 'unknown'
        assert product.stock_status_at is None

    @pytest.mark.parametrize('status', ['ok', 'low', 'out'])
    def test_create_carries_a_chosen_status(self, client, test_storage, status):
        resp = client.post('/products/add', data={'description': 'Flagged',
                                                  'stock_status': status})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        product = CatalogService(test_storage).get_product(pid)
        assert product.stock_status == status
        assert product.stock_status_at is not None

    @pytest.mark.parametrize('status, label', _STOCK_STATUS_OPTIONS)
    def test_each_value_round_trips_through_the_edit_form_and_the_page(
            self, client, test_storage, status, label):
        """Chosen on create, offered back on edit, shown on the detail page —
        the whole loop, because a value that stores but does not render back is
        a value the operator cannot revise."""
        resp = client.post('/products/add', data={'description': 'Walked',
                                                  'stock_status': status})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])

        body = client.get(f'/products/edit/{pid}').data.decode()
        assert _select_value(body, 'stock_status') == status

        detail = _detail_field(client.get(f'/products/{pid}').data.decode(),
                               'product-stock-status')
        # The label, with or without the age parenthetical that only a real
        # assertion carries.
        assert detail.startswith(label)

    def test_edit_flags_then_withdraws_the_assertion(self, client,
                                                     test_storage):
        """Set, then back to `Not set`. Withdrawing must clear the date with the
        flag, and must leave the quantity columns exactly where they were —
        captured first, so the assertion can fail."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Walked', quantity_on_hand='4')
        stamp = svc.get_product(pid).quantity_verified_at

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'stock_status': 'low'})
        product = svc.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at is not None

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'stock_status': 'unknown'})
        product = svc.get_product(pid)
        assert product.stock_status == 'unknown'
        assert product.stock_status_at is None
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == stamp

    def test_a_post_without_the_key_leaves_both_columns_alone(self, client,
                                                              test_storage):
        """The partial-update rule: absent is not `unknown`. A non-browser
        client that PATCHes one field must not withdraw an assertion it never
        mentioned."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Untouched', stock_status='low')
        stamp = svc.get_product(pid).stock_status_at

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Renamed'})
        assert resp.status_code == 302
        product = svc.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at == stamp

    def test_reposting_the_rendered_edit_form_does_not_re_date_the_assertion(
            self, client, test_storage):
        """THE regression this story's re-stamp rule exists for, taken verbatim
        from what the page rendered and with only the description changed — the
        shape of every real browser save.

        The `<select>` is worse than any text input here: it always posts, and
        it always posts a VALID value, so there is no submission a browser can
        make that means "untouched". Only the value comparison can tell this
        save from a real assertion, and the date is aged first so a re-stamp
        would be unmistakable rather than sub-millisecond.
        """
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Flagged', stock_status='low',
                                 quantity_on_hand='4', reorder_threshold='3')
        old = _backdate_status_stamp(test_storage, pid,
                                     datetime.now() - timedelta(days=95))

        body = client.get(f'/products/edit/{pid}').data.decode()
        data = _rendered_edit_form(body)
        # The rendered form really does carry the key — if it did not, this test
        # would prove nothing at all.
        assert data['stock_status'] == 'low'
        data['description'] = 'Flagged (typo fixed)'

        resp = client.post(f'/products/edit/{pid}', data=data)
        assert resp.status_code == 302

        product = svc.get_product(pid)
        assert product.description == 'Flagged (typo fixed)'
        assert product.stock_status == 'low'
        assert product.stock_status_at == old

    def test_reposting_the_rendered_form_keeps_an_unset_status_unset(
            self, client, test_storage):
        """The other half of the round trip, and the one a mis-rendered default
        would break: re-saving an untouched page must not turn "nothing
        asserted" into an assertion of anything."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Bare')

        body = client.get(f'/products/edit/{pid}').data.decode()
        client.post(f'/products/edit/{pid}', data=_rendered_edit_form(body))

        product = svc.get_product(pid)
        assert product.stock_status == 'unknown'
        assert product.stock_status_at is None

    @pytest.mark.parametrize('bad', ['', '   ', 'LOW', 'Low', ' low ', 'bogus',
                                     'x' * 5000],
                             ids=['blank', 'whitespace', 'upper', 'title',
                                  'padded', 'not-a-member', 'oversized'])
    def test_a_bad_status_rerenders_with_a_keyed_error_and_writes_nothing(
            self, client, test_storage, bad):
        """A blank is refused here where it is accepted for the two number
        fields, and the difference is the column: those are nullable and blank
        clears them, while this one cannot be NULL and `unknown` is how "no
        assertion" is spelled. A blank could only come from a truncated or
        hand-built POST, and reading it as `unknown` would quietly erase a flag.

        Whitespace-only and a padded member are refused rather than stripped, on
        both tiers, for the reason `_apply_stock_status_assertion` states: these
        four strings are a closed machine vocabulary that only this app's own
        `<select>` produces, so `' low '` is a caller bug and not an operator's
        typing slip. Parametrised alongside the rest so the route and the
        service are seen to answer the same way rather than assumed to.
        """
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Guarded', stock_status='low')
        stamp = svc.get_product(pid).stock_status_at

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Guarded',
                                 'stock_status': bad})
        assert resp.status_code == 200
        assert 'Stock Status must be one of unknown, ok, low, out.' in \
            _shown_keyed_errors(resp.data.decode())

        product = svc.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at == stamp

    def test_the_bad_status_also_refuses_a_create(self, client, product_ids):
        """The rule is in the SHARED validator, so the create form refuses the
        same value — and nothing is written."""
        resp = client.post('/products/add', data={'description': 'Guarded',
                                                  'stock_status': 'bogus'})
        assert resp.status_code == 200
        assert 'Stock Status must be one of unknown, ok, low, out.' in \
            _shown_keyed_errors(resp.data.decode())
        assert product_ids() == set()

    def test_a_refused_submit_still_renders_the_control(self, client,
                                                        test_storage):
        """A `<select>` cannot round-trip a value that is not one of its
        options, so what matters after a refusal is that the control is still
        there, still complete and still marked invalid — an operator handed a
        page with the field missing has no way to comply."""
        resp = client.post('/products/add', data={'description': '',
                                                  'stock_status': 'bogus'})
        body = resp.data.decode()
        assert [(value, label) for value, label, _
                in _select_options(body, 'stock_status')] == \
            _STOCK_STATUS_OPTIONS
        assert 'is-invalid' in _form_controls(body, ['stock_status'])[0]

    @pytest.mark.parametrize('bad', ['', 'bogus'],
                             ids=['blank', 'not-a-member'])
    def test_a_refused_edit_still_marks_the_stored_status_selected(
            self, client, test_storage, bad):
        """The refusal must not turn the page it hands back into a trap.

        This is the one control on the form where "submitted wins" is wrong.
        The two number fields render a rejected value straight back into their
        box, so the operator sees what they typed and fixes it. A `<select>`
        cannot: neither `''` nor `bogus` is one of its four options, so marking
        the submitted value selected marks NOTHING selected — and a browser
        then displays AND SUBMITS the first option, `Not set`. The operator
        corrects the field that was actually complained about, saves the page
        they were handed, and a stored `Low` is withdrawn with its assertion
        date nulled, with nothing on the page at any point saying the flag was
        there.

        Both a blank and a truthy non-member are parametrised because a
        template-side fallback distinguishes them where `_selected_stock_status`
        does not: a `{% set … or default %}` spelling would rescue any FALSY
        submitted value and still render nothing selected for `bogus`. The page
        must read `low` for both, and re-posting it VERBATIM — the shape of a
        real browser save — must leave both stored columns where they were.

        The over-long `location` is what makes this a realistic refusal rather
        than a self-inflicted one: the operator's attention is on the field the
        message names, and the status is collateral.
        """
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Flagged', stock_status='low')
        stamp = svc.get_product(pid).stock_status_at

        resp = client.post(f'/products/edit/{pid}',
                           data={'description': 'Flagged',
                                 'location': 'x' * 500,
                                 'stock_status': bad})
        assert resp.status_code == 200
        body = resp.data.decode()
        assert _select_value(body, 'stock_status') == 'low'

        # The re-save, taken from what the page rendered, with only the field
        # the operator was told about corrected.
        data = _rendered_edit_form(body)
        data['location'] = 'Bin 4'
        assert client.post(f'/products/edit/{pid}',
                           data=data).status_code == 302

        product = svc.get_product(pid)
        assert product.location == 'Bin 4'
        assert product.stock_status == 'low'
        assert product.stock_status_at == stamp

    def test_the_status_is_not_prefillable_from_a_query_string(self, client):
        """`_PRODUCT_PREFILL_ARGS` deliberately omits it: that whitelist is read
        from `request.args` and forwarded by the search page's "create" link, so
        membership would let a URL put a stock ASSERTION in front of the
        operator — a claim about a product nobody made."""
        body = client.get('/products/add?stock_status=low').data.decode()
        selected = [value for value, _label, is_selected
                    in _select_options(body, 'stock_status') if is_selected]
        assert selected == ['unknown']

    def test_every_stored_status_has_an_operator_facing_label(self):
        """The route's label mapping and the enum are two lists, and only one of
        them is the column's vocabulary.

        A member added to `StockStatus` without a label here would be a value
        the service accepts and stores, the form cannot offer, and the detail
        page falls back to showing raw — a state visible only to whoever
        happened to look at that product. Checked against the enum rather than
        against a copy, because the enum is what the service validates by.
        """
        from app.main.routes import _STOCK_STATUS_LABELS
        from app.models import StockStatus

        assert set(_STOCK_STATUS_LABELS) == {m.value for m in StockStatus}
        # And the labels are the ones the manual promises, in the order the
        # select renders them.
        assert list(_STOCK_STATUS_LABELS.items()) == _STOCK_STATUS_OPTIONS

    def test_the_route_and_the_service_enumerate_the_same_values(self):
        """Two modules hold an accepted-value tuple, and BOTH are read out
        verbatim into text the operator sees on a refusal — the route's into
        `Stock Status must be one of …`, the service's into the `ValueError`
        that becomes `error_details` in the audit log.

        Both are built from `StockStatus`, so this asserts a property the code
        already has rather than creating one. It is still worth asserting: the
        alternative spelling — the route deriving its tuple from its own label
        mapping — agrees today and would stop agreeing the moment that mapping's
        order changed, which it is free to do, being a DISPLAY decision that
        drives the select. Compared element for element rather than as sets,
        because the two messages enumerate in order and an operator comparing
        them would notice.
        """
        from app.main.routes import _STOCK_STATUS_VALUES as route_values
        from app.mariadb_catalog_service import (
            _STOCK_STATUS_VALUES as service_values)
        from app.models import StockStatus

        assert route_values == service_values
        assert route_values == tuple(m.value for m in StockStatus)

    def test_the_status_never_records_a_purchase(self, client, test_storage):
        """The create form's Purchase is triggered by the First Receipt block
        alone; a stock assertion is a fact about the SHELF, not a shipment."""
        resp = client.post('/products/add', data={'description': 'Flagged',
                                                  'stock_status': 'out'})
        pid = int(resp.headers['Location'].rstrip('/').split('/')[-1])
        assert CatalogService(test_storage).get_purchases_for_product(pid) == []


@pytest.mark.unit
class TestProductDetailStockStatus:
    """FR28/FR31 on the page: the stored assertion, its age, and what the
    derived Reorder signal now answers to.

    Both strings arrive finished from the route (AD-5) and the age is gated on
    the STATUS rather than on the date, which is what keeps `Not set` from ever
    growing a parenthesis.
    """

    def _detail(self, client, pid):
        return client.get(f'/products/{pid}').data.decode()

    def test_an_unasserted_product_reads_not_set_with_no_age(self, client,
                                                             test_storage):
        pid = CatalogService(test_storage).create_product(description='Bare')
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-stock-status') == 'Not set'
        assert _detail_field(body, 'product-effective-low') == '—'

    def test_an_unflushed_product_reads_not_set_rather_than_the_word_None(self):
        """The one instance whose `stock_status` is `None`.

        The column is NOT NULL, so no row reads None — but a `Product()` that
        has not been flushed does, because the Python-side default is applied
        on INSERT. `test_the_getter_answers_for_an_unset_status_attribute` pins
        that state on the model side, and it reaches the display helpers by the
        same route.

        Both helpers are exercised, because the uncoerced spelling of each fails
        differently and neither failure is loud: `_STOCK_STATUS_LABELS.get(None,
        None)` renders the literal word `None` into the page, while `None !=
        StockStatus.UNKNOWN.value` is TRUE, so the age gate would open on a row
        the line above it calls `Not set`. All three sites — these two and
        `_product_form_data` — coerce the case identically, which is what makes
        the form and the page agree about one instance.
        """
        from app.database import Product
        from app.main.routes import (_product_form_data,
                                     _product_stock_status_display)
        from app.models import StockStatus

        bare = Product(description='Unflushed')
        assert bare.stock_status is None

        assert _product_stock_status_display(bare) == 'Not set'
        # The age gate the detail route applies, spelled the same way.
        assert ((bare.stock_status or StockStatus.UNKNOWN.value)
                != StockStatus.UNKNOWN.value) is False
        assert _product_form_data(bare, [])['stock_status'] == 'unknown'

    @pytest.mark.parametrize('status, label', [('ok', 'OK'), ('low', 'Low'),
                                               ('out', 'Out of stock')])
    def test_an_asserted_status_reads_its_label_with_an_age(
            self, client, test_storage, status, label):
        pid = CatalogService(test_storage).create_product(
            description='Asserted', stock_status=status)
        assert _detail_field(self._detail(client, pid),
                             'product-stock-status') == \
            f'{label} (set just now)'

    def test_the_age_reflects_the_stored_date(self, client, test_storage):
        """The age is the age of the ASSERTION, so it has to come off the stored
        column rather than off anything about the render."""
        from datetime import datetime, timedelta

        pid = CatalogService(test_storage).create_product(
            description='Stale flag', stock_status='low')
        _backdate_status_stamp(test_storage, pid,
                               datetime.now() - timedelta(days=95))
        assert _detail_field(self._detail(client, pid),
                             'product-stock-status') == \
            'Low (set 3 months ago)'

    def test_a_date_without_an_assertion_shows_no_age(self, client,
                                                      test_storage):
        """The gate is on the STATUS, not on the date. The write contract moves
        the two together, so this state cannot arise through the app — but a
        restored backup or a hand-run UPDATE can produce it, and the ungated
        version renders `Not set (set 3 months ago)`: a date for an assertion
        the same line says was never made."""
        from datetime import datetime, timedelta

        pid = CatalogService(test_storage).create_product(description='Odd')
        _backdate_status_stamp(test_storage, pid,
                               datetime.now() - timedelta(days=95))
        assert _detail_field(self._detail(client, pid),
                             'product-stock-status') == 'Not set'

    @pytest.mark.parametrize('status', ['low', 'out'])
    def test_a_manual_flag_reads_low_with_no_count_and_no_threshold(
            self, client, test_storage, status):
        """FR29 on the page, and the state the whole story exists for: neither
        count nor threshold is set, so the threshold branch cannot fire and the
        signal is the manual assertion alone."""
        pid = CatalogService(test_storage).create_product(
            description='Flagged only', stock_status=status)
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-quantity') == 'Not tracked'
        assert _detail_field(body, 'product-reorder-threshold') == '—'
        assert _detail_field(body, 'product-effective-low') == 'Low stock'

    def test_flagging_ok_does_not_suppress_a_crossed_threshold(self, client,
                                                               test_storage):
        """FR30's OR is an OR, not an override: the operator's opinion cannot
        outrank a count they recorded against a threshold they set. An
        `elif`-shaped implementation gets exactly this row wrong."""
        pid = CatalogService(test_storage).create_product(
            description='Says ok', quantity_on_hand='2', reorder_threshold='3',
            stock_status='ok')
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-stock-status').startswith('OK')
        assert _detail_field(body, 'product-effective-low') == 'Low stock'

    def test_withdrawing_the_flag_clears_the_signal_and_the_date(
            self, client, test_storage):
        """The full walk through the form, re-read off the page each time — the
        signal is derived, so every step is a re-derivation rather than a stored
        flag being toggled."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Walked')
        assert _detail_field(self._detail(client, pid),
                             'product-effective-low') == '—'

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'stock_status': 'low'})
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-stock-status') == \
            'Low (set just now)'
        assert _detail_field(body, 'product-effective-low') == 'Low stock'

        client.post(f'/products/edit/{pid}', data={'description': 'Walked',
                                                   'stock_status': 'unknown'})
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-stock-status') == 'Not set'
        assert _detail_field(body, 'product-effective-low') == '—'

    def test_the_new_row_does_not_intrude_on_the_quantity_row(self, client,
                                                              test_storage):
        """`#product-quantity`'s rendered text is pinned character for character
        by the Story 5.1 tests, so the status row must sit BESIDE it rather than
        inside it — and its age must not leak into the count's parenthesis."""
        pid = CatalogService(test_storage).create_product(
            description='Both', quantity_on_hand='2', stock_status='low')
        body = self._detail(client, pid)
        assert _detail_field(body, 'product-quantity') == \
            'In stock: 2 (counted just now)'
        assert _detail_field(body, 'product-stock-status') == \
            'Low (set just now)'

    def test_reading_the_page_writes_neither_column(self, client,
                                                    test_storage):
        """AD-6: the signal is derived at read, and the status it now reads is
        STORED — so drawing the page must leave both columns and `updated_at`
        exactly where they were. A derived value that quietly writes would make
        the row's history a record of who LOOKED at it."""
        from datetime import datetime, timedelta

        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Untouched', stock_status='low')
        old = _backdate_status_stamp(test_storage, pid,
                                     datetime.now() - timedelta(days=95))
        before = svc.get_product(pid).updated_at

        assert _detail_field(self._detail(client, pid),
                             'product-effective-low') == 'Low stock'

        product = svc.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at == old
        assert product.updated_at == before
