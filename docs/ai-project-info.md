# Workshop Material Inventory Tracking

For the past few years, I have been tracking the materials inventory for my home workshop (mostly metal stock and threaded rod) via a Google Sheets spreadsheet. A copy of this spreadsheet in ODS format is available in [MaterialStock.ods](./MaterialStock.ods); it currently has two sheets, one for metal stock (also available at [MaterialStock-Metal.csv](./MaterialStock-Metal.csv)) and one for drive belts (also available at [MaterialStock-Belts.csv](./MaterialStock-Belts.csv)). All of my inventory/stock items have unique ID barcode labels on them, using Code128 barcode symbology and a custom numbering scheme beginning with the letters `JA` followed by six numeric digits (`JA` ID). I also track the location where materials are stored, using either a system made up of a letter followed by a number and an optional suffix made up of a letter or string of letters (`M1`, `T1`, `M1-A`, `T1-H`, `M1-left`, `T1-right`) also encoded in Code128, or a rarely used free-form string (such as `Bedroom closet`).

The spreadsheet for metal stock currently tracks whether each row is active or not (when I cut a portion off of a piece of stock copy the row, mark the old row as Active No, and update the new dimensions on the copy), the length, width, thickness, wall thickness (if applicable, for tubes), weight (optionally tracked only for some items), type (i.e. "Bar", "Angle", "Tube", "Plate", "Threaded Rod", etc.), shape (round, rectangular, square, hex, etc.), material (Steel, HRS, CRS, Stainless, O1 Tool Steel, B7 Steel, 321 Stainless, Brass, Copper, 15-5 Stainless, A-2, 4140 Steel, etc.), thread (if threaded; this could be an inch or metric standard thread, Acme, Trapezoidal, etc.), quantity, location (as described previously), sub-location (free-form string, usually encoded in a Code128 label), purchase date, purchase price, and purchase location, notes (free-form string), vendor name, and vendor part number. The only _required_ fields are the Code128 unique ID (`JA` ID), length, width or thread, type, shape, material, and location; all other fields are optional.

Our goal is to write a small, simple web application that can help optimize the tasks that I've been using the existing spreadsheet for. I have a few distinct use cases for this application:

1. **Logging-in new inventory**: I purchase most of my metal stock in mixed lots from machine shop closing auctions and similar venues; using the current spreadsheet to log in new inventory is inefficient, especially when logging in many pieces of the same type, shape, material, thread, purchase price and location, etc. when in reality all that I should have to input for each item is the `JA` ID, length, and storage location. Ideally, I could log in multiple items where subsequent items would re-use the same data as the previous item except for ID and length.
2. **Moving existing inventory**: There is no quick way for me to move an item (by ID) from one storage location to another. Ideally this could be accomplished with a special form/modal/interface and quickly scanning the two relevant barcodes (item ID and new storage location).
3. **Shortening existing inventory**: This involves invalidating an existing inventory item (by unique `JA` ID) and creating a copy of it with an updated length. This should be optimized.
4. **Searching inventory**: The current Google Sheets approach provides no easy way to filter based on ranges, such as finding round steel bar with a diameter (width) of between 0.5" and 0.625" and a length of at least 36", or finding all threaded steel rod with a thread size of over 3/4".

## Taxonomy

Obviously this application will have to understand some level of taxonomy, even if it just uses the current taxonomy in the Google Sheet and provides a means for adding to it. Ideally, it would validate some amount of the input, at least for Type / Shape / Material. Note that material I purchase is often unidentified when purchased in a lot, so my classification of "Material" needs to accomodate varying levels of specificity; i.e. I may know that one piece is 4140 Steel alloy, another piece is just generic "hot rolled steel" (HRS), and another piece can only be identified as "Steel" (of completely unknown alloy).

## Technical Constraints

* I will be the only person using this application. Assume that it will be served by a single-threaded server and therefore concurrency and locking are not concerns. There will only ever be one user writing to it at a time.
* I do not know what the backend data storage layer will be; using the existing Google Sheet is possible, as is using a lightweight local data storage layer such as SQLite or even a flat file. Let's discuss these options and decide on one.
* Bias for Python/Flask, but we can discuss other options. The main goal is simplicity and ease of maintenance going forward.

