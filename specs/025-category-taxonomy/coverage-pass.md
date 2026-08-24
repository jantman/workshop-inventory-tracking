# Coverage pass — every in-scope bin against the draft tree

Every labelled bin, box and named loose item in areas 2 (electrical), 3 (fasteners),
5 (electronics staging) and 6 (electronic components) of `shop-inventory.txt`, mapped to the
branch it lands in. This is the evidence for FR-008 and SC-004.

`—` means no branch takes it. Those are collected and argued at the bottom; they are the
output of this pass, not a defect in it.

A bin is storage, not a product: a bin holding two kinds of thing maps to two branches, and
that is not an ambiguity. An ambiguity is one *product* with two plausible homes.

---

## Area 2 — electrical

| Bin | Branch |
|---|---|
| fastCat alarm cable 18/4 | `electrical/wire & cable` |
| Wiremold, Small Wiremold | `electrical/conduit & raceway/surface raceway` |
| IEC PDU | `electrical/cords & plugs/pdus & splitters` |
| 60A unfused disconnect | `electrical/circuit protection/breakers & disconnects` |
| Elegrp 15A Decora Switches | `electrical/devices/switches` |
| Wire Lugs | `electrical/wire connectors/lugs & grounding` |
| Southwire junction / pull box | `electrical/boxes & enclosures` |
| Metal box w/ green pushbutton | `electrical/devices/switches` (G5: widened) |
| AC Splitters | `electrical/cords & plugs/pdus & splitters` |
| Extension Cord Parts & Ends | `electrical/cords & plugs/plugs & connector bodies` |
| Fuses / Holders / Small Breakers | `circuit protection/fuses & holders` + `breakers & disconnects` |
| Dielectric Grease | **—** agreed orphan |
| Waterproof Junctions | `electrical/boxes & enclosures` |
| Outlets | `electrical/devices/receptacles` |
| Outlet Covers, Switch Plates & Covers, Blank Covers, Decora Covers | `electrical/wall plates & covers` |
| Switches | `electrical/devices/switches` |
| Box & Plate Screws | `electrical/boxes & enclosures` (assembly rule) |
| Low Voltage Splice Connectors | `wire connectors/wire nuts & lever connectors` |
| Wago, Ideal In-Sure, Wire Nuts | `wire connectors/wire nuts & lever connectors` |
| Ground Crimp Sleeves, Grounding Pigtails | `wire connectors/lugs & grounding` |
| Heavy Wire Splices, Scotchlok Connectors | `wire connectors/crimp splices & sleeves` |
| Cat 5/6 1-3', 5-7', 10', 15' | `data & network cabling/patch cables` |
| Coax | `data & network cabling/coax` |
| RJ-45, Keystone | `data & network cabling/jacks & keystone` |
| Thermostats, Motor Capacitors | `electrical/motor & appliance parts` |
| Heat Shrink, Heat Shrink Kit | `electrical/insulation & sleeving` |
| Night Lights | `electrical/lighting/fixtures` (G4: added) |
| Lights & Lampholders | `electrical/lighting/lampholders & sockets` |
| Strain Reliefs & Cord Grips, Cable Glands, Grommets | `cords & plugs/strain reliefs & glands` |
| IEC C5, C7, C13 | `cords & plugs/iec cords & inlets` |
| Machine Switches | `electrical/devices/switches` (G5: widened) |
| Cable Boss Staples, Wire Tie Bases, Wire Ties, Nail-in Cable Clips, Nail Guards | `electrical/cable management` |
| Conduit Nuts | `electrical/conduit & raceway/fittings` (G6: added) |
| Screw-in Cable Clamps | `electrical/boxes & enclosures` — a box connector, not a raceway fitting |
| Knockout & Box Plugs, NM Box Fittings | `electrical/boxes & enclosures` |
| ENT Fittings, 3/4" PVC | `conduit & raceway/pvc & ent` |
| Liquid-Tight (LFMC), FMT & BX Fittings, Outdoor / Liquid Tight | `conduit & raceway/flexible & liquid-tight` |
| 1/2" EMT, 3/4" EMT, 1"+ EMT | `conduit & raceway/emt` |
| EMT Straps | `conduit & raceway/straps & clamps` |
| "...-Line Breakers" | `circuit protection/breakers & disconnects` |
| Blue coiled pneumatic air hoses | out of scope (pneumatics) |

## Area 3 — fasteners

