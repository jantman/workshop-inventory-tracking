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
    - Tube, Square: Length (in), Width (in), Thickness (in), Wall Thickness (in) [Width/Thickness are OD and equal for true square]
    - Tube, Round: Length (in), Width (in) [OD], Wall Thickness (in)
    - Angle, Rectangular: Length (in), Width (in) [leg A], Thickness (in) [leg B], Wall Thickness (in) [angle thickness]
    - Plate, Rectangular: Length (in), Width (in), Thickness (in)
    - Sheet, Rectangular: Length (in), Width (in), Thickness (in)
    - Threaded Rod, Round: Length (in), Thread
  - Normalization notes:
    - For Round/Hex bars, Thickness (in) is typically blank; use Width (in) as diameter/AF
- [x] Units: What inputs should be accepted (inches, fractional inches like 1-5/8, decimals, mm)? Should the app normalize and store in a canonical unit?
  - length, width, thickness, wall thickness are all decimal inches. The app should assume all units for these dimensions are inches; any fractions should be normalized to decimal. The only metric units used are for metric threads.
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
- [x] Materials taxonomy: Controlled list with ability to add on-the-fly. Want tiers like Unknown Steel, HRS, CRS, 4140, etc. Any aliases/synonyms in existing data should be to deduped, but we need to provide a way to also capture the aliases in use (i.e. maybe we have one category for `18-8 / 304`).
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
- [x] Types and shapes: Start with fixed lists. Maintain tables for Type/Shape/Material with active flags and alias relationships.
  - Canonical Types (v1): Bar, Tube, Angle, Plate, Sheet, Threaded Rod
  - Canonical Shapes (by Type):
    - Bar: Rectangular, Square, Round, Hex
    - Tube: Round, Square
    - Angle/Plate/Sheet/Threaded Rod: Rectangular or Round as per data; no additional shapes
  - Materials (canonical examples; aliases map to these):
    - Steels: Unknown Steel; A36; HRS; CRS; 1018; 12L14; 4140; 4140 Pre-Hard; 300M; B7; Cast Iron (Dura-Bar)
    - Stainless: 304; 304L; 316; 316L; 321; 410; 440; RA330; Unknown Stainless
    - Tool Steel: O1; A2; H11; L6
    - Nonferrous: Aluminum (6061-T6/T6511, 6063-T52); Brass (generic, 360, C693, C385, H58, H58-330, C23000 red brass, Naval Brass); Copper (generic, C10100); Bronze (Unknown); Lead (99.9%); Nickel (96%)
    - Structural/Tube: A500; A513; A53; EMT
    - Exotic: Inconel; Hastelloy; Vasco Max 350
  - Alias normalization (examples):
    - "Stainless?", "Stainless non-magnetic" → "Unknown Stainless"; "T-304L" → "304L"; "T-304 Stainless" → "304"; "T-316 Stainless" → "316"; "316L Sch. 40" → "316L"
    - "CRS mystery?" → "CRS" (with note retained); "Mystery", "Mystery Steel" → "Unknown Steel"; "Hasteloy" → "Hastelloy"
    - "Dura Bar Cast Iron" → "Cast Iron (Dura-Bar)"; "RA330 Stainless" → "RA330"

### IDs, barcodes, and labels
- [x] JA ID: These are assigned and printed manually outside of the app.
- [x] Barcode scanning is done via a keyboard wedge scanner.
- [x] Label printing is done manually outside of the app.