## Open questions and decisions

Please answer/decide the following to guide design and implementation.

### Core data and taxonomy
- [x] Scope: v1 should cover only metal stock (not belts) but should be written so that it will be easy to add additional material types/taxonomies in the future
- [x] Required fields by shape/type:
  - Observed Type values (from current CSV): Bar, Tube, Angle, Plate, Sheet, Threaded Rod
  - Observed Shape values (from current CSV): Rectangular, Square, Round, Hex (only required for Bar and Tube types)
  - Minimal required CSV columns by Type/Shape (based on current data):
    - Bar, Rectangular: Length (in), Width (in), Thickness (in)
    - Bar, Square: Length (in), Width (in) [Thickness equals Width if provided]
    - Bar, Round: Length (in), Width (in) [diameter]
    - Bar, Hex: Length (in), Width (in) [across flats]
    - Tube, Rectangular: Length (in), Width (in), Thickness (in), Wall Thickness (in) [Width/Thickness are OD]
    - Tube, Square: Length (in), Width (in) [equals Thickness], Wall Thickness (in) [Width/Thickness are OD]
    - Tube, Round: Length (in), Width (in) [OD], Wall Thickness (in)
    - Angle, Rectangular: Length (in), Width (in) [leg A], Thickness (in) [leg B], Wall Thickness (in)
    - Plate, Rectangular: Length (in), Width (in), Thickness (in)
    - Sheet, Rectangular: Length (in), Width (in), Thickness (in)
    - Threaded Rod, Round: Length (in), Thread
  - Normalization notes:
    - For Round/Hex bars, Thickness (in) is typically blank; use Width (in) as diameter/AF
- [x] Units: What inputs should be accepted (inches, fractional inches like 1-5/8, decimals, mm)? Should the app normalize and store in a canonical unit?
  - length, width, thickness, wall thickness are all decimal inches. The app should assume all units for these dimensions are inches; any fractions should be normalized to decimal.
- [x] Thread representation: How should thread be stored (e.g., 3/4-10 UNC, M12x1.75)? Include handedness and class? For searches like "> 3/4", should comparison use nominal major diameter?
  - Threads should be stored as six fields:
    - `Series` - `I` (imperial; default) or `M` (metric)
    - `Handedness` - `LH` or `RH` (latter is default unless specified otherwise)
    - `Size` - nominal diameter of thread, i.e. `1/2` or `1 1/4` imperial or `4` or `18` metric
    - `TPI / Pitch` - TPI for imperial or Pitch for metric. Provisions must be made for non-standard pitches.
    - `Type` - normally empty/blank for normal `Unified` (UN) or `Metric` (ISO) depending on `Series`, but could be `Acme`, `Trapezoidal`, `Buttress`, `Square`, `Whitworth`, `BA`, `NPT`, `BSPT`, etc.
    - `ThreadString` - when none of the above values can be determined accurately, a free-text value describing the best-known aspects of the thread. Only to be used when none of the above values can be accurately determined.
  - Observed thread values (from current CSV, de-duplicated); 
    - Inch UNC/UNF: #10-24, 1/4-20, 1/4-28, 5/16-18, 5/16-24, 3/8-16, 7/16-14, 1/2-13, 1/2-20, 5/8-11, 3/4-10, 7/8-9, 7/8-14, 1-7, 1-8, 1-14, 1 1/2-6, 1 1/2-12, 1 1/4-7, 1 1/8-7 (incl. LH)
    - Metric: M10-1.5, M12-1.75
    - Acme: 5/8-5 Acme, 5/8-8 Acme, 3/4-6 Acme, 1-5 Acme, 1-8 Acme, 1 1/4-5 LH Acme
    - Trapezoidal: 16x3 Trapezoidal
  - Normalization ideas:
    - Treat ambiguous entries as free-text `ThreadString` only until corrected.
