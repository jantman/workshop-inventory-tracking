# Feature: Bulk Label Printing

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

In our recent work for the `Remove Quantity Field and Add Bulk Item Creation` feature (github PR #21), we did some work in the frontend to enable bulk printing of item labels via a modal. We now want to extend this so that the item list (`/inventory` endpoint) adds a `Print Labels` option to the Options dropdown, allowing the user to select multiple items in the table (using their existing selection checkboxes) and print labels for all of them (obviously using the same label size for all selected items). Ensure that we have sufficient test coverage (both unit and e2e as appropriate) of existing code and behavior to verify that our changes don't break anything, and add complete test coverage of the new functionality.