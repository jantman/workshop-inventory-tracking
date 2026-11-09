# Feature Specification: MCP Server

**Feature Branch**: `robot-army/issue-222-mcp-server`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "This application should also serve a MCP endpoint ( https://modelcontextprotocol.io/ ) that can be used by AI tools (e.g. Claude Code and Claude Desktop) to interact with inventory and products. It should support the basic functionality such as view/get details, search, filter, add new items, edit items, shorten, move, categorize, count, print labels, etc. (GitHub issue #222)"

## Background

The application has two halves, and an AI assistant needs to reach both:

- **Inventory items** — specific pieces of stock (bar, tube, sheet…) identified by a JA ID,
  with dimensions, material, location and a shortening history.
- **Products** — the catalog of *kinds* of things bought (fasteners, electronics…),
  identified by an internal code, with a category, a three-state on-hand quantity
  ("not tracked", 0, or a number with the age of the count), and low/out flags.

Today every operation is reachable only through the web pages, plus a small JSON API for
creating items, uploading photos and reading suggestions. The owner wants to ask an AI
assistant things like "do I have any 1in round 6061 longer than 12in, and where is it?",
"add three pieces of 1/2in 4140 rod, 36in, in rack R2", "I just cut 8in off JA000123",
"move JA000200 and JA000201 to bin B4", "set these five products' category to
fasteners/screws", "I counted 40 of P0012 on the shelf", or "print a 1x2 label for that
item" — and have the assistant do it directly, with the application's own rules applied.

The Model Context Protocol (MCP) is the standard these assistants use to discover and call
tools on an external system. This feature makes the application itself offer an MCP
endpoint.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect an assistant and look things up (Priority: P1)

The owner adds the application's MCP endpoint to their AI assistant (Claude Code on the
workstation, or Claude Desktop). The assistant lists the available tools and the owner
asks questions about inventory and products: find stock matching a description, get the
full details and history of one JA ID, find products by text or category, see what needs
reordering. Answers come from the live database.

**Why this priority**: Read access is the foundation every other story builds on, carries
no risk to the data, and is useful on its own.

**Independent Test**: Register the endpoint in an MCP client against a seeded instance,
list tools, and call the item search, item details, product search and product details
tools; the results match what the web pages show for the same data.

**Acceptance Scenarios**:

1. **Given** the application is running, **When** an MCP client connects to the endpoint,
   **Then** the handshake succeeds and the client receives a list of tools, each with a
   description and an input schema it can call without reading this application's code.
2. **Given** inventory containing active and inactive (shortened-away) rows, **When** the
   assistant searches items by material, type, shape, dimension ranges, location or text,
   **Then** only current (active) items are returned, each with its JA ID, description of
   material and dimensions, and location.
3. **Given** a JA ID with shortening history, **When** the assistant asks for that item's
   details, **Then** it receives the current row's full fields plus its history in order.
4. **Given** a JA ID that does not exist, **When** the assistant asks for it, **Then** the
   tool reports a clear "not found" error rather than an empty success.
5. **Given** products in the catalog, **When** the assistant searches by text, category,
   or identifier (internal code, vendor or manufacturer part number), **Then** matching
   products are returned with code, description, category, and on-hand state including
   the age of the count.
6. **Given** products flagged low/out or at their reorder threshold, **When** the assistant
   asks for the reorder list, **Then** it receives the same set the Reorder List page shows.
7. **Given** a search that matches more results than the result limit, **When** the
   assistant searches, **Then** it receives the first page of results and is told that more
   exist and how to get them.

---

### User Story 2 - Change inventory items through the assistant (Priority: P2)

The owner asks the assistant to add new items, edit an item's fields, shorten an item after
a cut, or move one or several items to a location (and optional sub-location). The
assistant calls the tools and reports the result: the JA IDs allocated, the new length, the
new location.

**Why this priority**: This is the "do it for me" value the issue asks for, on the half of
the app with the strictest data rules.

**Independent Test**: Against a seeded instance, call add, edit, shorten and move tools and
confirm through the web UI (or details tool) that the data changed exactly as it would have
through the corresponding web page, including history rows for a shortening.

**Acceptance Scenarios**:

1. **Given** valid item fields, **When** the assistant adds an item with a quantity of N,
   **Then** N items are created with server-allocated JA IDs and those IDs are returned.
2. **Given** invalid item fields (unknown material, missing required dimension for the
   shape, malformed value), **When** the assistant adds or edits, **Then** nothing is
   written and the tool returns the same validation messages the web form would show.
3. **Given** an active item, **When** the assistant shortens it to a new length, **Then**
   the prior row is retained as inactive history, exactly one active row exists for the JA
   ID with the new length, and the result reports old and new length.
4. **Given** a shortening to a length not shorter than the current length, **When** the
   assistant calls shorten, **Then** it is refused with the same rule the web page applies.
5. **Given** one or more JA IDs and a location, **When** the assistant moves them, **Then**
   every item's location (and sub-location, if given) is updated, and the result lists each
   item's outcome; an ID that does not exist is reported without blocking the others.
