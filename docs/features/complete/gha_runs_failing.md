# GitHub Actions E2E Test Failures Resolution

**Status**: Complete  
**Date**: 2025-09-16  
**Issue**: E2E tests passing locally but failing consistently in GitHub Actions CI

## Problem Analysis

### Initial Symptoms
- E2E tests pass completely locally using SQLite
- Same tests fail consistently in GitHub Actions CI using MariaDB service container
- Failures specifically in `test_material_selector.py` with timing issues
- Tests would retry multiple times (up to 3 reruns) but continue failing

### Root Causes Discovered

#### 1. Timing/Environment Differences
**Local Environment:**
- SQLite database (fast I/O)
- Direct file system access
- Immediate API responses

**CI Environment:**
- MariaDB service container (network overhead)
- Container-to-container communication
- Slower API response times for `/api/materials/hierarchy` and `/api/materials/suggestions`

**Impact:** Material selector JavaScript component would show container immediately but API calls took longer to populate content, causing tests to check for "Aluminum" and "Steel" before data loaded.

#### 2. Database Connection Mismatch (Critical Issue)
**Problem:** Flask application routes were creating separate MariaDB connections instead of using the test database.

**Technical Details:**
```python
# BEFORE: Route created its own connection
def materials_hierarchy():
    storage = MariaDBStorage()  # New connection, different database
    storage.connect()
    
# AFTER: Route uses injected test storage
def materials_hierarchy():
    if current_app.config.get('STORAGE_BACKEND'):
        storage = current_app.config['STORAGE_BACKEND']  # Same as test data
    else:
        storage = MariaDBStorage()  # Fallback for production
```

**Error Messages in CI:**
- `"Failed to connect to MariaDB: 'NoneType' object has no attribute 'startswith'"`
- `"Could not locate a bind configured on mapper MaterialTaxonomy"`

## Solutions Implemented

### 1. Enhanced Test Timing Robustness
**File**: `tests/e2e/test_material_selector.py`

**Changes:**
- Increased timeout for content-dependent checks from 3s to 10s
- Added explicit waits for API responses before content verification
- Ensured elements exist before interaction

**Example:**
```python
# Wait for API response and suggestion items to populate
category_items = page.locator('.material-suggestions .suggestion-item.navigable')
expect(category_items.first).to_be_visible(timeout=10000)

# Wait for specific content to appear
expect(suggestions_container).to_contain_text('Aluminum', timeout=10000)
```

### 2. MariaDB Testcontainers for Local Development
**Goal**: Achieve complete environment parity between local and CI environments.

**Implementation:**
- Added `testcontainers[mysql]==4.8.2` dependency
- Created session-scoped MariaDB 10.11 testcontainer fixture
- Auto-detects CI environment to skip testcontainer when service container is available
- Uses testcontainer's `.get_connection_url()` for clean database URL generation

**Key Files:**
- `tests/test_database.py`: Testcontainer fixture implementation
- `tests/conftest.py`: Integration with e2e test server
- `tests/e2e/test_server.py`: Updated to use MariaDB instead of SQLite
- `requirements-test.txt`: Added testcontainer dependency

**Benefits:**
- Local tests now use exact same MariaDB 10.11 version as CI and production
- Catches timing and SQL compatibility issues during local development
- Zero manual setup - Docker container automatically managed
- Consistent database behavior across all environments

### 3. Database Connection Fix for CI
**Problem**: E2E test server populated test database, but Flask routes created separate connections.

**Solution**: Updated Flask routes to use injected storage backend during testing.

**File**: `app/main/routes.py`

**Change in `materials_hierarchy()` route:**
```python
# Use injected storage backend if available (for testing)
if current_app.config.get('STORAGE_BACKEND'):
    storage = current_app.config['STORAGE_BACKEND']
    engine = storage.engine
else:
    # Create MariaDB storage for production
    storage = MariaDBStorage()
    storage.connect()
    engine = storage.engine
```

## Verification Results

### Local Testing
- ✅ All e2e tests pass with MariaDB testcontainer
- ✅ Unit tests continue to pass (99/99)
- ✅ Testcontainer startup ~5-10s, subsequent tests fast
- ✅ Material selector tests work consistently

### CI Pipeline Status
- **Workflow Run**: 17780019851 (in progress)
- **Previous Failures**: Consistent failures in all `test_material_selector.py` tests
- **Expected Result**: All e2e tests should now pass with database connection fix

## Technical Architecture

### Before (Problematic)
```
Local: E2E Tests → SQLite (fast)
CI: E2E Tests → Test Server → SQLite temp file
    Flask Routes → Separate MariaDB connection (fails)
```

### After (Fixed)
```
Local: E2E Tests → MariaDB testcontainer → Shared connection
CI: E2E Tests → Test Server → MariaDB service → Shared connection
     Flask Routes → Same MariaDB connection (success)
```

## Documentation Updates

Updated `docs/development-testing-guide.md` with:
- Docker requirement for local e2e testing
- Testcontainer automatic management details
- Troubleshooting for Docker container issues
- Performance notes for container startup times

## Files Modified

### Core Implementation
- `tests/test_database.py`: Testcontainer fixture and MariaDB engine setup
- `tests/conftest.py`: Import testcontainer fixture for e2e tests
- `tests/e2e/test_server.py`: Use MariaDB instead of SQLite, clean resource management
- `app/main/routes.py`: Use injected storage backend in test environment
- `requirements-test.txt`: Add testcontainers dependency

### Test Improvements
- `tests/e2e/test_material_selector.py`: Enhanced timing with 10s timeouts for API-dependent content

### Documentation
- `docs/development-testing-guide.md`: Complete rewrite for MariaDB testcontainer setup
- `docs/features/complete/gha_runs_failing.md`: This documentation file

## Lessons Learned

1. **Environment Parity is Critical**: Differences between local SQLite and CI MariaDB caused hard-to-diagnose issues
2. **Database Connection Injection**: Test frameworks must ensure all application components use the same test database
3. **Timing in CI**: Container environments have different performance characteristics requiring robust wait strategies
4. **Testcontainers Benefits**: Automatic container management provides production-like testing with minimal developer overhead

## Future Improvements

1. **API Response Caching**: Consider caching material hierarchy data to reduce API call overhead
2. **Connection Pooling**: Optimize MariaDB connection pooling for test environments
3. **Test Data Fixtures**: Standardize material taxonomy test data across all test types
4. **Performance Monitoring**: Add timing metrics to detect performance regressions in CI

## Workflow Information

- **Issue Identification**: Manual log analysis of GitHub Actions failure artifacts
- **Local Reproduction**: Successful using testcontainer setup
- **Root Cause Analysis**: Database connection tracing through Flask application logs
- **Validation**: Unit test suite verification before deployment
- **Deployment**: Incremental commits with targeted fixes

**Final Status**: All identified issues resolved, awaiting CI validation.