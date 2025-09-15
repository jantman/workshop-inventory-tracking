# Feature: Move Item Error

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

I’ve just tried to move an item (and also a few items), but every time it fails with an error. The server logs show:

```
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: 2025-09-14 17:55:54,736 ERROR [anonymous@192.168.0.24] Error moving item JA000424: Exception during move: AttributeError: 'str' object has no attribute 'to_dict' at /home/jantman/GIT/workshop-inventory-tracking/app/main/routes.py:49 in _item_to_audit_dict(). Traceback: Traceback (most recent call last):
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:   File "/home/jantman/GIT/workshop-inventory-tracking/app/main/routes.py", line 838, in batch_move_items
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:     item_before=_item_to_audit_dict(item))
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:                 ~~~~~~~~~~~~~~~~~~~^^^^^^
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:   File "/home/jantman/GIT/workshop-inventory-tracking/app/main/routes.py", line 49, in _item_to_audit_dict
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:     'original_thread': item.original_thread.to_dict() if item.original_thread else None,
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: AttributeError: 'str' object has no attribute 'to_dict'
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: URL: http://192.168.0.24:5603/api/inventory/batch-move
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: Method: POST
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: /home/jantman/GIT/workshop-inventory-tracking/app/main/routes.py:870
```

Please help me debug and fix this problem. Just as important as fixing this problem, please help me understand why our existing e2e tests didn't catch this problem, and fix them so they would. Please investigate this problem and present me with a plan for fixing it and fixing the e2e tests before changing any code.

## Investigation Summary

**Root Cause:** The `_item_to_audit_dict` function in `app/main/routes.py:49` incorrectly treats `item.original_thread` as a Thread object that has a `.to_dict()` method, when it is actually defined as `Optional[str]` in the Item model (`app/models.py:378`).

**Audit of Related Fields:** The `original_material` field (`app/models.py:377`) is also `Optional[str]` but is correctly handled in `_item_to_audit_dict` on line 48 - it's treated as a string without any `.to_dict()` call. Only `original_thread` has this bug.

**Why E2E Tests Didn't Catch This:**
1. The existing E2E tests (`test_move_items.py` and `test_move_items_basic.py`) only create items with `original_thread=None` 
2. The tests use newly created items that don't have any `original_thread` value set
3. The error only occurs when `original_thread` is a non-None string value (which triggers the `.to_dict()` call)
4. The unit test for audit logging (`test_audit_logging.py:66`) also uses `'original_thread': None`

## Implementation Plan

### Milestone 1: Fix the Core Bug
**Prefix: `Move Item Error - 1.1`**

#### Task 1.1: Fix the _item_to_audit_dict function
- Update `app/main/routes.py:49` to handle `original_thread` as a string instead of calling `.to_dict()`
- Change from: `'original_thread': item.original_thread.to_dict() if item.original_thread else None`
- Change to: `'original_thread': item.original_thread`

#### Task 1.2: Add unit tests for the fix
- Update `tests/unit/test_audit_logging.py` to test with non-null `original_thread` values
- Ensure the `_item_to_audit_dict` function handles string `original_thread` values correctly

#### Task 1.3: Verify the fix with integration testing
- Run existing unit tests to ensure no regressions
- Test the move functionality manually to confirm the fix works

### Milestone 2: Fix E2E Test Coverage 
**Prefix: `Move Item Error - 2.1`**

#### Task 2.1: Add E2E test with items that have original_thread values
- Create a new E2E test that adds items with `original_thread` set to a string value
- Test moving these items to verify the bug would have been caught
- Ensure the test covers the specific code path that was failing

#### Task 2.2: Enhance existing E2E tests 
- Update at least one existing move test to use items with populated `original_thread` fields
- Verify the move functionality works end-to-end with these items

### Milestone 3: Documentation and Final Validation
**Prefix: `Move Item Error - 3.1`**

#### Task 3.1: Run full test suite
- Execute complete unit test suite (100% of tests MUST pass)
- Execute complete E2E test suite with 15-minute timeout (100% of tests MUST pass)
- Fix any failures discovered
- **CRITICAL REQUIREMENT:** Every test that existed when we began implementing this feature MUST be passing for this task to be complete. Tests cannot be disabled or deleted to achieve this requirement. Only explicit human approval can override this requirement for removing or disabling tests.

#### Task 3.2: Update documentation
- Update relevant documentation if needed
- Document the bug fix in commit messages

This plan addresses both the immediate bug fix and the test coverage gap that allowed this regression to occur.
