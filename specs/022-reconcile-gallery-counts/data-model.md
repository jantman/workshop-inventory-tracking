# Data Model: Gallery Image Counts

**Feature**: [spec.md](spec.md) | **Date**: 2026-08-20

## There is no schema change, and there must not be one

No table, column, index or constraint changes. **No Alembic revision is created by this feature.**

This is stated first and plainly because the shape of the finding invites the wrong reflex. The
defect is that seven photographs arrive as fourteen attachments; the obvious-looking remedies —
record which rendition a `Photo` came from, or which gallery entry it belongs to, so duplicates can
be recognised later — would each add a column. All of them are refused. The listing's own data
already says which addresses are one photograph, and the reading is where that knowledge belongs. A
column would be a place to store the answer to a question that has already been answered a moment
earlier, one layer up, and would then have to be maintained forever.

Constitution Principle I, and Principle V's "every schema change ships as an Alembic revision" is
not engaged because there is no schema change to ship.

## The entities this feature actually touches

None of these is a persisted type. They exist inside one capture and are gone.

### Gallery entry

One photograph, as the listing's own data describes it. Read out of the array in
`colorImages.initial`.

| Field | Meaning | Observed on the six probed listings |
|---|---|---|
| `hiRes` | The full-resolution address, tokened | Present on 38 of 39 entries; `null` on 4 of them (2 on `B099F4X4Q9`, 2 on `B09GM8FB3X`) |
| `large` | A smaller rendition of **the same photograph**, under a different asset id | Present on every entry |
| `thumb` | The strip rendition | Present on every entry; never captured |
| `variant` | `MAIN`, `PT01`, `PT02` … — position in the gallery, not a product variation | Sequential on every listing probed |

**One entry yields exactly one stored image** (spec FR-021). `hiRes` when it is there, `large` when
it is not. `thumb` never. The relationship is the whole model: an entry is a photograph, and the
several addresses on it are renditions of that one photograph, not separate pictures.

### Gallery reading

The list of addresses one capture derives from one listing. Ordered as the entries are ordered,
deduplicated by address, each with its transform token stripped (007 FR-004). Its length is the
number under dispute in issue #95 and is contracted in
[contracts/gallery-reading.md](contracts/gallery-reading.md).

Carried in the capture payload's `images` key, which is a flat list of strings. **The payload
contract does not change** — the server receives the same shape it receives today, and still never
learns which address came from the gallery and which from a description block. That is deliberate
(007 FR-019) and this feature relies on it: nothing server-side needs to know that this changed.

### Recorded expectation

Not code and not data — a figure in a checklist that a human compares against. Carries a value, a
provenance and a date, and ages. #80 §1b holds six of them for gallery counts plus one for the
FR-004 original. This feature's real product is that these say what they mean:

| Kind | What it must state | Why it went wrong |
|---|---|---|
| Gallery count | The number of entries the captured item's gallery data names | #57 recorded a whole-document `hiRes` sweep instead, which counts the whole variation family |
| Thumbnail count | What the strip displays | Correct as recorded; the mistake was the inference drawn from it |
| FR-004 original | Filename stem, dimensions, byte size, and the tokened figures beside them | Correct and unchanged; "a stored original" is ambiguous while duplicates exist |

## What is stored, and what changes about it

`Photo` rows and `ProductAttachment` rows, both unchanged in shape. What changes is **how many get
written by a capture** — for the six probed listings, from 14/12/6/14/14/14 down to 7/7/3/7/8/7.

Rows already written keep their `sha256_hash`, and the 500-pixel copies remain in the database until
the operator removes them. Nothing migrates them. There is no backfill, no cleanup job, and no
"repair" command:

* Which stored image is a low-resolution twin cannot be decided from the row — it needs the listing
  that produced it, and that listing may have changed since.
* Deleting attachments on the strength of a guess is exactly the kind of irreversible data loss
  Principle I says simplicity never justifies.
* The operator already has the tool (#96 bulk photo deletion, PR #102), the copies are visually
  obvious, and they sort next to their originals.

[quickstart.md](quickstart.md) says how to recognise them. That is the whole of the migration story.
