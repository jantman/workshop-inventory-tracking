# Draft tree — v2, after the first session pass

**Status: DRAFT.** Per issue #98 and FR-001 this is a working document, not the taxonomy
record. It becomes the record once the coverage pass against `shop-inventory.txt` is done.

Scope: electronics, electrical, fasteners. Machining and general DIY are deferred (FR-021),
and so is 3D printing.

## The seam rule (settled)

> **Installed infrastructure vs. bench stock.** `electrical` is what goes into the building
> or a machine permanently — mains AC wiring and devices, and the facility's data cabling.
> `electronics` is what goes onto a bench, a board, or into a project.

Area 2 of `shop-inventory.txt` is the first; areas 5 and 6 are the second. The roots line up
with the shelving because the shelving was organized by kind in the first place — the rule
above is what is recorded, not the shelf, so that a reorganization does not re-file the
catalog. Wayfinding labels (`eBench Top`, `Shop Shelf1`) and the within-area bank structure
stay out of the tree entirely (FR-011).

Worked consequences, each of which someone will eventually question:

- Patch cables, bulk Cat6, coax, RJ-45 and keystone are `electrical` — facility
  infrastructure. Ethernet switches, PoE injectors and modems are `electronics` — bench stock.
- Plain heat-shrink tubing is `electrical/insulation & sleeving`; heat-shrink *terminals* are
  `electronics/wire & terminations/terminals & crimps`. The split is intentional and matches
  where each is kept.
- Contactors and DIN rail are `electronics` despite switching mains: they are bought for
  projects and panels, not installed as building wiring.
- Motors, fans and solenoids are `electronics`; motor run capacitors and thermostats are
  `electrical/motor & appliance parts` — appliance and HVAC repair, not project parts.

## Two derived rules

- **A part of an assembly goes with the assembly, not with its generic form.** Box and plate
  screws are `electrical/boxes & enclosures`, not `fasteners/machine screws & bolts`.
  Without this every electrical branch leaks into fasteners.
- **Housings and pins vs. finished jumpers.** DuPont/JST crimp housings and pins are
  `electronics/connectors/dupont & jst`; pre-made M/M, M/F and F/F jumpers are
  `electronics/wire & terminations/jumper wires`. Without this it is a coin flip both ways.

## Conventions

- Lowercase. Not a choice — the application canonicalizes to lowercase already.
- Plural for things you count; singular for the uncountable.
- `&` rather than `and`, matching the bin labels.
- A name cannot contain `/`. Where a bin label does — `HDMI/DVI/VGA`, `Cat 5/6` — the branch
  is renamed rather than transliterated: `video`, `patch cables`.
- Thread size, voltage, material and finish are **not** branches. They are attributes of the
  product, and where they cut across branches, tags.

## fasteners

    fasteners/machine screws & bolts/socket head cap
    fasteners/machine screws & bolts/button head
    fasteners/machine screws & bolts/flat head & countersunk
    fasteners/machine screws & bolts/hex head
    fasteners/machine screws & bolts/pan & round head
    fasteners/machine screws & bolts/set screws
    fasteners/machine screws & bolts/thumb screws
    fasteners/machine screws & bolts/carriage bolts
    fasteners/wood & construction screws/wood screws
    fasteners/wood & construction screws/construction screws
    fasteners/wood & construction screws/deck screws
    fasteners/wood & construction screws/drywall screws
    fasteners/wood & construction screws/trim & cabinet screws
    fasteners/wood & construction screws/lag screws
    fasteners/wood & construction screws/structural screws
    fasteners/self-tapping screws
    fasteners/nuts
    fasteners/washers
    fasteners/nails & staples/nails
    fasteners/nails & staples/collated & air fasteners
    fasteners/nails & staples/staples & tacks
    fasteners/anchors/drywall anchors
    fasteners/anchors/masonry anchors
    fasteners/rivets
    fasteners/pins & clips
    fasteners/threaded inserts
    fasteners/standoffs & spacers
    fasteners/hooks & hangers

The imperial/metric split the shelving is built on is absent on purpose: a 1/4-20 socket head
cap screw and an M5 socket head cap screw are the same kind of thing bought for the same
reason, and putting the thread system in the path doubles every branch to answer a question
the product's own description already answers.