6. **Given** an edit to an item, **When** it succeeds, **Then** only the fields supplied are
   changed and dimensions are stored exactly as given (no rounding drift).

---

### User Story 3 - Manage products through the assistant (Priority: P2)

The owner asks the assistant to add a product, edit a product's fields, set the category on
one or several products, record a stock count or adjust it up or down, or set/clear a low or
out flag.

**Why this priority**: Equal value to Story 2 for the catalog half; independent of it.

**Independent Test**: Against a seeded catalog, call the add, edit, categorize, count and
flag tools and confirm the product pages show the changes with the same semantics as the
web controls (count age, flag age, category creation).

**Acceptance Scenarios**:

1. **Given** a description, **When** the assistant adds a product, **Then** a product is
   created with a new internal code that is returned.
2. **Given** several products and a category path, **When** the assistant categorizes them,
   **Then** every listed product gets that category and nothing else about them changes; a
   category not yet in use is created the same way the web form creates it.
3. **Given** a product, **When** the assistant records a count of N, **Then** the on-hand
   quantity becomes N and the count's age resets to now; **When** it adjusts by +k or −k,
   **Then** the quantity changes by k with the same rules as the web **+** / **−** buttons
   (count age resets; a result below zero is refused; adjusting an untracked product is
   refused with a message saying to record a count first).
4. **Given** a product, **When** the assistant sets it to "not tracked", **Then** its
   quantity reads "not tracked" thereafter, distinct from zero.
5. **Given** a product, **When** the assistant flags it low or out (or clears the flag),
   **Then** the flag and its age behave as they do from the product page.

---

### User Story 4 - Print labels through the assistant (Priority: P3)

The owner asks the assistant to print labels for one or several inventory items or
products, choosing the label stock and number of copies.

**Why this priority**: Saves a trip to the page after an assistant-driven add, but depends
on a printer being present; less central than reading and changing data.

**Independent Test**: With the printer replaced by a recording stand-in, call the print
tools for an item and a product and confirm the label requested matches what the web dialog
would print for the same item, stock and copy count.

**Acceptance Scenarios**:

1. **Given** an item JA ID, a label stock and a copy count, **When** the assistant prints,
   **Then** the same label the web dialog would print is sent to the printer and success is
   reported.
2. **Given** a product code, **When** the assistant prints a product label, **Then** the
   product label (description, manufacturer/part number, provenance, code) is printed.
3. **Given** an unknown label stock, a copy count outside 1–99, or a printer failure,
   **When** the assistant prints, **Then** the tool reports the error and the list of
   valid stocks where relevant.
4. **Given** the assistant lists the label stocks, **Then** it receives the same set of
   stocks the web dialog offers.

---

### User Story 5 - Reference lookups for correct input (Priority: P3)

So that the assistant gets inputs right the first time, it can look up the valid
materials, item types and shapes, known locations and sub-locations, product categories,
and label stocks.

**Why this priority**: Improves the success rate of Stories 2–4 but they can work without
it (validation errors guide the assistant).

**Independent Test**: Call each lookup tool and compare with the values the web forms offer.

**Acceptance Scenarios**:

1. **Given** the materials taxonomy, **When** the assistant asks for valid materials,
   **Then** it receives the active materials the Add Item form accepts.
2. **Given** existing locations, **When** the assistant asks for locations (optionally
   sub-locations within one location), **Then** it receives the same suggestions the forms
   offer.

### Edge Cases

- A request addressed to a deactivated (history-only) JA ID row: reads return the current
  active row and history; mutations act on the active row only.
- Moving a list containing duplicates or an unknown JA ID: each ID's outcome is reported
  individually; valid ones still move.
- Bulk add with a quantity outside the range the web form allows: refused.
- Dimensions given as fractions or decimals ("1/2", "0.5", "1-1/4"): accepted exactly as
  the web form accepts them; never converted through binary floating point.
- Product categorize with a path deeper than the taxonomy allows or with mixed case: same
  normalization and refusal rules as the web form.
- Count adjustments on a product that is not tracked: same behavior as the web buttons.
- Printer not configured or unreachable: the print tool fails with a clear message; no
  other tool is affected.
- A client speaking a protocol version the endpoint does not support: the handshake
  negotiates a supported version or fails with a protocol error, never a server crash.
- Malformed tool arguments (wrong types, missing required argument): the tool returns an
  error naming the argument; nothing is written.
- Searches with no filters: return the first page of active items, not the whole database.

## Requirements *(mandatory)*

### Functional Requirements

**Endpoint**

- **FR-001**: The application MUST serve an MCP endpoint from the same running application
  (same host and port as the web UI), usable by Claude Code and, through a standard local
  bridge, by Claude Desktop.
- **FR-002**: The endpoint MUST implement the MCP handshake, tool listing and tool calling
  for at least the current and previous stable protocol revisions.
