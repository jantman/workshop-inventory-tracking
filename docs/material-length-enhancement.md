# Material Length Enhancement

There are some serious issues with the production shortening workflow code itself that we should fix before addressing the tests, and in the process of investigating them I also stumbled across a larger issue with data storage in general.

## Problem Statement

On the material shortening form, the `Operation Summary` field and `Relationship Tracking` fields imply that when an item is shortened it is assigned a new ID. This process is also referred to in `docs/user-manual.md`. However, this is not the process I wanted when initially implementing this application.

Prior to implementing this application, when I was manually editing data in the Google Sheet that we're using for data storage, my process for "shortening" an item was to duplicate the existing row, set the previous row as inactive (active no), and update the length on the duplicate. This has resulted in some items (`JA000211`) as an example which have multiple rows in the Google Sheet, one which is active and one or more which are inactive and represent the historical shortening of the stock.

After exploring some of these items in the UI of our application, it's clear to me that this data is not being handled correctly. Looking at item `JA000211` for example, the Google Sheet has three rows for it: row 226 which is inactive with a length of 53.5, row 227 which is inactive with a length of 48, and row 228 which is active with a length of 45.625. The Inventory List view properly displays this item with a length of 45.625" but the Item Details modal (item view) shows a length of 53.5" as does the Edit Item view. If I enter this JA ID in the Shorten Items view, I get an error that the item was not found or not suitable for shortening, which I believe is because the code behind this is identifying one of the inactive rows instead of the most recent, active row.

## Open Questions

1. Given these issues, is it time for us to move from using the Google Sheet as backend storage to using something like SQLite instead? Or do we just need to update our storage backend code to understand that JA IDs are not primary keys, we need to use row numbers as primary keys?
2. Our e2e tests all use SQLite but the production data uses Google Sheets. Are our tests missing this issue because of that (i.e. because the data shape that exists in Google Sheets isn't possible with the test SQLite setup)?

## Goals

We must collaboratively develop a plan to resolve these issues, broken down as a series of Milestones each made up of discrete Tasks. Our primary goal is that we MUST keep the same JA ID for a given piece of stock, even after it's shortened; but we also want to retain history of shortening operations. Secondarily, we'd also like to ensure that our implementation allows for future addition of changing other dimensions in a similar way (i.e. sheet stock can be reduced in length _or width_ and that process should have similar tracking).

## Implementation Plan and Status Tracking

To be filled in by Claude Code. Milestones and Tasks within them should be numbered.

## Implementation Details

* We must commit our changes to git at the conclusion of each task; commit messages should be prefixed with `ClaudeCode - Material Length Enhancement (X.Y) - ` (where `X.Y` is the milestone/task number) followed by a one-sentence summary of the changes, and then additional details.
* As of beginning our work, we have five E2E tests failing, all in the `test_shorten_items.py` test file. A Milestone must not be considered complete until ALL unit and e2e tests (other than these known problems) are passing. Each milestone MUST not be complete until there are no additional test failures compared to when the milestone was begun.

## Additional Changes to make after completing the main task

* on the material shortening form, get rid of the "cut loss" and "operator" fields in Shortening Details (and any corresponding code related to these fields); they're not needed.