| Bin | Branch |
|---|---|
| Imperial Standoffs, Small Metric Standoffs | `fasteners/standoffs & spacers` |
| M2–M8 Grub Screws, #4–1/4-20 Grub Screws | `machine screws & bolts/set screws` |
| M3/4/5 Hex Bolts, M3–M6 Hex Bolts, A307 hex tap bolts | `machine screws & bolts/hex head` |
| Nylock Nuts M2–M12, M3–M6 Claw Nuts, 1/4-20 Nuts | `fasteners/nuts` |
| M3–M12 Washers, 1/4-20 Washers | `fasteners/washers` |
| M2/3/4 SHCS, 1/4-20 SHCS, 5/16 SHCS | `machine screws & bolts/socket head cap` |
| 1/4-20 Countersunk Hex Socket, #6/8/10 Flat Head Phillips | `machine screws & bolts/flat head & countersunk` |
| 1/4-20 Button Head Hex Socket | `machine screws & bolts/button head` |
| 1/4-20 Thumb Screws | `machine screws & bolts/thumb screws` |
| Carriage bolts 1/4 x 3 | `machine screws & bolts/carriage bolts` |
| Metric bins M2–>M8, imperial #4–#12, 1/4-20 by length, 1/4-28, 5/16–5/8 | assorted — filed by form, size is the `Thread` key |
| GRK R4 Multi-Purpose, SPAX <1"/1-2"/>2" | `wood & construction screws/construction screws` |
| Stainless TEK Screws, Self-Tapping Screws (ELCO) | `fasteners/self-tapping screws` |
| Thread Inserts & Helicoil, brass/plastic inserts | `fasteners/threaded inserts` |
| Pins — Cotter, Hitch, PTO; Hairpin / Hitch / R clips | `fasteners/pins & clips` |
| Staples (Arrow), Thumb Tacks | `nails & staples/staples & tacks` |
| Garden Staples | `nails & staples/staples & tacks` (ground staples; see G11) |
| Plier Staplers | **—** tool, see G9 |
| Hooks & Eyes, Picture & Mirror Hooks & Hangers | `fasteners/hooks & hangers` |
| Lag Screws | `wood & construction screws/lag screws` |
| Wood Screws, Misc Wood Screws | `wood & construction screws/wood screws` |
| U-Bolts | `fasteners/structural connectors` (G7: added) |
| Structural Screws, LedgerLOK 5" | `wood & construction screws/structural screws` |
| Drywall Screws | `wood & construction screws/drywall screws` |
| Trim Screws, Cabinet Screws | `wood & construction screws/trim & cabinet screws` |
| Deck Screws, Deckmate 2-1/2" | `wood & construction screws/deck screws` |
| Masonry Anchors | `fasteners/anchors/masonry anchors` |
| Drywall Anchors | `fasteners/anchors/drywall anchors` |
| Specialty Nails, Common Nails, 12" Spikes | `nails & staples/nails` |
| Air Fasteners, collated framing nails, FastenStrong nails | `nails & staples/collated & air fasteners` |
| Security Screws | filed by form + tag `security` (G8) |
| Rivets | `fasteners/rivets` |
| Simpson Fasteners (LUS28-2 hangers) | `fasteners/structural connectors` (G7: added) |
| Thread/tap gauge, fastener reference charts | **—** tool / paper, see G9 |

## Area 5 — electronics staging

| Bin | Branch |
|---|---|
| Machine Access Control (M12 8-pin cables) | `electronics/connectors/circular & waterproof` |
| Raspberry Pi | `electronics/dev boards/raspberry pi` |
| Seeed SenseCap | `electronics/dev boards/other boards` |
| Arduino | `electronics/dev boards/arduino` |
| PC Parts | `computing & storage/pc parts & peripherals` (G1) |
| Misc. Electronics | catch-all — no branch by policy (FR-007) |
| HDMI / DVI / VGA, JANTMAN HDMI wireless RX+TX | `cables & adapters/video` |
| Audio — RCA / TRS / Optical | `cables & adapters/audio` |
| USB — Hubs, Extensions, Misc | `cables & adapters/usb` |
| Heat Shrink Butt Crimps, Right Angle Spade, Bullet Connectors, Spade Terminals 1/4", Heat Shrink Terminals, End Caps, Solder Splices, Scotchlok T-taps, nylon terminals | `wire & terminations/terminals & crimps` |
| Crimper (cased) | **—** tool, see G9 |
| RPi 7" Touchscreen | `displays & indicators/displays` |
| RPi PoE HAT | `modules & breakouts` (rule 5) |
| Pumps | `actuators/pumps & fans` |
| PoE | `electronics/networking` |
| ESP32/8266 Enclosures | `electronics/enclosures & mounting` |
| RFID | `electronics/access control` |
| Label Tape | **—** agreed orphan |
| Wanptek bench PSU | `electronics/test & measurement` — bench instrument (rule 4) |
| Digital Loggers 8-ch Ethernet Relay | `relays & control/relays & contactors` |
| 4G LTE USB modem | `electronics/networking` |
| Breadboard + jumpers | `electronics/prototyping` |
| Red enclosures w/ cords (foot switches) | `switches & inputs/buttons & switches` |
| Batteries | `electronics/power/batteries` |
| 5C collet boxes, empty totes, 3D printing, reference books | out of scope |

