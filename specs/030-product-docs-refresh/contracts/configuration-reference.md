# Contract: The Configuration Reference

**Feature**: 030-product-docs-refresh | Satisfies spec FR-018 through FR-026

What `docs/deployment-guide.md` must say about configuration. This is the source; the guide is a rendering of it in the guide's own voice. Every row was read from the code — see `research.md` §1 for the file and line behind each.

## The set that must be documented

Seventeen variables change what a deployed or locally-run application does. Nothing else may appear as a deployment setting.

| Variable | Required | Default | When unset | In which example |
|----------|----------|---------|------------|------------------|
| `SQLALCHEMY_DATABASE_URI` | **Yes** | none | No database. `python manage.py config-check` reports it. | both |
| `SECRET_KEY` | Yes, in practice | `dev-secret-key-change-in-production` | Sessions and CSRF tokens signed with a key published in this repository. | both |
| `LOG_LEVEL` | No | `INFO` | INFO-level logging to stdout. | both |
| `FLASK_DEBUG` | No | `False`, but `.flaskenv` sets `1` for `flask run` | Debug off in a deployment; **on** in a source checkout started with `flask run`, which the guide must say. | source |
| `CUPS_SERVER` | No; needed for label printing from the container | none | `lp` looks for a local CUPS daemon, and the image has none, so label printing fails. | docker |
| `GOOGLE_SHEET_ID` | No | none | Sheets export unavailable. Export-only and legacy; nothing else is affected. | both |
| `GOOGLE_CREDENTIALS_FILE` | No | `<repo>/credentials/credentials.json` | The default path is used. | both |
| `GOOGLE_TOKEN_FILE` | No | `<repo>/credentials/token.json` | The default path is used. | both |
| `DIGIKEY_CLIENT_ID` | No | none | Both DigiKey screens render and say they are not configured. Nothing else changes. | both |
| `DIGIKEY_CLIENT_SECRET` | Yes, when a client id is set | none | DigiKey refuses the credentials and the screen says so. | both |
| `DIGIKEY_ACCOUNT_ID` | Yes, for order capture | none | Order calls answer `400 Account ID must not be 0`; part lookup still works. | both |
| `DIGIKEY_API_BASE` | No | `https://api.digikey.com` | The production API. `https://sandbox-api.digikey.com` for the sandbox. | both |
| `CATEGORY_TAXONOMY_FILE` | No | the shipped taxonomy | The branches in `docs/category-taxonomy.md` are offered. Set-but-unreadable stops startup. | both |
| `SPECIFICATION_KEYS_FILE` | No | the shipped key list | The shipped keys are offered. Independent of the taxonomy variable. | both |
| `FLASK_APP` | No | `wsgi.py`, from the repository's `.flaskenv` | Already correct; do not set it. | source, as a note |
| `FLASK_RUN_HOST` | No | `127.0.0.1`, from `.flaskenv` | `flask run` binds loopback only, so the checkout is unreachable from elsewhere on the LAN. | source |
| `FLASK_RUN_PORT` | No | `5000`, from `.flaskenv` | `flask run` listens on 5000. | source |

## The set that must be removed

Nine names currently in the guide, read by nothing:

`FLASK_ENV`, `STORAGE_BACKEND`, `SQLALCHEMY_TRACK_MODIFICATIONS`, `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_TOKEN_PATH`, `APP_NAME`, `APP_VERSION`, `CACHE_TTL`, `BATCH_SIZE`.

Plus one correction rather than a removal: the guide's `FLASK_APP=app.py` contradicts `.flaskenv`'s `FLASK_APP=wsgi.py`.

## The set that must move

`TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_USER`, `TEST_DB_PASSWORD`, `TEST_DB_NAME` are test-suite settings. They belong in `docs/development-testing-guide.md`, with their defaults, and must not appear as deployment settings.

## The set that must not be invented

`DISABLE_LABEL_PRINTING` is honored in code and populated from no environment variable. It may be described as an in-code test seam or omitted; it may not be listed as a variable.

## What each entry must state

Four things, in whatever order reads well: what it does, whether it is required, its default, and what is absent or fails without it. An entry that says only what a variable is for fails FR-020.

## The DigiKey entry carries setup as well as syntax

Because obtaining these four values is the part an operator cannot guess:

1. Create a Production App at `https://developer.digikey.com`.
2. Subscribe it to **Product Information** and **Order Status** — not **Ordering**, which the application never uses and which requires a DigiKey Credit account.
3. Give the portal `https://localhost` as the OAuth callback. It must be HTTPS and it is never used: 2-legged auth redirects no browser.
4. `DIGIKEY_ACCOUNT_ID` is the customer/account number from any order confirmation or invoice. It is not a credential, and without it every order call fails.

Placeholders only. No credential value appears in any tracked file.

## The two examples

Both are drawn from the table above and differ only where the deployment genuinely differs:

- **Docker**: passed with `--env-file`. The image contains no `.env` and reads none. `CUPS_SERVER` is meaningful here.
- **From source**: read from `.env` at the repository root, loaded by `config.py`. `.env.example` must cover the same set (FR-024) or state where it deliberately does not. The guide must also say that `.flaskenv` — committed, and read only by the `flask` CLI — already supplies `FLASK_APP`, `FLASK_DEBUG=1`, `FLASK_RUN_HOST` and `FLASK_RUN_PORT` for development, and is neither read by gunicorn nor copied into the image.

Neither example may name a variable outside the seventeen.
