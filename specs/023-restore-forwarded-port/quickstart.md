# Quickstart: Validating the Restored Port

**Feature**: `specs/023-restore-forwarded-port/` | **Date**: 2026-08-21

Validation has two halves that cannot substitute for each other. The automated half proves the
transformation is right for every case, including the ones nobody will ever deploy. The manual half
proves the real proxy actually sends what the contract requires — and it is the only thing that can,
because the defect exists only behind a real proxy on a real non-default port.

Do them in the order given. The first step is the one most likely to be skipped and the one that
makes the rest mean anything.

## Prerequisites

- The virtualenv at `venv/`, used by path (`venv/bin/nox`), not activated.
- `python3.13` reachable — prefix nox invocations with
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"` or environment creation fails.
- For the manual half: the deployed build at `https://titan.jasonantman.com:15603/`, running an
  image built **after** this feature's version bump. Without the bump no image is published and you
  will be testing the old code — see [research.md](research.md) Decision 5.

## 1. Watch the new tests fail — before the fix

This is a requirement, not a suggestion: FR-008 and FR-009 both say the coverage must fail against
the code as it stands, and SC-004 is the assertion that it does. A test written after the fix, that
has never been seen red, does not satisfy them. The whole reason this defect shipped is that the one
configuration that breaks was the one configuration never exercised.

With the new tests added to `tests/unit/test_proxy_headers.py` but `app/__init__.py` **not yet
changed**:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- -k proxy_headers
```

**Expected**: the non-default-port tests fail. The bookmarklet assertions fail because the addresses
carry no port; the same-origin assertion fails because the application believes it is at
`titan.example.com` while the browser was at `titan.example.com:15603`. Everything already in that
file passes, untouched.

Record that this was seen. It is SC-004's evidence.

## 2. Apply the fix and run the full suite

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

**Expected**: everything passes, including the tests from step 1, and nothing that passed before now
fails (SC-005). Pay particular attention to the pre-existing cases in `test_proxy_headers.py` —
`TestPlainHttpIsUnchanged` and the default-host cases are FR-006 and SC-006, and they are what proves
the fix did not move the no-proxy and default-port paths.

The cases the tests must cover, and the value each should produce, are tabulated in
[data-model.md](data-model.md). The malformed-port row is the one that fails without the guard, and
it is the row a reviewer should look for first.

## 3. Run the end-to-end suite

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e
```

Give this **at least a 15-minute timeout** on whatever runs it; it takes around 8m 15s warm and the
margin is for a cold start pulling the MariaDB image and installing browsers. It runs longer than a
10-minute command cap allows, so run it detached and poll.

**Expected**: unchanged. This suite runs over plain HTTP on a default-port origin and therefore does
not exercise this feature at all — the secure referrer path is never reached, which is precisely why
nothing here caught the defect. It is run to prove the change is invisible to it, not to validate the
feature. Afterwards, `git status` must be clean.

## 4. Confirm the proxy sends the port

On the deployment, after applying the `X-Forwarded-Port` line from
[contracts/proxy-headers.md](contracts/proxy-headers.md) and reloading the proxy — fetch the capture
page and read what the application built:

```bash
curl -s https://titan.jasonantman.com:15603/products/capture | grep -o 'id="capture-bookmarklet"[^>]*'
```

**Expected**: the `href` contains both addresses, each reading
`https://titan.jasonantman.com:15603/…` — the agent script and the `/api/capture` endpoint. This is
SC-003, and it is also the contract check: if the port is still absent here, the proxy is not sending
the header and no application change will help.

## 5. Submit a form (SC-001)

In a browser, over `https` on `:15603`, open any page that writes and submit it — editing an item is
the smallest one. 

**Expected**: the change is saved. Specifically **not** `400 Bad Request — The referrer does not
match the host`, which is what every one of these returns today.

This is the acceptance criterion that matters most. The bookmarklet was the reported symptom; this is
the one that made the deployment unusable.

## 6. Drag the bookmarklet and click it (SC-002)

Drag the bookmarklet fresh from `/products/capture` — do not reuse a previously dragged one, and do
not hand-correct its address, which is how #113's verification worked around this. Click it on any
Amazon listing.

**Expected**: a tab opens on this application's confirmation page carrying the reading. This is
#80 §1a check A1, which passed before 2026-08-19 and fails today.

## What this does *not* validate

Confirming a capture and measuring a stored file to show every gallery image is a full-resolution
original — 022 SC-010 / #80 §1b B4 — is **not** part of this feature. Step 5 unblocks it by making
the write path work; performing it belongs to #113. Do not close that task on the strength of a
successful submission here.
