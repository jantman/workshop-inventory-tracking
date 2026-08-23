# Feature Specification: Initial Category Taxonomy for the Existing Workshop

**Feature Branch**: `issues/98`

**Created**: 2026-08-23

**Status**: Draft

**Input**: GitHub issue #98 — "Design an initial category taxonomy for the existing workshop"

---

## Context

The product catalog has category machinery and no categories. A category is a materialized
path stored on the product itself; there is no categories table, so a category comes into
existence when someone types it and ceases to exist when the last product leaves it. That is
the right mechanism and the wrong starting condition: paths typed ad hoc as products arrive
produce `electronics/microcontrollers` on Monday and `electronic components/dev boards` on
Thursday, and nothing reconciles them afterwards.

Issue #98 states how this feature is to be executed, and it is a requirement, not a
preference: **the tree is settled interactively, in a working session with the workshop
owner.** A tree derived unattended from a file listing would be plausible, wrong in ways
nobody notices until the twentieth product is filed under the wrong branch, and expensive to
change afterwards. An agent picking this up opens the conversation, not the editor.

The session's raw input is `shop-inventory.txt` (attached to issue #80), a photo-derived
listing of roughly 300 labelled bins across six areas of the shop: general DIY, electrical,
fasteners, machining, electronics staging, and electronic components.

**This session covers three of those six**: electronics (staging and the component bin wall),
electrical, and fasteners — what the catalog is expected to hold in the near term. Machining
and general DIY are left for a later session and get no branches here. The tree that comes out
is carried by the application itself, so that a branch nobody has filed into yet is still
offered when filing; the alternative — a document read alongside the filing screen — leaves
the first product in every branch typed free-hand, which is the drift this feature exists to
remove.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Settle the tree in a working session and write it down (Priority: P1)

The workshop owner sits down with an assistant, works through what is actually in the shop,
argues the hard cases out loud, and converges on a tree. The result is written down: every
branch, and one line per branch saying what belongs in it. The naming conventions and the
tag boundary are written down alongside it.

**Why this priority**: Nothing else in this feature is possible without it, and it is the
whole of the value. With the record and no software change at all, the owner can already
file products consistently by hand — which is the state the catalog is missing today.

**Independent Test**: Hand the written record to someone who was not in the session, hand
them twenty in-scope bin labels drawn from `shop-inventory.txt`, and ask where each goes.
Compare against the owner's own answers.

**Acceptance Scenarios**:

1. **Given** the session has concluded, **When** the record is read, **Then** every branch
   in the tree carries a one-line statement of what belongs in it.
2. **Given** the record, **When** asked where a 1/4-20 socket head cap screw goes, **Then**
   exactly one branch is named, and the record's own wording is what settles it — not a
   judgement call by the reader.
3. **Given** the record, **When** asked where a Wago connector goes, **Then** exactly one
   branch is named, and the record says why it is not filed under the neighbouring
   candidate.
4. **Given** the record, **When** asked where an ESP32 dev board goes, **Then** exactly one
   branch is named.
5. **Given** the record, **When** any branch is inspected, **Then** it is at most three
   levels deep.
6. **Given** the record, **When** raw metal stock, drops/offcuts or threaded rod are looked
   for, **Then** no branch claims them — they belong to the Inventory side of the app.
7. **Given** the record, **When** a machining or general-DIY bin label is looked up, **Then**
   no branch claims it either, and the record says plainly that those areas are unsettled.

---

### User Story 2 - File a product into a branch nothing occupies yet (Priority: P2)

The owner adds or edits a product and reaches the category field. The branches agreed in the
session are offered to them, including the ones no product has been filed into yet. They
choose one instead of typing it from memory.

**Why this priority**: This is the moment the drift the feature exists to prevent actually
enters. Today the field suggests only paths already in use, so the *first* product in every
branch is typed free-hand — and the first one is the one every later product is matched
against. Without this, the written record is a document the owner has to keep open in
another window.

**Independent Test**: With a catalog containing no products in a given agreed branch, open
the product form and confirm the branch can be selected without typing it out; then confirm
the stored path is character-for-character the path in the record.

**Acceptance Scenarios**:

1. **Given** an agreed branch that no product occupies, **When** the owner reaches the
   category field, **Then** that branch is offered.
2. **Given** the owner selects an agreed branch, **When** the product is saved, **Then** the
   stored path matches the record's path exactly, so filing a second product into the same
   branch yields one path and not two.
3. **Given** an agreed branch that products already occupy, **When** the owner reaches the
   category field, **Then** it appears once, not twice — the branch on offer and the branch in
   use are the same branch.
4. **Given** a product that fits no branch — including anything from the machining or DIY
   areas — **When** it is saved with the category left empty, **Then** it saves;
   uncategorized is an ordinary state, not an error.
