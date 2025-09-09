# Feature Enhancements

## Implementation Plan

**Recommended Phase Order:**
1. **JA ID Assignment** - Foundation feature (easiest implementation)
2. **Hierarchical Materials** - Core data organization (moderate complexity) 
3. **Label Printing** - Dependent on clean data structure (integration complexity)

**Storage Backend Decision:** Defer SQLite upgrade. Current Google Sheets integration is well-architected and stable.

---

## Phase 1: JA ID Assignment

**Goal:** Automatically assign the next sequential JA ID to new items.

**Implementation Notes:**
- Current model only validates JA ID format (`app/models.py:402`) - no auto-generation exists
- Need to implement auto-generation logic in `app/inventory_service.py`
- Auto-discover current highest JA ID by querying Google Sheet data
- Update add item workflow in `app/main/routes.py` to call auto-generation
- Consider thread-safe ID generation for concurrent requests

---

## Phase 2: Hierarchical Materials

**Goal:** Create hierarchical taxonomy for materials and migrate existing flat structure.

**Current State:** 
- Long unorganized list including `Steel`, `Stainless` (and `Stainless??`), `4140`, `12L14`, `O1 Tool Steel`, etc.
- Foundation exists in `app/taxonomy.py`

**Proposed Structure:**
- Top-level: `Steel`, `Stainless`, `Aluminum`, `Brass`, `Copper`
- Sub-materials: Specific alloys (4140, 12L14) or groupings (Tool Steel → O1, W1)
- Support unlimited nesting depth

**Requirements:**
- Hierarchical material selection UI with search/filter
- Admin form for adding new materials at any level
- Migration tool for existing ~200 materials
- Maintain backward compatibility during transition

**Storage Solution:** New "Materials" Google Sheet tab with columns: `Name`, `Parent`, `Level`, `Category`

**Migration Strategy:**
1. Extract all unique material values from current inventory data
2. Clean ambiguous materials (strip question marks, etc.)
3. Generate proposed hierarchical taxonomy mapping
4. Present for user review and adjustment
5. Create manual verification list for remaining ambiguous materials
6. Populate Materials sheet with approved taxonomy

**Current State Analysis:**
- `app/taxonomy.py` is actively used for material normalization and type/shape validation
- All taxonomy data is currently in-memory/hardcoded - no persistent storage
- Current system only normalizes material names, no hierarchy enforcement

---

## Phase 3: Label Printing

**Goal:** Optional label printing for newly added items during the add item process.

**Integration:**
- External Python class in separate package  
- Different keyword arguments for different label sizes/types
- Integrate into add item workflow

**Implementation Notes:**
- Specifications will be provided prior to implementation
- Integration point with external Python class in separate package
- Support different label sizes/types with varying parameters

---

## Storage Backend Upgrade (Deferred)

**Analysis:** Current Google Sheets backend is production-ready with:
- Clean storage abstraction (`app/storage.py`, `app/google_sheets_storage.py`)
- Comprehensive error handling, retry logic, and circuit breakers  
- Authentication management

**Decision:** Defer SQLite upgrade. The existing architecture supports future migration without blocking current enhancements.

**Future Considerations:** If migrated, would need Google Sheets sync mechanism (on-demand endpoint or post-save hooks).
