# Contract: `CatalogService` additions

New methods on `app/catalog_service.py`. They follow the module's existing conventions: type hints on the signature, a docstring with Args/Returns/Raises, all work inside `self._session()`, and failures raised as the project's own exceptions (`app/exceptions.py`) rather than any new error type.

Semantics, validation order and result shapes are specified in [`../data-model.md`](../data-model.md); this document is the interface.

---

## `rename_category(old_path: str, new_path: str) -> Dict[str, Any]`

Rename a category, carrying its sub-categories and every product beneath them.

**Arguments**

| Name | Meaning |
|---|---|
| `old_path` | The category to rename, as displayed. Canonicalized before use. |
| `new_path` | What it becomes. Canonicalized before use. |

**Returns**

```python
{'from': str, 'to': str, 'products': int, 'categories': int}
```

`from` and `to` are the canonical forms actually applied. `products` is the number of rows rewritten; `categories` is the number of distinct paths rewritten, which is the renamed level plus each descendant path.

**Raises**

`ValidationError` for every refusal, with `field='category_path'` and a message naming the specific obstruction:

| Situation | Message names |
|---|---|
| Either path canonicalizes to `None` | which side was blank |
| The two canonicalize to the same string | that normalization already treats them as one category |
| The target sits inside the source | both paths |
| A category outside the source subtree already sits at or under the target | the colliding path |
| A rewritten path would exceed 512 characters | the offending path |
| No product carries the source | the source path |

Nothing is written unless every check passes. A raise rolls the transaction back.

**Guarantees**

- Every product at or beneath `old_path` ends at the corresponding position beneath `new_path`; relative structure below the renamed level is preserved.
- A sibling category that merely shares a prefix (`elctronics-surplus` under a rename of `elctronics`) is untouched.
- All-or-nothing: a refused rename leaves every product byte-identical.

---

## `rename_tag(old_name: str, new_name: str) -> Dict[str, Any]`

Rename a tag, merging into the target when the target already exists.

**Arguments**

| Name | Meaning |
|---|---|
| `old_name` | The tag to rename. Trimmed and lowercased before use, as `_attach_tag` already does. |
| `new_name` | What it becomes, or the tag to merge into. Same normalization. |

**Returns**

```python
{'from': str, 'to': str, 'merged': bool, 'products': int}
```

`merged` is `True` when the target name was already in use. `products` counts the products that gained the survivor because of this call — for a merge, that excludes products that already carried both.

**Raises**

`ValidationError` with `field='tag'` when either name normalizes to empty, when the two normalize to the same string, when the target exceeds 64 characters, or when no tag with the source name exists.

**Guarantees**

- After a plain rename, no tag with the old name exists and every product that carried it carries the new name.
- After a merge, exactly one tag remains and it carries the union of both tags' products, each association exactly once.
- A merge's outcome does not depend on which of the two names was the source.
- All-or-nothing.

---

## `tag_list_with_counts() -> List[Dict[str, Any]]`

Every tag with how many products carry it, for the tags page.

**Returns**

```python
[{'id': int, 'name': str, 'count': int}, ...]
```

Alphabetical by `name`. Tags carried by no product are included with `count: 0` — an orphaned tag is debris the page exists to reveal, and `Tag`'s own docstring already records that they are not collected on a schedule.

**Raises**: nothing. An empty catalogue returns `[]`.

Mirrors `category_tree()`, which is the equivalent for the categories page.

---

## Changes to existing methods

`create_product()` gains an optional `sub_location: Optional[str] = None` parameter, validated and stored the same way `location` already is, placed after `location` in the signature. Every existing call site passes by keyword (verified across `app/` and `tests/`), so none breaks.

`update_product()` takes `**fields` against an explicit `editable` set (`app/catalog_service.py:462-466`) — a field absent from that set raises rather than being silently ignored. `sub_location` must be added to the set and given its assignment branch, or editing a product will start refusing the form that now submits it.

`_form_product_fields()` in `app/product/routes.py:43` is the single definition of what the add and edit forms submit; `sub_location` goes there too.

`Product.to_dict()` gains a `sub_location` entry alongside `location`.
