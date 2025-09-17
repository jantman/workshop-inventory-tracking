# Feature: Model Architecture Consolidation

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

Consolidate the duplicate `Item` and `InventoryItem` models into a single model architecture to eliminate maintenance burden and prevent type mismatch bugs.

**Problem Statement:**
Currently we have two models representing the same domain concept:
- `InventoryItem` (database.py): SQLAlchemy ORM model with simple types (String, Boolean, Numeric)
- `Item` (models.py): Business logic dataclass with rich types, enums, and validation

This creates maintenance overhead, requires complex conversion logic, and is prone to bugs like the search functionality issue where enum values are compared against database string columns.

**Goal:**
Create a single model architecture that provides both database persistence and business logic capabilities while maintaining the current design principle of enum-without-migration (adding enum values without database schema changes).

**Proposed Approach:**
Convert to a single `InventoryItem` SQLAlchemy model with:
- String columns in the database (no schema changes required)
- Enum properties that convert to/from database string values automatically
- Validation and business logic methods integrated into the model
- Elimination of the separate `Item` dataclass and all conversion logic

**Success Criteria:**
- Single source of truth for field definitions
- No complex conversion layer between models
- Maintains enum-without-migration capability
- All existing functionality preserved
- Significant reduction in code complexity

## Implementation Plan

### Milestone 1: Enhance InventoryItem with Enum Properties and Dual Support
**Prefix:** `MAC - 1.`

This milestone enhances the InventoryItem model while maintaining full backward compatibility with the existing Item dataclass. All tests must pass at the end of this milestone.

#### Task 1.1: Add Enum Property System to InventoryItem
- Add hybrid properties to `InventoryItem` that automatically convert between database strings and enum objects
- Implement `item_type_enum`, `shape_enum`, `thread_series_enum`, `thread_handedness_enum` properties
- Maintain backward compatibility with existing string-based database columns
- Add comprehensive validation methods similar to current `Item` validation

#### Task 1.2: Add Business Logic Methods to InventoryItem
- Move validation logic from `Item.__post_init__()` to `InventoryItem` methods
- Add `display_name`, `is_threaded`, `estimated_volume` properties
- Implement enhanced `to_dict()` and `from_dict()` methods with enum handling
- Add `to_row()` and `from_row()` methods for Google Sheets compatibility

#### Task 1.3: Add Dimensions and Thread Helper Properties
- Add computed properties to `InventoryItem` that return `Dimensions` and `Thread` objects
- Ensure Decimal precision is maintained for dimension calculations
- Add validation for thread size formats and compatibility
- Maintain compatibility with existing dimension access patterns

#### Task 1.4: Update Unit Tests for Enhanced InventoryItem
- Add comprehensive tests for new enum properties in `tests/unit/test_database.py`
- Test all new business logic methods and properties
- Verify backward compatibility with existing string-based access
- Ensure all validation logic works correctly

#### Task 1.5: Update Affected E2E Tests
- Update any e2e tests that directly instantiate or test `InventoryItem`
- Ensure enhanced model works with existing database operations
- Verify search and filter operations work with new enum properties
- **Run complete test suites to ensure 100% pass rate**

### Milestone 2: Transition Services to Use Enhanced InventoryItem
**Prefix:** `MAC - 2.`

This milestone updates the service layer to use the enhanced InventoryItem directly while maintaining the Item dataclass for backward compatibility. All tests must pass at the end of this milestone.

#### Task 2.1: Update MariaDBInventoryService to Use Enhanced Model
- Modify service methods to work directly with enhanced `InventoryItem`
- Simplify search and filtering logic using new enum properties
- Remove complex enum conversion logic from `_db_item_to_model()`
- Maintain backward compatibility by keeping conversion method functional

#### Task 2.2: Update Storage Layer for Direct InventoryItem Usage
- Modify `MariaDBStorage` to leverage enhanced `InventoryItem` methods
- Simplify row conversion logic using new `to_row()` and `from_row()` methods
- Ensure Google Sheets compatibility is maintained
- Update any storage-related validation to use new methods

#### Task 2.3: Update Unit Tests for Service Changes
- Update `tests/unit/test_mariadb_inventory_service.py` for simplified logic
- Add tests for direct enum property usage in services
- Update any tests that verify conversion logic
- Ensure test coverage for new simplified code paths

#### Task 2.4: Update Affected E2E Tests for Service Changes
- Update e2e tests that verify service behavior
- Test search functionality with enum properties
- Verify CRUD operations work correctly with enhanced model
- Test shortening, moving, and other item operations
- **Run complete test suites to ensure 100% pass rate**

