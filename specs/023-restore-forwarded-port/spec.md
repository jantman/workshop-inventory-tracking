# Feature Specification: Restore the Browser's Port Behind a Reverse Proxy

**Feature Branch**: `issues/114`

**Created**: 2026-08-21

**Status**: Draft

**Input**: GitHub issue #114 — "Bookmarklet addresses lose the port behind a proxy on a non-default
port (#110's ProxyFix)", together with its first comment, *"This is worse than the bookmarklet. It
breaks every form submission over HTTPS."* Found live on 2026-08-21 while doing #80 §1b's manual
verification against the deployed build at `https://titan.jasonantman.com:15603/`. The proxy
declares the forwarded host without a port; the application believes that declaration and overwrites
the host it received, which did carry the port. Two consequences follow from that one loss. The
capture bookmarklet hands out addresses on port 443, where nothing is listening, so it can never
load its agent. And every state-changing form served over HTTPS is refused with `400 Bad Request —
The referrer does not match the host`, because the referrer names the real address, port and all,
and the application now believes it lives somewhere else. Reads are unaffected, which is why the
deployment looks healthy right up until you try to save something.

## Terminology

- **The browser-visible address** — the scheme, host and port the operator's browser actually used.
  For this deployment, `https://titan.jasonantman.com:15603`. It is the only address that means
  anything to a browser on the LAN, and the only one another origin can reach.
- **Reverse proxy** — the TLS-terminating server in front of the application. It speaks HTTPS to the
  browser and plain HTTP to the application, so the connection the application receives never
  resembles the one the operator made.
- **Forwarded declaration** — what the proxy tells the application about the original request:
  today the scheme, the host, and the client address; not, at present, the port. The application
  trusts exactly one hop of this. That trust is not a security control — the deployment is LAN-only
  with one user — it exists so the addresses come out right.
- **Non-default port** — any port other than 80 for `http` or 443 for `https`. A default port is
  never written into an address; a non-default one always must be. This whole feature exists in the
  gap between those two rules.
- **External address** — an address the application builds complete with scheme, host and port,
  because it will be read somewhere other than the page that produced it. The bookmarklet's two
  addresses are the ones that matter; everything the operator reaches by browsing the application
  uses relative addresses and is untouched by this defect.
- **The referrer check** — the guard on state-changing form submissions that, for a request the
  application believes is secure, compares the address the form was served from against the address
  the application believes it lives at. It is a same-origin check, and a port is part of an origin.
- **The capture bookmarklet** — the loader dragged from `/products/capture` to the browser's
  bookmark bar. Clicking it on a vendor listing loads this application's reading agent into that
  page. It is the one thing that must work from *another* origin, so it is the one thing that cannot
  fall back on a relative address.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The deployment can save data again (Priority: P1)

The owner, browsing the deployed application over HTTPS on its non-default port, fills in any form
that writes — a capture confirmation, an item added or edited, a product added or edited, a move, a
shorten, a receive — presses the button, and the write happens. Today every one of them is refused
with `400 Bad Request` before the handler ever runs.

**Why this priority**: This is the feature. Without it the deployment is readable and not writable,
which is to say it is not usable. The bookmarklet defect that opened the issue is the visible
symptom of the same missing port; this is the disabling one, and fixing it fixes both.

**Independent Test**: Against the deployed build over HTTPS on its non-default port, submit one
state-changing form and confirm the record is written. That single submission proves the origin the
application believes in now matches the one the browser used.

**Acceptance Scenarios**:

1. **Given** the application deployed behind the TLS proxy on a non-default port, **When** the owner
   submits any state-changing form, **Then** the submission is accepted and the change is written —
   no `400 Bad Request — The referrer does not match the host`.
2. **Given** the same deployment, **When** the application resolves the address it believes it is
   serving, **Then** that address includes the browser-visible port, so a same-origin comparison
   against a referrer from that origin succeeds.
3. **Given** a deployment on a default port (443 for HTTPS, 80 for HTTP), **When** forms are
   submitted, **Then** behaviour is exactly as it is today — a default port is never written into
   the address the application believes in.
4. **Given** no proxy in front at all, **When** a form is submitted over a direct plain-HTTP
   connection, **Then** behaviour is exactly as it is today, because there is no forwarded
   declaration to read.

---

### User Story 2 - A bookmarklet dragged from the deployment works (Priority: P2)

The owner opens `/products/capture` on the deployment, drags the bookmarklet to the bookmark bar,
opens a vendor listing, and clicks it. A tab opens on this application's confirmation page carrying
the reading. Today the bookmarklet's two baked-in addresses point at port 443, where nothing
listens, so clicking it does nothing at all and gives no indication why.

**Why this priority**: It rides on the same fix as P1, so it costs nothing extra once the port is
restored — but it is second because a working bookmarklet against an application that cannot save is
worth nothing, while a working save without the bookmarklet still leaves every other form usable.
It is separated from P1 because it is the only observable that proves *external addresses*
specifically, as distinct from the address the application believes it lives at.

**Independent Test**: Drag the bookmarklet fresh from the deployment's capture page and read its two
addresses. Both must carry the browser-visible port. Clicking it on any vendor listing must open a
tab on the confirmation page. This is #80 §1a check A1, which passed before #110 and fails today.

**Acceptance Scenarios**:

1. **Given** `/products/capture` served over HTTPS on a non-default port, **When** the rendered
   bookmarklet is read, **Then** both the agent address and the submission endpoint carry that port.
2. **Given** that bookmarklet, **When** it is clicked on a vendor listing, **Then** the agent loads
   and a tab opens on this application's confirmation page.
3. **Given** the capture page served on a default port, **When** the bookmarklet is read, **Then**
   its addresses carry no port, as today.
4. **Given** the capture page reached over plain HTTP with no proxy, **When** the bookmarklet is
   read, **Then** its addresses are unchanged from today's behaviour, and the existing "not served
   over https" warning box still appears.

---

### User Story 3 - The gap that hid this closes behind it (Priority: P3)

The next person to change how the application resolves its own address finds out immediately if they
break a non-default-port deployment, and the person deploying it finds the port requirement stated
where they are already reading.

**Why this priority**: Last, because it prevents a recurrence rather than restoring service — but
not optional. Every existing test of the forwarded declaration uses either the default host or a
bare hostname; **no test anywhere uses a non-default port**, so the one configuration that breaks is
the one configuration never exercised. That is why a defect that disables every write shipped on
2026-08-19 and was not found until it was used by hand two days later.

**Independent Test**: Run the new coverage against the code as it stands before the fix. It must
fail. That is the whole point of it.

**Acceptance Scenarios**:

1. **Given** the application as it stands before this feature, **When** the new automated coverage
   runs, **Then** it fails — demonstrating it exercises the defect rather than describing it.
2. **Given** the fixed application, **When** the full test suite runs, **Then** the new coverage
   passes and nothing that passed before now fails.
3. **Given** the deployment guide, **When** an operator follows its reverse-proxy section end to
   end, **Then** what the proxy must declare about the port is stated there, in the copyable
   configuration rather than only in prose.
4. **Given** the troubleshooting guide, **When** an operator hits a refused form submission or a
   dead bookmarklet on a non-default-port deployment, **Then** the symptom is listed with the cause
   and a pointer to the deployment guide, alongside the existing entry for the missing scheme.

---

### Edge Cases

- **The proxy declares a default port.** `443` on HTTPS, `80` on HTTP: the address must come out
  with no port at all. Writing `https://host:443/` into the bookmarklet would be a new defect of the
  same shape, and the referrer comparison would fail the same way.
- **The proxy declares nothing about the port.** The application cannot invent it. Behaviour must
  degrade to exactly what happens today, and the deployment guide must be what closes that gap — an
  operator who does not configure the declaration gets today's broken behaviour, which is why the
  documentation change is part of this feature and not a follow-up.
- **The proxy declares the port inside the forwarded host** (`host:15603`) **as well as separately.**
  Both convey the same fact. The result must be a single correct address either way, and must not
  produce a doubled port.
- **No proxy at all.** Direct plain HTTP, the development server, and the end-to-end suite: no
  forwarded declaration is present, nothing may change. The suite runs over plain HTTP on a default
  port, so it will not catch a regression here — which is exactly the gap User Story 3 closes.
- **A declared port that is not a number, or is empty.** Malformed input from the one trusted hop is
  a misconfiguration, not an attack. It must not produce a corrupt address or a crashed request; the
  application falls back to what it can determine on its own.
- **Reads on a non-default-port deployment.** They work today and must keep working. They are the
  reason the deployment looked healthy, and any fix that disturbs them is worse than the defect.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the application builds an external address, that address MUST carry the port the
  browser used, whenever that port is not the default for the scheme.
- **FR-002**: The application MUST take the browser's port from the reverse proxy's forwarded
  declaration, trusting exactly one hop, consistent with the single-hop trust it already places in
  the forwarded scheme, host and client address.
- **FR-003**: When the browser used the default port for the scheme — 443 for `https`, 80 for
  `http` — the port MUST NOT appear in any address the application builds.
- **FR-004**: The address the application believes it is serving MUST match the browser-visible
  address, including port, so that the referrer check on a state-changing form submission compares
  two like origins and accepts the submission.
- **FR-005**: Both of the capture bookmarklet's baked-in addresses — the agent it loads and the
  endpoint it submits to — MUST carry the browser-visible port.
- **FR-006**: When no forwarded declaration is present, the application's behaviour MUST be
  unchanged from today's, in address building and in form submission alike.
- **FR-007**: When the forwarded declaration names a default port, or names no port, or names a
  malformed one, the application MUST produce a usable address rather than a doubled port, a
  corrupted address, or a failed request.
- **FR-008**: Automated coverage MUST exercise a deployment on a non-default port and assert that
  the port survives into both of the bookmarklet's addresses. This test MUST fail against the code
  as it stands before this feature.
- **FR-009**: Automated coverage MUST assert that the address the application believes it is serving
  carries the non-default port — the condition the referrer check compares against — so that the
  write-path failure is covered and not only the bookmarklet's.
- **FR-010**: Automated coverage MUST assert that a default port does not appear in a built address,
  and that the no-proxy case is unchanged.
- **FR-011**: The deployment guide's reverse-proxy section MUST state what the proxy has to declare
  about the port, inside the copyable proxy configuration and not only in the surrounding prose.
- **FR-012**: The troubleshooting guide MUST list the refused form submission and the dead
  bookmarklet as symptoms of an undeclared port, alongside its existing entry for an undeclared
  scheme, and point to the deployment guide.

### Out of Scope

- **Measuring a stored capture image.** 022 SC-010 / #80 §1b B4 — confirming a capture and measuring
  the stored file to show every gallery image is a full-resolution original — is blocked on this
  feature but belongs to #113. It is unblocked by this work, not performed by it.
- **Anything about what the capture agent reads.** #113's gallery-count findings stand; this feature
  changes only the address the agent is loaded from and the origin a form is submitted to.
- **The forwarded scheme, host and client address.** They work. Their existing behaviour and their
  existing tests are unchanged.
- **Any security treatment of the forwarded declaration.** Single user, LAN-only, one trusted hop.
  The trust exists so the addresses come out right, and this feature does not revisit it.
- **Making the end-to-end suite exercise HTTPS or a non-default port.** The gap is real and named
  here; closing it would mean running the suite behind a TLS proxy, which is a disproportionate
  amount of machinery for one assertion that a unit-level test covers directly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the deployed build over HTTPS on its non-default port, every state-changing form
  the application offers can be submitted and its change written. Zero submissions are refused with
  `The referrer does not match the host`, against a count of every one of them refused today.
- **SC-002**: A bookmarklet dragged fresh from the deployment and clicked on a vendor listing opens
  the confirmation page on the first attempt, with no hand-editing of its address — the check that
  passed before 2026-08-19 and fails today.
- **SC-003**: Both of that bookmarklet's addresses, read from the page as served, carry the
  browser-visible port.
- **SC-004**: The new automated coverage fails against the code as it stands before this feature and
  passes after it, demonstrating that it exercises the defect.
- **SC-005**: The complete test suite passes, with no test that passed before this feature now
  failing.
- **SC-006**: A deployment on a default port, and a deployment reached directly over plain HTTP with
  no proxy, behave identically before and after — no port appears in an address where none appears
  today.
- **SC-007**: An operator following the deployment guide's reverse-proxy section end to end, on a
  non-default port, gets a deployment on which SC-001 and SC-002 hold, without needing to consult
  the issue or the source.

## Assumptions

- The remedy is the application trusting a forwarded port declaration from the one hop it already
  trusts, with the deployment guide stating that the proxy must send it. This was chosen on
  2026-08-21 over the two alternatives the issue raised: having the proxy carry the port inside the
  forwarded host, which needs no code but leaves any correctly-configured-looking deployment broken;
  and ceasing to trust the forwarded host at all, which would restore the port but regress the case
  the forwarded host was added for.
- The proxy in the affected deployment can be configured to declare the port. Every mainstream
  TLS-terminating proxy can; if this one could not, no application-side remedy would exist, because
  the port simply would not be in the request.
- Reads on the affected deployment are genuinely unaffected, as observed live on 2026-08-21: the
  products list showed 7 products before and after a refused submission, so the refusal happens
  before the handler and leaves no partial write to clean up.
- The end-to-end suite will continue to run over plain HTTP on a default port and will not cover
  this path. Focused coverage of the forwarded declaration is the guard, as it already is for the
  forwarded scheme.
- Verification of SC-001 and SC-002 happens by hand against the real deployment, because the defect
  exists only behind a real proxy on a real non-default port. Everything else is covered by the
  automated suite.
- This defect entered on 2026-08-19 with the change that made the application trust the forwarded
  host. Before that the port survived untouched, so there is no older deployment state to consider.
