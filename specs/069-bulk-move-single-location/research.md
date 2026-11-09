# Research: Bulk Move to a Single Location by Scanning

## R1. How the owner enters "bulk" mode

- **Decision**: No mode. Scanning a second ID while the first is waiting for its location
  forms a group.
- **Rationale**: The scan already carries the intent — an ID where a location was expected.
  Today that is treated as a mistake and the first ID is dropped (026's fix for #107). Turning
  it into accumulation keeps 026's guarantee (an ID scan always advances the machine) and
  drops nothing. A forgotten location now shows as a visibly waiting subject.
- **Alternatives**:
  - A "bulk" toggle or a `>>GROUP<<` control barcode: extra UI and an extra printed code for
    what the scan sequence already expresses; a toggle left on silently changes the next
    session.
  - A count prompt ("how many?"): more input, not less.
  - Only the list-page *Bulk Move Selected*: already exists; doesn't fit standing at a shelf
    with a scanner, which is the issue's case.

## R2. Reuse of 026's handed-over group

- **Decision**: The scanned group is stored in `pendingMoves`, queued by the existing
  `handleBulkLocationInput()`, and its sub-location applied by the existing
  `applySubLocationToGroup()` via `bulkGroupIds`. A new state `group_location` distinguishes
  it from `bulk_location` only where behaviour differs: an ID scan is *added* to the group
  instead of refused.
- **Rationale**: Same data shape, same queueing, same sub-location rule. A parallel
  implementation would duplicate the hardest-won code in the file (the identity-keyed group,
  the readiness wait).
- **Alternatives**: Extending `bulk_location` with a flag — a state whose meaning depends on
  a second variable is harder to read and to wait on in tests than a distinct state name.

## R3. Group of one

- **Decision**: A single ID followed by a location takes today's path (`location` →
  `id_or_sub_location` with `currentId` set). The group state is entered only on the second ID.
- **Rationale**: FR-006 — the one-at-a-time flow, and every waiter transition for it, is
  unchanged. Converting the first ID into a group on the second scan is one assignment.
- **Alternatives**: Always use the group path — would move the queue-row creation from the
  sub-location/next-ID scan to the location scan for every move, changing an existing,
  well-tested flow for no user gain.

## R4. Readiness of current locations

- **Decision**: Each pending entry carries its own lookup promise (`ready`); the location
  transition awaits `Promise.all` over the entries present at that moment. Replaces the single
  `pendingMovesReady` promise, which assumed the group was fixed at load.
- **Rationale**: A scanned group grows one lookup at a time.

## R5. Showing the waiting group

- **Decision**: A small card `#scan-group` ("Awaiting a destination", count, one row per
  subject with current location / sub-location and a Remove button) in both the desktop macro
  and the handheld template, hidden when empty. Rows are appended synchronously on scan.
- **Rationale**: FR-002/FR-008. The handoff card is server-rendered and has no Remove; the
  scanned group needs both client rendering and removal. Synchronous append gives the e2e
  waiter a render-implies-state signal (CLAUDE.md pattern C).

## R6. Products' free-text locations

- **Decision**: `ProductMoveManager.isLocation()` returns true in `group_location` as it does
  in `location` and `bulk_location`.
- **Rationale**: Product locations follow no convention; while the page waits for a
  destination, anything that is not a product code or a JA ID is the destination.
