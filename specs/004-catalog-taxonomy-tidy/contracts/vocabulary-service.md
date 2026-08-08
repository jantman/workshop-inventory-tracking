# Contract: `VocabularyService`

New module `app/services/vocabulary.py`. It is where `FIELD_SUGGESTION_COLUMNS` and `get_field_value_suggestions` move to from `MariaDBInventoryService`, widened to read the catalogue's columns as well as the metal stock's.

This is a relocation, not a rewrite. The ranking, LIKE-escaping and case-insensitive deduplication behaviour that `app/mariadb_inventory_service.py:776-908` implements today is preserved exactly; what changes is which columns it reads.

---

## Construction

```python
class VocabularyService:
    def __init__(self, storage: MariaDBStorage = None) -> None: ...
```

Follows the `CatalogService` precedent (`app/catalog_service.py:52-66`): borrow `storage.engine`, build a `sessionmaker` from it, fall back to building an engine from `Config` when no storage is supplied. Routes obtain one through their blueprint's existing `_get_storage_backend()` helper.

---

## `suggest(field, query=None, limit=10, location=None) -> List[str]`

```python
def suggest(
    self,
    field: str,
    query: Optional[str] = None,
    limit: int = 10,
    location: Optional[str] = None,
) -> List[str]: ...
```

Distinct existing values for a whitelisted field, drawn from every table that records one.

**Arguments** — unchanged in meaning from the method it replaces.

| Name | Meaning |
|---|---|
| `field` | One of the whitelisted names below. Anything else raises `ValueError`. |
| `query` | Optional case-insensitive substring filter. `None` or empty returns the first `limit` values alphabetically. |
| `limit` | Clamped to `[1, 50]`. A non-integer falls back to 10, as today. |
| `location` | Only meaningful for `sub_location`. Restricts results to sub-locations recorded under that location, case-insensitively, applied per source against that source's own location column. |

**Sources**

| `field` | Columns read |
|---|---|
| `location` | `inventory_items.location`, `products.location` |
| `sub_location` | `inventory_items.sub_location`, `products.sub_location` |
| `vendor` | `inventory_items.vendor`, `purchases.vendor` |
| `thread_size` | `inventory_items.thread_size` |
| `purchase_location` | `inventory_items.purchase_location` |

The last two stay single-source because nothing in the catalogue records either. Adding a source later is a one-line change to the mapping.

**Returns**: a list of at most `limit` distinct value strings.

**Ordering** — unchanged. With a `query`: exact match first, then starts-with, then contains, each tier alphabetized case-insensitively. Without one: alphabetized. When results come from more than one source they are merged and re-ranked as a whole, so a better match from either source outranks a worse one from the other.

**Deduplication**: case-insensitive, across sources. `Amazon` recorded on a metal stock item and `amazon` recorded on a purchase yield one suggestion, not two. The first-seen spelling under the established ordering is the one returned.

**Exclusions**: `NULL` values and values that are empty after trimming, from every source.

**Inclusions worth stating**: inactive `inventory_items` history rows contribute, exactly as they do today (FR-019). A name is not withdrawn from the vocabulary because the item carrying it was deactivated.

**Raises**

- `ValueError` when `field` is not whitelisted. The route already turns this into HTTP 400.
- Backend failures propagate. They are deliberately not swallowed — the existing code carries a comment saying so, because swallowing would turn a broken backend into an HTTP 200 with an empty list and break the endpoint's documented status contract. Preserve that comment and that behaviour.

**Escaping**: `%`, `_` and `\` in `query` are escaped before being used in a `LIKE`, so a query of `10%` matches the literal string. This is correctness, not defence — see the constitution's threat model.

---

## What is removed

`MariaDBInventoryService.FIELD_SUGGESTION_COLUMNS` and `MariaDBInventoryService.get_field_value_suggestions` are deleted, not left as delegating shims. A shim would be a second name for one behaviour with no caller needing it.

Their unit tests move from `tests/unit/test_mariadb_inventory_service.py` to `tests/unit/test_vocabulary.py` — **moved, not rewritten**, so the existing coverage of ranking, escaping, clamping and case-insensitive dedup survives the relocation intact. New tests are added on top for the union cases:

- a value present only in the catalogue is offered
- a value present only in metal stock is offered
- a value present in both, differing only in case, is offered once
- `sub_location` scoped by `location=` filters each source against its own location column
- `thread_size` and `purchase_location` still read metal stock only