- [ ] Materials taxonomy: Controlled list with ability to add on-the-fly? Do you want tiers like Unknown Steel, HRS, CRS, 4140, etc.? Any aliases/synonyms to dedupe (e.g., 304 vs 18-8)?
  - Observed Material values (from current CSV, grouped):
    - Stainless: 304 / 304L, 304 Stainless, T-304L, T-304 Stainless, 316L Sch. 40, T-316 Stainless, T-316 Annealed, 321 Stainless, 410 Stainless, 440 Stainless, RA330 Stainless, Stainless, Stainless?, Stainless non-magnetic
    - Carbon/Alloy Steel: HRS, A36, A36 HRS, HR A36, CRS, CRS mystery?, 1018, 12L14, 4140, 4140 Pre-Hard, ETD 4140?, 300M Alloy Steel, RDS Steel, Steel, Mystery, Mystery Steel
    - Tool Steel: O1 Tool Steel (Drill Rod), A-2, H11 Tool Steel, L6 Tool Steel, Vasco Max 350, B7 Steel
    - Tube/Structural grades: A500, A513, A53, EMT
    - Nonferrous: Aluminum, 6061-T6/T6511, 6063-T52; Brass (unspec), 360-H02, C693, C385-H02, H58, H58-330, C23000 red brass, Naval Brass; Copper, C10100 Copper; Bronze??; Lead (99.9%); 96% Nickel; Dura Bar Cast Iron
    - High-temp/special: Inconel, Hasteloy/Hastelloy (spelling varies)
  - Normalization ideas:
    - Use canonical names (e.g., 304 Stainless; 304L Stainless) and map aliases/suspect entries (e.g., "Stainless?", "CRS mystery?", "Hasteloy" → "Hastelloy").
    - Allow Unknown categories (e.g., Unknown Stainless, Unknown Steel) and preserve original text in a notes/original_material field.
- [ ] Types and shapes: Start with fixed lists? Maintain tables for Type/Shape/Material with active flags and alias relationships?
- [ ] Locations: Free-form strings or records with codes/barcodes? Should locations be hierarchical (e.g., M1 → M1-left)? Should the app print new location labels?

V1 recommendations (Core data and taxonomy)
- Scope: Metal stock only for v1; belts later.
- Shape fields: Use shape-specific fields (round uses diameter; tube uses OD + wall; plate uses length + width + thickness).
- Units: Accept inches (fractional and decimal) and mm; parse all; normalize and store canonically in millimeters using Decimal; display in preferred unit.
- Thread: Store free-text thread_spec plus numeric major_diameter_mm for search; default right-hand; class optional.
- Taxonomies: Seed fixed lists for Type/Shape/Material; allow add-on-the-fly via admin; support aliases.
- Locations: Structured records with code and optional parent (hierarchical like M1 → M1-left). No label printing in v1.

### IDs, barcodes, and labels
- [ ] JA ID: Will the app generate new IDs or will you use pre-printed labels? If generating, confirm pattern, handling of gaps, and any check digit.
- [ ] Barcode scanning: Plan to use a USB keyboard-wedge scanner? Should camera-based scanning be supported?
- [ ] Label printing: Should the app generate/print Code128 labels for items and locations? Specify printer/model or preferred label software/workflow.

V1 recommendations (IDs, barcodes, labels)
- IDs: Use pre-printed JA IDs; no in-app generation in v1.
- Scanning: USB keyboard-wedge scanner only; no camera scanning in v1.
- Printing: No label printing in v1; consider later export to label software if needed.

### Workflows
- [ ] Logging new inventory: Which fields should carry forward from the previous item? Do you want templates/presets (e.g., "3/4 CRS round bar")?
- [ ] Moving inventory: Always one item → one new location, or support batch moves by scanning multiple IDs first?
- [ ] Shortening inventory: Should the app compute new length (old − cut − kerf), or will you enter the new length? Track kerf loss? Link new record to old (parent/child) and auto-mark old inactive?
- [ ] Deactivation reasons: Besides shortening, capture reasons like lost/scrapped?
- [ ] Notes and attachments: Do you want photos/documents per item?

V1 recommendations (Workflows)
- Intake: Carry-forward type, shape, material, thread, purchase fields, and location; optional "save as template" lightweight presets.
- Move: Support single-item move and simple batch mode (scan many IDs, then scan destination).
- Shorten: Enter the new length manually; optional kerf field; auto-mark old inactive and link via parent_item_id.
- Deactivation: Enum reasons (Shortened, Scrapped, Lost, Correction).
- Attachments: Notes only in v1; photos later.

