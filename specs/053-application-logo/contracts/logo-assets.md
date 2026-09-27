# Contract: Logo Assets and Declarations

## Every HTML page (via `base.html`)

`<head>` contains, in order:

```html
<link rel="icon" href="/static/img/logo.svg" type="image/svg+xml">
<link rel="icon" href="/static/img/favicon.ico" sizes="16x16 32x32 48x48">
```

The navbar brand (`a.navbar-brand`) contains `img.brand-logo[src$="img/logo.svg"]`, followed
by the text "Workshop Inventory", and it contains no `.bi-tools`.

## Home page

The banner heading (`h1.display-4`) contains `img.brand-logo`, and it contains no `.bi-tools`.

## HTTP

| Request | Response |
|---------|----------|
| `GET /static/img/logo.svg` | 200, `image/svg+xml` |
| `GET /static/img/favicon.ico` | 200, ICO |
| `GET /favicon.ico` | 200, the same bytes as `/static/img/favicon.ico` |

## Extension

For each `size → path` in the manifest's `icons` and `action.default_icon`, the file at
`path` is a PNG whose width and height are both `size`.
