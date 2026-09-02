# Contract: The Application Clock

**Feature**: `specs/037-fix-timestamp-clock-basis/` | **Plan**: [../plan.md](../plan.md)

This feature adds no external interface and changes none. There are two contracts to record: the
internal surface everything now goes through, and the JSON shape that must stay exactly as it is.

---

## 1. `app/utils/clock.py` — internal

The single answer to "what time is it". Two functions, both returning a **naive** `datetime`.

```python
def utc_now() -> datetime:
    """The current instant in UTC, naive, for recording an event."""

def local_now() -> datetime:
    """The current instant on the operator's wall clock, naive, for defaulting a day."""
```

### `utc_now()`

- **Returns**: `datetime` with `tzinfo is None`, carrying UTC wall-clock fields.
- **Use for**: every persisted recorded timestamp (see
  [../data-model.md](../data-model.md)), and both ends of every age subtraction.
- **Do not use for**: any value the operator states or would have typed as a day.

Naive, not aware, and not `datetime.utcnow()`: the column cannot store an offset (R2), and
`utcnow()` is deprecated on Python 3.13. The implementation takes an aware UTC reading and drops
the offset, which is the only spelling that is both correct and non-deprecated.

### `local_now()`

- **Returns**: `datetime` with `tzinfo is None`, carrying the host's local wall-clock fields —
  identical to what `datetime.now()` returns today.
- **Use for**: defaulting a calendar day the operator did not supply. Five call sites, all
  enumerated in [../data-model.md](../data-model.md).
- **Do not use for**: anything that will be compared against a recorded timestamp.

It exists to be *named*. Its behavior is the status quo; its value is that after this feature a
bare `datetime.now()` in a service reads as a mistake, and the five deliberate exceptions say so
at the call site rather than in a comment a sweep can miss (R5).

### Rules this surface implies

1. No recorded timestamp is produced anywhere but `utc_now()` — not by a column default, not by
   the database server, not by `datetime.now()` in a service.
2. Neither function takes an argument, and neither reads configuration. There is no timezone
   setting, no injectable clock, and no freeze hook. Tests patch the module attribute.
3. Both return naive values. Nothing in `app/` writes an aware datetime to a column.

---

## 2. JSON timestamps — unchanged, and that is the contract

`to_dict()` on the ORM models and the `/api/...` responses built from them keep **exactly** the
shape they have today (FR-010). This is a data-correctness fix, not an API change.

| Property | Before | After |
|---|---|---|
| Field names | `date_added`, `last_modified`, `created_at`, `updated_at`, `quantity_updated_at`, `stock_status_updated_at`, `order_date`, `received_date` | identical |
| Which fields are present | as today, `None` where the column is null | identical |
| Text format | `datetime.isoformat()` — naive, no offset, no `Z` | identical |
| Values | mixed bases; two columns on one row can be four hours apart | one basis; consistent and comparable |

**No `Z` suffix and no `+00:00` is added.** Marking the values as UTC would be more self-
describing and it is deliberately not done: the only consumer is this application, a format change
would be visible for no observed need, and `app/models.py:_naive` documents what this codebase
paid the last time an offset appeared where one was not expected (PR #128). Recorded values
being on a single basis is the fix; announcing which basis is a separate change nobody has asked
for.

### Export round trip

`app/export_schemas.py:140-141` writes `date_added` and `last_modified` through
`formatter.format_datetime`, and `app/database.py:558-568` parses them back with
`fromisoformat(... .replace('Z', '+00:00'))`. A value exported and re-imported must denote the
same instant it did before the trip (FR-011). Since neither the written text nor the parser
changes, and both ends are now on one basis, the round trip is a no-op — which is the property to
confirm, not a behavior to build.

---

## 3. `app/api_client.py`

Untouched. It depends only on the standard library plus `requests`, must not import from `app`,
and its `__all__` is a contract. Nothing in this feature adds an import to it, changes a name in
it, or alters a value it returns — the timestamps it passes through are the same strings in the
same format.
