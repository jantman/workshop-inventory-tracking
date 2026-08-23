# Category taxonomy

The product catalog's category tree, and the rules that decide what goes where.

This is the authority. When a branch is renamed or added in the application, it is renamed or
added here in the same change — the branch name lives in three places (this document, the
reference data the application reads, and the paths products carry) and they must not drift
apart.

A category path is at most three segments, `/`-separated, and the application lowercases it.
`NULL` — no category — is an ordinary state, not a mistake.

## Scope

**Settled here**: electronics, electrical, and fasteners.

**Not settled**: machining, general DIY, 3D printing, hand tools and shop supplies, and
automotive diagnostics. Products in those areas are filed uncategorized until a later session
settles them. They are *deferred*, not homeless: no branch below is to be stretched to cover
them.

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
| `rivets` | Blind rivets and rivet nuts |
| `pins & clips` | Cotter, hitch, PTO, hairpin and R clips. Machining dowel, roll and taper pins are out of scope |
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

---

## The three probes

| Item | Branch | Why not the other one |
|---|---|---|
| 1/4-20 socket head cap screw | `fasteners/machine screws & bolts/socket head cap` | Thread size is a specification key, not a branch |
| Wago connector | `electrical/wire connectors/wire nuts & lever connectors` | Installed wiring, not bench stock |
| ESP32 dev board | `electronics/dev boards/esp32 & esp8266` | — |

## What deliberately has no branch

Uncategorized is an ordinary state. These are known, decided, and not gaps:

- **Deferred areas** — machining, general DIY, 3D printing, hand tools and shop supplies
  (staplers, crimpers, pin extractors, gauges, ESD supplies), automotive diagnostics.
- **Finished consumer instruments** — the weather station, the Govee display. Neither a sensor
  nor a display in this tree's sense.
- **One-offs with nothing to join** — dielectric grease, label tape, Cameo vinyl, negative ion
  generators.
- **Catch-all bins** — "Misc. Components", "Misc. Terminals", "Misc Connectors / Adapters",
  "Misc. Electronics". A `misc` branch under every parent is how a taxonomy dies. Products from
  these bins are filed by what they actually are, or left uncategorized.

`electrical/lighting/bulbs & lamps` currently has no stock in the surveyed areas — the bulbs
are stored elsewhere and were not in the photographed listing. The branch is correct; its
apparent emptiness is an artifact of the survey.
