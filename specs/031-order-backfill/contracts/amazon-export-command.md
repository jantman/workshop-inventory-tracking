# Contract: Amazon Export Reduction Command

**Requirements**: FR-009 – FR-017 | **Research**: research.md §7, §8

Reads a file. Writes nothing to the catalog, opens no database, makes no network call (FR-016).

## CLI (`manage.py`)

```text
python manage.py orders amazon-urls <path-to-edited-export.csv>
```

One argument, no options. The operator names the file, so the command does not need to know what
Amazon called it this year or how the zip is laid out (research.md §7).

**Output**: one address per line on stdout, then a summary on stderr so the addresses can be piped
without the summary coming with them.

```text
https://www.amazon.com/gp/css/order-details?orderID=111-2223334-5556667
...
Read 47 rows; 12 distinct orders.
3 row(s) carried an order id this could not use — digital orders and blanks are expected here.
2 order(s) carry a status other than the usual one. Nothing was dropped; check them before capturing.
```

## Columns

| Column | Required | Used for |
|---|---|---|
| `Order ID` | **yes** | The identifier, de-duplicated |
| `Website` | **yes** | The host the address is built against, per row, so a mixed-marketplace export yields live links |
| `Order Status` | no | Counted for the summary only |

**Amended during implementation.** The contract first said the command would count orders with a
status "other than the ordinary one". There is no published list of Amazon's status values, so
"ordinary" would have been a guess baked into code. It reports **each status and how many orders
carry it**, and only when more than one is present — honest, and it needs to know nothing about
what Amazon calls things.

Two required columns, not twenty-seven. Amazon has renamed this export at least once; requiring the
minimum is what keeps their next change from being this feature's problem (research.md §7).

**A missing required column is a refusal that names it** (FR-014):

```text
This does not look like an Amazon order-history export: no "Order ID" column.
Columns found: Website, Order Date, ASIN, Quantity, Product Name
```

Exit non-zero, emit no addresses. A partial list is worse than none, because it is
indistinguishable from a successful run.

## Rules

| Rule | Requirement |
|---|---|
| Each order appears exactly once, in first-seen order | FR-012 |
| Only ids matching `\d{3}-\d{7}-\d{7}` are emitted; the rest are counted and reported | research.md §7 — this filters Amazon's `D01-` digital orders out for free |
| The address is `https://{website}/gp/css/order-details?orderID={id}` | The capture agent's own comment records that this legacy path 302s to the canonical one it runs on (`app/static/js/capture-agent.js:75`) |
| Rows read and distinct orders are always reported | FR-013 |
| Nothing is filtered on `Order Status` — each status and its count are reported when they differ | research.md §7. The operator's edit of the file is authoritative (FR-012); a filter would be a knob |
| A file edited down to its **header alone** is empty, not unrecognizable | Found in implementation: the columns cannot be seen from zero rows, so the caller passes `csv.DictReader.fieldnames` and the shape is still checked |
| **No monetary value is parsed at all** | Constitution III is not at risk because no price is read. Prices come from the order page at capture, as they always have |

## Module (`app/services/amazon_order_export.py`)

```python
def summarize(
    rows: Iterable[Mapping[str, str]],
    fieldnames: Optional[Sequence[str]] = None,
) -> AmazonExportSummary
```

`fieldnames` is the file's header row, which the rows cannot supply when the operator has deleted
all of them. The CLI passes `reader.fieldnames`; without it the first row's keys are used.

Pure. Takes what `csv.DictReader` yields, returns the value object in
[data-model.md](../data-model.md). The click callback opens the file, calls this, and prints —
the same thin-entry-point rule Constitution II applies to routes (research.md §8).

`csv` from the standard library. No new dependency.
