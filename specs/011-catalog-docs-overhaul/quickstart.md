# Quickstart: Validating the Catalog Documentation Overhaul

Every check below maps to a success criterion in [spec.md](./spec.md). Run from the
repository root with the virtualenv sourced.

```bash
source venv/bin/activate
```

Baselines captured 2026-08-10 at commit `0f9cdfd`, before any work:

| Baseline | Value | How obtained |
|---|---|---|
| Unit tests collected | **1216** | `python -m pytest tests/unit -q --collect-only \| tail -1` |
| E2E tests passing | **459** | recorded in commit `e930e8c` |
| Screenshots on disk | **12** | 1 `readme/` + 11 `user-manual/` |
| `docs/user-manual.md` | 1,817 lines, 14 `##` sections | |

---

## SC-002 — the catalog's capabilities are top-level sections

```bash
grep -n "^## " docs/user-manual.md
```

**Expect** 25 `##` sections, matching the list in [data-model.md](./data-model.md). No
`## Product Catalogue` and no `## Product Catalog` container section — the container is
dissolved, replaced by `## The Product Catalog` as an intro peer.

**Expect** the twelve catalog sections to appear contiguously, after `## Batch Operations`
and before `## Data Export`.

```bash
# Distributor Labels is the one catalog heading that stays nested
grep -n "^### Distributor Labels" docs/user-manual.md
```

## SC-004 — every anchor resolves

Extract the TOC's link targets and the document's actual anchors, and diff them:

```bash
python3 - <<'PY'
import re, pathlib
t = pathlib.Path('docs/user-manual.md').read_text()
links = set(re.findall(r'\]\(#([a-z0-9-]+)\)', t))
heads = {
    re.sub(r'[^a-z0-9 -]', '', h.lower()).replace(' ', '-')
    for h in re.findall(r'^#{2,3} (.+)$', t, re.M)
}
missing = sorted(links - heads)
print("broken anchors:", missing or "none")
print("TOC entries:", len(links), "| headings:", len(heads))
PY
```

**Expect** `broken anchors: none`.

Then confirm nothing outside the manual points at a catalog anchor (research.md Finding 1
says only the TOC did):

```bash
grep -rn "user-manual.md#" --exclude-dir=.git --exclude-dir=venv . || echo "no external anchor refs"
```

## SC-003 — no guidance was dropped

The rework moves and re-titles prose. This check confirms the *facts* survived. Each phrase
below is load-bearing guidance from the current catalog section; each must still be present:

```bash
for phrase in \
  "fails its check digit is refused" \
  "all zeros" \
  "scoped to their vendor" \
  "upgrade-insecure-requests" \
  "baked in when the page renders" \
  "Not tracked" \
  "None on hand" \
  "Flagged low at an unknown time" \
  "Renaming never merges two categories" \
  "Renaming onto a name already in use merges" \
  "no forwarding address" \
  "deactivated" \
  "Thread Size and Purchase Location are inventory-only" ; do
  printf '%-50s %s\n' "$phrase" "$(grep -qF "$phrase" docs/user-manual.md && echo present || echo '*** MISSING ***')"
done
```

**Expect** every line `present`. A `MISSING` means the rework dropped a fact FR-004 requires
kept — not that the wording changed, since these are the exact strings in today's text.

For the split described in data-model.md, confirm both halves landed:

```bash
# browse material moved into Categories and Tags
sed -n '/^## Categories and Tags/,/^## /p' docs/user-manual.md | grep -c "Products → Categories\|Products → Tags"
# search material stayed in Finding Products
sed -n '/^## Finding Products/,/^## /p' docs/user-manual.md | grep -c "All Products"
```

## SC-005 — one spelling

```bash
# must print nothing
grep -ric "catalogue" README.md CLAUDE.md docs/ app/ tests/

# must still print matches — the frozen records are deliberately untouched
grep -ric "catalogue" specs/ migrations/ | head -3

# the substitution trap
grep -rn "uncatalogd\|uncatalogued" app/ tests/ || echo "uncataloged spelled correctly"
```

Confirm `CLAUDE.md` states the rule *and* its exclusions (FR-014):

```bash
grep -A4 -i "catalog" CLAUDE.md | grep -i "specs/\|migrations/"
```

## SC-006 — the renames changed no behavior

```bash
python -m pytest tests/unit -q --collect-only | tail -1   # expect: 1216 tests collected
nox -s tests                                              # expect: 1216 passed
```

**A green run is not sufficient.** A test renamed out of collection passes silently with less
in the suite — the count is the check, not the colour. Same for e2e (15-minute timeout):

```bash
nox -s e2e     # expect: 459 passed
```

## SC-007 — the README says the application has a catalog

```bash
grep -n -i "catalog" README.md
```

**Expect** at least one Features bullet naming the catalog's capabilities (FR-015), a
documentation link reaching the catalog guidance (FR-016), and an embedded catalog screenshot
(FR-017):

```bash
grep -n "product_search.png" README.md
```

## SC-008 / SC-009 — the screenshots regenerate and are all embedded

Delete them and prove they come back with no manual step:

```bash
rm -f docs/images/screenshots/user-manual/{product_search,product_detail,product_add_form,order_capture,reorder_list,category_tree}.png
nox -s screenshots_headless
ls -la docs/images/screenshots/user-manual/product_*.png \
       docs/images/screenshots/user-manual/{order_capture,reorder_list,category_tree}.png
nox -s screenshots_verify    # expect: all 18 valid, none over 500 KB
```

If `product_detail.png` fails the size gate, switch that capture to `full_page=False` per
[contracts/screenshot-manifest.md](./contracts/screenshot-manifest.md) — do not raise the
ceiling.

Confirm every capture is actually embedded (FR-019):

```bash
for s in product_search product_detail product_add_form order_capture reorder_list category_tree; do
  printf '%-20s %s\n' "$s" "$(grep -c "$s.png" docs/user-manual.md README.md | paste -sd/ -)"
done
```

**Expect** `product_search` in both files; the other five in the manual only.

Counts in the inventory documents (FR-023):

```bash
find docs/images/screenshots -name '*.png' | wc -l          # expect 18
grep -n "Total" docs/images/screenshots/GENERATION_GUIDE.md # expect 18
grep -n "Total Screenshots" docs/images/screenshots/VERIFICATION.md  # expect 18
```

`VERIFICATION.md` currently claims 8 against 12 on disk — it is regenerated, not appended to.

## SC-010 — a test run leaves the tree clean

The one that catches a missing `@pytest.mark.screenshot`:

```bash
nox -s tests && git status --porcelain
nox -s e2e   && git status --porcelain
```

**Expect** empty output from both `git status` calls. Any PNG or `metadata.json` appearing
means a new capture test is not carrying the `screenshot` marker and is running inside the
e2e selection.

## SC-001 — the contents page reads as two halves

Not scriptable. Open `docs/user-manual.md` on GitHub, look only at the table of contents, and
answer without scrolling into the body:

1. What are the two things this application does?
2. Name four things the catalog does, and the section documenting each.
3. Where would you look to record what you paid for something?

If the grouped TOC in [data-model.md](./data-model.md) was followed, all three answer in
under 30 seconds.

---

## Full gate before merge

```bash
nox -s tests                 # 1216 passed
nox -s e2e                   # 459 passed, 15-min timeout
git status --porcelain       # empty
nox -s screenshots_headless  # regenerates all 18
nox -s screenshots_verify    # all valid, all under 500 KB
```

`nox -s lint` is red at baseline (pre-existing flake8 E501) and is not a gate — but do not add
new findings.