## Area 6 — electronic components

| Bin | Branch |
|---|---|
| Old / Rechargeable / Batteries | `electronics/power/batteries` |
| Battery Holders | `power/battery holders & chargers` |
| Adjustable/Universal, 24 VDC, 24 V transformer, Misc, 12 VDC, 5 VDC, USB Power Supplies | `power/power supplies` |
| Buck/Boost Converters | `power/dc-dc converters` |
| Bus Bars, Terminal Blocks, DIN Rail | `power/distribution & din rail` |
| Voltmeters (Fultron panel meters) | `displays & indicators/panel meters` |
| Displays | `displays & indicators/displays` |
| Govee temp/humidity display | **—** finished consumer instrument, uncategorized (A6) |
| LEDs & Bulbs, Panel Mount LEDs & Indicators, NeoPixels | `displays & indicators/leds` |
| Buzzers / Speakers | `displays & indicators/indicators & buzzers` |
| Ultrasonic Sensors, IR Proximity, Proximity & Alarm Sensors | `sensors/proximity & distance` |
| Temperature Sensors, Thermocouples | `sensors/temperature & humidity` |
| Water Sensors | `sensors/water & environmental` |
| Sensors (assorted) | filed by kind across `sensors/*` |
| Current Clamps | `sensors/current & voltage` if wired in; clamp meters → `test & measurement` (rule 4) |
| Ribbon Cable | `wire & terminations/ribbon cable` |
| Hookup Wire, Scrap Wire | `wire & terminations/hookup wire` |
| Breadboard Wires, DuPont Jumpers M/M, M/F, F/F | `wire & terminations/jumper wires` |
| Wire Ferrules | `wire & terminations/terminals & crimps` |
| DuPont, JST & Similar | `connectors/dupont & jst` |
| Board Headers | `connectors/headers` |
| Binding Post / Banana | `connectors/banana & binding posts` |
| 3.5mm Barrel, 5.5/2.1mm Barrel | `connectors/barrel & power` |
| GX Aviation, M12 Locking, Waterproof Connectors | `connectors/circular & waterproof` |
| Mini USB, Micro USB, USB-C, Mini Female | `connectors/usb` — bare connectors (rule 3) |
| USB OTG | `cables & adapters/usb` — finished adapter (rule 3) |
| USB Breakout | `modules & breakouts` (rule 5); pigtails & terminals | `connectors/usb` |
| Serial / DB, SATA / eSATA, UPS Cables | `cables & adapters/data & serial` — finished cables (rule 3) |
| USB Flash Drives, SD/CF Cards | `computing & storage/drives & media` |
| Hard Drive Docks/Adapters | `computing & storage/docks & adapters` |
| Keyboard | `computing & storage/pc parts & peripherals` (G1) |
| Ethernet Switches/Hubs | `electronics/networking` |
| Small Capacitors | `components/capacitors` |
| Diodes | `components/diodes` |
| Resistors | `components/resistors` |
| Transistors | `components/transistors` |
| ICs | `components/integrated circuits` |
| Power / EMI Filters & Ferrites | `components/filters & ferrites` (G2: added) |
| ESP32/8266 | `dev boards/esp32 & esp8266` |
| ESP-32/8266 Breakout, Level Converters | `modules & breakouts` |
| Proto Board | `electronics/prototyping` |
| Soldering, solder spool | `electronics/soldering & rework` |
| Test Leads & Probes, multimeter leads, alligator leads, O-Scope, WattsUp | `electronics/test & measurement` |
| Multi-Relay Boards, Misc Relays, Smart Relays, 3v/5v Relays, Solid State Relays, Contactors | `relays & control/relays & contactors` |
| Timers, Counters | `relays & control/timers & counters` |
| Limit Switches | `switches & inputs/limit switches` |
| Switches, Buttons | `switches & inputs/buttons & switches` |
| Knobs / Dials / Rotary Things | `switches & inputs/knobs & encoders` |
| Motors, G24692 fridge fans & motors | `actuators/motors` |
| Motor Drives / Controls | `actuators/motor drivers` |
| Solenoids, Electro-Magnets | `actuators/solenoids` |
| Fans | `actuators/pumps & fans` |
| Electric Locks & Strikes | `electronics/access control` |
| Goosenecks | `electronics/enclosures & mounting` |
| Heating / Cooling | `actuators/thermal` (G3: `motion & actuators` renamed `actuators`) |
| OBD | **—** out of scope: automotive diagnostics (G10) |
| Weather (La Crosse), Anti-Static / ESD, Misc. Small Tools, Pin Extractors, Negative Ion Generators, Vinyl for Cameo | **—** agreed orphans / see G9 |
| Misc. Components, Misc. Terminals, Misc Connectors / Adapters | catch-all — no branch by policy (FR-007) |
| Wood Bits, T-handle hex keys, safety signs, Navy test set | out of scope |

