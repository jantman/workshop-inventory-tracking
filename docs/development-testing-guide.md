# Development and Testing Guide

## Development Setup

### Prerequisites
- Python 3.13
- Git
- **Docker** (for E2E tests with MariaDB testcontainer)
- Chrome/Chromium browser (for E2E tests)

### Initial Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd workshop-inventory-tracking
   ```

2. **Create and activate virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-test.txt
   ```

4. **Install Playwright browsers** (for E2E tests):
   ```bash
   python -m playwright install chromium
   ```

## Test Suites

The project uses **Nox** for consistent test execution across environments. All test commands should be run from the project root directory.

### Available Test Suites

#### 1. Unit Tests
**Command**: `nox -s tests`

**Purpose**: Tests individual components in isolation using mock dependencies.

**Coverage**:
- **Model Tests** (`test_models.py`): Item, Dimensions, Thread classes and enum validation
- **Service Tests** (`test_inventory_service.py`): Business logic, search, filtering, batch operations using SQLite backend
- **InventoryService Tests** (`test_mariadb_inventory_service.py`): MariaDB-specific active-only filtering logic
- **Basic Tests** (`test_basic.py`): Infrastructure and integration points
- **Audit Tests** (`test_audit_logging.py`): Audit logging functionality

**Runtime**: ~0.3 seconds

#### 2. End-to-End (E2E) Tests
**Command**: `nox -s e2e`

**Purpose**: Tests complete user workflows through the web interface using browser automation.

**Database**: Uses **MariaDB testcontainer** locally (auto-managed) and MariaDB service in CI

**Coverage**:
- **Form Submission**: Adding new inventory items via web form
- **Data Persistence**: Verifying items are saved and retrievable
- **UI Integration**: Testing Flask routes, templates, and JavaScript interactions
- **Multi-Row Scenarios**: Testing active item lookup and history functionality
- **API Endpoints**: Testing item history API and data retrieval logic

**Technology**: Playwright with Chromium browser + MariaDB 10.11 testcontainer

**Runtime**: ~10-15 seconds (plus initial Docker container startup)

**Debug Features**:
- Automatic failure capture with screenshots, HTML dumps, and console logs
- Debug output saved to `test-debug-output/` with timestamped directories
- Comprehensive diagnostic information for failed test analysis

#### 3. Test Coverage Report
**Command**: `nox -s coverage`

**Purpose**: Generates detailed code coverage analysis.

**Output**: 
- Terminal coverage summary
- HTML report in `htmlcov/index.html`

### Quick Test Commands

```bash
# Run all unit tests
nox -s tests

# Run specific test file
python -m pytest tests/unit/test_models.py -v

# Run specific test method
python -m pytest tests/unit/test_models.py::TestItem::test_item_creation_minimal -v

# Run E2E tests (requires Flask server)
nox -s e2e

# Generate coverage report
nox -s coverage

# List all available nox sessions
nox -l
```

## Test Architecture

### Unit Test Structure

**MariaDB with SQLite Backend**: Unit tests use MariaDBStorage with SQLite in-memory database for fast, isolated testing. This provides MariaDB interface compatibility while using SQLite for speed.

**Fixtures**: 
- `app`: Flask application context for service tests
- `test_storage`: Fresh MariaDBStorage instance with SQLite backend per test
- `service`: InventoryService with test storage (no batching or caching)
- `sample_item`/`sample_threaded_item`: Pre-configured test data with full validation

### E2E Test Structure

**Test Server**: Dedicated Flask server with test configuration that uses MariaDB (testcontainer locally, service in CI). Direct database writes ensure test data is immediately available.

**MariaDB Testcontainer**: Automatically managed Docker container with MariaDB 10.11, same version as production. No manual setup required.

**Page Objects**: Organized test code that interacts with web elements using Playwright selectors.

**Test Isolation**: Each E2E test runs with a fresh database state.

**Debug Capture**: Automated failure diagnostics with comprehensive debugging information:
- **Screenshots**: Full-page screenshots at failure point (`failure_screenshot.png`)
- **HTML Dumps**: Complete DOM state for analysis (`failure_page.html`)  
- **Console Logs**: Browser console output including errors (`console_logs.json`)
- **Page State**: URL, title, viewport, and failure context (`page_state.json`)
- **Browser Storage**: localStorage and sessionStorage contents
- **Debug Summary**: Human-readable analysis guide (`DEBUG_SUMMARY.md`)

## Running the Flask Application

