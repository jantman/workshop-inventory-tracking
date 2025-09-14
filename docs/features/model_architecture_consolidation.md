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
