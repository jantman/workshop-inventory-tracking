# Category taxonomy

The product catalog's category tree, and the rules that decide what goes where.

> **This is one workshop's taxonomy, and it ships as the default.** It came out of
> a working session held for this shop, and there is nothing universal about
> deciding that heat-shrink tubing is electrical while heat-shrink terminals are
> electronics. Another deployment replaces the whole thing by pointing
> `CATEGORY_TAXONOMY_FILE` and `SPECIFICATION_KEYS_FILE` at its own JSON --
> see the [deployment guide](deployment-guide.md#1-environment-variables).
>
> Read on if you want this shop's answers, or a worked example of what a taxonomy
> has to settle before it is useful: where the hard cases go, what earns a branch
> against what earns a tag, and which dimensions stay out of the path entirely.
> The reasoning transfers even where the branches do not.

This is the authority for the shipped default. When a branch is renamed or added in the application, it is renamed or
added here in the same change — the branch name lives in three places (this document, the
reference data the application reads, and the paths products carry) and they must not drift
apart.

A category path is at most three segments, `/`-separated, and the application lowercases it.
`NULL` — no category — is an ordinary state, not a mistake.

## Scope

**Settled here**: electronics, electrical, fasteners, tools, adhesives & chemicals, and
mechanical.

**Not settled**: general DIY, 3D printing, hand and power tools, measuring tools, and
automotive diagnostics. `tools` holds *consumable* tooling only: a tap is filed there, the tap
wrench that turns it is a hand tool and is not. Products in the unsettled areas are filed
uncategorized until a later session settles them. They are *deferred*, not homeless: no branch
below is to be stretched to cover them.

**Never in this tree**: raw metal stock, drops and offcuts, and threaded rod. Those are held
by the Inventory side of the application, not the catalog. The material taxonomy — the metal
stock hierarchy — is a different thing in a different table and is untouched by this.

## The seam rule

> **Installed infrastructure vs. bench stock.** `electrical` is what goes into the building or
> a machine permanently — mains AC wiring and devices, and the facility's data cabling.
> `electronics` is what goes onto a bench, a board, or into a project.

Not "what voltage": a solid state relay switches 240 V and is bought for a project. Not "which
shelf": the shelving and this tree agree today because the shelving was organized by kind in
the first place, but it is the rule that is recorded, so that moving a shelf does not re-file
the catalog.

Consequences worth stating, because each will be questioned later:

- Patch cables, bulk Cat6, coax, RJ-45 and keystone are **electrical** — facility
  infrastructure. Ethernet switches, PoE injectors and modems are **electronics** — bench stock.
- Plain heat-shrink tubing is **electrical**; heat-shrink *terminals* are **electronics**.
- Contactors and DIN rail are **electronics** despite switching mains: bought for projects and
  panels, not installed as building wiring.
- Motors, fans and solenoids are **electronics**; motor run capacitors and thermostats are
  **electrical** — appliance and HVAC repair parts.

### Seams of the tools, chemicals and mechanical roots

- **`tools` vs. everything else.** `tools` is consumable and wearing tooling, and the holders
  it mounts in: what goes *into* a machine, power tool or hand tool and is used up,
  resharpened or swapped. The machine or hand tool itself is not settled. Solder, flux and
  tips stay `electronics/soldering & rework`.
- **`tools/fastener installation` vs. `fasteners`.** The tool that sets a fastener is a tool;
  the fastener is a fastener. A rivet nut tool is `tools/fastener installation/rivet nut
  tools`; its rivet nuts are `fasteners/rivets`.
- **`adhesives & chemicals` vs. `electrical`.** Electrical tape and heat-shrink stay
  `electrical/insulation & sleeving`; every other tape is `adhesives & chemicals/tapes`. Thread
  seal tape is `thread compounds/thread sealants`, because it does the job pipe dope does.
- **`mechanical` vs. `fasteners`.** Pins, clips and retaining rings are fasteners. Bearings,
  springs, seals and wheels are mechanical.
- **Kits.** A thread repair kit (tap, inserts and installer) is
  `tools/taps & dies/thread repair`: the kit is bought to repair a thread. A kit of loose
  inserts alone is `fasteners/threaded inserts`.

## The tie-break rules

1. **A part of an assembly goes with the assembly, not with its generic form.** Box and plate
   screws are `electrical/boxes & enclosures`, not `fasteners/…`. Without this, every
   electrical branch leaks into fasteners.
2. **Housings and pins vs. finished jumpers.** DuPont/JST crimp housings, pins and shells are
   `electronics/connectors/dupont & jst`; finished M/M, M/F and F/F jumpers are
   `electronics/wire & terminations/jumper wires`.
3. **Connector vs. cable.** If it terminates a wire you assemble, it is a **connector**. If it
   arrives finished with ends already on it, it is a **cable**.
4. **Sensor vs. instrument.** If it is wired into a circuit and read by something else, it is a
   **sensor** (or a power supply). If it is held in the hand and read by you, it is
   **test & measurement**.
5. **A board is a board.** Anything that plugs onto or wires to another board is
   `modules & breakouts`, whatever function it performs.

## Naming conventions

- **Lowercase.** Not a choice — the application canonicalizes paths to lowercase.
- **Plural** for things you count (`screws`, `relays`); singular for the uncountable
  (`hookup wire`, `access control`).
- **`&`**, not `and`.
- **A name cannot contain `/`** — that is the separator. Where a bin label does (`HDMI/DVI/VGA`,
  `Cat 5/6`), the branch is renamed rather than transliterated: `video`, `patch cables`.
- **At most three segments**, and a path may not exceed 512 characters. At three levels with
  names of this length that limit is unreachable; it is stated so nobody discovers it by
  hitting it.
- **No dimensions in the path.** Thread system and size, length, voltage, material and finish
  are specification keys, not branches. See *Specification keys* below.

## Tags, not branches

An axis that would otherwise force one product into two branches belongs on a tag:

`consumable` · `surplus` · `stainless` · `security` · a project name

`security` is why security screws have no branch: a security drive is a property of a screw
that is otherwise an ordinary flat-head or button-head screw, and giving it a branch would
duplicate the whole head-type list.

---

## fasteners

Threaded and driven fasteners bought as loose stock, filed by **form** — what kind of fastener
it is — never by thread system or size.

| Branch | What belongs in it |
|---|---|
| `machine screws & bolts` | Screws with a machine thread, filed by head and drive |
| `machine screws & bolts/socket head cap` | Internal hex drive, cylindrical head — SHCS, any thread system |
| `machine screws & bolts/button head` | Internal hex drive, domed low-profile head |
| `machine screws & bolts/flat head & countersunk` | Conical head that sits flush, any drive |
| `machine screws & bolts/hex head` | External hex, driven with a wrench — hex bolts, tap bolts |
| `machine screws & bolts/pan & round head` | Raised head sitting proud, external drive — Phillips, slotted, Torx |
| `machine screws & bolts/set screws` | Headless, drives into a hole to lock a collar or pulley — "grub screws" |
| `machine screws & bolts/thumb screws` | Turned by hand — knurled or winged |
| `machine screws & bolts/carriage bolts` | Domed head with a square shoulder that bites into wood |
| `wood & construction screws` | Coarse-threaded screws cut for wood or board, filed by what they are for |
| `wood & construction screws/wood screws` | General tapered wood screws |
| `wood & construction screws/construction screws` | Multi-purpose framing and building screws — SPAX, GRK |
| `wood & construction screws/deck screws` | Coated exterior screws for decking |
| `wood & construction screws/drywall screws` | Bugle head, board to stud |
| `wood & construction screws/trim & cabinet screws` | Small-head finish screws, cabinet and pocket screws |
| `wood & construction screws/lag screws` | Heavy hex-head wood screws |
| `wood & construction screws/structural screws` | Engineered and load-rated — LedgerLOK and similar |
| `self-tapping screws` | Cut or form their own thread in metal or plastic — TEK, sheet metal |
| `nuts` | Every nut: hex, nylock, claw, tee, wing, cap |
| `washers` | Flat, fender, split and lock washers |
| `nails & staples/nails` | Loose nails and spikes |
| `nails & staples/collated & air fasteners` | Strip- and coil-collated fasteners for a nailer |
| `nails & staples/staples & tacks` | Hand and gun staples, thumb tacks, ground staples |
| `anchors/drywall anchors` | Toggles, self-drillers and expanding anchors for hollow board |
| `anchors/masonry anchors` | Sleeve, wedge and screw anchors for concrete and block |
| `rivets` | Blind rivets, solid rivets and rivet nuts. The tools that set them are `tools/fastener installation` |
| `pins & clips` | Pins, clips and retaining rings, filed by form below |
| `pins & clips/dowel pins` | Hardened and unhardened dowel pins |
| `pins & clips/roll & spring pins` | Slotted and coiled spring pins |
| `pins & clips/taper pins` | Taper pins |
| `pins & clips/cotter & hitch pins` | Cotter pins, hitch, PTO and hairpin (R) clips, linchpins |
| `pins & clips/clevis pins` | Clevis pins, and quick-release (ball-lock) pins |
| `pins & clips/retaining rings` | E-clips, snap rings, circlips and push-on retainers |
| `threaded inserts` | Inserts adding a machine thread to a softer material — helicoil, heat-set, brass |
| `standoffs & spacers` | Threaded and unthreaded pillars holding two things apart |
| `hooks & hangers` | Screw hooks, eyes, picture and mirror hangers |
| `structural connectors` | Load-carrying plates and brackets fastened into framing — joist hangers, U-bolts |

## electrical

Installed infrastructure: what goes into the building or a machine permanently.

| Branch | What belongs in it |
|---|---|
| `devices/receptacles` | Outlets, including GFCI and tamper-resistant |
| `devices/switches` | Wall switches and dimmers, **and** machine disconnect and control switches — both are devices you install rather than project parts |
| `wall plates & covers` | Faceplates, blank covers, weatherproof covers |
| `boxes & enclosures` | Boxes, junction and pull boxes, and what belongs to them: NM connectors, screw-in cable clamps, knockout and box plugs, box and plate screws |
| `conduit & raceway/emt` | EMT tubing with its couplings, connectors and elbows |
| `conduit & raceway/flexible & liquid-tight` | LFMC, FMC and BX with their fittings |
| `conduit & raceway/pvc & ent` | Rigid PVC and ENT with their fittings |
| `conduit & raceway/surface raceway` | Wiremold and other surface channel |
| `conduit & raceway/straps & clamps` | One- and two-hole straps and hangers that secure a run |
| `conduit & raceway/fittings` | Locknuts, bushings and fittings not specific to one raceway type |
| `wire connectors/wire nuts & lever connectors` | Twist-on, lever (Wago) and push-in (In-Sure) splices, including low-voltage splice connectors |
| `wire connectors/crimp splices & sleeves` | Butt splices and taps for building wire, Scotchlok IDC, heavy splices |
| `wire connectors/lugs & grounding` | Lugs, ground crimp sleeves, grounding pigtails |
| `wire & cable` | Bulk building wire and control or alarm cable, sold by the foot or the spool |
| `data & network cabling/patch cables` | Finished Ethernet patch leads |
| `data & network cabling/bulk cable` | Cat5e and Cat6 by the box |
| `data & network cabling/jacks & keystone` | RJ-45 plugs, keystone jacks and their plates |
| `data & network cabling/coax` | Coaxial cable, connectors and adapters |
| `insulation & sleeving` | Heat-shrink tubing, electrical tape, sleeving. Heat-shrink *terminals* are electronics |
| `cords & plugs/plugs & connector bodies` | Replacement plugs, connector bodies, twist-lock ends |
| `cords & plugs/iec cords & inlets` | C5, C7 and C13 cords, inlets and outlets |
| `cords & plugs/strain reliefs & glands` | Cord grips, cable glands, grommets |
| `cords & plugs/pdus & splitters` | Power strips, PDUs, AC splitters |
| `circuit protection/fuses & holders` | Fuses, holders and fuse blocks |
| `circuit protection/breakers & disconnects` | Breakers, safety switches, unfused disconnects |
| `lighting/lampholders & sockets` | Sockets, pull-chain holders, cord sets |
| `lighting/bulbs & lamps` | Lamps of any technology |
| `lighting/fixtures` | Finished luminaires — night lights, shop lights |
| `cable management` | Ties, tie bases, staples, clips, nail guards |
| `motor & appliance parts` | Repair parts for installed motors and appliances — run and start capacitors, thermostats |

## electronics

Bench stock: what goes onto a bench, a board, or into a project.

| Branch | What belongs in it |
|---|---|
| `dev boards/esp32 & esp8266` | ESP32 and ESP8266 dev boards of any form |
| `dev boards/arduino` | Arduino and Arduino-compatible boards |
| `dev boards/raspberry pi` | Raspberry Pi boards |
| `dev boards/other boards` | Dev boards and single-board computers from other families |
| `modules & breakouts` | Anything that plugs onto or wires to another board — breakouts, level converters, HATs |
| `components/resistors` | Fixed and variable resistors, bought by value |
| `components/capacitors` | Capacitors, bought by value |
| `components/diodes` | Diodes, rectifiers, zeners, TVS |
| `components/transistors` | Transistors and MOSFETs |
| `components/integrated circuits` | ICs, regulators, logic, op-amps |
| `components/filters & ferrites` | Power and EMI filters, ferrite cores and clamps |
| `connectors/headers` | Pin and socket headers, board to board |
| `connectors/dupont & jst` | Crimp housings, pins and shells |
| `connectors/barrel & power` | DC barrel jacks and plugs — 3.5 mm, 5.5/2.1 mm |
| `connectors/circular & waterproof` | GX aviation, M12 and other sealed circular connectors |
| `connectors/banana & binding posts` | Test and panel terminals |
| `connectors/usb` | USB connectors and pigtails for assembly. Finished cables go to `cables & adapters/usb` |
| `wire & terminations/hookup wire` | Solid and stranded wire by the spool, including scrap |
| `wire & terminations/ribbon cable` | Flat ribbon by the foot and its IDC ends |
| `wire & terminations/jumper wires` | Finished jumpers — DuPont M/M, M/F, F/F, breadboard wire |
| `wire & terminations/terminals & crimps` | Insulated and heat-shrink terminals, spades, rings, bullets, butt crimps, ferrules |
| `cables & adapters/usb` | Finished USB cables, hubs, extensions, OTG adapters |
| `cables & adapters/video` | HDMI, DVI, VGA and DisplayPort cables and adapters |
| `cables & adapters/audio` | RCA, TRS and optical audio cables and adapters |
| `cables & adapters/data & serial` | Serial, DB, SATA and eSATA cables, UPS data cables |
| `power/power supplies` | Mains-input supplies, wall warts, transformers. Bench instruments are `test & measurement` |
| `power/dc-dc converters` | Buck, boost and regulator modules |
| `power/batteries` | Cells and packs of any chemistry |
| `power/battery holders & chargers` | Holders, clips, chargers |
| `power/distribution & din rail` | DIN rail, terminal blocks, bus bars |
| `sensors/temperature & humidity` | Temperature and humidity sensors, thermocouples, probes |
| `sensors/proximity & distance` | Ultrasonic, IR, inductive and alarm proximity sensors |
| `sensors/current & voltage` | Current transformers, clamps and voltage sensing wired into a circuit |
| `sensors/water & environmental` | Water, gas, light and air-quality sensors |
| `relays & control/relays & contactors` | Every relay — mechanical, solid state, smart, relay boards — and contactors |
| `relays & control/timers & counters` | Standalone timing and counting devices |
| `actuators/motors` | DC, stepper, gear and shaded-pole motors |
| `actuators/motor drivers` | Motor drives, ESCs and stepper drivers |
| `actuators/solenoids` | Solenoids, electromagnets, solenoid valves |
| `actuators/pumps & fans` | Pumps, blowers and cooling fans |
| `actuators/thermal` | Peltiers, heaters and thermal control elements |
| `displays & indicators/displays` | Screens and display modules |
| `displays & indicators/leds` | Discrete LEDs, strips, NeoPixels, panel-mount indicators |
| `displays & indicators/panel meters` | Voltmeters, ammeters and other panel readouts |
| `displays & indicators/indicators & buzzers` | Buzzers, speakers and audible indicators |
| `switches & inputs/buttons & switches` | Pushbuttons, toggles, foot switches, panel switches |
| `switches & inputs/knobs & encoders` | Knobs, dials, potentiometers, rotary encoders |
| `switches & inputs/limit switches` | Limit and microswitches |
| `access control` | RFID readers and tags, electric locks and strikes |
| `prototyping` | Breadboards, proto board, perfboard |
| `soldering & rework` | Solder, flux, wick, tips |
| `test & measurement` | Instruments you hold and read — scopes, meters, probes, leads, bench supplies |
| `networking` | Active network gear — switches, PoE injectors, modems. Passive cabling is electrical |
| `computing & storage/drives & media` | Flash drives, SD and CF cards, disks |
| `computing & storage/docks & adapters` | Drive docks, SATA and eSATA adapters |
| `computing & storage/pc parts & peripherals` | Internal PC components, keyboards, mice |
| `enclosures & mounting` | Project boxes, panel and DIN mounts, goosenecks, brackets |

## tools

Consumable and wearing tooling, and the holders it mounts in, filed by **what the tool does**. Tool material, size, inch vs. metric and length series are specification keys, never branches — there is no `metric taps` or `cobalt drills`.

| Branch | What belongs in it |
|---|---|
| `taps & dies` | Thread-cutting tools |
| `taps & dies/taps` | Hand and machine taps: taper, plug, bottoming, and sets of all three; spiral point, spiral flute, forming. Inch and metric alike |
| `taps & dies/dies` | Round (split/adjustable) and hex dies |
| `taps & dies/thread repair` | Thread files, thread chasers, and thread repair kits that ship tap, inserts and installer together |
| `drill bits` | Tools that make a hole by drilling |
| `drill bits/twist drills` | Number, letter, fractional and metric twist drills of every length series (stub, jobber, aircraft, extra long), material and shank, and sets of them |
| `drill bits/spotting & center drills` | Spotting drills, and combined drill & countersinks (center drills) |
| `drill bits/step drills` | Step (Unibit-style) drills |
| `drill bits/wood & masonry bits` | Brad point, spade, Forstner, auger and masonry bits |
| `hole cutters` | Tools that cut a hole by removing a ring |
| `hole cutters/annular cutters` | Annular (Rotabroach-style) cutters |
| `hole cutters/hole saws` | Hole saws of any tooth material |
| `hole cutters/arbors & pilots` | Hole saw arbors, annular cutter pilot pins and ejector pins, and the parts of their assemblies |
| `countersinks & counterbores` | Tools that shape the mouth of an existing hole |
| `countersinks & counterbores/countersinks` | Single-flute, multi-flute and zero-flute (cross-hole) countersinks |
| `countersinks & counterbores/counterbores` | Counterbores, piloted or with interchangeable pilots |
| `countersinks & counterbores/counterbore pilots` | Interchangeable pilots sold on their own |
| `countersinks & counterbores/deburring tools` | Deburring handles and replacement blades |
| `reamers` | Tools that finish a hole to size |
| `reamers/straight reamers` | Chucking, hand, adjustable and expansion reamers |
| `reamers/taper reamers` | Taper pin, Morse taper and other taper reamers |
| `extractors` | Broken screw, stud and tap extractors |
| `fastener installation` | Tools that set a fastener, as opposed to the fastener. The fasteners stay under `fasteners/` |
| `fastener installation/rivet tools` | Solid rivet sets, bucking bars, rivet squeezer sets, blind rivet nosepieces |
| `fastener installation/rivet nut tools` | Rivet nut setters, mandrels and nosepieces |
| `fastener installation/anchor setting tools` | Drop-in anchor setting tools, anchor setting punches, sleeve and wedge anchor setters |
| `fastener installation/insert installation tools` | Helicoil-style insert installers and tang breakers, threaded-insert drivers, heat-set insert tips |
| `milling cutters` | Rotating cutters for a mill |
| `milling cutters/end mills` | Square, ball and corner-radius end mills; roughers |
| `milling cutters/face mills & fly cutters` | Indexable face mills, shell mills and fly cutters. Their inserts go to `tools/indexable inserts` |
| `milling cutters/slitting & slotting saws` | Slitting, slotting and screw-slotting saws, and their arbors |
| `milling cutters/form cutters` | Chamfer, dovetail, T-slot, corner-rounding and keyseat cutters |
| `lathe tooling` | Non-rotating cutting tools for a lathe |
| `lathe tooling/tool bits & blanks` | HSS and brazed carbide tool bits and blanks |
| `lathe tooling/turning & boring holders` | Indexable turning holders, boring bars, quick-change tool post holders |
| `lathe tooling/parting & grooving` | Parting blades, grooving tools and their holders |
| `lathe tooling/knurls` | Knurling tools and wheels |
| `indexable inserts` | Carbide and ceramic inserts for any holder, lathe or mill. They get their own branch because one insert fits both |
| `toolholding` | What holds a cutter in a spindle |
| `toolholding/collets` | R8, 5C, ER and other collets, of any bore shape |
| `toolholding/holders & adapters` | End mill holders, collet chucks, drill chucks and arbors, Morse taper sleeves |
| `abrasives` | Anything that cuts by grit |
| `abrasives/grinding wheels` | Bench, surface and tool-and-cutter grinding wheels; depressed-center grinding wheels |
| `abrasives/cut-off wheels` | Thin cut-off and chop saw wheels |
| `abrasives/flap & sanding discs` | Flap discs, fiber discs, hook-and-loop and PSA sanding discs, quick-change (Roloc) discs |
| `abrasives/sanding belts` | Belts for belt sanders and grinders |
| `abrasives/sheets & rolls` | Sandpaper, emery cloth, abrasive rolls and non-woven (Scotch-Brite) pads |
| `abrasives/sharpening stones` | Bench stones, files-in-a-stone, diamond plates, slip stones |
| `abrasives/hones` | Cylinder, brake and flex (ball) hones |
| `abrasives/wire wheels & brushes` | Wire wheels, cup and end brushes, hand wire brushes |
| `abrasives/polishing & buffing` | Buffing wheels and polishing compounds |
| `abrasives/mounted points & burrs` | Mounted stones and rotary carbide burrs for die grinders and rotary tools |
| `saw blades` | Blades for a saw |
| `saw blades/bandsaw blades` | Bandsaw blades, cut to length or by the coil |
| `saw blades/hacksaw blades` | Hand and power hacksaw blades |
| `saw blades/circular & cold saw blades` | Circular, miter and cold saw blades |
| `saw blades/jigsaw & reciprocating blades` | Jigsaw, reciprocating and oscillating multi-tool blades |
| `driver bits` | Screwdriver, nut driver and impact bits, and bit holders |
| `knife & scraper blades` | Utility knife, scraper and hobby knife blades |
| `welding consumables` | What a welder, torch or plasma cutter uses up |
| `welding consumables/electrodes` | Stick electrodes |
| `welding consumables/filler wire` | MIG and flux-core wire on a spool |
| `welding consumables/filler rod` | TIG, gas and brazing rod |
| `welding consumables/tungsten` | TIG tungsten electrodes |
| `welding consumables/torch consumables` | Contact tips, nozzles, cups, collets and collet bodies for MIG and TIG torches, and plasma electrodes, tips and shields |

## adhesives & chemicals

What is applied from a tube, bottle, can or roll.

| Branch | What belongs in it |
|---|---|
| `adhesives` | Things that bond |
| `adhesives/epoxies` | Two-part epoxies and epoxy putties (JB Weld) |
| `adhesives/cyanoacrylates` | Super glues and their accelerators and primers |
| `adhesives/glues` | Wood (PVA), polyurethane, contact cement, construction adhesive, plastic cement |
| `adhesives/hot melt` | Hot glue sticks |
| `tapes` | Duct, masking, painter's, double-sided, foil, Kapton and PTFE-film tape. Electrical tape is `electrical/insulation & sleeving`; thread seal tape is `thread compounds/thread sealants` |
| `thread compounds` | Compounds applied to a thread or a fit |
| `thread compounds/threadlockers` | Low, medium and high strength threadlockers |
| `thread compounds/retaining compounds` | Cylindrical retaining compounds (Loctite 6xx) |
| `thread compounds/anti-seize` | Anti-seize compounds |
| `thread compounds/thread sealants` | PTFE thread seal tape, pipe dope, thread sealant pastes |
| `lubricants` | Things that make parts slide |
| `lubricants/oils` | Way, spindle, machine and general-purpose oils; penetrating oils |
| `lubricants/greases` | Greases of any base, including dielectric grease |
| `lubricants/cutting fluids` | Tapping fluid, cutting oil, coolant concentrate, cutting wax |
| `lubricants/dry lubricants` | Graphite, PTFE and molybdenum dry lubricants |
| `sealants & caulks` | Silicone and polyurethane sealants, caulk, RTV gasket makers |
| `solvents & cleaners` | Degreasers, brake cleaner, acetone, IPA, hand cleaner |
| `paints & coatings` | Spray paint, primers, cold galvanizing, layout fluid, rust preventives, anti-spatter |

## mechanical

Machine components that are not threaded fasteners.

| Branch | What belongs in it |
|---|---|
| `bearings` | Things that carry a rotating or sliding load |
| `bearings/ball bearings` | Radial and angular-contact ball bearings, sealed or open |
| `bearings/roller & needle bearings` | Tapered roller, cylindrical roller, needle and thrust bearings |
| `bearings/bushings` | Plain bearings: bronze, oil-impregnated, plastic |
| `bearings/mounted bearings` | Pillow blocks and flange bearings |
| `balls` | Loose precision balls of any material: steel, stainless, ceramic, bearing balls |
| `springs` | Springs |
| `springs/compression springs` | Compression springs, including die springs |
| `springs/extension springs` | Extension springs |
| `springs/torsion springs` | Torsion springs |
| `springs/gas springs` | Gas springs and struts |
| `lubrication fittings` | Grease fittings (zerks), oil cups, ball oilers and fitting caps |
| `seals & gaskets` | Things that seal a joint |
| `seals & gaskets/o-rings` | O-rings, individually or in kits, and O-ring cord |
| `seals & gaskets/gaskets` | Cut gaskets and gasket sheet material |
| `seals & gaskets/shaft seals` | Lip and oil seals for rotating shafts |
| `wire & wire rope` | Non-electrical wire |
| `wire & wire rope/music & spring wire` | Music wire and spring-temper wire |
| `wire & wire rope/safety wire` | Lockwire and general-purpose tie wire |
| `wire & wire rope/wire rope & fittings` | Wire rope, cable, and its thimbles, ferrules, clips and turnbuckles |
| `wheels & casters` | Rolling things |
| `wheels & casters/casters` | Swivel, rigid and locking casters |
| `wheels & casters/wheels` | Loose wheels and their axles |
| `power transmission` | Things that transmit rotation |
| `power transmission/shaft collars` | Set-screw and clamp collars |
| `power transmission/keys & keystock` | Machine keys and key stock |
| `power transmission/couplings` | Shaft couplings of any type |
| `power transmission/belts & pulleys` | V-belts, timing belts and their pulleys |
| `power transmission/chain & sprockets` | Roller chain, links and sprockets |
| `power transmission/gears` | Spur, bevel and worm gears, and racks |
| `linear motion` | Linear rails, shafts and bearings, lead screws and nuts |

---

## Specification keys

Dimensions kept out of the path are recorded as specifications. The application filters on an
exact key name with a partial value match, autocompletes both halves, and links every value on
the product page — so clicking `1/4-20` on any screw returns every 1/4-20 fastener across all
head types.

**There is no rename for a specification name.** `rename_category` and `rename_tag` exist;
nothing repairs `Thread` beside `Thread Size` in bulk. So the vocabulary is pinned here, and a
new key is added to this table when it is first needed rather than invented while filing.

| Branch family | Expected keys |
|---|---|
| `fasteners/machine screws & bolts/*` | `Thread`, `Length`, `Drive`, `Material` |
| `fasteners/wood & construction screws/*`, `self-tapping screws` | `Size`, `Length`, `Drive`, `Material` |
| `fasteners/nuts`, `washers` | `Thread`, `Material` |
| `fasteners/anchors/*` | `Size`, `Length`, `Substrate` |
| `fasteners/threaded inserts`, `standoffs & spacers` | `Thread`, `Length`, `Material` |
| `fasteners/pins & clips/*` | `Size`, `Length`, `Material`, `Type` |
| `electrical/devices/*` | `Amperage`, `Voltage`, `Poles`, `Color` |
| `electrical/conduit & raceway/*` | `Trade Size`, `Material` |
| `electrical/wire & cable` | `Gauge`, `Conductors`, `Type`, `Length` |
| `electrical/data & network cabling/*` | `Category`, `Length`, `Shielding` |
| `electrical/circuit protection/*` | `Amperage`, `Voltage`, `Type` |
| `electronics/components/*` | `Value`, `Tolerance`, `Voltage`, `Package` |
| `electronics/connectors/*` | `Series`, `Pitch`, `Positions`, `Gender` |
| `electronics/wire & terminations/*` | `Gauge`, `Length`, `Color` |
| `electronics/cables & adapters/*` | `Length`, `Ends` |
| `electronics/power/power supplies` | `Output Voltage`, `Output Current`, `Input Voltage` |
| `electronics/power/batteries` | `Chemistry`, `Size`, `Capacity`, `Voltage` |
| `electronics/relays & control/relays & contactors` | `Coil Voltage`, `Contact Rating`, `Poles` |
| `electronics/sensors/*` | `Interface`, `Range`, `Supply Voltage` |
| `electronics/actuators/motors` | `Voltage`, `Type`, `Shaft` |
| `electronics/dev boards/*` | `Chipset`, `Flash`, `PSRAM`, `Connectivity` |
| `tools/taps & dies/taps` | `Thread`, `Chamfer`, `Flute Type`, `Material`, `Coating` |
| `tools/taps & dies/dies` | `Thread`, `Size`, `Type`, `Material` |
| `tools/drill bits/*` | `Size`, `Length Series`, `Material`, `Point Angle`, `Shank`, `Coating` |
| `tools/hole cutters/*` | `Size`, `Cut Depth`, `Material`, `Shank`, `Arbor` |
| `tools/countersinks & counterbores/*` | `Size`, `Angle`, `Flutes`, `Pilot`, `Shank`, `Material` |
| `tools/reamers/*` | `Size`, `Taper`, `Flute Type`, `Shank`, `Material` |
| `tools/extractors` | `Size`, `Type`, `Material` |
| `tools/fastener installation/*` | `Size`, `Thread`, `Type`, `Shank` |
| `tools/milling cutters/*` | `Size`, `Flutes`, `Cut Depth`, `Shank`, `Material`, `Coating` |
| `tools/lathe tooling/*` | `Size`, `Shank`, `Material`, `Insert` |
| `tools/indexable inserts` | `Insert`, `Grade`, `Material`, `Coating` |
| `tools/toolholding/collets` | `Collet`, `Size`, `Type` |
| `tools/toolholding/holders & adapters` | `Collet`, `Shank`, `Taper`, `Size` |
| `tools/abrasives/*` | `Size`, `Grit`, `Abrasive`, `Arbor`, `Type` |
| `tools/saw blades/*` | `Length`, `Size`, `Width`, `TPI`, `Material`, `Arbor` |
| `tools/driver bits` | `Drive`, `Size`, `Shank`, `Length` |
| `tools/welding consumables/*` | `Process`, `Classification`, `Size`, `Series` |
| `adhesives & chemicals/adhesives/*` | `Type`, `Cure Time`, `Volume`, `Temperature` |
| `adhesives & chemicals/tapes` | `Type`, `Width`, `Length`, `Temperature` |
| `adhesives & chemicals/thread compounds/*` | `Strength`, `Color`, `Volume`, `Temperature` |
| `adhesives & chemicals/lubricants/*` | `Type`, `Viscosity`, `Grade`, `Volume`, `Temperature` |
| `adhesives & chemicals/sealants & caulks`, `solvents & cleaners`, `paints & coatings` | `Type`, `Color`, `Volume` |
| `mechanical/bearings/*` | `Size`, `Bore`, `OD`, `Width`, `Seal` |
| `mechanical/balls` | `Size`, `Material`, `Grade` |
| `mechanical/springs/*` | `OD`, `Wire Diameter`, `Length`, `Rate`, `Material` |
| `mechanical/lubrication fittings` | `Thread`, `Angle`, `Type` |
| `mechanical/seals & gaskets/*` | `Size`, `ID`, `OD`, `Cross Section`, `Material`, `Durometer` |
| `mechanical/wire & wire rope/*` | `Size`, `Material`, `Length` |
| `mechanical/wheels & casters/*` | `Size`, `Capacity`, `Mount`, `Type`, `Material` |
| `mechanical/power transmission/*` | `Size`, `Bore`, `Type`, `Material` |
| `mechanical/linear motion` | `Size`, `Length`, `Type`, `Thread` |

### Key meanings

Keys whose meaning is not obvious from the name:

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

### Normalizing a vendor's names

A captured listing arrives carrying the vendor's vocabulary. Normalize on capture:

| Vendor name | Key |
|---|---|
| `Thread Size` | `Thread` |
| `Screw Length`, `Cable Length` | `Length` |
| `Resistance`, `Capacitance`, `Inductance` | `Value` |
| `Package / Case` | `Package` |
| `Number of Positions` | `Positions` |
| `Voltage - Rated`, `Voltage - Supply` | `Voltage`, `Supply Voltage` |
| `Head Style`, `Head Type` | *not a key* — it is the branch |
| `Diameter` (tools, balls) | `Size` |
| `Length of Cut`, `Depth of Cut` | `Cut Depth` |
| `Included Angle` | `Angle` |
| `Bore Diameter` | `Bore` |
| `Outside Diameter`, `Inside Diameter` | `OD`, `ID` |
| `Teeth per Inch` | `TPI` |

---

## Probes

| Item | Branch | Why not the other one |
|---|---|---|
| 1/4-20 socket head cap screw | `fasteners/machine screws & bolts/socket head cap` | Thread size is a specification key, not a branch |
| Wago connector | `electrical/wire connectors/wire nuts & lever connectors` | Installed wiring, not bench stock |
| ESP32 dev board | `electronics/dev boards/esp32 & esp8266` | — |
| 1/4-20 plug tap, HSS | `tools/taps & dies/taps` | Plug vs. bottoming is `Chamfer`, and inch vs. metric is `Thread`. Neither is a branch |
| #7 cobalt jobber drill | `tools/drill bits/twist drills` | Size, material and length series are keys |
| 7/8" x 1" annular cutter | `tools/hole cutters/annular cutters` | — |
| Drop-in anchor setting tool | `tools/fastener installation/anchor setting tools` | It sets an anchor; the anchor is `fasteners/anchors` |
| 5C 3/8" collet | `tools/toolholding/collets` | The collet system is `Collet`, not a branch |
| Loctite 243 | `adhesives & chemicals/thread compounds/threadlockers` | Not an adhesive: it is applied to a thread |
| 6203-2RS bearing | `mechanical/bearings/ball bearings` | — |
| 1/4" x 1" dowel pin | `fasteners/pins & clips/dowel pins` | A pin is a fastener, not a mechanical component |
| Electrical tape | `electrical/insulation & sleeving` | The only tape that is not `adhesives & chemicals/tapes` |

## What deliberately has no branch

Uncategorized is an ordinary state. These are known, decided, and not gaps:

- **Deferred areas** — general DIY, 3D printing, hand and power tools (staplers, crimpers,
  pin extractors, tap wrenches and die stocks), measuring tools and gauges, ESD supplies,
  automotive diagnostics.
- **Finished consumer instruments** — the weather station, the Govee display. Neither a sensor
  nor a display in this tree's sense.
- **One-offs with nothing to join** — label tape, Cameo vinyl, negative ion generators.
- **Catch-all bins** — "Misc. Components", "Misc. Terminals", "Misc Connectors / Adapters",
  "Misc. Electronics". A `misc` branch under every parent is how a taxonomy dies. Products from
  these bins are filed by what they actually are, or left uncategorized.

`electrical/lighting/bulbs & lamps` currently has no stock in the surveyed areas — the bulbs
are stored elsewhere and were not in the photographed listing. The branch is correct; its
apparent emptiness is an artifact of the survey.
