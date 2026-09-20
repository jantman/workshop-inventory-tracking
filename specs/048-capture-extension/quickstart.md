# Quickstart: validating the Browser Capture Extension

How to prove this feature works. The automated half runs in CI; the manual half is the part
that cannot run in CI, and it is the part that actually closes issue #133 — no local fixture
carries McMaster's content policy, so nothing but a real McMaster page proves the bug is fixed.

Run commands from the repository root against the project virtualenv.

---

## 1. Automated

```bash
venv/bin/nox -s tests          # unit; includes the manifest/pyproject version assertion
venv/bin/nox -s e2e            # ~20 min warm; give your tool a 25-minute timeout, or detach
```

`e2e` outlasts most agent shell timeouts — run it detached and poll rather than blocking on it.

**What passing means, and what it does not.** The e2e suite proves the readers still extract
what they extracted and the application still does what it did. It does **not** prove the
extension defeats McMaster's policy, because the fixtures serve no such policy. That is §3's
job.

Expected:

| Check | Expectation |
|---|---|
| Existing capture tests | Pass unchanged in substance; only their entry point differs |
| New extension tests | The packed extension loads, the options screen persists an address, a capture reaches the application |
| Version assertion | `manifest.json` and `pyproject.toml` agree |
| Working tree afterwards | **Clean.** A test run that dirties it fails the constitution's gate |

## 2. Build and install the package

```bash
# What CI publishes, built the same way
cd extension && zip -r ../capture-extension.zip . && cd ..
```

Then, in Chrome:

1. `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → select the unzipped directory (or `extension/` directly)
3. Open the extension's **options**, enter the application's address — `https://`, including the
   port — and save
4. Confirm the version shown matches the application footer's

**Check the negative cases here, not later:**

- Save an `http://` address → a warning appears, and it still saves (FR-012)
- Save an address with a trailing slash and surrounding spaces → capture still works (FR-013)
- Before configuring anything, invoke capture → it says the address is unset and opens the
  options screen; **it must not silently do nothing** (FR-011)

## 3. The manual checks that CI cannot do

This is §9a of the #80 verification pass, which is what failed and produced this feature.

| # | Page | Expected |
|---|---|---|
| 3a | A real McMaster **product** page (`mcmaster.com/<part>/`) | Capture opens the confirmation, pre-filled. **No content-policy error in the console.** |
| 3b | A real McMaster **order** page (`/order-history/order/<id>`) | Capture opens the order review with the order's lines |
| 3c | A real Amazon **order** page | Same review the bookmarklet produced, including per-line listing details, with progress shown while it reads |
| 3d | A real Amazon **listing** | Confirmation opens pre-filled, exactly as before |
| 3e | Any unrelated page | Says it is not a page it can read; no context-menu entry offered |
| 3f | 3a again, from the **right-click menu** | Identical result to the toolbar control (FR-016) |

**3a and 3b are the feature.** Everything else is regression cover.

For 3a, open the console *before* clicking. The old failure was a `script-src` violation naming
`capture-agent.js`; its absence is the check.

**Confirm the vendor tab survives.** After every capture the original page must still be open
and unnavigated — that is the behavior change research.md §3 buys, and a regression in it would
otherwise go unnoticed.

## 4. Publishing

| Check | Where |
|---|---|
| Ordinary build publishes the zip | The build's artifacts (FR-022) |
| Release attaches the zip | The release's assets (FR-023) |
| Versions agree | The asset's `manifest.json` against that release's tag |

---

## What to do when a manual check fails

| Symptom | Likely cause |
|---|---|
| Nothing happens at all | The address is unset and the "unset" path is not reporting — the exact bug being fixed, reintroduced |
| Console names a `script-src` violation | The reader is being injected into the main world instead of an isolated one (research.md §1) |
| Capture tab opens but the POST fails | Address wrong, application unreachable, or not served over TLS (research.md §4) |
| Amazon order lines lack listing details | The per-line same-origin fetches are not behaving as the page's own (research.md §2) |
| A new tab is blocked by the popup blocker | A submission is still being made from the vendor page rather than the extension's (research.md §3) |
| One field missing, everything else present | A vendor markup change. Expected and contained (FR-006) — not a transport bug |

The last row matters: a single missing field is the designed degradation, not a failure of this
feature. Do not chase it as one.
