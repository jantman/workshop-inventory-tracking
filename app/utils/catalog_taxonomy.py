"""
The category taxonomy and specification vocabulary a deployment offers.

A category is a materialized path on the product and there is no categories table,
so a branch nobody has filed into has no row anywhere -- which means it cannot be
offered while filing, and the first product into every branch would be typed by
hand.  That is precisely where ``electronics/microcontrollers`` on Monday and
``electronic components/dev boards`` on Thursday come from.

What this module supplies is what the application offers *in addition to* the paths
products already carry.  It creates nothing: a branch listed here and occupied by no
product still has no row, and a path in use that is absent from here is still
returned by every query.  A set of suggestions with the weight of a decision behind
it, not a whitelist -- ``CatalogService`` accepts a path from outside it, because a
taxonomy that refuses the thing in your hand is worse than none.

**The defaults below are one workshop's.**  They came out of a session held for this
shop and documented in ``docs/category-taxonomy.md``, and there is nothing universal
about deciding that heat-shrink tubing is electrical while heat-shrink terminals are
electronics.

They were originally the only option, and the repository owner asked in review that a
deployment be able to replace them without editing source -- so
``CATEGORY_TAXONOMY_FILE`` and ``SPECIFICATION_KEYS_FILE`` do that.  The reason is not
a second workshop somebody imagines; it is that this file currently holds one person's
data and the application is published for anyone to run.  Set neither variable and
nothing is read from disk at all.

An override **replaces**, it does not merge.  Merging would leave
``fasteners/machine screws & bolts/carriage bolts`` in a shop that has never owned a
carriage bolt, which is the whole objection to a built-in list.

The defaults are also more constrained than the loader is, deliberately.  This shop
chose three levels; the application has never required that, so an override may nest
as deep as it likes.  The only limits enforced on a loaded file are the ones the
database actually imposes.

``docs/category-taxonomy.md`` remains the authority *for the defaults*, and
``tests/unit/test_catalog_taxonomy.py`` asserts the two agree -- which makes a change
to one without the other a failing test rather than a slow divergence.

Specification keys are pinned for a sharper reason than categories: ``rename_category``
and ``rename_tag`` exist and there is no ``rename_specification``, so ``Thread``
beside ``Thread Size`` cannot be repaired in bulk once both are in use.  Prevention is
the only mechanism available.

Standard library only.  No Flask, no database.  File I/O happens only when one of the
environment variables is set, and the file is read on each call rather than cached:
it is a few kilobytes on a single-user LAN application, and there is no measured
problem to optimise away.
"""

import json
import os
from typing import List, Optional, Tuple

from . import category as category_utils

#: Points at a JSON array of category paths.  Unset means "use the defaults".
CATEGORY_TAXONOMY_ENV = 'CATEGORY_TAXONOMY_FILE'
#: Points at a JSON array of specification key names.
SPECIFICATION_KEYS_ENV = 'SPECIFICATION_KEYS_FILE'

# app/database.py: Product.category_path is String(512).
MAX_CATEGORY_PATH_LENGTH = 512
# app/database.py: ProductSpecification.name is String(100).
MAX_SPECIFICATION_NAME_LENGTH = 100

