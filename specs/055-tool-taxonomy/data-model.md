# Data Model: 055 Tool Taxonomy

No schema change. The feature changes two constants in `app/utils/catalog_taxonomy.py`; their
invariants are unchanged from 025.

| Constant | Before | After | Invariants (enforced by `tests/unit/test_catalog_taxonomy.py`) |
|---|---|---|---|
| `DEFAULT_CATEGORY_PATHS` | 142 paths, 3 roots | 266 paths, 6 roots | canonical (lowercase), ≤3 segments, ≤512 chars, sorted, unique, every parent present, ≤20 children per parent, equal to the record's branch set |
| `DEFAULT_SPECIFICATION_KEYS` | 39 keys | 74 keys | trimmed, non-blank, ≤100 chars, unique case-folded, sorted, equal to the record's registry key set |

**Added paths**: every branch in the spec's `tools`, `adhesives & chemicals` and `mechanical`
tables, the three roots themselves, and the six `fasteners/pins & clips/*` leaves.

**Added keys**: `Abrasive`, `Angle`, `Arbor`, `Bore`, `Chamfer`, `Classification`, `Coating`,
`Collet`, `Cross Section`, `Cure Time`, `Cut Depth`, `Durometer`, `Flute Type`, `Flutes`,
`Grade`, `Grit`, `ID`, `Insert`, `Length Series`, `Mount`, `OD`, `Pilot`, `Point Angle`,
`Process`, `Rate`, `Seal`, `Shank`, `Strength`, `TPI`, `Taper`, `Temperature`, `Viscosity`,
`Volume`, `Width`, `Wire Diameter`.

**Existing products**: untouched. A product at `fasteners/pins & clips` stays valid: that path
is now a parent, and parents remain filing targets.
