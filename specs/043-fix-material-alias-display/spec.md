# Feature Specification: Fix Material Alias Display and Conflict Detection

**Feature Branch**: `speckit/043-fix-material-alias-display`

**Created**: 2026-09-13

**Status**: Draft

**Input**: User description: "I have a L3 material named `Oil Embedded Bronze` with aliases set (confirmed in the DB) to `Oilite, Sintered Bronze, 841 Bronze`. However, at /admin/materials, it's rendering as `L3 Oil Embedded Bronze (aliases: O, i, l, i, t, e, ,, , S, i, n, t, e, r, e, d, , B, r, o, n, z, e, ,, , 8, 4, 1, , B, r, o, n, z, e)`"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read a material's aliases on the materials admin page (Priority: P1)

The user opens the materials admin page to review the taxonomy. For each material that has
aliases, the page shows those aliases as the names the user entered, separated by commas —
for example `Oil Embedded Bronze (aliases: Oilite, Sintered Bronze, 841 Bronze)`. Today every
character of the stored aliases appears as its own comma-separated entry, which makes the
aliases unreadable.

**Why this priority**: This is the reported defect. The admin page is the only place the user
can see which aliases a material has, and right now that information is illegible for every
material with aliases.

**Independent Test**: Seed a level-3 material with aliases `Oilite, Sintered Bronze, 841 Bronze`,
open the materials admin page, and confirm the material's entry reads
`(aliases: Oilite, Sintered Bronze, 841 Bronze)`.

**Acceptance Scenarios**:

1. **Given** a material with aliases `Oilite, Sintered Bronze, 841 Bronze`, **When** the user opens the materials admin page, **Then** that material's entry shows `aliases: Oilite, Sintered Bronze, 841 Bronze`.
2. **Given** a material with a single alias `TIM`, **When** the user opens the materials admin page, **Then** the entry shows `aliases: TIM`, not `aliases: T, I, M`.
3. **Given** a material with no aliases, **When** the user opens the materials admin page, **Then** the entry shows no aliases label at all.
4. **Given** inactive materials are shown on the page, **When** an inactive material has aliases, **Then** its aliases display the same way as an active material's.

---

### User Story 2 - Alias conflicts are judged on whole aliases (Priority: P2)

When the user adds a material, the app checks whether any of its aliases is already used as
another material's alias, so that a name never resolves to two materials. The same mishandling
behind User Story 1 also breaks this check. The live check on the Add Material form compares
the new alias against individual *characters* of existing aliases, so it almost never detects a
real duplicate. The check performed on save matches *substrings*, so it wrongly rejects an alias
that merely appears inside a longer existing alias. Both checks must compare whole aliases.

**Why this priority**: The user did not report this, but it has the same cause and it affects data
integrity. A duplicate alias that slips through makes material lookup ambiguous, and a false
rejection blocks a legitimate entry. It is secondary to the visible defect.

**Independent Test**: With `Oil Embedded Bronze` holding the aliases above, try to add a new
material whose alias is `Oilite` (it must be refused), then one whose alias is `Bronze` (it must
be accepted, because `Bronze` is not an existing alias in its own right).

**Acceptance Scenarios**:

1. **Given** an existing material with alias `Oilite`, **When** the user enters a new material with alias `Oilite` on the Add Material form, **Then** the form reports that the alias conflicts with the existing material, both while typing and on save.
2. **Given** an existing material with alias `Oilite`, **When** the user enters a new material with alias `oilite` (a case variant) or ` Oilite ` (surrounding spaces), **Then** it is treated as the same alias and refused.
3. **Given** an existing material with alias `Sintered Bronze`, **When** the user adds a new material with alias `Bronze`, **Then** the alias is accepted (no false conflict from a partial match).
4. **Given** an existing material with alias `841 Bronze`, **When** the user adds a new material with alias `841`, **Then** the alias is accepted.
5. **Given** an existing material *named* `Carbon Steel`, **When** the user adds a new material with alias `Carbon Steel`, **Then** it is refused as before (the check against material names is unchanged).

---

### Edge Cases

- A material whose stored aliases contain stray whitespace or empty entries (for example `Oilite,, Sintered Bronze ,`): the page shows only the non-empty trimmed names — `Oilite, Sintered Bronze`.
- An alias that itself contains punctuation other than a comma (for example `SAE 841`, `C-932`): it displays whole.
- Aliases stored with and without a space after each comma (`Oilite,Sintered Bronze` vs `Oilite, Sintered Bronze`) display identically.
- Categories (level 1) and families (level 2) carry no aliases on this page today; they continue to show none.
- The public taxonomy API already returns aliases as a proper list; its output must not change.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The materials admin page MUST display each material's aliases as the individual alias names, in stored order, separated by `, `.
- **FR-002**: The materials admin page MUST omit empty or whitespace-only alias entries and trim surrounding whitespace from each displayed alias.
- **FR-003**: The materials admin page MUST show no aliases label for a material that has no aliases.
- **FR-004**: The alias-conflict check run live while the user fills in the Add Material form MUST detect when a new alias equals an existing material's alias, comparing whole aliases case-insensitively after trimming whitespace.
- **FR-005**: The alias-conflict check run when the Add Material form is saved MUST apply the same whole-alias, case-insensitive, trimmed comparison, and MUST NOT report a conflict merely because the new alias occurs inside a longer existing alias.
- **FR-006**: The live and on-save checks MUST reach the same verdict for the same input.
- **FR-007**: The existing check that an alias must not equal an existing material's name MUST continue to work.
- **FR-008**: Stored alias data MUST NOT be altered by this change; the fix is in how aliases are read and compared, not a data migration.
- **FR-009**: The public taxonomy API's alias output MUST remain unchanged.
- **FR-010**: Automated tests MUST cover the multi-alias display from User Story 1 and the conflict and non-conflict cases from User Story 2, so that the character-by-character regression cannot return unnoticed.

### Key Entities

- **Material taxonomy entry**: A category (level 1), family (level 2) or material (level 3) in the materials hierarchy. Level-3 materials may carry zero or more **aliases** — alternative names (for example trade names such as `Oilite`) by which the material is also known and can be matched. Each alias is a whole name; aliases are compared and displayed as whole names, never as characters or fragments.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every material with aliases, the materials admin page shows exactly the stored alias names — the user's `Oil Embedded Bronze` reads `aliases: Oilite, Sintered Bronze, 841 Bronze` — with zero entries consisting of a single character split out of a longer alias.
- **SC-002**: Attempting to add an alias that duplicates an existing alias (in any letter case) is refused 100% of the time, both while typing and on save.
- **SC-003**: Adding an alias that is only a fragment of an existing alias (such as `Bronze` against `Sintered Bronze`) is accepted 100% of the time.
- **SC-004**: No stored alias data changes as a result of deploying the fix.

## Assumptions

- The aliases in the user's database are stored correctly; the defect lies entirely in how they are read for display and comparison. The user confirmed the stored value directly.
- The fix restores the display format the page was evidently designed for — `(aliases: A, B, C)` — with no redesign of the page layout.
- Adding a material is the only flow that assigns aliases today (there is no edit-material flow), so conflict detection is fixed only where it currently runs.
- The material-selector autocomplete does not read aliases, so the hierarchy endpoint that feeds it is out of scope, even though it passes aliases through unconverted.
- Existing aliases that already duplicate one another (possibly admitted by the broken live check) are not detected or repaired by this change; that would be a separate data cleanup if the user wants one.
- Screenshot regeneration is only required if the change touches page templates or scripts; the fix may not need to.
