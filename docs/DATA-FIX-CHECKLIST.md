# Data Migration Fix Checklist

## Overview

Before running the data migration, the following data issues need to be fixed in your Google Sheet. The migration script has identified **81 problematic rows** out of 505 total rows (16% failure rate).

## Current Migration Status
- ✅ **Total Rows**: 505
- ✅ **Valid Rows**: 424 (84%)
- ❌ **Rows Needing Fixes**: 81 (16%)

**Goal**: Fix all rows so 100% migrate successfully.

---

## Issue Categories & Fix Instructions

### 🔴 **CRITICAL: Invalid JA ID Format (15 rows)**

**Problem**: Rows have "N/A" in the Code128 (JA ID) column  
**Impact**: These rows cannot be imported as JA ID is the primary key  

**Affected Rows**: 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 357, 358, 359, 360, 361

**How to Fix**:
1. Go to each row listed above
2. Replace "N/A" in the **Code128** column with proper JA ID format
3. **Format**: `JA######` (e.g., JA000123, JA001234)
4. **Important**: Each JA ID must be unique across all rows

**Suggested Fix Process**:
```
Find the highest existing JA ID number (e.g., JA000500)
Assign sequential numbers starting from the next available:
- Row 341: JA000501
- Row 342: JA000502
- Row 343: JA000503
- etc.
```

---

### 🟡 **MAJOR: Missing Diameter for Round Items (66 rows)**

**Problem**: Items with Shape="Round" are missing the diameter value in Width column  
**Impact**: Round items require a diameter measurement to be valid  

**Affected Rows**: 381, 440-506 (approximately 66 rows)

**How to Fix**:
1. Go to each affected row
2. Check if **Shape** column = "Round" 
3. If **Width (in)** column is empty, you have 3 options:

**Option A - Add Diameter** (Recommended if you know it):
- Measure or estimate the diameter
- Enter the value in **Width (in)** column (e.g., "0.5", "1.25")

**Option B - Change Shape** (If not actually round):
- Change **Shape** from "Round" to appropriate shape:
  - "Rectangular" (for bars, plates)
  - "Square" (for square stock)
  - "Other" (for unusual shapes)

**Option C - Mark Inactive** (For items you don't want to migrate):
- Change **Active?** column to "No" 
- These will be migrated but marked as inactive

---

### 🟡 **MINOR: Invalid Dimension Values (1 row)**

**Problem**: Non-numeric values in dimension fields  
**Example**: "Thin" in thickness field instead of a number  

**How to Fix**:
1. Find rows with text values in dimension columns
2. Replace with proper numeric values:
   - "Thin" → estimate thickness (e.g., "0.125", "0.0625")
   - "Thick" → estimate thickness (e.g., "0.25", "0.5")
   - Leave empty if unknown

---

## Step-by-Step Fix Process

### Phase 1: Fix JA ID Issues (CRITICAL)
- [ ] **Row 341**: Change "N/A" to next available JA ID
- [ ] **Row 342**: Change "N/A" to next available JA ID  
- [ ] **Row 343**: Change "N/A" to next available JA ID
- [ ] **Row 344**: Change "N/A" to next available JA ID
- [ ] **Row 345**: Change "N/A" to next available JA ID
- [ ] **Row 346**: Change "N/A" to next available JA ID
- [ ] **Row 347**: Change "N/A" to next available JA ID
- [ ] **Row 348**: Change "N/A" to next available JA ID
- [ ] **Row 349**: Change "N/A" to next available JA ID
- [ ] **Row 350**: Change "N/A" to next available JA ID
- [ ] **Row 357**: Change "N/A" to next available JA ID
- [ ] **Row 358**: Change "N/A" to next available JA ID
- [ ] **Row 359**: Change "N/A" to next available JA ID
- [ ] **Row 360**: Change "N/A" to next available JA ID
- [ ] **Row 361**: Change "N/A" to next available JA ID

### Phase 2: Fix Round Item Diameters
- [ ] **Row 381**: Add diameter to Width column OR change Shape
- [ ] **Rows 440-506**: Review each round item and fix Width column

### Phase 3: Fix Text Dimensions  
- [ ] Search for "Thin", "Thick", or other text in dimension columns
- [ ] Replace with numeric values or leave empty

---

## Validation Process

After making fixes, you can test the migration:

1. **Test Migration** (Dry Run):
   ```bash
   cd /home/jantman/GIT/workshop-inventory-tracking
   source venv/bin/activate  
   python migrate_data.py
   ```

2. **Check Results**:
   - Look for "Valid rows: XXX" in the output
   - Goal: "Valid rows: 505" (100% success)
   - Any remaining errors will show specific row numbers

3. **Iterate**: Fix any remaining issues and test again

---

## Quick Reference

### JA ID Format Rules
- **Format**: JA + 6 digits (padded with zeros)
- **Examples**: JA000001, JA000123, JA012345
- **Must be unique**: No duplicate JA IDs allowed

### Dimension Field Rules
- **Numeric values only**: Use decimals (e.g., 0.125, 1.5, 12.75)
- **Fractions OK**: Migration will convert (e.g., "1/2" → 0.5)
- **Empty OK**: Leave blank if unknown
- **No text**: Remove "Thin", "Thick", "N/A", etc.

### Shape-Specific Requirements
- **Rectangular**: Needs Length, Width, Thickness
- **Round**: Needs Length, Width (diameter)  
- **Square**: Needs Length, Width
- **Other**: Flexible requirements

---

## Common Patterns to Look For

When reviewing your data, watch for these common issues:

### ❌ Invalid JA IDs
- "N/A", "TBD", "Unknown", empty cells
- Wrong format: "JA1", "JA12", "123456"

### ❌ Missing Dimensions for Round Items  
- Shape = "Round" but Width column is empty
- Shape = "Round" but Width contains text

### ❌ Text in Dimension Fields
- "Thin", "Thick", "Small", "Large"  
- "1/8 inch", "2mm" (use just the number)
- "~0.5", ">1" (use just the number)

### ❌ Inconsistent Materials
- Check for typos: "304 Stainless", "304L Stainless", "304/304L"
- The migration will normalize some aliases automatically

---

## After All Fixes Are Complete

1. **Final Test Migration**:
   ```bash
   python migrate_data.py
   ```

2. **Verify 100% Success**:
   - Should show "Valid rows: 505"  
   - Should show "Skipped rows: 0"

3. **Ready for Migration**:
   ```bash  
   python migrate_data.py --execute
   ```

---

## Need Help?

If you encounter issues:

1. **Check the migration log** for specific error messages
2. **Look up row numbers** in the Google Sheet to see the actual data
3. **Focus on JA ID issues first** - these are blocking
4. **Round item issues can be fixed by changing Shape** if you don't know diameter

Remember: The goal is to get all 505 rows to migrate successfully. Focus on the critical JA ID issues first, then work through the round items.