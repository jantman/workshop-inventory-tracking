# Contract: what the operator sees

Two templates and one Jinja filter. No JavaScript: `product-stock.js` already reloads the page after every successful PATCH, so both age lines are server-rendered like the count's age beside them.

---

## The filter: `relative_age(age, unknown='never counted')`

Registered in `app/product/routes.py` as an `app_template_filter`. One optional parameter is added; the positional behaviour and every existing call site are unchanged.

```python
@bp.app_template_filter('relative_age')
def relative_age(age, unknown: str = 'never counted') -> str:
```

| `age` | Renders |
|---|---|
| `None` | the `unknown` argument — `'never counted'` for a count, `'at an unknown time'` for a flag |
| negative, or under an hour | `just now` |
| under a day | `3 hours ago` |
| one day | `yesterday` |
| under 31 days | `9 days ago` |
| under a year | `8 months ago` |
| a year or more | `2 years ago` |

Every row but the first is shared between a count and a flag, which is FR-012 satisfied by construction rather than by discipline: two pieces of evidence on one screen cannot drift into different vocabularies if one function renders both.

**Why a parameter and not a second filter**: `'never counted'` is right for a count and wrong for a flag — a flag with no date was certainly set, its date simply was not recorded. See `research.md`.

---

## `product/detail.html` — the stock card

Under the three flag buttons, rendered only when a flag is set:

```jinja
{% if product.stock_status %}
<div class="text-muted small mt-2" id="flag-age">
    Flagged {{ product.stock_status }}
    {{ product.stock_status_age | relative_age('at an unknown time') }}
</div>
{% endif %}
```

Reads as *Flagged low 3 months ago*, *Flagged out just now*, *Flagged low at an unknown time*.

`id="flag-age"` is the E2E hook. The element is absent — not empty — when there is no flag, so a test asserting its absence is asserting something real.

The count's age line above it (`id="quantity-age"`) is unchanged in markup. Its *meaning* changes, because the writer that was not a person has stopped writing.

---

## `product/reorder.html` — the "Why" column

Under the existing `Flagged low` badge:

```jinja
{% if entry.is_manually_low %}
<span class="badge text-bg-secondary reason-manual">
    Flagged {{ product.stock_status }}
</span>
<div class="text-muted small flag-age">
    {{ product.stock_status_age | relative_age('at an unknown time') }}
</div>
{% endif %}
```

A class rather than an id, because the reorder list has many rows. Scoped by the row's `data-product-id` in tests.

This is the screen SC-004 is measured on: two flagged products, and the operator can tell which was flagged more recently without opening either.

## What does not change

- **Reorder list membership and ordering.** FR-013 and FR-014: no age is classified as stale, nothing is withheld, warned about, coloured differently or re-sorted. The age is text in the muted style the count's age already uses.
- **No new screen, no new control.** Both lines are read-only text next to controls that already exist.
- **No screenshots.** `tests/e2e/screenshot_config.yaml` covers the metal-stock screens; no committed image shows a product page. See the deviation note in `plan.md`.
