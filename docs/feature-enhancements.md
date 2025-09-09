# Feature Enhancements

## Hierarchical Materials

Right now we have a long and mostly unorgaized list of materials in use, covering everything from `Steel` and `Stainless` (and `Stainless??`) to `4140`, `12L14`, `O1 Tool Steel`, etc. I think that we need to come up with a hierarchical taxonomy for materials and map all existing data to that taxonomy. When adding new items, we'll want to enforce material choice from this taxonomy. We should also add a form that allows adding new materials/sub-materials to the taxonomy at any level. We should assume that the taxonomy can be nested numerous levels deep. I think it's reasonable to assume that the top-level items will be `Steel`, `Stainless`, `Aluminum`, `Brass`, `Copper`, etc. and then under each of those we would have specific alloys (e.g. 4140, 12L14, etc. for steel) or groupings of alloys (e.g. "Tool Steel" as a group under "Steel", and then sub-items of "O1", "W1", etc.).

## Storage Backend Upgrade

We're currently using Google Sheets as our storage backend, specifically a single sheet. Is it time to consider switching to a more robust storage backend, such as a SQLite3 database stored on disk? If we do this, we would still need a method of synchronizing our data to the Google Sheet in its current format, either on-demand (i.e. an endpoint that a cron job can `curl`, or a human can click a button to trigger) or possibly after saving any changes to the database.

## JA ID Assignment

I would like to automatically assign the next sequential JA ID to new items.

## Label Printing

I'd like to have an option to print a label for newly added items, as part of the item adding process. Label printing will be handled by an existing Python class in a separate package, and will simply need to be called with different sets of keyword arguments for different sizes/types of labels. I will provide the full details for this prior to implementation.
