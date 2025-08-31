# Workshop Inventory Tracking - Getting Started Guide

This guide will walk you through setting up and running the Workshop Inventory Tracking application.

## Overview

The Workshop Inventory Tracking application is a Flask-based web application that manages workshop materials inventory using Google Sheets as the backend storage. It provides features for adding inventory, moving items, shortening materials, and comprehensive inventory listing with search capabilities.

## Prerequisites

- Python 3.8 or higher
- Google account with access to Google Sheets
- Google Cloud Console access (for API credentials)

## Installation

### 1. Clone and Setup Environment

```bash
# Clone the repository
git clone [repository-url]
cd workshop-inventory-tracking

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and customize it:

```bash
cp .env.example .env
```

Edit `.env` to set your configuration:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True

# Google Sheets API Configuration
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json
GOOGLE_SHEET_ID=your-google-sheet-id-here

# Application Configuration  
LOG_LEVEL=INFO
```

## Google Sheets API Setup

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Note your project ID

### 2. Enable Google Sheets API

1. In Google Cloud Console, go to **APIs & Services** → **Library**
2. Search for "Google Sheets API"
3. Click on it and click **Enable**

### 3. Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. If prompted, you'll need to configure the OAuth consent screen first:
   - Choose "External" user type
   - Fill in required fields (App name, User support email, Developer contact)
   - Add your email to test users
   - Save and continue through the steps
4. After the consent screen is configured, you'll be taken to create the OAuth client ID
5. For **Application type**, choose **Desktop application**
6. Give it a name (e.g., "Workshop Inventory")
7. Click **Create**
8. **Download** the credentials JSON file
9. Rename it to `credentials.json` and place it in the project root directory

### 4. Prepare Google Sheet

You need a Google Sheet with your inventory data. The application expects:
- A sheet named "Metal" with your current inventory data
- The migration script will create the proper structure

Update your `.env` file with your Google Sheet ID (found in the sheet URL):
```
GOOGLE_SHEET_ID=your-actual-sheet-id-here
```

## First Time Setup

### 1. Test Google Sheets Connection

```bash
source venv/bin/activate
python test_connection.py
```

This will:
- Validate your configuration
- Test Google Sheets API connection
- Prompt for OAuth authorization (first time only)
- Create a `token.json` file for future use

### 2. Run Data Migration (if you have existing data)

First, run a dry-run to see what would be migrated:

```bash
python migrate_data.py
```

If the dry-run looks good, execute the migration:

```bash
python migrate_data.py --execute
```

This will:
- Backup your original "Metal" sheet (rename to "Metal_original")
- Create a new "Metal" sheet with the proper structure
- Migrate and normalize your data
- Generate a migration report

## Running the Application

### Development Mode

```bash
source venv/bin/activate
flask run --debug
```

The application will be available at: http://127.0.0.1:5000

### Production Mode

```bash
source venv/bin/activate
python wsgi.py
```

## Application Features

### Main Navigation

- **Home**: Application overview and status
- **Inventory → Add New Item**: Add individual inventory items
- **Inventory → View All Items**: Browse and search all inventory
- **Inventory → Move Items**: Batch move items to new locations
- **Inventory → Shorten Items**: Cut materials and track relationships

### Key Features

1. **Barcode Scanning**: Supports keyboard wedge barcode scanners
2. **Form Validation**: Comprehensive validation for all data entry
3. **Carry-Forward**: Previous values are remembered to speed data entry
4. **Parent-Child Tracking**: Track material relationships when shortening
5. **Real-time Updates**: All changes sync immediately to Google Sheets

## Testing the Application

### 1. Test Inventory Listing

- Navigate to "View All Items" to see your migrated inventory
- Test filtering, sorting, and search functionality

### 2. Test Adding New Items

- Use "Add New Item" to add a test item
- Verify barcode scanning works (if you have a scanner)
- Check that carry-forward works for repeated fields

### 3. Test Item Movement

- Use "Move Items" to test batch moving functionality
- Try scanning item IDs and locations
- Use ">>DONE<<" to submit batch operations

### 4. Test Item Shortening

- Use "Shorten Items" to cut a piece of material
- Verify parent-child relationships are created
- Check that the original item is marked inactive

## File Structure

```
workshop-inventory-tracking/
├── app/                    # Main application package
│   ├── models.py          # Data models and validation
│   ├── inventory_service.py # Business logic
│   ├── taxonomy.py        # Material and type management
│   ├── google_sheets_storage.py # Google Sheets integration
│   ├── auth.py           # Google OAuth handling
│   ├── main/             # Main blueprint
│   │   └── routes.py     # Web routes and API endpoints
│   ├── static/           # Static assets (CSS, JS)
│   └── templates/        # Jinja2 templates
├── docs/                 # Documentation
├── logs/                 # Application logs
├── migrate_data.py       # Data migration script
├── test_connection.py    # Connection testing utility
├── requirements.txt      # Python dependencies
├── .env                  # Environment configuration
└── wsgi.py              # WSGI entry point
```

## Configuration Files

- **`.env`**: Environment variables and configuration
- **`credentials.json`**: Google OAuth client credentials (you provide this)
- **`token.json`**: OAuth access token (auto-generated)
- **`config.py`**: Flask configuration class

## Troubleshooting

### Common Issues

1. **"No Google Sheets ID provided"**
   - Make sure `GOOGLE_SHEET_ID` is set in `.env`

2. **"Google credentials file not found"**
   - Download `credentials.json` from Google Cloud Console
   - Place it in the project root directory

3. **OAuth errors**
   - Make sure the OAuth consent screen is configured
   - Add yourself as a test user
   - Check that the Google Sheets API is enabled

4. **Permission denied errors**
   - Make sure your Google account has access to the sheet
   - Check that the sheet ID in `.env` is correct

### Getting Help

1. Check application logs in the `logs/` directory
2. Run `python test_connection.py` to diagnose connection issues
3. Verify your Google Cloud Console configuration
4. Make sure all required environment variables are set

## Data Backup

The application automatically creates backups during migration, but you should:
1. Regularly backup your Google Sheet
2. Keep a copy of your `credentials.json` and `.env` files
3. Monitor the `logs/` directory for any errors

## Security Considerations

- Keep your `credentials.json` file secure and never commit it to version control
- Use a strong `SECRET_KEY` in production
- Regularly rotate your Google API credentials
- Monitor access logs for unusual activity

## Next Steps

Once the application is running:
1. Test all core workflows with real data
2. Set up any barcode scanners you plan to use
3. Train users on the interface and workflows
4. Consider setting up automated backups
5. Monitor logs for any issues or performance problems