### Search and reporting
- [ ] Range queries: Confirm numeric fields to support ranges (length, diameter/width, thickness, thread size). Support compound filters and saved searches?
- [ ] Sorting and export: Need CSV export of results? Any standard reports (by location, by material, by type)?
- [ ] Derived fields: Compute theoretical weight from material and dimensions? For which materials only, and with what density source?

V1 recommendations (Search and reporting)
- Filters: Range filters for length, diameter/width, thickness, and thread major diameter; support compound filters.
- Export: CSV export of search results; basic sorting by columns.
- Weight: Compute theoretical weight when density known for round bar, plate, and tube; optional toggle.

### Data import, storage, and integrity
- [ ] Import: Perform a one-time import from existing CSV/ODS? How to handle conflicts/duplicates?
- [ ] Storage choice: Pick one:
  - [ ] SQLite (local file, simple, good with Flask)
  - [ ] Google Sheets (no local DB; API limits/latency/complexity)
  - [ ] Flat files (JSON/CSV; simple, but weaker for range queries/integrity)
- [ ] Backups: Automatic periodic exports to CSV? Where to store backups?
- [ ] History/audit: Do you want full audit trail (who/when/what changed) or just item events (create/move/shorten/update)?
- [ ] Validation: Enforce JA ID pattern, required fields by shape/type, and allowed values for enums. How strict should validation be?

V1 recommendations (Data/import/storage/integrity)
- Import: One-time import from CSV; dedupe on JA ID; preserve inactive rows.
- Storage: SQLite with SQLAlchemy; NullPool in tests.
- Backups: Daily CSV export to `backups/` with timestamped filenames.
- Audit: Minimal events table logging create/move/shorten/update.
- Validation: Strict JA ID regex, shape-specific required fields, FK to taxonomy tables.

### Security and deployment
- [ ] Access: Single user on LAN only? Require basic auth? Any plan to expose beyond localhost?
- [ ] Hosting: Local Flask + SQLite OK? Prefer Docker or simple virtualenv/poetry?
- [ ] Offline: Must it work offline in the browser? Or is local-only server sufficient?

V1 recommendations (Security/deployment)
- Access: Localhost or LAN only; optional HTTP Basic Auth.
- Hosting: Flask + SQLite managed via Poetry; no Docker in v1.
- Offline: Not required.

### UX details
- [ ] Scanner-first flows: Auto-focus on input, submit on Enter, audible/visual feedback, and "undo last" operation?
- [ ] Bulk actions: "Scan many" mode for moves and intake?
- [ ] Keyboard-only operation: Is full keyboard operation required/preferred?

V1 recommendations (UX)
- Scanner-first: Autofocus, Enter-to-submit, toast + beep, and Undo Last.
- Bulk: Provide scan-many modes for moves and intake.
- Keyboard: Keyboard-first navigation throughout.

### Schema and structure to validate
- [ ] Separate tables for items, locations, materials, types, shapes, and optional events/history? Any additional entities needed?
- [ ] Item fields to include: active flag, sub-location, quantity, purchase info (date/price/source), vendor info (name/part number), notes, parent_item_id (for shortening), timestamps (created_at/updated_at).

V1 recommendations (Schema)
- Tables: items, locations, materials, types, shapes, aliases (for taxonomy), events.
- Fields: Include those listed above; add `thread_spec` (text) and `thread_major_diameter_mm` (numeric).

### Decisions to make now
1) Storage backend selection (SQLite vs Google Sheets vs flat files)
2) Units handling and normalization rules
3) Shape-specific required fields and how to treat width/diameter
4) Whether the app should generate/print labels and/or JA IDs
5) Audit/history depth and backup/export approach
6) v1 workflow scope (intake, move, shorten, search) and any extras (templates, saved searches)

V1 proposal (quick answers)
1) SQLite
2) Accept inches (fractional/decimal) and mm; store canonical in millimeters (Decimal)
3) Shape-specific fields; use diameter for round, no generic width for round
4) No ID generation or label printing in v1; use pre-printed labels
5) Minimal events log + daily CSV backups
6) Scope: intake, move, shorten, search; extras: carry-forward, simple batch move, CSV export; templates optional