### Data import, storage, and integrity
- [x] Import: All of our initial data is in the existing Google sheet.
- [x] Storage choice: Use Google Sheets initially (wrapped by a storage adapter class). Other options remain possible later.
  - Storage abstraction plan:
    - Define a `Storage` interface (or abstract base class) with methods: `create_item`, `update_item`, `deactivate_and_copy`, `move_item`, `get_item`, `search_items(filters)`, `list_taxonomy`, `upsert_taxonomy_alias`, `validate_unique_ja_id`.
    - Implement `GoogleSheetsStorage` using the Sheets API; all app code calls only the interface.
    - Map between logical schema fields and sheet columns in one place; keep JA ID unique among active rows.
    - Handle retries/backoff for API errors; single-writer assumption simplifies concurrency.
    - Enable swapping to `SQLiteStorage` later without changing callers.
  - Google Sheets auth/config (decision): Use OAuth (installed app)
    - Use OAuth 2.0 Installed App flow. On first run, a browser consent will authorize and create a refresh token.
    - Credentials files: `credentials.json` (client ID/secret) and `token.json` (access/refresh). Store paths via env vars (e.g., `GOOGLE_SHEETS_CREDENTIALS`, `GOOGLE_SHEETS_TOKEN`) and restrict file perms.
    - Scope: `https://www.googleapis.com/auth/spreadsheets` with offline access so refresh happens silently.
    - Configuration: Spreadsheet ID: `1ZC2ifvEebC7tK2-Ns4TG98dc7E8zon9ru-CPUWrx0J4`; Tab: `Metal`; Header row index: 1. Keep these in a single config module.
- [x] Backups will be handled external to the app.
- [x] History/audit is not needed outside of normal logging by the application when data is changed.
- [x] Validation: Enforce JA ID pattern, required fields by shape/type, and allowed values for enums. Validation should err on the side of being lax and allowing bad data to be corrected later.

V1 recommendations (Data/import/storage/integrity)
- Storage: Google Sheets via a storage wrapper now; keep a clean interface for an easy future switch to SQLite.
- Backups: External to the app.
- Audit: Rely on app logs only.
- Validation: Strict on format, lenient on unknown materials with alias/original text preserved.

### Workflows
- [x] Logging new inventory: We don't need templates. We should be able to easily change/configure the fields that carry forward from one item to the next in a single list in code, but to start with we'll carry forward type, shape, material, purchase date, and purchase location.
- [x] Moving inventory: We should be able to scan one or more pairs of item/location codes and then move them all.
- [x] Shortening inventory: I'll enter the new length. No need to track kerf loss. We want to keep the old and new records linked, such as by using the current process of setting the old record's `Active?` column to `No` and then adding a new record with the new length.
- [x] Deactivation reasons: Let's make provision for selecting a deactivation reason from a list of possible options in code, but for now the only option will be shortening (used part of the stock).
- [x] Notes and attachments: We do not want photos/documents per item.

V1 recommendations (Workflows)
- Intake: Carry-forward type, shape, material, purchase date, and purchase location. No templates in v1.
- Move (batch pairs): User scans JA ID then location ID, repeating for multiple pairs; then scans a special submit code to finish. If errors are made, user clears/reset and starts over.
- Submit code literal for batch move: ">>DONE<<"
- Shorten: Enter the new length manually; auto-mark old inactive and link via parent_item_id.
- Deactivation: Enum reasons (start with Shortened).
- Attachments: None in v1.

### Search and reporting
- [x] Range queries: Only the basic numeric fields to support ranges (length, diameter/width, thickness, wall thickness). We will need to support compound filters, including filters on any/all of the fields; we will not need to support saved searches at this time.
- [x] Sorting and export: Need CSV export of results. Do not need any saved reports, but ideally reports could be bookmark-able by URL.
- [x] No need for derived fields.

V1 recommendations (Search and reporting)
- Filters: Numeric operators <, <=, =, >=, > for numeric fields; exact match or wildcard for text/enums.
- Export: CSV export of search results; basic sorting by columns; filter state reflected in URL for bookmarking (exact schema to be set during implementation).
- Derived fields: None in v1.

### Schema and structure to validate

- Logical entities: items and simple taxonomy lists (materials, types, shapes, aliases). Events/history optional and not required in v1.
- Item fields: JA ID, active, type, shape, material, location, sub-location, length, width, thickness, wall_thickness, thread fields (series/handedness/size/tpi-or-pitch/type/threadString), quantity, purchase_date, purchase_price, purchase_source, vendor_name, vendor_part_number, notes, parent_item_id, created_at, updated_at.

#### Proposed column header mapping (Metal tab)
- Core
  - ja_id -> "JA ID"
  - active -> "Active?" (Yes/No)
  - type -> "Type"
  - shape -> "Shape"
  - material -> "Material"
  - location -> "Location"
  - sub_location -> "Sub-Location"
