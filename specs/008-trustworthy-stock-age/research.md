# Phase 0 Research: Trustworthy Stock Age

Everything here is a decision taken with its alternatives, or a fact about the existing code that changed what the plan says. There were no unknowns in the Technical Context to resolve — the stack, storage and test strategy are all fixed by the constitution — so this document is entirely about *which* small change, not *whether* one is possible.

## The write surface is four functions, and that is the whole safety argument

SC-003 says the only things that reset a count's age are an operator entering a count and an operator adjusting one at the shelf. That is a universal claim, and universal claims are usually expensive to verify. Here it is cheap, because the places that write these fields are enumerable:

| Writer | Touches | After this feature |
|---|---|---|
| `CatalogService.create_product` (`catalog_service.py:167`) | `quantity_updated_at` when a quantity is supplied | Unchanged — creating a product *with* a count is the operator entering one |
| `CatalogService.set_quantity` (`:377`, `:382`) | `quantity_updated_at`, set or cleared | Unchanged — this is both the typed count and the +/- buttons (`product-stock.js` calls the same endpoint) |
| `CatalogService.set_stock_status` (`:421`) | `stock_status` | Gains the date, set and cleared with the flag |
| `CatalogService.receive_purchase` (`:1319`, `:1328`) | `quantity`, `quantity_updated_at`, `stock_status` | Loses the `quantity_updated_at` write; clears the flag's date with the flag |

`update_product` cannot reach either field: it validates `fields` against an explicit `editable` set and raises `ValidationError` for anything else (`catalog_service.py:563-573`). So the product edit form, which is the one place an operator might expect to be able to type a count, cannot silently restamp an age. Nothing else in `app/` assigns `quantity_updated_at` or `stock_status`.

**Consequence for the plan:** FR-008 is a deletion, not a redesign. There is no "audit every path" task, because the audit is the table above.

## One age per count, not two

**Decision**: a count carries exactly one date, meaning the last time an operator counted it. A receipt changes the number and leaves the date alone. (FR-015.)

**Rationale**: the alternative — `quantity_counted_at` beside `quantity_changed_at`, rendered as "counted 3 months ago, adjusted yesterday" — buys one line of display and costs a permanent rule. Every future write of a count would have to decide which of the two dates it moves, and getting that wrong reintroduces exactly the bug this feature removes, only harder to see because now there are two dates to disbelieve instead of one. The information it would surface is not lost: the product's purchases already record what arrived, when, from whom and how many, and that list is on the same page.

**Alternatives considered**:

- *Two timestamps.* Rejected above. Its real appeal is that it makes the number self-explaining, and the honest answer is that the purchase list already does that better.
- *Receiving stops touching the count entirely*, which was the archived plan's position and is the third reading of issue #59. Rejected: a count that ignores a delivery is knowingly wrong from the moment the box is opened until the operator next counts, which is a worse trade than a correct number whose age is honest about who last verified it. The spec records this in Assumptions so the reasoning survives.
- *Show the count as provisional* (an asterisk, an italic, a "since last count" note) when a receipt has moved it since it was counted. Rejected as the two-timestamp option wearing a hat: it needs the same second date to know when to show itself.

## No CHECK constraint pairing the flag with its date

**Decision**: the invariant "no flag means no flag date" is enforced in `set_stock_status` and `receive_purchase` and covered by unit tests, not by a database constraint.

**Rationale**: the first draft of this plan added `CHECK (stock_status IS NOT NULL OR stock_status_updated_at IS NULL)`, on the grounds that a stale date surviving a cleared flag is precisely the class of lie this feature exists to remove, and that `products` already carries three CHECK constraints in that spirit. It was dropped because of the asymmetry it would create: the identical invariant for `quantity` / `quantity_updated_at` has been enforced in code alone since feature 001, and adding a constraint for the new pair and not the old one leaves the table saying that one of two matching rules is important. The two ways out — constrain both, or constrain neither — are a migration touching an existing column for no observed problem, or Principle I. Principle I wins.

Note that the constraint could not have been symmetric in any case: FR-005 requires a flag with *no* date to be a legal row, because that is every row that predates this feature.

## Nothing is backfilled

**Decision**: the migration adds the column and writes nothing into it. Products already flagged read as an unknown age until they are flagged again.

**Rationale**: `products.last_modified` is the only candidate and it is not evidence. It moves when a description is corrected, when a specification is added, when a receipt clears an unrelated field — none of which is somebody looking at a shelf. Backfilling from it would reproduce inside the flag the exact error being removed from the count, and it would be worse there, because a fabricated date is indistinguishable from a real one afterwards.

