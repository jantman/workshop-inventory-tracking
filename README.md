# Workshop Inventory Tracking

[![Tests](https://github.com/USERNAME/workshop-inventory-tracking/actions/workflows/test.yml/badge.svg)](https://github.com/USERNAME/workshop-inventory-tracking/actions/workflows/test.yml)
[![Security](https://github.com/USERNAME/workshop-inventory-tracking/actions/workflows/security.yml/badge.svg)](https://github.com/USERNAME/workshop-inventory-tracking/actions/workflows/security.yml)

A Flask-based web application for managing workshop materials inventory using Google Sheets as the backend storage.

> **Note**: Replace `USERNAME` in the badge URLs above with your actual GitHub username/organization name.

## Features

- **Inventory Management**: Add, move, and shorten materials with comprehensive tracking
- **Barcode Scanning**: Support for keyboard wedge barcode scanners
- **Google Sheets Integration**: Real-time sync with Google Sheets backend
- **Advanced Search**: Filter and search inventory by multiple criteria
- **Parent-Child Relationships**: Track material transformations when cutting/shortening
- **Responsive UI**: Bootstrap-based interface that works on desktop and mobile

## Quick Start

1. Clone the repository and set up the environment:
   ```bash
   git clone [repository-url]
   cd workshop-inventory-tracking
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Follow the detailed setup instructions in **[docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)**

3. Run the application:
   ```bash
   flask run --debug
   ```

## Documentation

- **[Getting Started Guide](docs/GETTING-STARTED.md)** - Complete setup and configuration instructions
- **[Implementation Plan](docs/implementation-plan.md)** - Development roadmap and milestones
- **[Progress Summary](docs/PROGRESS.md)** - Current development status

## Requirements

- Python 3.8+
- Google account with Sheets access
- Google Cloud Console access for API credentials