- Dimensions (inches)
  - length -> "Length (in)"
  - width -> "Width (in)"  [for Round = diameter; for Hex = across flats]
  - thickness -> "Thickness (in)"
  - wall_thickness -> "Wall Thickness (in)"
- Thread (structured)
  - thread_series -> "Thread Series"  [I/M]
  - thread_handedness -> "Thread Handedness"  [RH/LH]
  - thread_size -> "Thread Size"
  - thread_tpi_or_pitch -> "Thread TPI/Pitch"
  - thread_type -> "Thread Type"
  - thread_string -> "Thread String"
- Other
  - quantity -> "Qty"
  - purchase_date -> "Purchase Date"
  - purchase_price -> "Purchase Price"
  - purchase_source -> "Purchase Source"
  - vendor_name -> "Vendor Name"
  - vendor_part_number -> "Vendor Part Number"
  - notes -> "Notes"
  - parent_item_id -> "Parent JA ID"
  - deactivation_reason -> "Deactivation Reason"
  - created_at -> "Created At"
  - updated_at -> "Updated At"
  - weight (optional) -> "Weight (lb)"

Notes
- No derived columns; all dimensions are decimal inches. For Round/Hex bars, use Width (in) as diameter/AF.
- Existing single "Thread" text in the legacy data can be retained as "Thread String"; structured fields fill as data is normalized.

#### Sheet header changes and data migration plan
- Header rename/add map (from likely legacy names):
  - "Length" → "Length (in)"; "Width" → "Width (in)"; "Thickness" → "Thickness (in)"; "Wall Thickness" → "Wall Thickness (in)"
  - "Quantity" → "Qty"
  - "Purchase Location" → "Purchase Source"
  - "Thread" → "Original Thread" (preserve original free-text)
  - Add new: "Thread Series", "Thread Handedness", "Thread Size", "Thread TPI/Pitch", "Thread Type", "Thread String", "Original Material", "Parent JA ID", "Deactivation Reason", "Created At", "Updated At", "Weight (lb)" (if not present)
- Migration steps:
  1) Backup: Make a full copy of the spreadsheet and export the Metal tab to CSV.
  2) Rename existing: `Metal` tab → `Metal_original`.
  3) Create new tab: `Metal` with the proposed headers in row 1; freeze row 1.
  4) Copy data: Read from `Metal_original`, write to `Metal` applying header renames above; insert any missing columns as empty.
  5) Normalize values:
     - Convert fractional dimensions (e.g., `1-5/8`) to decimal inches using customary precision (e.g., 1/4 → 0.25, not 0.2500); preserve user-entered precision exactly.
     - For Bar Round/Hex, interpret Width (in) as diameter/AF; for Tube Round, ensure Width (in) is OD.
     - Standardize `Active?` to `Yes`/`No`.
     - Copy original Material text to `Original Material`; map normalized Material via alias rules.
     - Copy original Thread text to `Original Thread`; parse into structured fields where confidently recognized.
  6) Validate: Enforce required fields by type/shape, JA ID pattern, and uniqueness among active rows; emit a report of anomalies.
  7) Test: The new `Metal` tab can be deleted and regenerated if migration needs adjustment.
- Automation plan:
  - Provide a dedicated migration script using the Sheets API with a dry-run mode; idempotent and safe to rerun.

### Final Decisions Made
- **OAuth Configuration**: Store `credentials.json` and `token.json` in the current working directory. Environment variables: `GOOGLE_SHEETS_CREDENTIALS_PATH` and `GOOGLE_SHEETS_TOKEN_PATH`.
- **Data Preservation**: Create separate `Original Material` and `Original Thread` columns to preserve raw inputs from existing data.
- **Thread Parsing**: Dedicated migration script will parse threads into structured fields during initial migration.
- **Decimal Precision**: Preserve user-entered precision exactly (e.g., distinguish between `1.2` and `1.2000` for machining practices).
- **Technology Stack**: Python/Flask backend with Jinja2 templates and Bootstrap CSS for UI (optimized for simplicity and maintainability).
- **Column Header Mapping**: Approved as specified above.
- **Migration Plan**: Approved with modifications (rename to `Metal_original`, use customary decimal precision, preserve original values).
