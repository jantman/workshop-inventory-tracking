# Feature: Inactive Item List

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

Inactive items are not showing up on the `/inventory` endpoint all items list, even if the "Status" dropdown is changed to "Inactive Only" or "All Items". First, add end-to-end tests to confirm this bug (should initially be failing). Then, fix the bug such that the new e2e regression tests pass and all existing tests also pass. Ensure that the "Active Only" status dropdown option remains the default and only shows active items in the list.
