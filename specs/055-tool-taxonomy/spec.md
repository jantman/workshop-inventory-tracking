# Feature Specification: Tool, Chemical and Mechanical Categories in the Default Taxonomy

**Feature Branch**: `robot-army/issue-182-add-tool-categories-to-default-taxonomy`

**Created**: 2026-09-27

**Status**: Draft. **The proposal below is waiting for the owner's approval.** The issue says
"Let me review and approve your proposed categories and specification keys before proceeding".
Planning and implementation start only after that approval.

**Input**: GitHub issue #182, "Add tool categories to default taxonomy". During drafting the
owner added one requirement: fastener installation tools (rivet setters, rivet nut tools,
concrete anchor installation tools and the like) need a home, possibly as a second-level
branch.

---

## Context

Feature 025 (#98, merged in #117) settled the default category tree for three areas:
`electrical`, `electronics` and `fasteners`. The authority for that tree is
`docs/category-taxonomy.md`, and the application's built-in branches and specification keys
are kept in exact agreement with it by a unit test. That document explicitly *deferred*
machining, general DIY, hand tools and shop supplies. Products in those areas are filed
uncategorized until a later session settles them.

This feature is that later session for part of the deferred ground. The owner now wants to
track **consumable tooling**, mostly machining and metal fabrication: taps, drills, cutters,
abrasives, collets and the like. The owner also wants a home for a list of non-tool shop
supplies that today fit no branch: adhesives, springs, bearings, O-rings, pins and so on.

The rules 025 established still govern, and the proposal below is built to them:

- At most three segments; lowercase; `&`, not `and`; plural for counted things; no `/` in a
  name.
- **No dimensions in the path.** Thread, size, inch vs. metric, length series and tool material
  are specification keys, not branches. That is why the proposal has no `inch taps`,
  `metric taps` or `cobalt drills` branch.
- No `misc` branches.
- No parent with more than twenty children.
- A part of an assembly goes with the assembly.
- Specification keys are pinned in advance, because there is no bulk rename for a key name.

The machinery does not change. The feature adds entries to the shipped defaults and the
record. Deployments that override the defaults with `CATEGORY_TAXONOMY_FILE` /
`SPECIFICATION_KEYS_FILE` are unaffected.

---

## Proposal for review

### New roots

| Root | Settles | Seam against the existing roots |
|---|---|---|
| `tools` | Consumable and wearing tooling, and the holders it mounts in: what goes *into* a machine, power tool or hand tool and is used up, resharpened or swapped | The power tool or hand tool itself is **not** settled here; see Open Question 2. Solder, flux and tips stay `electronics/soldering & rework` |
| `adhesives & chemicals` | Things applied from a tube, bottle, can or roll: adhesives, tapes, thread compounds, lubricants, sealants, cleaners, coatings | Electrical tape and heat-shrink stay `electrical/insulation & sleeving`. Dielectric grease, a "one-off with nothing to join" in 025, now joins `lubricants/greases` |
| `mechanical` | Machine components that are not threaded fasteners: bearings, springs, seals, balls, wheels, power transmission | A pin, clip or retaining ring is a fastener (see the `fasteners` additions below). A bearing, spring or seal is mechanical |

### `tools`

| Branch | What belongs in it |
|---|---|
| `tools/taps & dies` | Thread-cutting tools |
| `tools/taps & dies/taps` | Hand and machine taps: taper, plug, bottoming, and sets of all three; spiral point, spiral flute, forming. Inch and metric alike |
| `tools/taps & dies/dies` | Round (split/adjustable) and hex dies |
| `tools/taps & dies/thread repair` | Thread files, thread chasers, and thread repair kits that ship tap, inserts and installer together |
| `tools/taps & dies/wrenches & die stocks` | Tap wrenches, T-handles, tap guides and die stocks |
| `tools/drill bits` | Tools that make a hole by drilling |
| `tools/drill bits/twist drills` | Number, letter, fractional and metric twist drills of every length series (stub, jobber, aircraft, extra long), material and shank, and sets of them |
| `tools/drill bits/spotting & center drills` | Spotting drills, and combined drill & countersinks (center drills) |
| `tools/drill bits/step drills` | Step (Unibit-style) drills |
| `tools/drill bits/wood & masonry bits` | Brad point, spade, Forstner, auger and masonry bits |
| `tools/hole cutters` | Tools that cut a hole by removing a ring |
| `tools/hole cutters/annular cutters` | Annular (Rotabroach-style) cutters |
| `tools/hole cutters/hole saws` | Hole saws of any tooth material |
| `tools/hole cutters/arbors & pilots` | Hole saw arbors, annular cutter pilot pins and ejector pins, and the parts of their assemblies |
| `tools/countersinks & counterbores` | Tools that shape the mouth of an existing hole |
| `tools/countersinks & counterbores/countersinks` | Single-flute, multi-flute and zero-flute (cross-hole) countersinks |
| `tools/countersinks & counterbores/counterbores` | Counterbores, piloted or with interchangeable pilots |
| `tools/countersinks & counterbores/counterbore pilots` | Interchangeable pilots sold on their own |
| `tools/countersinks & counterbores/deburring tools` | Deburring handles and replacement blades |
| `tools/reamers` | Tools that finish a hole to size |
| `tools/reamers/straight reamers` | Chucking, hand, adjustable and expansion reamers |
| `tools/reamers/taper reamers` | Taper pin, Morse taper and other taper reamers |
| `tools/extractors` | Broken screw, stud and tap extractors |
| `tools/fastener installation` | Tools that set a fastener, as opposed to the fastener. The fasteners stay under `fasteners/` |
| `tools/fastener installation/rivet tools` | Solid rivet sets, bucking bars, rivet squeezer sets, blind rivet nosepieces |
| `tools/fastener installation/rivet nut tools` | Rivet nut setters, mandrels and nosepieces |
| `tools/fastener installation/anchor setting tools` | Drop-in anchor setting tools, anchor setting punches, sleeve and wedge anchor setters |
| `tools/fastener installation/insert installation tools` | Helicoil-style insert installers and tang breakers, threaded-insert drivers, heat-set insert tips |
| `tools/milling cutters` | Rotating cutters for a mill |
| `tools/milling cutters/end mills` | Square, ball and corner-radius end mills; roughers |
| `tools/milling cutters/face mills & fly cutters` | Indexable face mills, shell mills and fly cutters. Their inserts go to `tools/indexable inserts` |
| `tools/milling cutters/slitting & slotting saws` | Slitting, slotting and screw-slotting saws, and their arbors |
| `tools/milling cutters/form cutters` | Chamfer, dovetail, T-slot, corner-rounding and keyseat cutters |
| `tools/lathe tooling` | Non-rotating cutting tools for a lathe |
| `tools/lathe tooling/tool bits & blanks` | HSS and brazed carbide tool bits and blanks |
| `tools/lathe tooling/turning & boring holders` | Indexable turning holders, boring bars, quick-change tool post holders |
| `tools/lathe tooling/parting & grooving` | Parting blades, grooving tools and their holders |
| `tools/lathe tooling/knurls` | Knurling tools and wheels |
| `tools/indexable inserts` | Carbide and ceramic inserts for any holder, lathe or mill. They get their own branch because one insert fits both |
| `tools/toolholding` | What holds a cutter in a spindle |
| `tools/toolholding/collets` | R8, 5C, ER and other collets, of any bore shape |
| `tools/toolholding/holders & adapters` | End mill holders, collet chucks, drill chucks and arbors, Morse taper sleeves |
| `tools/abrasives` | Anything that cuts by grit |
| `tools/abrasives/grinding wheels` | Bench, surface and tool-and-cutter grinding wheels; depressed-center grinding wheels |
| `tools/abrasives/cut-off wheels` | Thin cut-off and chop saw wheels |
| `tools/abrasives/flap & sanding discs` | Flap discs, fiber discs, hook-and-loop and PSA sanding discs, quick-change (Roloc) discs |
| `tools/abrasives/sanding belts` | Belts for belt sanders and grinders |
| `tools/abrasives/sheets & rolls` | Sandpaper, emery cloth, abrasive rolls and non-woven (Scotch-Brite) pads |
| `tools/abrasives/sharpening stones` | Bench stones, files-in-a-stone, diamond plates, slip stones |
| `tools/abrasives/hones` | Cylinder, brake and flex (ball) hones |
| `tools/abrasives/wire wheels & brushes` | Wire wheels, cup and end brushes, hand wire brushes |
| `tools/abrasives/polishing & buffing` | Buffing wheels and polishing compounds |
| `tools/abrasives/mounted points & burrs` | Mounted stones and rotary carbide burrs for die grinders and rotary tools |
| `tools/saw blades` | Blades for a saw |
| `tools/saw blades/bandsaw blades` | Bandsaw blades, cut to length or by the coil |
| `tools/saw blades/hacksaw blades` | Hand and power hacksaw blades |
| `tools/saw blades/circular & cold saw blades` | Circular, miter and cold saw blades |
| `tools/saw blades/jigsaw & reciprocating blades` | Jigsaw, reciprocating and oscillating multi-tool blades |
| `tools/driver bits` | Screwdriver, nut driver and impact bits, and bit holders |
| `tools/knife & scraper blades` | Utility knife, scraper and hobby knife blades |
| `tools/welding consumables` | What a welder, torch or plasma cutter uses up |
| `tools/welding consumables/electrodes` | Stick electrodes |
| `tools/welding consumables/filler wire` | MIG and flux-core wire on a spool |
| `tools/welding consumables/filler rod` | TIG, gas and brazing rod |
| `tools/welding consumables/tungsten` | TIG tungsten electrodes |
| `tools/welding consumables/torch consumables` | Contact tips, nozzles, cups, collets and collet bodies for MIG and TIG torches, and plasma electrodes, tips and shields |

`tools` has 16 children. The largest leaf family is `abrasives` with 10.

### `adhesives & chemicals`

| Branch | What belongs in it |
|---|---|
| `adhesives & chemicals/adhesives` | Things that bond |
| `adhesives & chemicals/adhesives/epoxies` | Two-part epoxies and epoxy putties (JB Weld) |
| `adhesives & chemicals/adhesives/cyanoacrylates` | Super glues and their accelerators and primers |
| `adhesives & chemicals/adhesives/glues` | Wood (PVA), polyurethane, contact cement, construction adhesive, plastic cement |
| `adhesives & chemicals/adhesives/hot melt` | Hot glue sticks |
| `adhesives & chemicals/tapes` | Duct, masking, painter's, double-sided, foil, Kapton and PTFE-film tape. Electrical tape is `electrical/insulation & sleeving`; thread seal tape is `thread compounds/thread sealants` |
| `adhesives & chemicals/thread compounds` | Compounds applied to a thread or a fit |
| `adhesives & chemicals/thread compounds/threadlockers` | Low, medium and high strength threadlockers |
| `adhesives & chemicals/thread compounds/retaining compounds` | Cylindrical retaining compounds (Loctite 6xx) |
| `adhesives & chemicals/thread compounds/anti-seize` | Anti-seize compounds |
| `adhesives & chemicals/thread compounds/thread sealants` | PTFE thread seal tape, pipe dope, thread sealant pastes |
| `adhesives & chemicals/lubricants` | Things that make parts slide |
| `adhesives & chemicals/lubricants/oils` | Way, spindle, machine and general-purpose oils; penetrating oils |
| `adhesives & chemicals/lubricants/greases` | Greases of any base, including dielectric grease |
| `adhesives & chemicals/lubricants/cutting fluids` | Tapping fluid, cutting oil, coolant concentrate, cutting wax |
| `adhesives & chemicals/lubricants/dry lubricants` | Graphite, PTFE and molybdenum dry lubricants |
| `adhesives & chemicals/sealants & caulks` | Silicone and polyurethane sealants, caulk, RTV gasket makers |
| `adhesives & chemicals/solvents & cleaners` | Degreasers, brake cleaner, acetone, IPA, hand cleaner |
| `adhesives & chemicals/paints & coatings` | Spray paint, primers, cold galvanizing, layout fluid, rust preventives, anti-spatter |

### `mechanical`

| Branch | What belongs in it |
|---|---|
| `mechanical/bearings` | Things that carry a rotating or sliding load |
| `mechanical/bearings/ball bearings` | Radial and angular-contact ball bearings, sealed or open |
| `mechanical/bearings/roller & needle bearings` | Tapered roller, cylindrical roller, needle and thrust bearings |
| `mechanical/bearings/bushings` | Plain bearings: bronze, oil-impregnated, plastic |
| `mechanical/bearings/mounted bearings` | Pillow blocks and flange bearings |
| `mechanical/balls` | Loose precision balls of any material: steel, stainless, ceramic, bearing balls |
| `mechanical/springs` | Springs |
| `mechanical/springs/compression springs` | Compression springs, including die springs |
| `mechanical/springs/extension springs` | Extension springs |
| `mechanical/springs/torsion springs` | Torsion springs |
| `mechanical/springs/gas springs` | Gas springs and struts |
| `mechanical/lubrication fittings` | Grease fittings (zerks), oil cups, ball oilers and fitting caps |
| `mechanical/seals & gaskets` | Things that seal a joint |
| `mechanical/seals & gaskets/o-rings` | O-rings, individually or in kits, and O-ring cord |
| `mechanical/seals & gaskets/gaskets` | Cut gaskets and gasket sheet material |
| `mechanical/seals & gaskets/shaft seals` | Lip and oil seals for rotating shafts |
| `mechanical/wire & wire rope` | Non-electrical wire |
| `mechanical/wire & wire rope/music & spring wire` | Music wire and spring-temper wire |
| `mechanical/wire & wire rope/safety wire` | Lockwire and general-purpose tie wire |
| `mechanical/wire & wire rope/wire rope & fittings` | Wire rope, cable, and its thimbles, ferrules, clips and turnbuckles |
| `mechanical/wheels & casters` | Rolling things |
| `mechanical/wheels & casters/casters` | Swivel, rigid and locking casters |
| `mechanical/wheels & casters/wheels` | Loose wheels and their axles |
| `mechanical/power transmission` | Things that transmit rotation |
| `mechanical/power transmission/shaft collars` | Set-screw and clamp collars |
| `mechanical/power transmission/keys & keystock` | Machine keys and key stock |
| `mechanical/power transmission/couplings` | Shaft couplings of any type |
| `mechanical/power transmission/belts & pulleys` | V-belts, timing belts and their pulleys |
| `mechanical/power transmission/chain & sprockets` | Roller chain, links and sprockets |
| `mechanical/power transmission/gears` | Spur, bevel and worm gears, and racks |
| `mechanical/linear motion` | Linear rails, shafts and bearings, lead screws and nuts |

### Additions to `fasteners`

025 recorded `fasteners/pins & clips` as "Cotter, hitch, PTO, hairpin and R clips. Machining
dowel, roll and taper pins are out of scope". The issue asks for exactly those pins. That
exclusion is lifted and the branch gains leaves. Pins stay in `fasteners`, not `mechanical`,
because a clevis pin and a hitch pin are the same kind of thing, and 025 already put hitch pins
here.

| Branch | What belongs in it |
|---|---|
| `fasteners/pins & clips/dowel pins` | Hardened and unhardened dowel pins |
| `fasteners/pins & clips/roll & spring pins` | Slotted and coiled spring pins |
| `fasteners/pins & clips/taper pins` | Taper pins |
| `fasteners/pins & clips/cotter & hitch pins` | Cotter pins, hitch, PTO and hairpin (R) clips, linchpins |
| `fasteners/pins & clips/clevis pins` | Clevis pins, and quick-release (ball-lock) pins |
| `fasteners/pins & clips/retaining rings` | E-clips, snap rings, circlips and push-on retainers |

`fasteners/rivets` widens from "blind rivets and rivet nuts" to "blind rivets, solid rivets and
rivet nuts". The tools that set them are `tools/fastener installation`.

### Specification keys

025 pinned 39 keys. The families below reuse existing keys wherever the meaning is the same:
`Size`, `Length`, `Material`, `Thread`, `Type`, `Drive`, `Color`, `Capacity`, `Gauge`,
`Series`. The **new** keys are in bold. There are 35 of them.

| Branch family | Expected keys |
|---|---|
| `tools/taps & dies/taps` | `Thread`, **`Chamfer`**, **`Flute Type`**, `Material`, **`Coating`** |
| `tools/taps & dies/dies` | `Thread`, `Size`, `Type`, `Material` |
| `tools/drill bits/*` | `Size`, **`Length Series`**, `Material`, **`Point Angle`**, **`Shank`**, **`Coating`** |
| `tools/hole cutters/*` | `Size`, **`Cut Depth`**, `Material`, **`Shank`**, **`Arbor`** |
| `tools/countersinks & counterbores/*` | `Size`, **`Angle`**, **`Flutes`**, **`Pilot`**, **`Shank`**, `Material` |
| `tools/reamers/*` | `Size`, **`Taper`**, **`Flute Type`**, **`Shank`**, `Material` |
| `tools/extractors` | `Size`, `Type`, `Material` |
| `tools/fastener installation/*` | `Size`, `Thread`, `Type`, **`Shank`** |
| `tools/milling cutters/*` | `Size`, **`Flutes`**, **`Cut Depth`**, **`Shank`**, `Material`, **`Coating`** |
| `tools/lathe tooling/*` | `Size`, **`Shank`**, `Material`, **`Insert`** |
| `tools/indexable inserts` | **`Insert`**, **`Grade`**, `Material`, **`Coating`** |
| `tools/toolholding/collets` | **`Collet`**, `Size`, `Type` |
| `tools/toolholding/holders & adapters` | **`Collet`**, **`Shank`**, **`Taper`**, `Size` |
| `tools/abrasives/*` | `Size`, **`Grit`**, **`Abrasive`**, **`Arbor`**, `Type` |
| `tools/saw blades/*` | `Length`, `Size`, **`Width`**, **`TPI`**, `Material`, **`Arbor`** |
| `tools/driver bits` | `Drive`, `Size`, **`Shank`**, `Length` |
| `tools/welding consumables/*` | **`Process`**, **`Classification`**, `Size`, `Series` |
| `adhesives & chemicals/adhesives/*` | `Type`, **`Cure Time`**, **`Volume`**, **`Temperature`** |
| `adhesives & chemicals/tapes` | `Type`, **`Width`**, `Length`, **`Temperature`** |
| `adhesives & chemicals/thread compounds/*` | **`Strength`**, `Color`, **`Volume`**, **`Temperature`** |
| `adhesives & chemicals/lubricants/*` | `Type`, **`Viscosity`**, **`Grade`**, **`Volume`**, **`Temperature`** |
| `adhesives & chemicals/sealants & caulks`, `solvents & cleaners`, `paints & coatings` | `Type`, `Color`, **`Volume`** |
| `mechanical/bearings/*` | `Size`, **`Bore`**, **`OD`**, **`Width`**, **`Seal`** |
| `mechanical/balls` | `Size`, `Material`, **`Grade`** |
| `mechanical/springs/*` | **`OD`**, **`Wire Diameter`**, `Length`, **`Rate`**, `Material` |
| `mechanical/lubrication fittings` | `Thread`, **`Angle`**, `Type` |
| `mechanical/seals & gaskets/*` | `Size`, **`ID`**, **`OD`**, **`Cross Section`**, `Material`, **`Durometer`** |
| `mechanical/wire & wire rope/*` | `Size`, `Material`, `Length` |
| `mechanical/wheels & casters/*` | `Size`, `Capacity`, **`Mount`**, `Type`, `Material` |
| `mechanical/power transmission/*` | `Size`, **`Bore`**, `Type`, `Material` |
| `mechanical/linear motion` | `Size`, `Length`, `Type`, `Thread` |
| `fasteners/pins & clips/*` | `Size`, `Length`, `Material`, `Type` |

What the new keys mean, where it is not obvious:

| Key | Meaning | Example values |
|---|---|---|
| `Chamfer` | Tap chamfer | `Taper`, `Plug`, `Bottoming`, `Set of 3` |
| `Flute Type` | Flute *form* | `Straight`, `Spiral Point`, `Spiral Flute`, `Forming` |
| `Flutes` | Flute *count* | `2`, `4`, `Single`, `Zero` |
| `Length Series` | Drill length class. Kept apart from `Length`, which is a measurement | `Stub`, `Jobber`, `Aircraft`, `Extra Long` |
| `Shank` | Shank form and size | `Reduced 1/2"`, `MT2`, `3/4" Weldon`, `1/4" Hex`, `R8` |
| `Angle` | Included angle of a countersink, or the angle of a lubrication fitting | `82°`, `90°`, `45°` |
| `Point Angle` | Drill point angle. Kept apart from `Angle` so a filter on `90` does not mix spotting drills with countersinks | `118°`, `135°`, `90°` |
| `Taper` | A standard taper | `MT3`, `#4 taper pin`, `JT33` |
| `Collet` | Collet system | `R8`, `5C`, `ER32` |
| `Insert` | ISO/ANSI insert designation | `CCMT 32.51`, `TCMT 21.51` |
| `Grade` | Carbide grade, NLGI grease grade, or ball grade | `C2`, `NLGI 2`, `Grade 25` |
| `Abrasive` | Abrasive grain | `Aluminum Oxide`, `Zirconia`, `Ceramic`, `Silicon Carbide`, `Diamond`, `CBN` |
| `Process` | Welding process | `MIG`, `TIG`, `Stick`, `Gas`, `Plasma` |
| `Classification` | AWS classification | `ER70S-6`, `E7018`, `ER4043` |
| `Volume` | Container contents | `10 ml`, `14 oz` |

The vendor-name normalization table gains these rows: `Diameter` → `Size` (for tools and
balls), `Length of Cut` / `Depth of Cut` → `Cut Depth`, `Included Angle` → `Angle`,
`Bore Diameter` → `Bore`, `Outside Diameter` → `OD`, `Inside Diameter` → `ID`, and
`Teeth per Inch` → `TPI`.

---

## Open questions for the reviewer

1. **Root names.** `adhesives & chemicals` and `mechanical` are proposals. Alternatives:
   `shop supplies` for the first; `machine components` or `hardware` for the second.
2. **Hand and power tools.** The issue asks for *consumable* tools, so the tools that consume
   them (a tap wrench aside) have no branch here and stay deferred. They could later go under
   `tools/hand tools`, `tools/power tools` and `tools/measuring` without disturbing anything
   proposed here.
3. **Welding consumables under `tools`.** They are consumed by a tool, which is why they are
   placed here. They could instead be a fourth root (`welding`).
4. **Non-electrical wire vs. stock.** 025 put raw metal stock on the Inventory side. The
   proposal treats music wire and safety wire as catalog products (bought by the coil, pulled
   from a bin). If the owner tracks music wire as material stock instead,
   `mechanical/wire & wire rope/music & spring wire` should be dropped.
5. **"towel" pins** in the issue is read as **dowel** pins.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Approve the proposal (Priority: P1)

The owner reads the proposed branches and keys above, marks what to change, and approves a
final list.

**Why this priority**: The issue makes approval a precondition. Nothing is built from an
unapproved list, because a branch is cheap to rename but a specification key is not.

**Independent Test**: The approved list is recorded in this spec, and each change the reviewer
asked for is reflected in it.

**Acceptance Scenarios**:

1. **Given** the proposal, **When** the owner requests changes, **Then** the spec is revised,
   and the revision is what gets built.
2. **Given** the proposal, **When** it is approved, **Then** planning begins from the approved
   list.

### User Story 2 - File a tool into a branch nothing occupies yet (Priority: P2)

The owner adds a product, such as a 1/4-20 plug tap, a #7 jobber drill or an R8 1/2" collet.
The category field offers the approved `tools/…` branch, and the specification key field
offers the approved keys, before any product has used them.

**Why this priority**: This is the whole of the delivered value. It works exactly as 025 does
for the existing roots.

**Independent Test**: On a catalog with no tools, the category suggestions include every
approved new branch, and the key suggestions include every approved new key.

**Acceptance Scenarios**:

1. **Given** an empty catalog, **When** the owner reaches the category field, **Then**
   `tools/taps & dies/taps` is offered.
2. **Given** the key field, **When** the owner types `Cha`, **Then** `Chamfer` is offered.
3. **Given** the category tree page, **When** it is opened, **Then** the new roots and their
   branches render with no gaps above any branch.

### User Story 3 - The record says where things go (Priority: P3)

`docs/category-taxonomy.md` gains a section for each new root, the `fasteners` additions, the
new keys, and seam notes for each boundary above. Its "Scope" and "What deliberately has no
branch" sections are updated so that areas this feature settles are no longer listed as
deferred.

**Independent Test**: Given the probes below, a reader of the record names exactly one branch
for each.

| Item | Branch |
|---|---|
| 1/4-20 plug tap, HSS | `tools/taps & dies/taps` |
| #7 cobalt jobber drill | `tools/drill bits/twist drills` |
| 7/8" x 1" annular cutter | `tools/hole cutters/annular cutters` |
| Drop-in anchor setting tool | `tools/fastener installation/anchor setting tools` |
| 5C 3/8" collet | `tools/toolholding/collets` |
| Loctite 243 | `adhesives & chemicals/thread compounds/threadlockers` |
| 6203-2RS bearing | `mechanical/bearings/ball bearings` |
| 1/4" x 1" dowel pin | `fasteners/pins & clips/dowel pins` |
| Electrical tape | `electrical/insulation & sleeving` (unchanged) |

### Edge Cases

- **A product already filed at a path that becomes a parent.** A product filed at
  `fasteners/pins & clips` before this change keeps that valid path. Parents remain filing
  targets.
- **Kits spanning branches.** A thread repair kit with a tap, inserts and an installer goes to
  `tools/taps & dies/thread repair`: the kit is the product, and it is bought to repair a
  thread. A kit of loose inserts alone is `fasteners/threaded inserts`.
- **A deployment with an override file.** It sees none of this. An override replaces the
  defaults entirely, as 025 specified.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The shipped default category branches MUST include every approved branch and
  every intermediate parent of one.
- **FR-002**: The shipped default specification keys MUST include every approved new key, and
  still include every existing key.
- **FR-003**: No existing default branch or key may be renamed or removed. Existing products'
  paths MUST remain valid and MUST NOT be altered.
- **FR-004**: Every new branch MUST obey 025's shape rules: at most three segments, already
  canonical (lowercase), no parent with more than twenty children, sorted, no duplicates.
- **FR-005**: `docs/category-taxonomy.md` MUST be updated in the same change. It must name
  exactly the shipped branches and keys, so the existing agreement test keeps holding.
- **FR-006**: The record MUST state the seam between each new root and its neighbors, as in the
  "New roots" table above.
- **FR-007**: No schema or data migration. Categories and keys remain suggestions, not a
  whitelist.
- **FR-008**: Planning and implementation MUST NOT begin until the owner has approved the
  proposal.

### Key Entities

- **Category branch**: a lowercase `/`-separated path of at most three segments, offered when
  filing.
- **Specification key**: a pinned name offered when recording a product specification.

## Success Criteria *(mandatory)*

- **SC-001**: Every item the issue lists has exactly one approved branch that it belongs in,
  and the record's wording settles which.
- **SC-002**: All nine probes in User Story 3 resolve to the stated branch from the record
  alone.
- **SC-003**: On an empty catalog, 100% of approved new branches and keys are offered for
  selection.
- **SC-004**: No existing product changes category as a result of this feature.

## Assumptions

- The shape rules and conventions from 025 still hold, including the twenty-child cap.
- Consumable tooling is tracked as catalog products, with inventory by count and location,
  not as Inventory-side material stock.
- The before-specify git hook, which would create a new branch, is not run. This session
  delivers on the branch it was started on.
