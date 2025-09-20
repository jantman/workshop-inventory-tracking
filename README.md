# Workshop Inventory Tracking

[![Tests](https://github.com/jantman/workshop-inventory-tracking/actions/workflows/test.yml/badge.svg)](https://github.com/jantman/workshop-inventory-tracking/actions/workflows/test.yml)
[![Security](https://github.com/jantman/workshop-inventory-tracking/actions/workflows/security.yml/badge.svg)](https://github.com/jantman/workshop-inventory-tracking/actions/workflows/security.yml)

A ⚠️☠️🚨 **vibe-coded**, authored by Claude, and minimally reviewed ⚠️☠️🚨 Flask web application for comprehensive workshop materials inventory management with dual storage backend support (Google Sheets/MariaDB), advanced search capabilities, and professional user experience features.

## Features

- **Complete Inventory Management**: Add, move, shorten, and track materials with parent-child relationships
- **MariaDB Storage Backend**: Production-ready database with Google Sheets export functionality
- **Multi-Row Item History**: Complete shortening history tracking with active/inactive item management
- **Barcode Scanner Integration**: Keyboard wedge barcode scanner support across all workflows
- **Advanced Search & Filtering**: Range queries, compound filters, CSV export, and URL bookmarking
- **Item History API**: RESTful endpoints for accessing complete item modification history
- **Thread System Management**: Standardized thread formats with semantic validation
- **Professional UI/UX**: Bootstrap 5.3.2 responsive interface with 15+ keyboard shortcuts
- **Performance Optimization**: Caching, batch operations, and monitoring capabilities
- **Production-Grade Error Handling**: Custom exceptions, circuit breakers, and comprehensive logging
- **Automated Deployment**: Complete Docker containerization and monitoring tools

## Quick Start

1. **Clone and Setup**:
   ```bash
   git clone [repository-url]
   cd workshop-inventory-tracking
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Database**:
   - Follow the setup guide in [docs/deployment-guide.md](docs/deployment-guide.md)
   - Set up MariaDB database
   - Configure Google Sheets credentials for export functionality (optional)

3. **Run the Application**:
   ```bash
   flask run --debug
   ```

## Documentation

- **[Deployment Guide](docs/deployment-guide.md)** - Production deployment and configuration
- **[User Manual](docs/user-manual.md)** - Complete feature guide and workflows
- **[Development Testing Guide](docs/development-testing-guide.md)** - Testing framework and development workflow
- **[Troubleshooting Guide](docs/troubleshooting-guide.md)** - Problem-solving and diagnostics

## Production Deployment

For production deployment, follow the comprehensive setup guide in [docs/deployment-guide.md](docs/deployment-guide.md) which covers:

- MariaDB installation and configuration
- Environment variable setup
- Database migrations
- Application service configuration

## Testing

The project includes a comprehensive testing framework with 100% success rates:

- **Unit Tests**: 66/66 passing - `nox -s tests`
- **E2E Tests**: 20/20 passing - `nox -s e2e`
- **Coverage Report**: `nox -s coverage`

## Requirements

- Python 3.13
- MariaDB database server
- Google Cloud Console access for API credentials (for export functionality)
- Chrome/Chromium browser (for E2E testing)
