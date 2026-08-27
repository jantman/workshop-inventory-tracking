# Workshop Inventory Tracking - Deployment Guide

## Table of Contents

- [Docker Deployment](#docker-deployment)
  - [1. Pull the Image](#1-pull-the-image)
  - [2. Configure](#2-configure)
  - [3. Run Migrations](#3-run-migrations)
  - [4. Start the Application](#4-start-the-application)
  - [Image Details](#image-details)
  - [Upgrading](#upgrading)
- [Installation Process](#installation-process)
  - [1. Download Application](#1-download-application)
  - [2. Create Virtual Environment](#2-create-virtual-environment)
  - [3. Install Python Dependencies](#3-install-python-dependencies)
- [Configuration](#configuration)
  - [1. Environment Variables](#1-environment-variables)
  - [2. Secret Key Generation](#2-secret-key-generation)
  - [3. Configuration File (config.py)](#3-configuration-file-configpy)
- [Storage Backend Setup](#storage-backend-setup)
  - [MariaDB Setup (Recommended for Production)](#mariadb-setup-recommended-for-production)
- [Database Management](#database-management)
  - [Database Commands](#database-commands)
  - [Migration Best Practices](#migration-best-practices)
  - [Troubleshooting Database Issues](#troubleshooting-database-issues)
- [Data Integrity Auditing](#data-integrity-auditing)
  - [Audit Commands](#audit-commands)
  - [Materials Audit](#materials-audit)
  - [Locations Audit](#locations-audit)
- [Photo Management](#photo-management)
  - [PDF Thumbnail Regeneration](#pdf-thumbnail-regeneration)
- [Google Sheets Setup (Data Export Only)](#google-sheets-setup-data-export-only)
  - [1. Create Google Cloud Project](#1-create-google-cloud-project)
  - [2. Create Service Account](#2-create-service-account)
  - [3. Share Google Sheet](#3-share-google-sheet)
  - [4. Test Connection](#4-test-connection)
- [Monitoring and Maintenance](#monitoring-and-maintenance)
  - [1. Log Monitoring](#1-log-monitoring)
  - [2. Health Checks](#2-health-checks)

## Docker Deployment

Prebuilt `linux/amd64` images are published to GHCR by the release workflow.

### 1. Pull the Image

```bash
# A specific release (recommended -- pin the version you deployed)
docker pull ghcr.io/jantman/workshop-inventory-tracking:0.1.0

# Or the most recent release
docker pull ghcr.io/jantman/workshop-inventory-tracking:latest
```

Every CI build is also pushed, tagged `ci-<commit-sha>`, if you need to run an
unreleased commit.

### 2. Configure

The container is configured entirely through environment variables -- there is no
`.env` file inside the image and it reads none. (`.flaskenv`, which a source
checkout uses, is not copied into the image either, and `gunicorn` would not read
it if it were.) Put the variables in a file and pass it with `--env-file`:

```bash
# inventory.env

# Required
SQLALCHEMY_DATABASE_URI=mysql+pymysql://user:password@dbhost/workshop_inventory
SECRET_KEY=your-secret-key-here-change-this

# Optional
LOG_LEVEL=INFO

# Optional: label printing via a CUPS server on the network
CUPS_SERVER=cups-host.lan

# Optional: DigiKey order capture and part lookup
DIGIKEY_CLIENT_ID=your-digikey-client-id-here
DIGIKEY_CLIENT_SECRET=your-digikey-client-secret-here
DIGIKEY_ACCOUNT_ID=your-digikey-account-number-here

# Optional: your own category taxonomy instead of the shipped one
CATEGORY_TAXONOMY_FILE=/etc/workshop-inventory/categories.json
SPECIFICATION_KEYS_FILE=/etc/workshop-inventory/specification-keys.json

# Optional: Google Sheets export
GOOGLE_SHEET_ID=your-sheet-id-here
GOOGLE_CREDENTIALS_FILE=/credentials/credentials.json
GOOGLE_TOKEN_FILE=/credentials/token.json
```

Every variable, what it does, and what happens when you leave it out is in
[Environment Variables](#1-environment-variables) below. Nothing outside that
list has any effect.

### 3. Run Migrations

**Migrations are not run automatically at startup.** Run them yourself before
starting a new image version, using the same image:

```bash
docker run --rm --env-file inventory.env \
  ghcr.io/jantman/workshop-inventory-tracking:0.1.0 \
  python manage.py db upgrade
```

The image has no `ENTRYPOINT`, so every `manage.py` command works the same way
(`db current`, `audit materials`, `photos regenerate-pdf-thumbnails`, ...).

### 4. Start the Application

```bash
docker run -d --name workshop-inventory \
  --restart unless-stopped \
  --env-file inventory.env \
  -p 5000:5000 \
  ghcr.io/jantman/workshop-inventory-tracking:0.1.0
```

Or with Compose:

```yaml
services:
  app:
    image: ghcr.io/jantman/workshop-inventory-tracking:0.1.0
    restart: unless-stopped
    env_file: inventory.env
    ports:
      - "5000:5000"
    # Only needed for Google Sheets export. Must be writable -- the token file
    # is rewritten whenever the OAuth credentials are refreshed.
    volumes:
      - ./credentials:/credentials
```

If you use Google Sheets export, generate `token.json` on a host first. The
first export triggers an interactive OAuth flow (`run_local_server`, which opens
a browser) that cannot complete inside the container. Mount the directory
containing `credentials.json` and `token.json` read-write, owned by uid 1000.

### Image Details

- Runs `gunicorn` with 2 workers on port 5000 as the non-root `inventory` user
- Built-in `HEALTHCHECK` polls `/health`, so `docker ps` reports health directly
- Logs go to STDOUT/STDERR in the same structured JSON format as a bare-metal
  install, so `docker logs` is the equivalent of `journalctl -u workshop-inventory`
- Label printing works through the `lp` binary from `cups-client`; set
  `CUPS_SERVER` to the hostname of a CUPS server that has the Sato printers
  configured. Without it, label printing fails but nothing else is affected.
- No application data lives in the container -- photos and inventory are all in
  MariaDB, so there is nothing to persist in a volume

### Upgrading

```bash
docker pull ghcr.io/jantman/workshop-inventory-tracking:<new-version>
docker run --rm --env-file inventory.env \
  ghcr.io/jantman/workshop-inventory-tracking:<new-version> python manage.py db upgrade
docker stop workshop-inventory && docker rm workshop-inventory
# then re-run the `docker run` from step 4 with the new tag
```

Take a database backup before running migrations for a new release.

## Installation Process

The steps below are for running directly on a host instead of in Docker.

### 1. Download Application

```bash
# Clone repository
git clone https://github.com/your-org/workshop-inventory-tracking.git
cd workshop-inventory-tracking
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration

### 1. Environment Variables

**This list is the whole configuration surface.** A variable that is not on it
has no effect, whatever it is named -- the application reads these and nothing
else. Where a variable is optional, the last column says what you give up by
leaving it out, so you can decide before you deploy rather than after.

A source deployment reads them from a `.env` file in the repository root; a
container gets them from `--env-file` (see [Configure](#2-configure) above).

#### Required

| Variable | What it does | Without it |
|----------|--------------|------------|
| `SQLALCHEMY_DATABASE_URI` | The MariaDB connection string, e.g. `mysql+pymysql://user:password@localhost/workshop_inventory`. | Nothing works: there is no database. `python manage.py config-check` reports it by name. |
| `SECRET_KEY` | Signs Flask sessions and CSRF tokens. Generate one -- see [Secret Key Generation](#2-secret-key-generation). | Falls back to `dev-secret-key-change-in-production`, a key published in this repository. Set it. |

#### Optional

| Variable | What it does | Default | Without it |
|----------|--------------|---------|------------|
| `LOG_LEVEL` | Log verbosity, written to stdout. | `INFO` | INFO-level logging. |
| `FLASK_DEBUG` | Debug mode. Leave it off in a deployment. | `False` | Debug off -- which is what you want. See the note on `.flaskenv` below. |
| `CUPS_SERVER` | Hostname of the CUPS server holding the label printers. Read by the `lp` client, not by the application. | none | In the container, label printing fails: `lp` looks for a local CUPS daemon and the image has none. |
| `CATEGORY_TAXONOMY_FILE` | Path to your own category list, replacing the shipped one. | the shipped taxonomy | The branches in [category-taxonomy.md](category-taxonomy.md) are offered. See [below](#category-taxonomy-and-specification-vocabulary-optional). |
| `SPECIFICATION_KEYS_FILE` | Path to your own specification key list. | the shipped keys | The shipped keys are offered. Independent of the variable above. |
| `GOOGLE_SHEET_ID` | The sheet that data is exported to. | none | Google Sheets export is unavailable. Sheets is export-only and legacy; nothing else is affected. |
| `GOOGLE_CREDENTIALS_FILE` | Path to the Google API credentials file. | `<repo>/credentials/credentials.json` | The default path is used. |
| `GOOGLE_TOKEN_FILE` | Path to the Google API token file. | `<repo>/credentials/token.json` | The default path is used. |
| `DIGIKEY_CLIENT_ID` | DigiKey API client id. | none | *Products → Capture a DigiKey Order* and *Capture a DigiKey Part* both render and say they are not configured. Nothing else in the application changes. See [DigiKey](#digikey-order-capture-and-part-lookup-optional). |
| `DIGIKEY_CLIENT_SECRET` | DigiKey API client secret. Required whenever the client id is set. | none | DigiKey refuses the credentials and the screen says so. |
| `DIGIKEY_ACCOUNT_ID` | Your DigiKey customer/account number. Required for **order** capture. | none | Order calls answer `400 Account ID must not be 0`. Part lookup still works. |
| `DIGIKEY_API_BASE` | Which DigiKey API to talk to. | `https://api.digikey.com` | The production API. Set `https://sandbox-api.digikey.com` to work against the sandbox. |

#### A source checkout also reads `.flaskenv`

`.flaskenv` is committed to the repository and read by the `flask` command --
not by `gunicorn`, and it is not copied into the Docker image. It supplies four
values for local development:

```bash
FLASK_APP=wsgi.py          # already correct; do not set it yourself
FLASK_DEBUG=1              # so `flask run` from a checkout runs WITH debug on
FLASK_RUN_HOST=127.0.0.1   # loopback only -- not reachable from the rest of the LAN
FLASK_RUN_PORT=5000
```

Two of those matter when you run from source rather than in a container:
`flask run` gives you a debug-mode server, and it binds to loopback, so nothing
else on the network can reach it until you override `FLASK_RUN_HOST`. A
production deployment runs `gunicorn` (as the image does) and gets neither.

Test-database settings (`TEST_DB_HOST` and friends) are not deployment
configuration; they belong to the test suite and are documented in the
[Development Testing Guide](development-testing-guide.md).

#### DigiKey order capture and part lookup (optional)

Leaving `DIGIKEY_CLIENT_ID` unset disables the two DigiKey screens cleanly --
they still render, and they say they are not configured. Everything else in the
application, including Amazon and McMaster-Carr capture, is unaffected. To turn
them on:

1. Sign in at <https://developer.digikey.com> and create a **Production App**.
2. Subscribe it to **Product Information** and **Order Status**. Do *not*
   subscribe to **Ordering** -- this application never places orders, and that
   product requires a DigiKey Credit account.
3. The portal demands an OAuth callback URL. Use `https://localhost`: it must be
   HTTPS, and 2-legged authentication never redirects a browser, so it is unused.
4. Find your DigiKey customer/account number on any order confirmation or
   invoice. This is `DIGIKEY_ACCOUNT_ID`. It is not a credential, but it is
   required for order capture: a 2-legged token identifies the *application*
   rather than the customer, so without this header every order call answers
   `400 Account ID must not be 0`.

```bash
DIGIKEY_CLIENT_ID=your-digikey-client-id-here
DIGIKEY_CLIENT_SECRET=your-digikey-client-secret-here
DIGIKEY_ACCOUNT_ID=your-digikey-account-number-here
# Override to https://sandbox-api.digikey.com to work against the sandbox.
DIGIKEY_API_BASE=https://api.digikey.com
```

Keep the client secret out of version control -- `.env` is untracked, and it
should stay that way. What each vendor's capture gives you is in the user
manual's [Which Vendors Are Supported](user-manual.md#which-vendors-are-supported).

#### Category taxonomy and specification vocabulary (optional)

The application ships with one workshop's category taxonomy -- the branches
documented in [category-taxonomy.md](category-taxonomy.md) -- and the
specification keys that go with it. They are offered as suggestions when filing a
product, so a branch nobody has filed into yet can be picked rather than typed
from memory.

**Those branches are somebody else's shop.** Point these at your own to replace
them:

```bash
CATEGORY_TAXONOMY_FILE=/etc/workshop-inventory/categories.json
SPECIFICATION_KEYS_FILE=/etc/workshop-inventory/specification-keys.json
```

Each file is a JSON array of strings and nothing else:

```json
["electronics", "electronics/sensors", "fasteners/nuts"]
```

```json
["Thread", "Length", "Voltage"]
```

- Parent branches are filled in for you: listing `a/b/c` also offers `a` and `a/b`.
- Paths are lowercased, and may nest as deep as you like -- the three-level limit
  in the shipped taxonomy was that workshop's decision, not the application's.
- An override **replaces** the built-in list rather than adding to it, and the two
  variables are independent: set one and the other keeps its default.
- Neither is required. With both unset nothing is read from disk.
- Suggestions are never a whitelist. A category outside the list can still be
  typed on a product, and an empty array is a valid way to say "offer nothing".

If a variable is set but the file cannot be read, parsed or validated, **the
application refuses to start** and the error names the file and the problem.
Falling back to the built-in list would quietly file your products under another
shop's branches.

### 2. Secret Key Generation
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Configuration File (config.py)
Verify configuration settings:
- Database/storage paths
- API credentials paths
- Logging levels
- Security settings

## Storage Backend Setup

### MariaDB Setup (Recommended for Production)

1. **Install MariaDB**:
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install mariadb-server python3-pymysql
   
   # CentOS/RHEL
   sudo yum install mariadb-server python3-PyMySQL
   ```

2. **Create Database and User**:
   ```sql
   CREATE DATABASE workshop_inventory CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'inventory_user'@'localhost' IDENTIFIED BY 'your_secure_password';
   GRANT ALL PRIVILEGES ON workshop_inventory.* TO 'inventory_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

3. **Initialize Database Schema**:
   ```bash
   # Initialize database with migrations (for new installations)
   python manage.py db init
   ```

4. **Point the application at it**:
   ```bash
   SQLALCHEMY_DATABASE_URI=mysql+pymysql://inventory_user:your_secure_password@localhost/workshop_inventory
   ```

   That is the only variable involved. MariaDB is the sole storage backend --
   there is nothing to select.

## Database Management

The application uses Alembic for database migrations. All database operations should be performed using the `manage.py` script.

### Database Commands

#### For New Installations
```bash
# Initialize a new database with the latest schema
python manage.py db init
```

#### For Updates/Migrations
```bash
# Check current database version
python manage.py db current

# View migration history
python manage.py db history

# Upgrade to latest version (run after app updates)
python manage.py db upgrade

# Downgrade to specific revision (if needed)
python manage.py db downgrade <revision>
```

#### For Development
```bash
# Create a new migration after model changes
python manage.py db migrate -m "Description of changes"

# Reset database (WARNING: destroys all data)
python manage.py db reset
```

#### Configuration Check
```bash
# Verify configuration and database connectivity
python manage.py config-check
```

### Migration Best Practices

1. **Always backup your database** before running migrations in production
2. **Test migrations** in a staging environment first
3. **Review migration files** before applying them to production
4. **Run migrations during maintenance windows** to avoid conflicts
5. **Monitor the process** and be prepared to rollback if issues occur

### Troubleshooting Database Issues

If you encounter database connection issues:

1. **Check configuration**:
   ```bash
   python manage.py config-check
   ```

2. **Verify database service is running**:
   ```bash
   sudo systemctl status mariadb
   ```

3. **Test manual connection**:
   ```bash
   mysql -u inventory_user -p workshop_inventory
   ```

4. **Check migration status**:
   ```bash
   python manage.py db current
   python manage.py db history
   ```

## Data Integrity Auditing

The application provides audit commands to help identify data integrity issues and inconsistencies in your inventory.

### Audit Commands

All audit commands are available under the `audit` subcommand group:

```bash
# View available audit commands
python manage.py audit --help
```

### Materials Audit

The materials audit identifies inventory items that have materials not present in the materials taxonomy. This helps maintain data consistency and identify materials that need to be added to the taxonomy or corrected in existing items.

**Note**: The materials taxonomy supports a 3-level hierarchy (Category → Family → Material), and inventory items can be associated with materials at ANY level of this hierarchy. For example, an item can be labeled as "Carbon Steel" (Level 1 category), "Low Carbon Steel" (Level 2 family), or "A36" (Level 3 specific material) - all are equally valid.

#### Running Materials Audit

```bash
# Audit materials in inventory items
python manage.py audit materials
```

**Example output:**
```
Auditing materials...

Found 55 materials not in taxonomy:
============================================================
  Carbon Steel                             (153 items)
  Steel                                    (52 items)
  Brass                                    (49 items)
  Unknown                                  (37 items)
  Copper                                   (30 items)
  Aluminum                                 (18 items)
  321 Stainless                            (17 items)
  Brass 360-H02                            (9 items)
  Stainless?                               (9 items)
  15-5 Stainless                           (7 items)
  T-304 Stainless                          (5 items)
  410 Stainless                            (5 items)
  ...
============================================================
Total items with invalid materials: 470
```

#### Understanding Results

The audit report shows:
- **Material name**: The exact material string found in inventory items
- **Item count**: Number of inventory items using this material
- **Sort order**: Results are sorted by item count (descending), then alphabetically

#### Resolving Material Issues

When the audit finds materials not in the taxonomy, you can:

1. **Add materials to taxonomy**: Use the admin interface to add missing materials to the materials taxonomy
2. **Update inventory items**: Correct material names in existing inventory items to match taxonomy entries
3. **Add aliases**: If materials are variations of existing taxonomy entries, add them as aliases

#### When to Run Materials Audit

Run the materials audit:
- **After data imports** to identify materials that need taxonomy entries
- **Before major data cleanup** to understand the scope of material inconsistencies
- **Periodically** as part of regular data maintenance
- **After taxonomy changes** to verify all inventory items use valid materials

#### Best Practices

1. **Regular auditing**: Run materials audit monthly or after significant data changes
2. **Document decisions**: Keep notes on why certain materials were added or corrected
3. **Batch corrections**: Group similar materials for efficient processing
4. **Coordinate with users**: Inform users of material naming standards and taxonomy updates

### Locations Audit

The locations audit generates a comprehensive report of all inventory locations and sub-locations, showing which items are stored in each location. This helps with physical inventory management, organization planning, and identifying items that may need location updates.

#### Running Locations Audit

```bash
# Generate locations report
python manage.py audit locations
```

**Example output:**
```
Generating locations report...

Location Report
================================================================================
Total locations: 20
Total items: 514
================================================================================

📍 M1-A (94 items)
------------------------------------------------------------
  📂 Steel Bar 1 (30 items)
    JA000037   Carbon Steel Bar Rectangular (L:16.2500, W:2.0000, T:1.5000)
    JA000038   Carbon Steel Bar Rectangular (L:10.8750, W:1.5000, T:1.5000)
    JA000039   Carbon Steel Bar Rectangular (L:17.0000, W:1.0000, T:1.0000)
    ...

  📂 Steel Tube 1 (18 items)
    JA000015   Carbon Steel Tube Square (L:15.0000, W:2.0000, T:2.0000, ...
    JA000016   Carbon Steel Tube Square (L:15.5000, W:2.0000, T:2.0000, ...
    ...

📍 M1-B (117 items)
------------------------------------------------------------
  📂 Stainless 1 (26 items)
    JA000074   Unknown Bar Rectangular (L:5.0000, W:3.0000, T:0.3750)
    JA000099   Stainless? Bar Rectangular (L:14.2500, W:1.5000, T:0.2500)
    ...

📍 No Location (37 items)
------------------------------------------------------------
  📂 No Sub-location (37 items)
    JA000001   Unknown Bar Rectangular (L:24.0000, W:1.5000, T:0.7500)
    ...
================================================================================
Report complete
```

#### Understanding the Report

The locations report provides:
- **Total summary**: Overview of total locations and items
- **Hierarchical organization**: Locations grouped by main location, then sub-location
- **Item counts**: Number of items in each location and sub-location
- **Item details**: Each item shows JA ID, material, type, shape, and key dimensions
- **Sorted display**: Locations and sub-locations sorted alphabetically (with "No Location"/"No Sub-location" at the end)

#### Report Features

1. **Visual organization**: Uses emojis (📍 for locations, 📂 for sub-locations) for easy scanning
2. **Dimension display**: Shows relevant dimensions (Length, Width, Thickness, Wall Thickness) when available
3. **Description truncation**: Long item descriptions are truncated to maintain readable formatting
4. **Missing location handling**: Items without location/sub-location are clearly grouped and labeled

#### Using the Report

The locations audit is useful for:

**Inventory Management:**
- Physical location verification during inventory counts
- Identifying items that may be misplaced or need relocation
- Planning workshop organization and storage optimization

**Space Planning:**
- Understanding current space utilization across locations
- Identifying overcrowded or underutilized storage areas
- Planning expansion or reorganization of storage systems

**Workflow Optimization:**
- Grouping related materials for easier access
- Identifying frequently accessed items that should be in convenient locations
- Planning tool and equipment placement based on material locations

#### Best Practices

1. **Regular reporting**: Generate location reports monthly for inventory management
2. **Physical verification**: Use reports during physical inventory counts to verify item locations
3. **Organization planning**: Use item counts and types to optimize storage layout
4. **Data cleanup**: Identify items with missing or vague location information that need updates
5. **Coordinate updates**: Share location information with all workshop users to maintain accuracy

## Photo Management

The application provides tools for managing photo uploads and thumbnails, particularly for PDF files that require special processing.

### PDF Thumbnail Regeneration

When upgrading from a version without PDF thumbnail generation to one with PDF thumbnails, existing PDFs in the database will still have PDF binary data in their thumbnail fields instead of generated JPEG thumbnails. This prevents them from displaying properly as thumbnails.

#### Management Command

Use the integrated management command to regenerate thumbnails for existing PDFs:

```bash
# Preview what PDFs would be processed (recommended first step)
python manage.py photos regenerate-pdf-thumbnails --dry-run

# Actually regenerate thumbnails for existing PDFs
python manage.py photos regenerate-pdf-thumbnails
```

**Example output:**
```
PDF Thumbnail Regeneration
========================================
Started at: 2025-01-15 14:30:00.123456

Found 15 total PDF photos
Found 8 PDF photos that need thumbnail regeneration

Photos that would be processed:
  - manual.pdf (ID: 23, JA ID: JA000156)
  - schematic.pdf (ID: 34, JA ID: JA000198)
  - datasheet.pdf (ID: 45, JA ID: JA000234)
  ... and 5 more

To actually regenerate thumbnails, run without --dry-run

Completed at: 2025-01-15 14:30:01.456789
```

#### API Endpoint

For programmatic access or automation, use the admin API endpoint:

```bash
# Using curl
curl -X POST http://localhost:5000/api/admin/photos/regenerate-pdf-thumbnails

# Expected response
{
  "success": true,
  "message": "Regenerated thumbnails for 8 PDF photos",
  "photos_updated": 8
}

# Error response (if PyMuPDF not available)
{
  "success": false,
  "error": "Failed to regenerate PDF thumbnails: PyMuPDF not available"
}
```

#### When to Use

Run PDF thumbnail regeneration in these scenarios:
- **After upgrading** from a version without PDF thumbnail support
- **When PDFs show red placeholders** instead of actual page previews  
- **After system maintenance** that may have corrupted thumbnail data
- **When troubleshooting PDF display issues**

#### Technical Details

The regeneration process:
1. **Identifies PDFs** where `thumbnail_data` contains PDF binary data (starts with `%PDF`)
2. **Uses PyMuPDF** to generate JPEG thumbnails from the first page
3. **Updates database** with new JPEG thumbnail and medium-size data
4. **Preserves original PDF** data unchanged
5. **Requires PyMuPDF** to be installed (`pip install PyMuPDF==1.28.0`)

#### Best Practices

1. **Always run with `--dry-run` first** to preview what will be processed
2. **Backup your database** before running the actual regeneration
3. **Run during maintenance windows** for large numbers of PDFs
4. **Monitor process output** for any errors or warnings
5. **Verify results** by checking that PDFs now show proper thumbnails in the UI

### Photo Schema Refactoring (v2.x)

Starting in version 2.x, the photo storage schema was refactored to enable efficient photo copying between items. The database migration handles this automatically.

#### Schema Changes

**Old Schema** (v1.x):
- `item_photos` table: Photo data stored directly with each item
- Copying photos required duplicating large BLOB data

**New Schema** (v2.x):
- `photos` table: Photo data stored once, shared between items
- `item_photo_associations` table: Many-to-many relationships between items and photos
- Copying photos only creates association records (no BLOB duplication)

#### Migration Process

The Alembic migration (`refactor_photo_schema`) automatically:
1. Creates new `photos` and `item_photo_associations` tables
2. Migrates all existing photo data from `item_photos` to new schema
3. Preserves display order based on creation timestamps
4. Verifies data integrity before dropping old table
5. Includes rollback capability if migration fails

**Important:** The migration runs automatically when you run `flask db upgrade`. No manual intervention required.

#### Post-Migration Verification

After upgrading to v2.x, verify photo migration:

```bash
# Check that photos display correctly in the UI
# Navigate to inventory items with photos and verify they appear

# Check database schema
flask db current  # Should show latest migration

# Verify photo counts match
# All photos should be accessible after migration
```

#### Storage Benefits

With the new schema:
- **Storage Efficiency**: Photo data shared between items, not duplicated
- **Fast Operations**: Copying photos = creating association records only
- **Automatic Cleanup**: Orphaned photos (no associations) are automatically removed
- **Photo Copying**: New feature enables copying photos during duplication and via manual workflow

## Google Sheets Setup (Data Export Only)

**Note**: Google Sheets is used exclusively for data export functionality. The primary storage backend is MariaDB.

### 1. Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project or select existing
3. Enable Google Sheets API
4. Enable Google Drive API (for file access)

### 2. Create Service Account
1. Navigate to IAM & Admin → Service Accounts
2. Create new service account
3. Add role: Editor (or custom role with Sheets access)
4. Generate and download JSON key file
5. Save as `credentials/service_account.json`

### 3. Share Google Sheet
1. Open your inventory Google Sheet
2. Share with service account email
3. Grant Editor permissions
4. Copy Sheet ID from URL

### 4. Test Connection
```bash
python3 test_connection.py
```

## Monitoring and Maintenance

### 1. Log Monitoring

#### Application Logs
All application logs are output to STDOUT/STDERR in structured JSON format for easy integration with log aggregation systems (Docker, systemd, etc.). Logs include:
- General application events
- Error logs with full context
- Structured audit trail
- Performance metrics
- API access logs

#### System Logs
```bash
# Application service logs
sudo journalctl -u workshop-inventory -f
```

### 2. Health Checks
```bash
# Application health endpoint -- also reports the running version
curl http://localhost:5000/health
# {"service":"workshop-inventory-tracking","status":"healthy","version":"0.1.0"}
```

## Versioning and Releases

The project uses [Semantic Versioning](https://semver.org/). The version in the
`[project]` table of `pyproject.toml` is the single source of truth: the
application reads it at runtime (shown in the page footer and returned by
`/health`), and the release workflow reads it to decide whether to cut a release.

To cut a release:

1. Bump `version` in `pyproject.toml` following SemVer:
   - **MAJOR** -- a change that requires manual intervention to deploy, such as a
     migration that is not backward compatible or a required new configuration
     variable
   - **MINOR** -- new features or new (automatic) database migrations
   - **PATCH** -- bug fixes and documentation
2. Merge to `main`.

The `Release` workflow compares the new version against the latest GitHub
release. If it is higher, the workflow builds and pushes
`ghcr.io/jantman/workshop-inventory-tracking:<version>` and `:latest`, then
creates a `v<version>` GitHub release with generated notes. If the version is
unchanged, the workflow does nothing, so ordinary merges to `main` are safe.

## Serving Behind a TLS Reverse Proxy

If you terminate TLS in front of the application -- nginx, Caddy, Traefik -- the
proxy must pass the original scheme, host **and port** through:

```nginx
location / {
    proxy_pass http://workshop-inventory:5000;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host  $host;
    proxy_set_header X-Forwarded-Port  $server_port;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
}
```

All five lines are required. `$host` deliberately excludes the port, so the port
travels in its own header -- `$server_port` is the port the proxy is listening
on, which is the port the browser connected to. Send it unconditionally: on a
deployment that does sit on 443 or 80 the application omits a standard port from
the addresses it builds, so declaring it costs nothing.

The application trusts exactly one hop of those headers
(`werkzeug.middleware.proxy_fix.ProxyFix` in `app/__init__.py`). It has to,
because the connection it actually receives is plain HTTP: without them it
reports the page as `http` even though the browser loaded it over `https`.

That matters in one place beyond cosmetics. The capture bookmarklet on
`/products/capture` bakes the server's own address into itself when that page
renders. If the app thinks it is on `http`, the bookmarklet points at `http`,
and a vendor page sending `upgrade-insecure-requests` rewrites that to `https`
and fails against a server that does not answer TLS on that port. The page shows
a warning box whenever it believes it is being served over `http`, so if you are
looking at an `https` address bar and still see that box, the proxy is not
sending `X-Forwarded-Proto`.

**If you are serving on a non-default port, `X-Forwarded-Port` is not optional
and its absence is not cosmetic.** Without it the application believes it is on
the scheme's default port, and two things follow. The bookmarklet points at that
default port, where nothing is listening, so clicking it does nothing at all.
More seriously, every form that writes -- capture confirmation, add and edit
item, add and edit product, move, shorten, receive -- is refused with
`400 Bad Request: The referrer does not match the host`, because the CSRF
referrer check compares the address the form came from against the address the
application thinks it lives at, and a port is part of an address. Reads are
unaffected, so the deployment looks entirely healthy until you try to save
something. That was issue #114.

Nothing here is a security control. On a LAN-only single-user application there
is no one to spoof the headers; the trust is there so the URLs come out right.

## Security Posture for `/api/*` Endpoints

The application exposes a handful of JSON endpoints under `/api/*`
(item creation, photo upload, search, batch move, etc.). These
endpoints are intentionally:

- **Exempt from CSRF** so non-browser clients can call them without
  obtaining a token. The session-based form routes (e.g. the add-item
  page) remain CSRF-protected.
- **Unauthenticated** at the application layer. There is no built-in
  user identity, API key, or token check.

When deploying, restrict access to these endpoints at the network
layer (e.g. bind the service to localhost behind a reverse proxy that
enforces authentication, run only on a trusted internal network, or
front the application with mTLS / basic auth). Treat the API surface
as equivalent in trust to direct database access.