**Consequence**: on the operator's live database, every currently flagged product will read "Flagged low at an unknown time" after the upgrade. That is correct and it will look like a bug. It is called out in `quickstart.md`, in the user manual change, and in the plan.

## One filter parameter, not a second filter

**Decision**: `relative_age(age, unknown='never counted')` — the existing filter gains one optional keyword, and the flag templates pass `'at an unknown time'`.

**Rationale**: the filter's `None` branch returns the string `'never counted'` (`app/product/routes.py:734-735`), which is right for a count and wrong for a flag — a flag with no date was certainly set, its date just was not recorded. The three ways to get the right words were a second filter (`flag_age`), a wrapper, or a parameter. A second filter duplicates twenty lines of date arithmetic to change one string. The parameter changes one line, leaves all four existing call sites reading exactly as they do today, and keeps FR-012 true by construction: a flag and a count on the same screen are rendered by the same code, so they cannot drift into different vocabularies.

## The feature ships no JavaScript

**Fact that changed the plan.** `product-stock.js:76-79` handles every successful PATCH with `window.location.reload()`, with a comment saying why: "the age line and the badge both change", so re-rendering from the server was already chosen over patching the DOM in two places. That decision, made for the count's age, pays for the flag's age for free. There is no client-side render of stock state anywhere, so:

- no JS file is touched;
- the new lines are ordinary Jinja;
- and the E2E tests are asserting against server-rendered HTML, which means the "never snapshot a JavaScript-rendered region" hazard in `CLAUDE.md` does not apply to the new assertions. It still applies to the existing `reorder_rows()` helper, which is fine as written for the same reason.

## Re-asserting a flag is currently a silent no-op

**Fact that made FR-002 worth stating.** `set_stock_status` assigns `product.stock_status = value` and nothing else. When the value equals what is already stored, SQLAlchemy detects no change and emits no `UPDATE` — so today, pressing **Low** on a product already flagged low does nothing at all, and the page reloads to the identical state.

FR-002 makes that press meaningful: the assignment of a fresh timestamp is a real change, so the `UPDATE` happens and the age resets. This is not incidental. Re-affirming a flag is the operator saying "I have just looked and it is still low", which is the only way, short of clearing and re-setting, to renew evidence on a product that has no count.

## How a test backdates a timestamp

**Problem**: every path that writes an age writes `datetime.now()`. A test that needs "counted three months ago" cannot get there through the UI or the service.

**Decision**: write the field directly through a session, in the test.

- **Unit** (`tests/unit/test_stock_status.py`): `CatalogService` exposes `self.Session`, a `sessionmaker` bound to the storage engine. The test opens one, sets the field, commits, and then exercises the service. The file already reaches into the model for property tests (`:105-109` mutates `quantity_updated_at` on a detached object), so this is the same move one step deeper.
- **E2E** (`tests/e2e/test_stock_age.py`): `sessionmaker(bind=live_server.engine)` is established practice in this suite — `test_toggle_item_status.py`, `test_edit_item_deactivation.py`, `test_move_items.py` and four others all do it — and `CatalogService(live_server.storage)` is used directly by `test_tag_rename.py:184`. Seeding this way is also what `CLAUDE.md` asks for: direct seeding over driving forms, because the form is not what is under test.

**Alternative rejected**: freezing or patching the clock. The E2E server runs in a thread in the same process, so monkeypatching `datetime` would in fact reach it — and would reach every other request in flight at the same time. A direct write to one column is smaller, local, and cannot affect anything it did not name.

## What this feature is not

- **Not a staleness policy** (FR-013). No threshold, no warning colour, no re-sort, no notification. The existing filter's docstring already refused this once — "a staleness *flag* would need a policy that nobody has measured" — and adding the flag's age does not license inventing the policy now.
- **Not a change to who appears on the reorder list** (FR-014). Membership is derived from `is_effectively_low`, which this feature does not touch. A two-year-old flag still means "low", because nothing has been told otherwise.
- **Not a history of flag transitions.** One operator, one current fact, one column. See the plan.
- **Not a change to receiving's effect on the flag.** Receiving still clears it (feature 001's FR-029). Only the date now travels with it.

## The risk that is not mitigated

An operator who never re-affirms a flag gets an ever-growing age on a product that may genuinely still be low, and nothing prompts them. That is the intended behaviour — FR-013 forbids the prompt — but it means the flag's age is only as useful as the operator's habit of pressing the button again when they check. There is no way to distinguish "flagged two years ago and still low" from "flagged two years ago and forgotten", and this feature does not try to; it makes the ambiguity visible instead of hiding it, which is the whole of what issue #59 asked for.