# Every branch of the record: roots, intermediate parents and leaves.  Parents are
# included deliberately.  They are legitimate filing targets when the leaf is not yet
# known, and ``category_tree`` derives one entry per distinct path -- so without them
# a catalog whose only product sits three levels deep renders a tree with holes above
# it.
DEFAULT_CATEGORY_PATHS: Tuple[str, ...] = (
    "electrical",
    "electrical/boxes & enclosures",
    "electrical/cable management",
    "electrical/circuit protection",
    "electrical/circuit protection/breakers & disconnects",
    "electrical/circuit protection/fuses & holders",
    "electrical/conduit & raceway",
    "electrical/conduit & raceway/emt",
    "electrical/conduit & raceway/fittings",
    "electrical/conduit & raceway/flexible & liquid-tight",
    "electrical/conduit & raceway/pvc & ent",
    "electrical/conduit & raceway/straps & clamps",
    "electrical/conduit & raceway/surface raceway",
    "electrical/cords & plugs",
    "electrical/cords & plugs/iec cords & inlets",
    "electrical/cords & plugs/pdus & splitters",
    "electrical/cords & plugs/plugs & connector bodies",
    "electrical/cords & plugs/strain reliefs & glands",
    "electrical/data & network cabling",
    "electrical/data & network cabling/bulk cable",
    "electrical/data & network cabling/coax",
    "electrical/data & network cabling/jacks & keystone",
    "electrical/data & network cabling/patch cables",
    "electrical/devices",
    "electrical/devices/receptacles",
    "electrical/devices/switches",
    "electrical/insulation & sleeving",
    "electrical/lighting",
    "electrical/lighting/bulbs & lamps",
    "electrical/lighting/fixtures",
    "electrical/lighting/lampholders & sockets",
    "electrical/motor & appliance parts",
    "electrical/wall plates & covers",
    "electrical/wire & cable",
    "electrical/wire connectors",
    "electrical/wire connectors/crimp splices & sleeves",
    "electrical/wire connectors/lugs & grounding",
    "electrical/wire connectors/wire nuts & lever connectors",
    "electronics",
    "electronics/access control",
    "electronics/actuators",
    "electronics/actuators/motor drivers",
    "electronics/actuators/motors",
    "electronics/actuators/pumps & fans",
    "electronics/actuators/solenoids",
    "electronics/actuators/thermal",
    "electronics/cables & adapters",
    "electronics/cables & adapters/audio",
    "electronics/cables & adapters/data & serial",
    "electronics/cables & adapters/usb",
    "electronics/cables & adapters/video",
    "electronics/components",
    "electronics/components/capacitors",
    "electronics/components/diodes",
    "electronics/components/filters & ferrites",
    "electronics/components/integrated circuits",
    "electronics/components/resistors",
    "electronics/components/transistors",
    "electronics/computing & storage",
    "electronics/computing & storage/docks & adapters",
    "electronics/computing & storage/drives & media",
    "electronics/computing & storage/pc parts & peripherals",
    "electronics/connectors",
    "electronics/connectors/banana & binding posts",
    "electronics/connectors/barrel & power",
    "electronics/connectors/circular & waterproof",
    "electronics/connectors/dupont & jst",
    "electronics/connectors/headers",
    "electronics/connectors/usb",
    "electronics/dev boards",
    "electronics/dev boards/arduino",
    "electronics/dev boards/esp32 & esp8266",
    "electronics/dev boards/other boards",
    "electronics/dev boards/raspberry pi",
    "electronics/displays & indicators",
    "electronics/displays & indicators/displays",
    "electronics/displays & indicators/indicators & buzzers",
    "electronics/displays & indicators/leds",
    "electronics/displays & indicators/panel meters",
    "electronics/enclosures & mounting",
    "electronics/modules & breakouts",
    "electronics/networking",
    "electronics/power",
    "electronics/power/batteries",
    "electronics/power/battery holders & chargers",
    "electronics/power/dc-dc converters",
    "electronics/power/distribution & din rail",
    "electronics/power/power supplies",
    "electronics/prototyping",
    "electronics/relays & control",
    "electronics/relays & control/relays & contactors",
    "electronics/relays & control/timers & counters",
    "electronics/sensors",
    "electronics/sensors/current & voltage",
    "electronics/sensors/proximity & distance",
    "electronics/sensors/temperature & humidity",
    "electronics/sensors/water & environmental",
    "electronics/soldering & rework",
    "electronics/switches & inputs",
    "electronics/switches & inputs/buttons & switches",
    "electronics/switches & inputs/knobs & encoders",
    "electronics/switches & inputs/limit switches",
    "electronics/test & measurement",
    "electronics/wire & terminations",
    "electronics/wire & terminations/hookup wire",
    "electronics/wire & terminations/jumper wires",
    "electronics/wire & terminations/ribbon cable",
    "electronics/wire & terminations/terminals & crimps",
    "fasteners",
    "fasteners/anchors",
    "fasteners/anchors/drywall anchors",
    "fasteners/anchors/masonry anchors",
    "fasteners/hooks & hangers",
    "fasteners/machine screws & bolts",
    "fasteners/machine screws & bolts/button head",
    "fasteners/machine screws & bolts/carriage bolts",
    "fasteners/machine screws & bolts/flat head & countersunk",
    "fasteners/machine screws & bolts/hex head",
    "fasteners/machine screws & bolts/pan & round head",
    "fasteners/machine screws & bolts/set screws",
    "fasteners/machine screws & bolts/socket head cap",
    "fasteners/machine screws & bolts/thumb screws",
    "fasteners/nails & staples",
    "fasteners/nails & staples/collated & air fasteners",
    "fasteners/nails & staples/nails",
    "fasteners/nails & staples/staples & tacks",
    "fasteners/nuts",
    "fasteners/pins & clips",
    "fasteners/rivets",
    "fasteners/self-tapping screws",
    "fasteners/standoffs & spacers",
    "fasteners/structural connectors",
    "fasteners/threaded inserts",
    "fasteners/washers",
    "fasteners/wood & construction screws",
    "fasteners/wood & construction screws/construction screws",
    "fasteners/wood & construction screws/deck screws",
    "fasteners/wood & construction screws/drywall screws",
    "fasteners/wood & construction screws/lag screws",
    "fasteners/wood & construction screws/structural screws",
    "fasteners/wood & construction screws/trim & cabinet screws",
    "fasteners/wood & construction screws/wood screws",
)