- **FR-003**: Every tool MUST have a name, a description that tells an assistant when to
  use it, and an input schema; tools that do not change data MUST be marked read-only and
  tools that change data MUST NOT be.
- **FR-004**: The endpoint MUST require no login, consistent with the rest of the
  application.
- **FR-005**: Tool failures (validation, not found, printer error) MUST be reported as tool
  errors with a human-readable message, distinct from protocol errors.

**Behavioral parity and data integrity**

- **FR-006**: Every tool that changes data MUST apply the same validation and business
  rules as the corresponding web operation, by using the same underlying logic — not a
  parallel reimplementation.
- **FR-007**: Measurements MUST be accepted as strings or numbers and handled as exact
  decimals; results MUST report measurements as exact decimal strings.
- **FR-008**: Item reads presented as current inventory MUST include only active rows;
  shortening MUST preserve the one-active-row-per-JA-ID and retained-history invariants.
- **FR-009**: A tool call that fails validation MUST write nothing.

**Inventory item tools**

- **FR-010**: Search items with filters for: material (including hierarchical material
  matching), item type, shape, length/width/thickness/wall-thickness ranges, thread, location (text),
  notes text, JA ID, precision, inactive rows on request, and a result limit and offset
  (the Advanced Search filter set).
- **FR-011**: Get one item's details by JA ID, including its history.
- **FR-012**: Add one or more items (quantity) with the same fields the Add Item API accepts,
  returning allocated JA IDs.
- **FR-013**: Edit an item's fields by JA ID, changing only the fields supplied.
- **FR-014**: Shorten an item to a new length, with the optional cut date and notes the web
  flow accepts.
- **FR-014a**: Find stock a described part could be cut from (material, shape and part
  dimensions with optional tolerances), returning the same fits as the Find Stock page.
- **FR-015**: Move one or more items to a location and optional sub-location, reporting
  per-item outcomes.

**Product tools**

- **FR-016**: Search products by text, category, and identifier, with a result limit and
  offset.
- **FR-017**: Get one product's details by internal code or numeric product ID, including identifiers, category,
  quantity state with count age, flags with age, and location.
- **FR-018**: Add a product (description required; other catalog fields optional),
  returning its internal code.
- **FR-019**: Edit a product's fields, changing only the fields supplied.
- **FR-020**: Set the category on one or more products.
- **FR-021**: Record a count, adjust the count by a signed amount, or set the product to
  not tracked.
- **FR-022**: Set or clear a product's low/out flag.
- **FR-023**: Get the reorder list.
- **FR-024**: Move one or more products to a location and optional sub-location.

**Labels and lookups**

- **FR-025**: Print item labels for one or more JA IDs and product labels for one or more
  product codes, with a label stock and copy count (1–99).
- **FR-026**: List valid label stocks, materials, item types and shapes, locations and
  sub-locations, and product categories.

**Out of scope**

- **FR-027**: Deleting items or products, photos and attachments, orders and purchases
  (capture, receiving, editing), exports, and taxonomy administration are NOT offered as
  tools in this feature.

**Documentation**

- **FR-028**: The user documentation MUST describe how to connect Claude Code and Claude
  Desktop to the endpoint and list the tools offered.

### Key Entities

- **Tool**: a named operation offered over MCP — description, input schema, read-only
  marker, and a result (text the assistant reads, plus structured data).
- **Inventory item**: as today — JA ID, type, shape, material, dimensions, location,
  sub-location, active flag, history.
- **Product**: as today — internal code, description, category, identifiers, quantity state,
  count age, flags, location.
- **Label stock**: one of the label sizes the printer supports.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The owner can register the endpoint in Claude Code with one command and see
  all tools listed, with no code or config changes on the application beyond deploying it.
- **SC-002**: Every capability named in the issue — view details, search, filter, add, edit,
  shorten, move, categorize, count, print labels — is reachable by at least one tool (10 of
  10).
- **SC-003**: For each data-changing tool, an automated test shows the same input produces
  the same stored result as the corresponding web operation, and invalid input writes
  nothing.
- **SC-004**: An assistant can answer "where is stock matching X" in a single tool call for
  any filter the Advanced Search page supports.
- **SC-005**: No tool can leave a JA ID with zero or more than one active row.

## Assumptions

- The application is reached only from the home LAN by its one trusted owner; the endpoint
  inherits that threat model and has no authentication, as the constitution requires.
  Assistants may prompt the owner before calling non-read-only tools; that is the client's
  concern.
- Claude Desktop reaches a LAN-only HTTP endpoint through a local bridge (a standard
  stdio-to-HTTP MCP proxy); the application does not need to ship its own stdio program.
- Tools return both a human-readable text summary and structured data so assistants can
  either read or reason over results.
- Result pages default to a modest size (e.g. 50) with a maximum, so a filterless search
  cannot dump the whole database into the assistant's context.
- Deletion is deliberately excluded: the issue does not ask for it and it is the one
  operation where an assistant's mistake loses data.
- Prompts and resources (other MCP features) are not needed; tools cover the issue.
