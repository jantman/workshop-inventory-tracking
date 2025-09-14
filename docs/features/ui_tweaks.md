# Feature: UI Tweaks

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

We want to make some minor tweaks to the UI:

1. Please get rid of the placeholder values in the Purchase Information and Location fields on the add and edit item views; I find them confusing.
2. The `ja-id-lookup` input field in the header of our pages seems to automatically add a `JA` prefix when anything is entered in the field. We must stop doing this as it breaks barcode input. Remove this functionality and any code that is rendered unused after doing so.
