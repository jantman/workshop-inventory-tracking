# Contract: Details panel vendor links

Rendered by `app/templates/product/detail.html` for `GET /products/<id>`.

## Present when the product has at least one supported vendor identifier

```html
<dt class="col-sm-4">Vendor Pages</dt>
<dd class="col-sm-8" id="product-vendor-links">
  <a class="vendor-link me-3" href="{url}" target="_blank" rel="noopener"
     data-vendor="{vendor}">{vendor} {value} <i class="bi bi-box-arrow-up-right"></i></a>
  ...
</dd>
```

## Absent otherwise

Neither the `<dt>` nor `#product-vendor-links` is rendered.

## Addresses (`<id>` percent-encoded, `safe=''`)

| Vendor | Address |
|--------|---------|
| `Amazon` | `https://www.amazon.com/dp/<id>` |
| `McMaster-Carr` | `https://www.mcmaster.com/<id>/` |
| `DigiKey` | `https://www.digikey.com/en/products/result?keywords=<id>` |

Tests select on `#product-vendor-links`, `.vendor-link` and `data-vendor`.