# The specification keys the record expects, across every branch family.  A key is
# added here when the record adds it, never while filing a product.
DEFAULT_SPECIFICATION_KEYS: Tuple[str, ...] = (
    "Amperage",
    "Capacity",
    "Category",
    "Chemistry",
    "Chipset",
    "Coil Voltage",
    "Color",
    "Conductors",
    "Connectivity",
    "Contact Rating",
    "Drive",
    "Ends",
    "Flash",
    "Gauge",
    "Gender",
    "Input Voltage",
    "Interface",
    "Length",
    "Material",
    "Output Current",
    "Output Voltage",
    "PSRAM",
    "Package",
    "Pitch",
    "Poles",
    "Positions",
    "Range",
    "Series",
    "Shaft",
    "Shielding",
    "Size",
    "Substrate",
    "Supply Voltage",
    "Thread",
    "Tolerance",
    "Trade Size",
    "Type",
    "Value",
    "Voltage",
)


class TaxonomyFileError(Exception):
    """A taxonomy override file was named but could not be used.

    Deliberately fatal rather than a fallback.  Falling back to the built-in
    defaults would silently file another shop's products under this shop's
    branches, and the operator who set the variable would have no way to tell.
    """


def _load_json_list(path: str, variable: str) -> List[str]:
    """Read a JSON array of strings, or say precisely what is wrong with it."""
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            content = json.load(handle)
    except OSError as exc:
        raise TaxonomyFileError(
            f"{variable} points at {path!r}, which cannot be read: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise TaxonomyFileError(
            f"{variable} points at {path!r}, which is not valid JSON: {exc}"
        ) from exc

    if not isinstance(content, list):
        raise TaxonomyFileError(
            f"{variable} points at {path!r}, which must contain a JSON array of "
            f"strings; found {type(content).__name__}"
        )

    for entry in content:
        if not isinstance(entry, str):
            raise TaxonomyFileError(
                f"{variable} points at {path!r}, whose entries must all be strings; "
                f"found {type(entry).__name__} ({entry!r})"
            )

    return content


def _with_ancestors(paths: List[str]) -> List[str]:
    """Add every intermediate parent of every path.

    An override file lists the branches its author cares about.  Parents are
    filing targets in their own right, and ``category_tree`` renders one row per
    distinct path -- so without them a tree indents under rows that do not exist.
    """
    filled = set()
    for path in paths:
        segments = path.split(category_utils.SEPARATOR)
        for depth in range(1, len(segments) + 1):
            filled.add(category_utils.SEPARATOR.join(segments[:depth]))
    return sorted(filled)


def category_paths(source: Optional[str] = None) -> Tuple[str, ...]:
    """The category branches this deployment offers.

    Args:
        source: A file to read instead of consulting the environment. For tests
            and for ``create_app``'s startup check; ordinary callers pass nothing.

    Returns:
        The canonical branches, parents included, sorted. The built-in defaults
        when no override is configured.

    Raises:
        TaxonomyFileError: If a file is named and cannot be read, parsed, or
            validated. Never falls back to the defaults.
    """
    path = source or os.environ.get(CATEGORY_TAXONOMY_ENV)
    if not path:
        return DEFAULT_CATEGORY_PATHS

    raw = _load_json_list(path, CATEGORY_TAXONOMY_ENV)

    canonical_paths = []
    for entry in raw:
        canonical = category_utils.canonical(entry)
        if canonical is None:
            raise TaxonomyFileError(
                f"{CATEGORY_TAXONOMY_ENV} points at {path!r}, which contains an "
                f"entry that is not a category: {entry!r}"
            )
        if len(canonical) > MAX_CATEGORY_PATH_LENGTH:
            raise TaxonomyFileError(
                f"{CATEGORY_TAXONOMY_ENV} points at {path!r}, which contains a path "
                f"longer than {MAX_CATEGORY_PATH_LENGTH} characters: {canonical!r}"
            )
        canonical_paths.append(canonical)

    # No depth limit. Three levels was this shop's decision, recorded in
    # docs/category-taxonomy.md; the application has never required it, and
    # imposing it here would push one workshop's judgement onto every other.
    return tuple(_with_ancestors(canonical_paths))


def specification_keys(source: Optional[str] = None) -> Tuple[str, ...]:
    """The specification key names this deployment offers.

    Args:
        source: A file to read instead of consulting the environment.

    Returns:
        The keys, trimmed and sorted, one spelling per case-folded name. The
        built-in defaults when no override is configured.

    Raises:
        TaxonomyFileError: If a file is named and cannot be read, parsed, or
            validated.
    """
    path = source or os.environ.get(SPECIFICATION_KEYS_ENV)
    if not path:
        return DEFAULT_SPECIFICATION_KEYS

    raw = _load_json_list(path, SPECIFICATION_KEYS_ENV)

    kept = {}
    for entry in raw:
        name = entry.strip()
        if not name:
            raise TaxonomyFileError(
                f"{SPECIFICATION_KEYS_ENV} points at {path!r}, which contains a "
                f"blank key"
            )
        if len(name) > MAX_SPECIFICATION_NAME_LENGTH:
            raise TaxonomyFileError(
                f"{SPECIFICATION_KEYS_ENV} points at {path!r}, which contains a key "
                f"longer than {MAX_SPECIFICATION_NAME_LENGTH} characters: {name!r}"
            )
        # One spelling per folded name, matching how the datalist dedupes them.
        kept.setdefault(name.lower(), name)

    return tuple(sorted(kept.values()))
