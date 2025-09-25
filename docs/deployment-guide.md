# Workshop Inventory Tracking - Deployment Guide

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
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=your-secret-key-here-change-this

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

# Application Settings
APP_NAME=Workshop Inventory Tracking
APP_VERSION=1.0.0

# Performance Settings
CACHE_TTL=300
BATCH_SIZE=100
```

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
5. **Requires PyMuPDF** to be installed (`pip install PyMuPDF==1.24.9`)

#### Best Practices

1. **Always run with `--dry-run` first** to preview what will be processed
2. **Backup your database** before running the actual regeneration
3. **Run during maintenance windows** for large numbers of PDFs
4. **Monitor process output** for any errors or warnings
5. **Verify results** by checking that PDFs now show proper thumbnails in the UI

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
