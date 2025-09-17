# Feature: Photo Upload

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

Please implement functionality to upload photos of Items using the following guidance:

* Photos should be able to be uploaded during the Item Add or Item Edit processes. Uploaded photos should also be able to be deleted from these processes (i.e the user should be able to upload two photos and then delete one of them, as part of one add or edit operation).
* Photos should be stored in the database as blobs, using a new table to store them. Assume that photos can be up to approximately 20MB in size.
* Photos should be displayed in the UI as small thumbnails that can be clicked to show them larger/full size (also include a download option); the larger/full size view should be clickable to dismiss it. This photo display functionality should exist in the Add Item and Edit Item views, as well as the Item Details modal.
* Photo display should use a common library, not bespoke code.
* e2e tests should be added for all of the above user interactions, to verify proper functionality.
* Photos should not be required; they are optional and we can assume that in actual usage they will be uploaded for only a small portion of items.