### Development Server

For local development and testing, you can run the Flask application directly with automatic reloading enabled.

**Command**: 
```bash
# Activate virtual environment first
source venv/bin/activate

# Run Flask development server
python app.py
```

**Features**:
- **Auto-reload**: Server automatically restarts when code changes are detected
- **Debug mode**: Detailed error messages with stack traces in browser
- **Local access**: Available at `http://127.0.0.1:5000`
- **Hot reloading**: Template and static file changes are reflected immediately

**Alternative Methods**:
```bash
# Using Flask CLI
export FLASK_APP=app.py
export FLASK_ENV=development
flask run

# Using Python module
python -m flask run --debug

# Custom host/port
python app.py  # Configured for 127.0.0.1:5000
```

**Development Configuration**:
- Debug mode enabled by default in `app.py`
- Automatic template reloading
- Static file serving with cache disabled
- Detailed error pages with interactive debugger

**Note**: The development server uses MariaDB for data storage (production setup). E2E tests use MariaDB testcontainer to match production exactly.

## Development Workflow

### Running Tests During Development

1. **Quick validation**: `nox -s tests` (runs in ~0.3s)
2. **Full validation**: `nox -s tests && nox -s e2e`
3. **Coverage check**: `nox -s coverage` (check `htmlcov/index.html`)

### Test-Driven Development

1. Write failing test for new feature
2. Implement minimal code to make test pass
3. Refactor while keeping tests green
4. Run full test suite before committing

### Common Test Patterns

```python
# Unit test with fixtures
@pytest.mark.unit
def test_feature(self, service, sample_item):
    result = service.some_method(sample_item)
    assert result.success

# E2E test with browser automation
@pytest.mark.e2e
def test_workflow(page):
    page.goto("http://127.0.0.1:5000/inventory/add")
    page.fill("#ja_id", "JA000001")
    page.click("#submit-btn")
    expect(page.locator(".alert-success")).to_be_visible()
```

## Troubleshooting

### Common Issues

**Docker Container Issues**:
- Error: `Cannot connect to the Docker daemon`
- Solution: Ensure Docker is running: `sudo systemctl start docker` (Linux) or start Docker Desktop
- Error: `Permission denied while trying to connect to Docker`
- Solution: Add user to docker group: `sudo usermod -aG docker $USER` and restart terminal

**Testcontainer Startup Issues**:
- Error: `MariaDB container failed to start`
- Solution: Check Docker logs: `docker logs <container_id>`, ensure port 3306 is available
- Slow startup: Initial MariaDB container download may take time, subsequent runs are faster

**Playwright Browser Issues (Arch Linux)**:
- Error: `sudo: a password is required`
- Solution: Browsers installed without `--with-deps` flag to avoid sudo requirements

**Test Failures After Model Changes**:
- Check that test data matches new validation rules (e.g., JA ID format: `JA######`)
- Update fixtures if model constructors change

**E2E Test Flakiness**:
- MariaDB testcontainer provides consistent database state
- Check Docker container health if tests consistently fail
- Use explicit waits: `page.wait_for_selector(selector)`

**E2E Test Debugging**:
- Failed tests automatically capture debug information to `test-debug-output/`
- Review captured screenshots to see visual state at failure
- Check console logs for JavaScript errors or API failures
- Examine HTML dumps for missing elements or incorrect page state
- Use debug summary for guided troubleshooting steps

**Import Errors**:
- Ensure virtual environment is activated
- Verify all dependencies installed: `pip install -r requirements-test.txt`

### Getting Help

- Check test output for specific error messages
- Run with verbose mode: `python -m pytest -v --tb=long`
- Use debugger: Add `import pdb; pdb.set_trace()` in test code

## Performance Notes

- **Unit tests**: Optimized for speed with SQLite in-memory database via MariaDB interface
- **E2E tests**: Use MariaDB testcontainer for production parity. Initial startup ~5-10s, subsequent tests are fast
- **Docker optimization**: Testcontainer reuses same container across test session for efficiency
- **Test Isolation**: Each test uses fresh database state with fast MariaDB operations
- **E2E data persistence**: Direct database writes ensure test data is immediately available

## Continuous Integration

All test suites run automatically on pull requests. Local development should ensure:

1. All unit tests pass: `nox -s tests`
2. E2E tests pass: `nox -s e2e`  
3. Code coverage maintained: `nox -s coverage`

The test suite is designed to be fast and reliable for rapid development iterations.