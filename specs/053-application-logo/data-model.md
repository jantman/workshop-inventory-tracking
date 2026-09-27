# Data Model: Application Logo

No persisted data. Nothing touches the database or the schema.

## Logo assets

| File | Role | Size(s) | Consumed by |
|------|------|---------|-------------|
| `app/static/img/logo.svg` | **Master**, hand-written | vector, 16-unit grid | navbar, home banner, SVG favicon |
| `app/static/img/favicon.ico` | derived | 16, 32, 48 | ICO favicon link; `GET /favicon.ico` |
| `extension/icons/icon-16.png` | derived | 16 × 16 | manifest `icons`/`action.default_icon` "16" |
| `extension/icons/icon-48.png` | derived | 48 × 48 | manifest "48" |
| `extension/icons/icon-128.png` | derived | 128 × 128 | manifest "128" |

**Rule**: every derived file is a render of the master. When the master changes, re-run the
commands in its header comment and commit all of them together.
