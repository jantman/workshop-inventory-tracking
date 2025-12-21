# Feature: Activate Item Bug

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

I am trying to re-activate an item but cannot. If I type the item ID in the search box at the top right of the pages, I just get an "Item not found" error; the same thing happens if I try to manually go to the `/item/edit/JAxxxxxx` URL. If I do a search for inactive items or filter the item list view to inactive items, and then use the "Activate Item" option from the dropdown, nothing seems to happen and in my browser console I see `search:1 Uncaught ReferenceError: toggleItemStatus is not defined`. Furthermore, and only slightly related, if I use the `/inventory/search?active=false` endpoint it returns 58 results for inactive items, but the `/inventory` list with filtering to `Inactive Only` only returns 25 results and shows no indication of any additional results. Please FIRST create e2e tests to reproduce each of these four bugs (these tests should initially be failing, confirming that the tests identify the bugs), commit that work, and then fix the bugs so that the tests pass.
