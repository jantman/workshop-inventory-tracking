# Workshop Inventory Tracking

[![Tests](https://github.com/USERNAME/workshop-inventory-tracking/actions/workflows/test.yml/badge.svg)](https://github.com/USERNAME/workshop-inventory-tracking/actions/workflows/test.yml)
[![Security](https://github.com/USERNAME/workshop-inventory-tracking/actions/workflows/security.yml/badge.svg)](https://github.com/USERNAME/workshop-inventory-tracking/actions/workflows/security.yml)

A production-ready Flask web application for comprehensive workshop materials inventory management with Google Sheets integration, advanced search capabilities, and professional user experience features.

> **Note**: Replace `USERNAME` in the badge URLs above with your actual GitHub username/organization name.

## Features

- **Complete Inventory Management**: Add, move, shorten, and track materials with parent-child relationships
- **Barcode Scanner Integration**: Keyboard wedge barcode scanner support across all workflows
- **Google Sheets Backend**: Real-time synchronization with Google Sheets for data persistence
- **Advanced Search & Filtering**: Range queries, compound filters, CSV export, and URL bookmarking
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

2. **Configure Google Sheets Integration**:
   - Follow the setup guide in [docs/deployment-guide.md](docs/deployment-guide.md)
   - Set up Google Cloud Console API credentials
   - Configure your Google Sheets backend

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

**Automated deployment**:
```bash
git clone [repository]
cd workshop-inventory-tracking
sudo deployment/deploy.sh
```

**Docker deployment**:
```bash
cd deployment/docker
cp .env.example .env
# Edit .env with your configuration
docker-compose up -d
```

## Testing

The project includes a comprehensive testing framework with 100% success rates:

- **Unit Tests**: 66/66 passing - `nox -s tests`
- **E2E Tests**: 20/20 passing - `nox -s e2e`
- **Coverage Report**: `nox -s coverage`

## Requirements

- Python 3.13
- Google account with Sheets access
- Google Cloud Console access for API credentials
- Chrome/Chromium browser (for E2E testing)
