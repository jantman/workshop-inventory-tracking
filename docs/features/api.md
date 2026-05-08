# Feature: API and Client Class

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Requirements

Our goal is to:

1. Add a ReST API endpoint for creating items, similar to the existing `POST /inventory/add` form handler endpoint (or update that endpoint to alternatively handle JSON POST). The endpoint should return the IDs of any items that were created, along with any errors. Do not duplicate code paths between the existing form handler and the new JSON handler; refactor as needed to ensure no duplication.
2. Add a standalone Python script at `app/api_client.py` whose only external dependency is the `requests` library, and which provides a Class that can be used to create items via the API and also to upload photos via the API (existing API for this, `POST /api/items/<ja_id>/photos`).
3. Add/update tests accordingly to verify full test coverage at least via unit tests and ideally also via e2e tests.
