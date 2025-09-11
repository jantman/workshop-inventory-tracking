# Material Length Enhancement

This document outlines a comprehensive migration from Google Sheets to MariaDB storage backend to resolve critical data model issues with the inventory shortening workflow.

## Problem Statement

The current shortening workflow and data storage system has fundamental issues that prevent proper functionality:

### Data Model Issues
The application currently treats JA IDs as unique primary keys, but the actual requirement is to support multiple rows per JA ID representing the history of shortening operations. In the original Google Sheets data, items like `JA000211` have multiple rows:
- Row 226: inactive, length 53.5"
- Row 227: inactive, length 48" 
- Row 228: active, length 45.625"

### UI Data Display Problems
This multi-row structure causes inconsistent data display across the application:
- **Inventory List**: Correctly shows active row data (45.625")
- **Item Details Modal**: Incorrectly shows first/inactive row data (53.5") 
- **Edit Item View**: Incorrectly shows first/inactive row data (53.5")
- **Shorten Items View**: Fails to find items due to finding inactive rows

### Test Coverage Gap
E2E tests use SQLite while production uses Google Sheets, creating a disparity that masks data model issues that only occur with the Google Sheets multi-row structure.

### Workflow Design Issues
The shortening UI contains fields like "Operation Summary" and "Relationship Tracking" that imply creating new JA IDs, but the requirement is to keep the same JA ID throughout the item's lifecycle.

## Solution Overview

Migrate from Google Sheets to MariaDB as the primary data store to:
- Enable proper data modeling with primary keys, constraints, and relationships
- Support multiple rows per JA ID with proper active/inactive tracking
- Eliminate production/test backend disparity
- Enable proper shortening workflow that preserves JA IDs

## Design Decisions

### Storage Backend
- **MariaDB** chosen over SQLite for production robustness and existing infrastructure
- **Same backend for tests** to eliminate production/test disparity
- **Google Sheets export capability** maintained for data access and backup

### Data Model
- **Row-based primary keys** instead of JA ID primary keys
- **Unique constraint** preventing multiple active rows per JA ID
- **History tracking** through inactive rows with timestamp data
- **Keep same JA ID** throughout item lifecycle, including after shortening

### Shortening Workflow
- **Preserve JA ID** when shortening items
- **Create new active row** and deactivate previous row
- **Track history** of previous lengths and modification dates
- **Remove obsolete UI fields** that imply new ID generation

### Testing Strategy
- **MariaDB for all tests** using Docker Compose locally and GitHub Actions
- **Multi-row test scenarios** to verify proper active/inactive handling
- **Comprehensive coverage** of inventory list, item details, edit, and shorten views

## Goals and Requirements

### Primary Goals
- **Preserve JA IDs** throughout item lifecycle, including after shortening
- **Maintain shortening history** showing previous lengths and modification dates
- **Fix data display consistency** across all UI views
- **Enable proper shortening workflow** that works with multi-row items

### Secondary Goals
- **Future-proof for dimension changes** (support length/width modifications)
- **Maintain data export capability** to Google Sheets format
- **Eliminate test/production disparity** through consistent backend usage

## Implementation Plan and Status Tracking

### Milestone 1: Database Foundation & Test Infrastructure

#### Task 1.1: Setup MariaDB Support & Schema Design
- Add MariaDB/MySQL dependencies to requirements.txt
- Create database configuration management (environment variables, connection pooling)
- Design initial database schema with proper primary keys and constraints
- Ensure schema supports multiple rows per JA ID with active/inactive status
- Add unique constraint preventing multiple active rows per JA ID

#### Task 1.2: Implement Alembic Migration System
- Setup Alembic configuration and directory structure
- Create initial migration for base schema
- Add migration commands to application CLI or management interface
- Document migration workflow for development and deployment

#### Task 1.3: Setup MariaDB Test Infrastructure
- Create Docker Compose configuration for local MariaDB test instance
- Update GitHub Actions to use MariaDB service container instead of SQLite
- Modify test fixtures and setup to work with MariaDB
- Ensure test isolation (fresh database per test or transaction rollbacks)
- Update all existing unit tests to work with MariaDB

#### Task 1.4: Create New Storage Backend
- Implement MariaDB storage backend alongside existing Google Sheets backend
- Ensure storage interface remains consistent for application code
- Add configuration switch between storage backends
- Update storage backend to handle multi-row queries correctly (active vs all rows)

### Milestone 2: Data Migration & Verification

#### Task 2.1: Analyze Existing Google Sheets Data
- Examine actual inventory data structure and content (Metal sheet)
- Examine actual materials taxonomy data structure and content (Materials sheet)
- Identify all JA IDs with multiple rows and their patterns
- Document any data quality issues or edge cases in both datasets
- Create comprehensive inventory of data to be migrated

#### Task 2.2: Build Data Migration Tool
- Create migration script to read from both Google Sheets (Metal and Materials) and write to MariaDB
- Handle data type conversions and validation for both inventory items and materials taxonomy
- Map Google Sheets columns to database schema for both tables
- Add error handling and logging for migration process
- Support hierarchical materials taxonomy migration with proper parent-child relationships

#### Task 2.3: Execute and Verify Data Migration
- Run migration process on actual Google Sheets data (both Metal and Materials sheets)
- Implement verification script to compare Google Sheets vs MariaDB data for both datasets
- Verify item counts, active/inactive status, and data integrity for inventory items
- Verify materials taxonomy hierarchy, relationships, and data integrity
- Generate migration report showing successful transfers and any issues
- Fix any discrepancies between source and target data

#### Task 2.4: Update Application Configuration and Services
- Switch application from Google Sheets to MariaDB backend
- Update inventory service to use new storage backend
- Update materials service to use MariaDB instead of Google Sheets storage
- Ensure all existing functionality works with MariaDB (inventory and materials)
- Remove Google Sheets dependencies from core application logic

### Milestone 3: Google Sheets Export Functionality

#### Task 3.1: Design Export Data Structure
- Define export data format that matches original Google Sheets layout for both datasets
- Include row IDs and optimize for human readability
- Handle both active and inactive rows in inventory export
- Design inventory export to match current `Metal_Export` sheet structure
- Design materials taxonomy export to match original Materials sheet structure

#### Task 3.2: Implement Export Service Class
- Create service class to query all inventory data from MariaDB
- Create service class to query all materials taxonomy data from MariaDB
- Format data for Google Sheets export (column mapping, data types) for both datasets
- Handle large datasets efficiently (batching if necessary)
- Add error handling and logging for export operations

#### Task 3.3: Create Export Web Endpoint
- Add admin endpoint for triggering exports (`/admin/export` or similar)
- Support exporting inventory data, materials taxonomy, or both
- Support both web UI button and direct API calls (curl-friendly)
- Return appropriate responses (success/failure, progress updates)
- Add authentication/authorization as needed

#### Task 3.4: Implement Google Sheets Upload
- Connect to Google Sheets API to write to `Metal_Export` sheet for inventory data
- Connect to Google Sheets API to write to `Materials_Export` sheet for materials taxonomy
- Clear existing data and replace with fresh export
- Handle API rate limits and error conditions
- Add progress indication for large exports

### Milestone 4: Fix Item Data Retrieval Logic

#### Task 4.1: Update Item Lookup Logic
- Modify all item queries to return only active rows by default
- Update get_item(), search_items(), and related methods
- Ensure consistent active-only behavior across all views
- Add explicit methods for historical data when needed

#### Task 4.2: Fix UI Data Display Issues
- Update Inventory List view to show active row data (already working)
- Fix Item Details modal to display active row data instead of first row
- Fix Edit Item view to load and update active row data
- Update Shorten Items view to find and load active rows correctly

#### Task 4.3: Add Item History Functionality
- Create method to retrieve all rows (active and inactive) for a JA ID
- Add "Item History" section to Item Details modal
- Display historical lengths and modification dates
- Show clear indication of which row is currently active

#### Task 4.4: Update E2E Tests for Multi-Row Scenarios
- Create test data with multiple rows per JA ID (active/inactive)
- Add tests verifying inventory list shows active data
- Add tests verifying item details and edit views show active data
- Add tests verifying shorten functionality works with multi-row items

### Milestone 5: Fix Shortening Workflow

#### Task 5.1: Remove Obsolete UI Fields
- Remove "cut loss" and "operator" fields from shortening form
- Remove "Operation Summary" and "Relationship Tracking" fields that imply new IDs
- Update form validation and processing logic
- Clean up related CSS and JavaScript

#### Task 5.2: Implement Keep-Same-ID Shortening Logic
- Update shortening service to deactivate current row and create new active row
- Ensure new row preserves all data except length and timestamps
- Add validation to prevent shortening to invalid lengths
- Update database constraints and business logic

#### Task 5.3: Update Shortening UI and Workflow
- Redesign shortening form to reflect keep-same-ID approach
- Show current item details and new length clearly
- Add confirmation step showing before/after comparison
- Update success messages and workflow completion

#### Task 5.4: Fix and Update Shortening E2E Tests
- Fix the 5 currently failing tests in `test_shorten_items.py`
- Update tests to verify keep-same-ID behavior
- Add tests for multi-row shortening scenarios
- Ensure all tests pass with new MariaDB backend

### Status Tracking

✅ **Milestone 1**: Database Foundation & Test Infrastructure - **COMPLETE**

- ✅ **Task 1.1**: Setup MariaDB Support & Schema Design - **COMPLETE** (including materials taxonomy table)
- ✅ **Task 1.2**: Implement Alembic Migration System - **COMPLETE** (migrations applied)
- ✅ **Task 1.3**: Setup MariaDB Test Infrastructure - **COMPLETE** (Docker, GitHub Actions, fixtures)
- ✅ **Task 1.4**: Create New Storage Backend - **COMPLETE** (MariaDB with Google Sheets compatibility)

✅ **Milestone 2**: Data Migration & Verification - **COMPLETE**

- ✅ **Task 2.1**: Analyze Existing Google Sheets Data - **COMPLETE** (505 inventory items, 74 materials, 21 multi-row items identified)
- ✅ **Task 2.2**: Build Data Migration Tool - **COMPLETE** (working migration with data validation and error handling)
- ✅ **Task 2.3**: Execute and Verify Data Migration - **COMPLETE** (505 items + 74 materials migrated successfully)
- ✅ **Task 2.4**: Update Application Configuration and Services - **COMPLETE** (MariaDB backend functional)

Remaining milestones:
- ⏸️ **Milestone 3**: Google Sheets Export Functionality
- ⏸️ **Milestone 4**: Fix Item Data Retrieval Logic
- ⏸️ **Milestone 5**: Fix Shortening Workflow

## Implementation Requirements

### Git Commit Standards
* Commit changes at the conclusion of each task
* Commit messages must be prefixed with `ClaudeCode - Material Length Enhancement (X.Y) - ` (where `X.Y` is the milestone/task number)
* Include one-sentence summary followed by additional details
* Every commit must update this `docs/material-length-enhancement.md` file to indicate completion progress

### Testing Standards
* No milestone is complete until ALL unit and E2E tests pass (except known failing tests in `test_shorten_items.py`)
* Each milestone must not introduce new test failures beyond the baseline
* As of beginning this work, we have 5 E2E tests failing in `test_shorten_items.py`

### Documentation Standards
* Each milestone must update relevant documentation before being considered complete
* Update README, development/testing guides, deployment guides, and user guides in `docs/` as applicable
* Maintain clear documentation of database schema changes and migration procedures

### Implementation Standards
* No backward compatibility needs to be maintained - optimize for simplicity
* All changes will be deployed as one unit after completion
* Focus on clean, maintainable code with proper error handling and logging

## Additional Changes to make after completing the main task

* on the material shortening form, get rid of the "cut loss" and "operator" fields in Shortening Details (and any corresponding code related to these fields); they're not needed.