## electrical

    electrical/devices/receptacles
    electrical/devices/switches
    electrical/wall plates & covers
    electrical/boxes & enclosures
    electrical/conduit & raceway/emt
    electrical/conduit & raceway/flexible & liquid-tight
    electrical/conduit & raceway/pvc & ent
    electrical/conduit & raceway/surface raceway
    electrical/conduit & raceway/straps & clamps
    electrical/wire connectors/wire nuts & lever connectors
    electrical/wire connectors/crimp splices & sleeves
    electrical/wire connectors/lugs & grounding
    electrical/wire & cable
    electrical/data & network cabling/patch cables
    electrical/data & network cabling/bulk cable
    electrical/data & network cabling/jacks & keystone
    electrical/data & network cabling/coax
    electrical/insulation & sleeving
    electrical/cords & plugs/plugs & connector bodies
    electrical/cords & plugs/iec cords & inlets
    electrical/cords & plugs/strain reliefs & glands
    electrical/cords & plugs/pdus & splitters
    electrical/circuit protection/fuses & holders
    electrical/circuit protection/breakers & disconnects
    electrical/lighting/lampholders & sockets
    electrical/lighting/bulbs & lamps
    electrical/cable management
    electrical/motor & appliance parts

## electronics

    electronics/dev boards/esp32 & esp8266
    electronics/dev boards/arduino
    electronics/dev boards/raspberry pi
    electronics/dev boards/other boards
    electronics/modules & breakouts
    electronics/components/resistors
    electronics/components/capacitors
    electronics/components/diodes
    electronics/components/transistors
    electronics/components/integrated circuits
    electronics/connectors/headers
    electronics/connectors/dupont & jst
    electronics/connectors/barrel & power
    electronics/connectors/circular & waterproof
    electronics/connectors/banana & binding posts
    electronics/connectors/usb
    electronics/wire & terminations/hookup wire
    electronics/wire & terminations/ribbon cable
    electronics/wire & terminations/jumper wires
    electronics/wire & terminations/terminals & crimps
    electronics/cables & adapters/usb
    electronics/cables & adapters/video
    electronics/cables & adapters/audio
    electronics/cables & adapters/data & serial
    electronics/power/power supplies
    electronics/power/dc-dc converters
    electronics/power/batteries
    electronics/power/battery holders & chargers
    electronics/power/distribution & din rail
    electronics/sensors/temperature & humidity
    electronics/sensors/proximity & distance
    electronics/sensors/current & voltage
    electronics/sensors/water & environmental
    electronics/relays & control/relays & contactors
    electronics/relays & control/timers & counters
    electronics/motion & actuators/motors
    electronics/motion & actuators/motor drivers
    electronics/motion & actuators/solenoids
    electronics/motion & actuators/pumps & fans
    electronics/displays & indicators/displays
    electronics/displays & indicators/leds
    electronics/displays & indicators/panel meters
    electronics/displays & indicators/indicators & buzzers
    electronics/switches & inputs/buttons & switches
    electronics/switches & inputs/knobs & encoders
    electronics/switches & inputs/limit switches
    electronics/access control
    electronics/prototyping
    electronics/soldering & rework
    electronics/test & measurement
    electronics/networking
    electronics/storage & media
    electronics/enclosures & mounting

LEDs sit under `displays & indicators` rather than `components`: they are looked at, not
soldered into a circuit as a value. NeoPixels and panel-mount indicators go there with them.
DIN rail, terminal blocks and bus bars sit under `power` as distribution, not under control.

## Tags, not branches

`consumable`, `surplus`, a project name, `stainless`. Each is an axis that would otherwise
force one product into two branches.

## Deliberately without a branch

3D printing, and the in-scope-area orphans: dielectric grease, label tape, Cameo vinyl, the
weather station, misc small tools, ESD supplies. These stay uncategorized rather than each
growing a branch. Uncategorized is an ordinary state (FR-014).

## The three probes

| Item | Branch | Why not the other one |
|---|---|---|
| 1/4-20 socket head cap screw | `fasteners/machine screws & bolts/socket head cap` | Thread size is an attribute, not a branch |
| Wago connector | `electrical/wire connectors/wire nuts & lever connectors` | Installed wiring, not bench stock |
| ESP32 dev board | `electronics/dev boards/esp32 & esp8266` | — |

## Counts

Roots 3. Direct children: `fasteners` 12, `electrical` 13, `electronics` 19 — all within the
twenty-child limit of SC-003. Maximum depth 3 (FR-004). 134 branches in total, of which 109
are leaves.
