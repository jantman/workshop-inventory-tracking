# Workshop Inventory Tracking - Deployment Guide

## Table of Contents

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

## Installation Process

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
Create `.env` file in project root:
```bash
# Flask Configuration
FLASK_APP=wsgi.py
# FLASK_ENV was removed in Flask 2.3 and is ignored by the version this
# application runs on -- setting it to `production` does NOT turn debug off.
# FLASK_DEBUG is the only switch, and leaving it off is what arms the
# SECRET_KEY refusal described below.
FLASK_DEBUG=0
# REQUIRED. Paste the value generated in "2. Secret Key Generation" below --
# do NOT leave a placeholder here. The application refuses to start when a
# non-debug config resolves SECRET_KEY to any value published in the repository
# (this placeholder included), because such a key makes every session cookie
# and CSRF token forgeable by anyone who can read the source.
SECRET_KEY=

# Storage Backend Configuration
STORAGE_BACKEND=mariadb  # MariaDB is the primary storage backend

# MariaDB Configuration (Production)
SQLALCHEMY_DATABASE_URI=mysql+pymysql://user:password@localhost/workshop_inventory
SQLALCHEMY_TRACK_MODIFICATIONS=False

# Google Sheets Configuration (Export Only)
GOOGLE_SHEET_ID=your-sheet-id-here  # Only needed for export functionality
GOOGLE_CREDENTIALS_PATH=credentials/service_account.json
GOOGLE_TOKEN_PATH=credentials/token.json

# Logging Configuration
LOG_LEVEL=INFO

# Request body size limits, in BYTES, enforced at the WSGI layer. A body over
# its limit is rejected with 413 before any view code runs.
#
# WHICH LIMIT GOVERNS WHICH KIND OF BODY:
#
#   MAX_REQUEST_BODY_BYTES  the whole-body transport cap for every request.
#                           Default 1 MiB.
#
#   MAX_UPLOAD_BODY_BYTES   replaces it, but ONLY for a request to
#                           /products/<id>/attachments or
#                           /api/items/<ja_id>/photos that is SHAPED LIKE a
#                           multipart upload -- Content-Type multipart/form-data
#                           with a non-empty boundary parameter. Default 24 MiB.
#                           Anything else sent to those same URLs gets the 1 MiB
#                           limit like every other request. Note the honest
#                           scope: that header is supplied by the caller, so the
#                           raised ceiling is available to anything shaped like
#                           an upload, not only to real ones.
#
#   MAX_FORM_MEMORY_SIZE    Flask's own 500 KB limit on a single non-file form
#                           value. It is NOT set here, and it is LOWER than the
#                           1 MiB default above, so where it applies it -- not
#                           the variables below -- is what rejects a large
#                           urlencoded POST or a long text field inside a
#                           multipart upload.
#
#                           IT DOES NOT ALWAYS APPLY. Werkzeug enforces it only
#                           when the request declares a Content-Length. Measured
#                           on the shipped defaults, one 600 KB urlencoded
#                           field:
#
#                             with Content-Length              -> 413
#                             no Content-Length, chunked or
#                             streamed (what gunicorn hands
#                             the app)                         -> NOT a 413;
#                                                                 the field is
#                                                                 parsed IN
#                                                                 FULL, all
#                                                                 600 KB of it
#
#                           In that second column MAX_FORM_MEMORY_SIZE is not
#                           consulted at all, and MAX_REQUEST_BODY_BYTES below
#                           is the only limit in play -- so a form field there
#                           is bounded at 1 MiB, NOT at 500 KB. Past 1 MiB the
#                           body is rejected in either column. To let a form
#                           carry more text WITH a declared length, set
#                           MAX_FORM_MEMORY_SIZE in config.py; raising
#                           MAX_REQUEST_BODY_BYTES will not move that column.
#
# The upload ceiling must be at least as large as the global limit, or the app
# refuses to start. Setting the two EQUAL is allowed and is the strictest
# uniform posture: the upload endpoints simply get the same cap as everything
# else. Setting the ceiling below the service file limits (20971520 bytes for a
# photo, 16777215 for an attachment) plus a few KiB of multipart framing is
# allowed too and logs a startup WARNING naming each one — that is the
# supported way to take a stricter posture, since the photo endpoint is
# unauthenticated and reads its file fully into memory.
#
# Neither value may exceed 1 GiB. These are allocation bounds, not just policy
# numbers, so an implausibly large value is treated as the typo it almost
# certainly is rather than as a decision to remove the bound.
#
# Plain digits only: no units, no '+', no '_' separators (surrounding whitespace
# is ignored). A value like 1MB is a startup error naming the variable.
#
# This is an APPLICATION-level bound. It does not stop the bytes reaching the
# WSGI server, which has already buffered or is streaming them by the time this
# runs. To stop them earlier, set the reverse proxy's own body limit as well —
# nginx's client_max_body_size, which needs to be at least as large as
# MAX_UPLOAD_BODY_BYTES or uploads will fail at the proxy instead.
MAX_REQUEST_BODY_BYTES=1048576
MAX_UPLOAD_BODY_BYTES=25165824

# Application Settings
APP_NAME=Workshop Inventory Tracking
APP_VERSION=1.0.0

# Performance Settings
CACHE_TTL=300
BATCH_SIZE=100
```

### 2. Secret Key Generation
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

The generator matters only in that the value must be private and random —
nothing checks the format. `token_hex` is used here, in `.env.example`, and in
the error message the application prints when it refuses to start, so that all
three tell you the same thing; `token_urlsafe(32)` is equally good if you
already have one.

> **The refusal only fires for a non-debug app.** `DEBUG` comes from
> `FLASK_DEBUG`, and this repository commits a `.flaskenv` setting
> `FLASK_DEBUG=1` — a file the Flask CLI reads automatically. A deployment
> started with `flask run` from a checkout therefore runs in debug mode, which
> both downgrades this refusal to a logged ERROR and exposes the Werkzeug
> debugger. Serve through `wsgi.py` under a real WSGI server, and do not set
> `FLASK_DEBUG` in a production `.env`.

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

4. **Update Environment Variables**:
   ```bash
   STORAGE_BACKEND=mariadb
   SQLALCHEMY_DATABASE_URI=mysql+pymysql://inventory_user:your_secure_password@localhost/workshop_inventory
   ```

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
# Application health endpoint
curl http://localhost:5000/health
```

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
