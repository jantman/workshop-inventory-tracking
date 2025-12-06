# Test Isolation Issue Investigation Plan

## Problem Summary
- Test `test_duplicate_multiple_items` **passes** when run alone or with just test_duplicate_item.py
- Test **fails** when run in full e2e suite with "TypeError: argument of type 'NoneType' is not iterable"
- Error occurs at URL: `http://127.0.0.1:38255/inventory/edit/JA000103`
- This is a test execution order dependency issue

## Investigation Steps

### 1. Identify the Root Cause
The error message suggests checking if something is `in None`.

Possible locations in `inventory_edit`:
- Line 405: `if material and material.lower() not in valid_materials_lower:`
  - If `valid_materials_lower` is None, this would fail
  - But `_get_valid_materials()` always returns a list (lines 110-125, routes.py)

### 2. Check Test Execution Order
- Determine which test runs immediately before `test_duplicate_multiple_items` in full suite
- Check if that test leaves behind state that affects this test

### 3. Verify Test Cleanup
Current cleanup (conftest.py:259-278):
```python
def clear_test_data(self):
    session.query(InventoryItem).delete()
    session.query(MaterialTaxonomy).delete()
    session.commit()
    self.setup_materials_taxonomy()
```

Potential issues:
- **Session state**: Browser session/cookies not being cleared between tests
- **Database connection pool**: Stale connections
- **Application state**: Flask app state carrying over
- **Timing issues**: Race conditions in cleanup

### 4. Hypothesis
The error might be happening in the template rendering, not in the route code itself.
The edit template might be trying to check something like `if field in item.some_property`
where `item.some_property` is None for items created by earlier tests.

## Action Plan

### Step 1: Add Defensive Code
Add None check to prevent the error:
```python
# In routes.py line 403-405
valid_materials_lower = [m.lower() for m in (valid_materials or [])]

if material and valid_materials_lower and material.lower() not in valid_materials_lower:
```

### Step 2: Search Template for `in` Operators
Check edit.html for any `{% if x in y %}` where y could be None

### Step 3: Add Browser Context Isolation
Ensure each test gets a fresh browser context:
```python
@pytest.fixture
def page(context):
    page = context.new_page()
    yield page
    page.close()
```

### Step 4: Add Explicit Session Cleanup
Clear browser storage between tests

### Step 5: Run Tests with --lf (Last Failed)
Use pytest's --lf flag to run just the failed test in the same context

## Next Actions
1. Search edit.html template for `in` operators
2. Add defensive None checks in route code
3. Test the fix with full suite
