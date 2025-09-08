# GitHub Actions Workflows

This directory contains automated workflows for the Workshop Inventory Tracking project.

## Workflows

### 🧪 `test.yml` - Main Test Suite
**Triggers:** Push to `main`/`develop`, Pull Requests
**Purpose:** Comprehensive testing and coverage reporting

**Jobs:**
- **Unit Tests**: Matrix testing across Python 3.8-3.13
- **Coverage**: Code coverage analysis with PR comments
- **E2E Tests**: End-to-end browser testing with Playwright
- **Test Summary**: Consolidated results and artifact management

**Artifacts on Failure:**
- `test-debug-output/` - E2E test failure diagnostics (screenshots, HTML dumps, console logs)
- `test-results/` - Playwright test results
- `.pytest_cache/` - Pytest cache and logs
- `coverage-reports` - HTML and XML coverage reports

### 🔒 `security.yml` - Security & Dependencies
**Triggers:** Weekly schedule, dependency file changes, manual dispatch
**Purpose:** Security scanning and dependency monitoring

**Jobs:**
- **Security Scan**: vulnerability scanning with pip-audit, safety, and bandit
- **Dependency Review**: License and security review for PRs

## Features

### PR Integration
- **Coverage Comments**: Automatic coverage percentage comments on PRs
- **Artifact Upload**: Debug information uploaded on test failures
- **Test Summary**: Consolidated pass/fail status across all test suites

### Caching
- **Pip Dependencies**: Cached based on requirements file hashes
- **Retention**: Artifacts retained for 7-30 days based on type

### Matrix Testing
- **Python Versions**: 3.8, 3.9, 3.10, 3.11, 3.12, 3.13
- **Fail-Fast**: Disabled to test all versions even if one fails

## Usage

### Manual Workflow Dispatch
```bash
# Trigger security scan manually
gh workflow run security.yml
```

### Local Testing Before Push
```bash
# Run the same commands as CI
nox -s tests     # Unit tests
nox -s coverage  # Coverage report
nox -s e2e       # E2E tests
```

### Viewing Results
- **GitHub UI**: Check Actions tab for workflow results
- **PR Comments**: Coverage percentage automatically commented
- **Artifacts**: Download debug information from failed runs

## Troubleshooting

### E2E Test Failures
1. Check `test-debug-output/` artifact for screenshots and HTML dumps
2. Review console logs in captured debug information
3. Examine page state JSON for context

### Coverage Issues
1. HTML coverage report available in `coverage-reports` artifact
2. XML report uploaded to Codecov (if configured)
3. Minimum threshold: 80%

### Dependency Issues
1. Security reports available in `security-reports` artifact
2. Dependency review blocks PRs with security issues
3. Weekly automated scans detect new vulnerabilities