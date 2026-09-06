# Phase 1 Data Model: A Vendor's Category Is Not the Shop's Category

**There is no schema change.** This document exists to say precisely that, and to record why the
one field involved is shaped the way it is — because that shape is the reason the bug is a bug.

## Product.category_path

| Property | Value | Changed by this feature |
|---|---|---|
| Column | `Product.category_path` (`app/database.py`) | No |
| Type | `String(512)`, `nullable=True`, indexed | No |
| Vocabulary | Free-form. Slash-separated, any depth. No lookup table, no foreign key, no enumeration | No |
| Normalization | Lowercased and separator-joined with empty segments dropped, on write | No |
| Validation | Length only. Over 512 characters is a rejection, not a truncation | No |
| Blank | Permitted and ordinary. Means "not filed", never "unknown" or "error" | No |

**What changes is who is allowed to write it**: the operator, and no vendor.

## The category tree is derived, not stored

The browsable hierarchy on `/products/categories` has no rows of its own. It is computed from the
distinct `category_path` values in use across products. Two consequences, and they are the whole
argument of the feature:

1. **Storing a value creates a branch.** There is no separate step at which a category is
   "created", so there is no step at which a vendor's value could be reviewed before it becomes
   part of the taxonomy. Writing the field *is* extending the tree.
2. **Un-storing a value removes a branch.** Nothing has to be cleaned up for a category to
   disappear; when the last product carrying it stops carrying it, it is gone. This is why FR-008
   can decline a migration without leaving debris: a value already recorded stays until the
   operator renames or clears it, through tooling that already exists.

## The vendor's part detail

`DigiKeyPart.category_path` (`app/models.py`) — read from the vendor's payload, defaulting to `''`.

| Property | Changed by this feature |
|---|---|
| Read from the vendor's response | No. The client keeps parsing it; its tests keep asserting it |
| Displayed to the operator as the vendor's own statement | No. It stays in "What DigiKey says" |
| Used as the value written to `Product.category_path` | **Yes — this stops** |
| Pre-loaded into a form field that will be recorded | **Yes — this stops** |

The distinction between the third and fourth rows and the first two is the feature in one sentence:
the value is still read and still shown; it is no longer asserted.

## State transitions

None. Products have no category lifecycle: the field is set, changed or cleared by the operator at
any time, and no transition is gated on any other state. Nothing in this feature adds one.