5. **Given** a path that is not in the agreed tree, **When** the owner types it anyway,
   **Then** it is accepted — the tree is a strong default, not a whitelist.

---

### User Story 3 - File the products already in the catalog (Priority: P3)

The handful of products captured during the issue #80 verification pass have no category.
The owner files each of them into the new tree.

**Why this priority**: It is the first real exercise of the tree against things rather than
against bin labels, and it is the cheapest way to find the branch that reads fine on paper
and does not work in practice — while the cost of moving it is still a rename of a few rows.

**Independent Test**: Every product in the catalog has a category path, and every one of
those paths appears in the written record.

**Acceptance Scenarios**:

1. **Given** the tree is established, **When** every existing product that falls in an
   in-scope area has been filed, **Then** no category path exists in the catalog that the
   record does not name, and any product outside those areas is left uncategorized rather
   than forced into a branch.
2. **Given** filing an existing product reveals a branch that does not work, **When** the
   branch is renamed, **Then** its sub-branches and their products move with it, and the
   record is updated in the same sitting.

---

### Edge Cases

- **An item that honestly belongs in two branches.** A heat-shrink butt crimp is both an
  electrical termination and an electronics connector. The record has to state the tie-break
  rule, not leave it to whoever is filing at the time. Where two branches would both be
  right, that is the signal the axis belongs on a tag instead.
- **A label that describes a place, not a kind of thing.** `shop-inventory.txt` contains
  shelf-edge wayfinding labels — `eBench Top`, `Shop Shelf1`, `FASTENERS` as a unit label —
  and area headings that mirror the physical shelving. These describe where something is,
  which the product's own location field already holds. They must not be transplanted into
  the tree.
- **The catch-all bins.** The listing contains `Misc./Unknown`, `Misc. Components`, `Misc.
  Terminals` and similar. A `misc` branch under every parent is how a taxonomy dies; the
  record has to say what happens to these instead.
- **A branch that will only ever hold one product.** Acceptable. Breadth is chosen for one
  person finding one thing, not for even distribution.
- **A vendor's own category.** A captured listing carries the vendor's category, which is a
  statement about the vendor's catalog, not about this shop. It does not enter the tree.
- **A category name containing the path separator.** The separator is structural; a name
  cannot contain one. The naming conventions must say what is used instead.
- **A path near the 512-character limit.** Not reachable at three levels with sane names, but
  the record states the limit so that nobody discovers it by hitting it.
- **A product from an out-of-scope area.** A bearing, a caster or a length of Cat6 arrives
  before machining and DIY have been settled. It is filed uncategorized. Nothing in the tree
  stretches to accommodate it, and nobody invents a branch for it in passing.
- **A boundary item between an in-scope and an out-of-scope area.** Hose clamps sit in DIY,
  heat-shrink butt crimps in electronics staging, motor capacitors in the component wall. The
  areas are shelving, not definitions, and the tree's branch definitions have to be written
  tightly enough that an out-of-scope item does not fall into an in-scope branch by default.
- **A path in use that the reference data does not name.** Typed before the tree existed, or
  typed deliberately outside it. It stays, and it stays visible — establishing the tree adds
  branches on offer, it does not prune the catalog.
- **The record, the reference data and the app disagreeing.** There are now three places a
  branch name lives: the written record, the reference data the app reads, and the paths
  products actually carry. A rename that lands in one or two of them restores exactly the
  drift this feature removes.

---

## Requirements *(mandatory)*

### Functional Requirements

**How the tree is arrived at**

- **FR-001**: The taxonomy MUST be settled in an interactive working session with the
  workshop owner. A tree derived unattended from `shop-inventory.txt` MUST NOT be adopted.
  A draft proposed from the listing is a legitimate way to *start* the session, as something
  to react to; it is not the deliverable.
- **FR-002**: The session MUST resolve, explicitly and out loud, the placement of a 1/4-20
  socket head cap screw, a Wago connector, and an ESP32 dev board. These three are the
  feature's disagreements in miniature.

**What the session produces**

- **FR-003**: The session MUST produce a written taxonomy record naming every agreed branch,
  each with a one-line statement of what belongs in it.
- **FR-004**: The tree MUST be at most three levels deep.
- **FR-005**: The record MUST state the naming conventions in force: singular or plural,
  how names interact with the canonical form the application already applies (lowercased,
  separator-joined, blank segments dropped), what stands in for the separator inside a name,
  and the 512-character path limit.
- **FR-006**: The record MUST state which cross-cutting axes are carried by tags rather than
  by branches, and MUST state the rule for deciding: anything that would otherwise force one
  product into two branches belongs on a tag.
- **FR-007**: The record MUST state what happens to items that fit no branch, and MUST NOT
  answer that with a `misc` branch under each parent.
- **FR-008**: Every in-scope bin in `shop-inventory.txt` MUST map to exactly one branch under
  the record's own wording. Where two branches would both be defensible, the record MUST name
  the tie-break.