---

## Gaps — bins with no branch (all resolved)

Every gap below was decided in session on 2026-08-23 and is folded into
`docs/category-taxonomy.md`.

| # | What | Decision |
|---|---|---|
| G1 | PC Parts, Keyboard | **Adopted.** `storage & media` widened to `computing & storage/{drives & media, docks & adapters, pc parts & peripherals}` |
| G2 | Power / EMI Filters & Ferrites | **Adopted.** `electronics/components/filters & ferrites` added |
| G3 | Heating / Cooling (peltiers, heaters) | **Adopted.** `motion & actuators` renamed `actuators`, gaining `thermal`. A root-level `electronics/thermal` would have put `electronics` at exactly twenty children |
| G4 | Night Lights | **Adopted.** `electrical/lighting/fixtures` added |
| G5 | Machine Switches, pushbutton box | **Adopted, widened rather than split.** `electrical/devices/switches` now covers machine disconnect and control switches; no new branch |
| G6 | Conduit Nuts, Screw-in Cable Clamps | **Adopted.** `electrical/conduit & raceway/fittings` added. Screw-in cable clamps went to `boxes & enclosures` instead — they are box connectors |
| G7 | U-Bolts, Simpson joist hangers | **Adopted.** `fasteners/structural connectors` added |
| G8 | Security Screws | **Adopted.** Filed by form; `security` added to the tag list. A drive type is not a branch |
| G9 | Plier staplers, crimper, pin extractors, thread gauge, misc small tools, ESD supplies, reference charts | **Confirmed out of scope** after the count was raised from two bins to six. Hand tools and shop supplies belong to a deferred area |
| G10 | OBD, WattsUp automotive gear | **Confirmed out of scope.** Automotive diagnostics is its own domain |
| G11 | Garden Staples | Filed to `staples & tacks`. Arguably a ground anchor; low stakes, recorded rather than argued |

## Ambiguities — one product, two plausible branches (all resolved)

The proposed rules were adopted and are recorded as tie-break rules 3, 4 and 5 in
`docs/category-taxonomy.md`.

| # | What | Rule adopted |
|---|---|---|
| A1 | `Mini USB`, `Micro USB`, `USB-C`, `USB OTG` — connector or cable? | **Terminates a wire you assemble → `connectors`. Arrives finished with ends on it → `cables & adapters`.** |
| A2 | `USB Breakout, Pigtails & Terminals` | A board is a board: breakouts → `modules & breakouts`; pigtails and terminals → `connectors/usb` |
| A3 | `Serial / DB`, `SATA / eSATA`, `UPS Cables` | Same rule as A1 |
| A4 | `Current Clamps` — sensor or instrument? | **Wired into a circuit → `sensors`. Held in the hand and read → `test & measurement`.** |
| A5 | `RPi PoE HAT` — module or networking? | A board that plugs onto a dev board is a module, whatever it does |
| A6 | Govee display, weather station — display or sensor? | A finished consumer instrument is neither; leave uncategorized |
| A7 | Bench PSU — `test & measurement` or `power/power supplies` | Same rule as A4: bench instrument → `test & measurement` |

## Branches with nothing to hold

- `electrical/lighting/bulbs & lamps` — not empty: the bulbs are stored outside the
  photographed areas and were never in the listing. The apparent emptiness is an artifact of
  the survey, not of the tree.
- `fasteners/machine screws & bolts/pan & round head` — implied by the `#4`–`#12` bins, never
  labelled. An obvious kind to buy; kept.