### Milestone 3: Transition API Layer and Remove Item Dataclass
**Prefix:** `MAC - 3.`

This milestone updates the API/route layer and removes the Item dataclass entirely. All tests must pass at the end of this milestone.

#### Task 3.1: Update Route Handlers to Use InventoryItem
- Update Flask route handlers in `app/main/routes.py` to work with enhanced `InventoryItem`
- Ensure API responses maintain same format (backward compatibility)
- Remove any remaining model conversion calls
- Update form handling to work directly with ORM model

#### Task 3.2: Update Model Imports Across Codebase
- Replace all imports of `Item` from `models.py` with `InventoryItem` from `database.py`
- Update enum imports to use centralized definitions from `models.py`
- Update type hints throughout the codebase
- Ensure all files compile without import errors

#### Task 3.3: Remove Item Dataclass and Cleanup
- Remove the `Item` dataclass from `models.py`
- Remove conversion methods like `_db_item_to_model()`
- Remove unused import statements and conversion utilities
- Clean up any dead code related to dual model system

#### Task 3.4: Update All Unit Tests for Single Model
- Update `tests/unit/test_models.py` to test enhanced `InventoryItem` only
- Remove tests for removed `Item` dataclass
- Update all test imports and instantiation patterns
- Add any missing test coverage for new functionality

#### Task 3.5: Update All E2E Tests for Single Model
- Update all e2e tests to use enhanced `InventoryItem`
- Update test imports and object creation patterns
- Verify all functionality still works with single model
- Test backward compatibility with existing data
- **Run complete test suites to ensure 100% pass rate**

### Milestone 4: Final Validation and Documentation
**Prefix:** `MAC - 4.`

This milestone focuses on final validation, performance testing, and documentation updates. All tests must pass at the end of this milestone.

#### Task 4.1: Complete Test Suite and Performance Validation
- Run full unit test suite and ensure 100% pass rate
- Run complete e2e test suite with extended timeout (15+ minutes)
- Verify no regressions in existing functionality
- Test enum-without-migration capability with new enum values
- Validate search performance is maintained or improved
- Ensure memory usage hasn't increased significantly

#### Task 4.2: Code Quality and Architecture Validation
- Run lint and type checking to ensure code quality
- Validate that codebase complexity has actually decreased
- Review code for any remaining duplication or conversion logic
- Ensure proper error handling for enum conversion edge cases

#### Task 4.3: Documentation Updates
- Update `README.md` if model usage patterns have changed
- Update `docs/development-testing-guide.md` with new architecture details
- Update any API documentation to reflect single model approach
- Update troubleshooting guide if needed
- Update code comments and docstrings throughout the codebase

#### Task 4.4: Final Integration Test
- **Run complete test suites one final time to ensure 100% pass rate**
- Verify all functionality works end-to-end with real data
- Test edge cases and error conditions
- Confirm feature meets all success criteria

## Technical Implementation Details

### Enhanced InventoryItem Model Design
```python
class InventoryItem(Base):
    # Existing database columns remain unchanged
    item_type = Column(String(50), nullable=False)  # Store as string
    shape = Column(String(50), nullable=True)
    thread_series = Column(String(10), nullable=True) 
    thread_handedness = Column(String(10), nullable=True)
    
    # New enum properties
    @hybrid_property
    def item_type_enum(self) -> ItemType:
        return ItemType(self.item_type) if self.item_type else None
    
    @item_type_enum.setter
    def item_type_enum(self, value: ItemType):
        self.item_type = value.value if value else None
        
    # Similar properties for shape_enum, thread_series_enum, etc.
    
    # Business logic methods
    def validate(self) -> List[str]:
        """Validate item data and return list of errors"""
        
    @property
    def display_name(self) -> str:
        """Generate human-readable display name"""
        
    @property
    def dimensions(self) -> Dimensions:
        """Get dimensions as helper object"""
```

### Migration Strategy
1. **No database schema changes** - all existing columns remain as strings
2. **Gradual migration** - enum properties work alongside string columns
3. **Backward compatibility** - existing code continues to work during transition
4. **Incremental testing** - each milestone can be tested independently

### Risk Mitigation
- Comprehensive test coverage at each milestone
- Maintain backward compatibility throughout
- Staged rollout with validation at each step
- No database schema changes reduce risk
- Rollback capability by reverting code changes only