**What the tree excludes**

- **FR-009**: Raw metal stock, drops, offcuts and threaded rod MUST NOT appear in the
  taxonomy. They are held by the existing Inventory functionality, not by the catalog.
- **FR-010**: The material taxonomy — the metal stock hierarchy, a different concept in a
  different table — MUST be left unchanged by this feature.
- **FR-011**: Physical location MUST NOT be encoded in the tree. Location is a separate field
  on the product and stays there.

**Using the tree**

- **FR-012**: When filing a product, the owner MUST be able to choose an agreed branch that
  no product currently occupies, without typing the path from memory. The agreed tree is
  carried by the application and offered alongside the paths already in use, so that no
  branch is ever entered free-hand for the first time.
- **FR-013**: A path written by choosing an agreed branch MUST match the record's path
  exactly, so that two products filed into the same branch produce one path and not two.
- **FR-014**: A product MUST still be allowed to have no category at all.
- **FR-015**: A path outside the agreed tree MUST still be accepted. The tree is a default,
  not a constraint enforced against the owner.

**Establishing and maintaining it**

- **FR-016**: The agreed tree MUST be established as reference data that the application
  reads. It MUST NOT be established by creating placeholder products, and it MUST NOT require
  a categories table — a category still exists because a product carries it, and the reference
  data is a list of branches on offer, not a set of rows that own them.
- **FR-017**: Establishing or re-establishing the tree MUST be repeatable without harm: it
  MUST NOT duplicate branches, MUST NOT change a category already assigned to a product, and
  MUST NOT delete or hide an in-use path that the reference data does not name.
- **FR-018**: A branch offered by the reference data and a branch already carried by products
  MUST be presented as one branch, not two, when their paths are the same.
- **FR-019**: When a branch is renamed after the tree is in use, its sub-branches and their
  products MUST move with it, and both the written record and the reference data MUST be
  updated in the same change. The three MUST NOT be left disagreeing.

**Scope of the tree**

- **FR-020**: The tree MUST cover three of the six areas in `shop-inventory.txt`: the
  electronic components bin wall and electronics staging (areas 5 and 6), the electrical
  shelving (area 2), and the fasteners shelving (area 3). These are what the catalog is
  expected to hold in the near term.
- **FR-021**: Machining (area 4) and general DIY (area 1) are out of scope for this session
  and MUST NOT be given branches. A product from either area is filed uncategorized until a
  later session settles those areas.
- **FR-022**: The out-of-scope areas MUST NOT be absorbed by stretching an in-scope branch to
  cover them. Where the boundary between an in-scope and an out-of-scope area is genuinely
  contested — a bearing, an o-ring, a hose clamp — the record MUST state which side it falls
  on and say so explicitly, rather than leaving the branch definition wide enough to swallow
  it by accident.

**What the branches expect of the product**

- **FR-023**: The record MUST name, for each branch or family of branches, the specification
  keys products filed there are expected to carry — the exact key as it is to be typed, not a
  description of it. `fasteners/machine screws & bolts/*` expects `Thread`, `Length`, `Drive`
  and `Material`; it does not expect "something recording the thread".
- **FR-024**: The record MUST state how a vendor-supplied specification name is normalized to
  the key the record names. A captured listing arrives carrying the vendor's vocabulary —
  `Thread Size` where the record says `Thread` — and nothing reconciles the two afterwards.
- **FR-025**: The specification keys MUST carry the dimensions that were deliberately kept out
  of the path. Thread system, size, length, voltage, material and finish are attributes of the
  product, and the record MUST say under which key each is recorded rather than leaving it to
  whoever files the product.

**Whose taxonomy it is**

- **FR-026**: The shipped taxonomy and specification keys MUST be replaceable at runtime by
  the deployment, without editing the application's source. They are one workshop's answers,
  and the application is not this workshop's alone.
- **FR-027**: The replacement MUST be opt-in: with nothing configured the application MUST
  behave exactly as it does with the built-in defaults, and MUST NOT read anything from disk.
- **FR-028**: A replacement MUST replace rather than merge. Adding to the built-in list would
  leave one workshop's branches in every other workshop's catalog, which is the whole
  objection.
- **FR-029**: A replacement that is configured but unusable MUST stop the application at
  startup, naming the file and the problem. It MUST NOT fall back to the defaults: an operator
  who asked for their own vocabulary and silently got somebody else's has no way to notice.
- **FR-030**: The constraints the record chose for itself — three levels, in particular — MUST
  NOT be imposed on a replacement. Only the limits the application genuinely has apply.

### Key Entities

- **Category path**: A `/`-separated path of at most three segments held on the product
  itself. Already exists. No product means no category — the tree cannot be stored as rows
  of empty branches without changing that.
- **Taxonomy record**: The written outcome of the session. The single authority on what the
  branches are, what belongs in each, and how they are named. New.
- **Tag**: A free-form label already available on products, cutting across categories. Where
  the cross-cutting axes go.
- **Vocabulary source**: Where a deployment's branches and specification keys come from —
  the built-in defaults, or a JSON file the deployment names. New. It supplies suggestions and
  owns no rows: replacing it changes what is offered, never what any product carries.
- **Specification key**: The name half of a named value already recorded on products. Already
  exists, is already filterable and already autocompletes — but unlike a category or a tag it
  has no rename, so its vocabulary has to be settled in advance rather than corrected later.
  This is where the dimensions kept out of the path live.
- **Product**: What is filed. Carries at most one category path, any number of tags, and a
  location that is not part of the taxonomy.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given the written record and no other help, two readers independently place
  all three named probe items — a 1/4-20 socket head cap screw, a Wago connector, an ESP32
  dev board — in the same branch.
- **SC-002**: Given twenty bin labels drawn from the electronics, electrical and fasteners
  areas of `shop-inventory.txt`, a reader using only the record places at least eighteen in
  the same branch the owner would.
- **SC-003**: Every branch is at most three levels deep, and no branch has more than twenty
  direct children — a picklist that has to be scrolled past twenty entries is a tree that has
  stopped helping anybody find anything.
- **SC-004**: Every bin in the three in-scope areas of `shop-inventory.txt` has a home in the
  tree; the count of in-scope bins with no branch to go to is zero.
- **SC-005**: Given twenty bin labels drawn from the machining and general-DIY areas, no more
  than one is placed into an in-scope branch — the tree declines the work it has not been
  designed for rather than absorbing it.
- **SC-006**: After the tree is established, no category path exists in the catalog that the
  written record does not name, except paths that predate the tree.
- **SC-007**: Filing the next ten in-scope products after the session produces no ad-hoc
  path: each goes into an agreed branch, or the branch it needed is added to the record and
  the reference data in the same sitting.
- **SC-008**: The owner can decide where a newly arrived in-scope product goes, and select
  the branch, without opening anything other than the screen they are filing it on.
- **SC-009**: Every branch in the record is selectable on the filing screen before any
  product occupies it — the count of agreed branches that cannot be chosen without typing
  them out is zero.
- **SC-010**: Across the specification names in use in the catalog, the count of near-duplicate
  keys recording the same attribute — `Thread` beside `Thread Size`, `Length` beside `Screw
  Length` — is zero. The application offers no rename for a specification name, so this is
  measured as prevention, not as cleanup.
- **SC-011**: Given a filed fastener, every dimension a person would filter on — thread, length,
  drive, material — is recoverable by a specification filter rather than by reading the
  description, for at least nine of any ten products filed after the record exists.
- **SC-012**: A second workshop can replace both vocabularies with its own by writing two
  files and setting two environment variables, touching no application source, and sees zero
  branches from the shipped taxonomy afterwards.
- **SC-013**: With nothing configured, the number of files the application reads from disk for
  its vocabularies is zero, and the suggestions offered are byte-identical to the built-in
  defaults.

---

## Assumptions

- **The session is the work.** This spec specifies the session and its deliverable. It
  deliberately does not propose a tree; a tree proposed here would be exactly the unattended
  guess issue #98 rules out.
- **`shop-inventory.txt` is evidence, not authority.** It is derived from photographs, its
  own notes flag entries as partially obscured or best-guess readings, and misread labels do
  not need branches built for them.
- **The catalog is nearly empty.** Only the handful of products captured during the issue #80
  verification exist, so establishing the tree is not a migration of existing data and no
  bulk re-filing is required.
- **The application's canonical path form is unchanged.** Lowercasing, separator-joining and
  the dropping of blank segments stay as they are; the naming conventions are written to fit
  that behaviour rather than to change it.
- **The existing category browse and rename tooling is reused** for later corrections. This
  feature does not build new editing machinery for categories.
- **Tags already exist and are sufficient** for the cross-cutting axes. This feature decides
  which axes are tags; it does not extend what a tag is.
- **Location and sub-location already exist as product fields.** The "taxonomy and location"
  gap that prompted issue #98 is addressed here only on the taxonomy half.
- **No categories table.** A category still exists because a product carries it. The
  reference data carrying the agreed tree is a list of branches on offer; it does not own
  them, does not create them, and does not make an unoccupied branch into a stored thing that
  has to be cleaned up later.
- **Machining and DIY are deferred, not dropped.** A second session settles them. Until then
  those products are uncategorized, and that is the intended state rather than a backlog item
  the tree should paper over.
- **`shop-inventory.txt` describes shelving, not the taxonomy's shape.** Its six areas are
  where things physically sit. They are used here only to bound which *things* are in scope;
  the branches themselves are not obliged to mirror them.
