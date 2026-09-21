# Feature Specification: Browser Capture Extension

**Feature Branch**: `robot-army/issue-133-mcmaster-s-csp-blocks-the-capture-agent`

**Created**: 2026-09-20

**Status**: Draft

**Input**: GitHub issue #133, "McMaster's CSP blocks the capture agent, so no McMaster page can be captured by bookmarklet"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture a McMaster order (Priority: P1)

The workshop owner has just received a McMaster-Carr order. They open the order in their
browser, where it is rendered on screen in front of them, and they want its lines in the
catalog so the bags can be scanned against it as they are unpacked.

Today this is impossible by any route. The bookmarklet is refused by McMaster's page policy
before it can read anything, and the only other capture path takes a product address rather
than an order, so it cannot express an order at all. This story is the whole reason the
feature exists.

After this feature the owner clicks the capture control provided by an installed browser
extension while standing on the order page, and lands on the application's order review with
the order's lines read off the page they were looking at.

**Why this priority**: It is the only outcome that is impossible today rather than merely
awkward. Everything else in this specification either preserves something that already works
or improves how it is reached.

**Independent Test**: With the extension installed and pointed at the application, invoke
capture on a McMaster order page. The application's order review opens in a new tab listing
the order's lines. Delivers the entire blocked half of the McMaster capture feature.

**Acceptance Scenarios**:

1. **Given** the extension is installed and configured with the application's address,
   **When** the owner invokes capture on a McMaster order page, **Then** a new tab opens on
   the application's order review showing the lines read from that page.
2. **Given** that same page, **When** capture runs, **Then** it is not refused by the page's
   content policy, and the owner is never required to change any browser or site setting to
   make it work.
3. **Given** a McMaster order page, **When** capture runs, **Then** the order is read from the
   document as it is rendered on screen, not from a freshly requested copy of the address.
4. **Given** an order whose page no longer exposes some field the reader looks for, **When**
   capture runs, **Then** that one field is absent from the result and every other field and
   line is still captured.

---

### User Story 2 - Keep capturing everything that already worked (Priority: P2)

The owner also captures Amazon orders, Amazon listings, and McMaster product pages. All three
work today through the bookmarklet. The bookmarklet is being removed, so all three must arrive
through the extension instead, with nothing lost.

**Why this priority**: This is a no-regression obligation rather than new value, but the
feature cannot ship without it — removing the bookmarklet without replacing these paths would
trade one broken vendor for three.

**Independent Test**: Invoke capture on each of an Amazon order page, an Amazon listing, and a
McMaster product page. Each produces the same result the bookmarklet produced for that page.

**Acceptance Scenarios**:

1. **Given** an Amazon order page, **When** the owner invokes capture, **Then** the resulting
   order review is the same one the bookmarklet produced, including each line's own listing
   details.
2. **Given** an Amazon listing page, **When** the owner invokes capture, **Then** the capture
   confirmation opens pre-filled exactly as it was before this feature.
3. **Given** a McMaster product page, **When** the owner invokes capture, **Then** the capture
   confirmation opens pre-filled exactly as it was before this feature.
4. **Given** an Amazon order with several lines, **When** capture runs and takes several
   seconds to read each line's listing, **Then** the owner is shown that reading is in
   progress rather than being left with no feedback.
5. **Given** any supported page, **When** capture completes, **Then** what the application
   receives is unchanged from what the bookmarklet sent, so nothing downstream of the capture
   endpoint had to change to accept it.

---

### User Story 3 - Point the extension at my own installation (Priority: P2)

The application is self-hosted. Its address is whatever the person running it chose — host,
port and all. The extension must be told that address by the person installing it, and must
not assume any particular one.

**Why this priority**: Without it nothing else in the feature works at all, and a built-in
address would make the published artifact useless to anyone other than its author.

**Independent Test**: Install the extension, open its options, enter an application address,
and confirm a capture reaches that address. Restart the browser and confirm the address is
still there.

**Acceptance Scenarios**:

1. **Given** a freshly installed extension, **When** the owner opens its options and enters
   their application's address, **Then** the address is saved and used by subsequent captures.
2. **Given** a saved address, **When** the browser is closed and reopened, **Then** the address
   is still configured and capture still works.
3. **Given** a freshly installed extension with no address yet, **When** the owner invokes
   capture, **Then** they are told the address has not been set and are taken to where they can
   set it — capture does not fail silently.
4. **Given** the owner enters an address that is not secure, **When** they save it, **Then**
   they are warned that capture requires a secure address, because a vendor's page will not
   submit to an insecure one.
5. **Given** the owner enters an address with a trailing slash or surrounding whitespace,
   **When** it is saved, **Then** capture still reaches the right place.

---

### User Story 4 - Install and update the extension from a published build (Priority: P2)

The owner does not build the extension by hand. Every build of the project publishes the
packaged extension for download, and a released version publishes it alongside the release, in
the same way the container image already is. A documentation page tells the owner how to
install it, configure it, use it, and update it later.

**Why this priority**: The extension has no value sitting in the repository. This is what makes
it reachable, and it is the part the project has no existing equivalent of.

**Independent Test**: From a completed build, download the published extension package, follow
the documentation page, and reach a first successful capture without editing any file.

**Acceptance Scenarios**:

1. **Given** a completed ordinary build of the project, **When** the owner looks at that
   build's outputs, **Then** the packaged extension is there to download.
2. **Given** a released version of the project, **When** the owner looks at that release,
   **Then** the packaged extension is attached to it.
3. **Given** the downloaded package and the documentation page, **When** the owner follows it,
   **Then** they reach a first successful capture without editing any file.
4. **Given** an installed extension and a newer published one, **When** the owner follows the
   documentation's update instructions, **Then** the newer one is running and the address they
   configured is still set.
5. **Given** any published extension package, **When** its declared version is compared with
   the application's declared version, **Then** they are the same, so the owner can tell at a
   glance whether the two match.

---

### User Story 5 - Start a capture from the right-click menu (Priority: P3)

Rather than reaching for a toolbar control, the owner right-clicks on the vendor page and
starts the capture from the context menu.

**Why this priority**: A workflow improvement, wanted but not required. The feature is a
success without it, and it is specified separately so it can be dropped if it proves
expensive.

**Independent Test**: Right-click on a supported vendor page and confirm the capture entry is
offered and works. Right-click elsewhere and confirm it is not offered.

**Acceptance Scenarios**:

1. **Given** a supported vendor page, **When** the owner right-clicks it, **Then** a capture
   entry is offered, and choosing it captures exactly as the toolbar control does.
2. **Given** a page on a site the extension does not read, **When** the owner right-clicks it,
   **Then** no capture entry is offered.

---

### Edge Cases

- **No address configured yet.** The first capture after installing must say so and lead the
  owner to the options, rather than doing nothing — which is precisely the failure mode of the
  bug this feature fixes.
- **Address configured but unreachable**, because the application is down, the host is wrong,
  or the owner is off the network. The owner must be able to tell this apart from a page the
  extension could not read.
- **Application served without a secure address.** Capture cannot work, because a vendor page
  that upgrades insecure requests will not submit to it. The owner must be warned where they
  enter the address, not left to discover it at capture time.
- **Invoked on a page the extension does not read** — a McMaster family table, an Amazon order
  *list*, a search results page, or anything else. The owner must be told the page is not one
  it can read.
- **The landing tab is refused by the browser's popup control.** Capture must still deliver its
  result rather than being lost.
- **Extension version and application version disagree** because one was updated and the other
  was not. The owner must be able to see both version numbers and notice.
- **A vendor changes their markup** so a reader stops finding a field. That field is lost and
  nothing else is — unchanged from today, and still containment rather than prevention.
- **An order page with a single line, and one with many.** Both must capture; the many-line
  case is the one that takes long enough to need progress shown.

## Requirements *(mandatory)*

### Functional Requirements

#### Capturing

- **FR-001**: The extension MUST capture from every kind of page the existing capture reader
  recognizes: McMaster order pages, McMaster product pages, Amazon order pages, and Amazon
  listings.
- **FR-002**: Capture MUST succeed on pages whose content policy forbids loading scripts from
  other origins, which is the defect this feature exists to fix.
- **FR-003**: What the extension sends to the application MUST be unchanged from what the
  bookmarklet sent for the same page, so that no part of the application behind the capture
  endpoint has to change to accept it.
- **FR-004**: The extension MUST read the document as rendered on screen, not a separately
  requested copy of the address, except where the existing reader already re-reads a canonical
  address for Amazon listings — that behavior is retained exactly.
- **FR-005**: A completed capture MUST open the application's capture confirmation or order
  review in a new browser tab, as it does today.
- **FR-006**: A reader failing to find one field MUST cost only that field. No single missing
  field may abandon the capture.
- **FR-007**: When a capture reads additional pages and therefore takes several seconds, the
  extension MUST show the owner that work is in progress.
- **FR-008**: Invoking capture on a page the extension does not read MUST tell the owner so.

#### Configuration

- **FR-009**: The extension MUST take the application's address from the person who installed
  it, through an options screen. No address may be built into the published package.
- **FR-010**: The configured address MUST persist across browser restarts.
- **FR-011**: Invoking capture with no address configured MUST inform the owner and lead them
  to the options screen.
- **FR-012**: The options screen MUST warn when the entered address is not a secure one,
  because capture cannot work against an insecure address.
- **FR-013**: The options screen MUST accept an address entered with surrounding whitespace or
  a trailing slash and still reach the right place.
- **FR-014**: The owner MUST be able to see the extension's version, so it can be compared with
  the application's.

#### Entry points

- **FR-015**: The extension MUST offer a toolbar control that starts a capture on the current
  page.
- **FR-016**: The extension SHOULD offer a right-click context-menu entry that starts a
  capture, offered only on the sites it can read. This requirement is explicitly optional: the
  feature is complete without it.

#### Retiring the bookmarklet

- **FR-017**: The bookmarklet MUST be removed — the draggable control, the warning shown beside
  it when the application is served insecurely, and the code that builds it.
- **FR-018**: The capture page MUST point the owner at the extension in place of the removed
  bookmarklet, including where to get it.
- **FR-019**: The existing paste-an-address capture path MUST continue to work exactly as it
  does now. It is untouched by this feature.
- **FR-020**: After this feature there MUST be exactly one way to capture from a vendor's page
  in a browser. The bookmarklet is not retained for Amazon or for anything else.

#### Packaging, publishing and documentation

- **FR-021**: The extension MUST live in this repository, in its own subdirectory.
- **FR-022**: Every ordinary build of the project MUST publish the packaged extension as a
  downloadable build output.
- **FR-023**: Every released version MUST publish the packaged extension as an asset of that
  release.
- **FR-024**: The extension's declared version MUST equal the application's declared version,
  and this MUST be enforced automatically rather than by memory.
- **FR-025**: The project MUST carry a documentation page for the extension covering
  installation, configuration, use, and updating.
- **FR-026**: Changing the reader logic MUST be understood to require a new application version
  and a new extension version, which the owner installs by hand. The previously guaranteed
  property — that the reader could be edited with nothing to re-install — is deliberately
  given up, and the documentation MUST say so.

### Key Entities

- **Captured payload**: What the extension reads off a vendor's page and hands to the
  application — the listing details and, for an order page, the order and its lines. Its shape
  is fixed by the existing capture contract and does not change in this feature.
- **Configured application address**: The single piece of configuration the extension holds.
  Supplied by whoever installed it, persisted by the browser, and required before any capture.
- **Supported page kind**: Which of the recognized vendor pages the current address names —
  McMaster order, McMaster product, Amazon order, Amazon listing, or none of them. Determined
  from the address alone, as it is today.
- **Packaged extension**: The published, downloadable form of the extension, carrying a version
  that matches the application's.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A McMaster order can be captured from the browser. This is impossible by any
  route before this feature, so the measure is binary: zero capture routes before, one after.
- **SC-002**: All four supported page kinds — McMaster order, McMaster product, Amazon order,
  Amazon listing — capture successfully, with the McMaster pages newly working and the two
  Amazon pages producing what they produced before.
- **SC-003**: Starting from a published build output and the documentation page, a person who
  has never installed it reaches their first successful capture in under 10 minutes, without
  editing any file and without writing any code.
- **SC-004**: A capture takes the owner no more actions than the bookmarklet did — one
  deliberate invocation on the page being captured, and no steps in between.
- **SC-005**: Exactly one browser-based capture path exists after this feature; the count of
  separately maintained vendor-page transports goes from one to one, not to two.
- **SC-006**: The application's capture endpoint accepts the extension's submissions without
  any change to its contract, demonstrated by the existing capture behavior tests continuing to
  pass with only their entry point replaced.
- **SC-007**: Every completed build offers the extension for download, and every release
  carries it as an asset — measured as 100% of builds and releases, not most.
- **SC-008**: The extension's version and the application's version cannot disagree without the
  project's own checks failing.

## Out of Scope

- Publishing to any extension store, and anything that requires a store listing or review.
- Supporting browsers other than Chrome and Chromium-derived browsers.
- Any change to what the application does with a capture once it has received it — the review,
  the matching, the writing, and the receiving flows are all untouched.
- Removing the requirement that the application be served over a secure address. That
  requirement already applies to Amazon captures today, it is not a regression introduced here,
  and it is not addressed by this feature.
- The paste-an-address capture path, which is unaffected.
- Automatic updating of the installed extension.

## Assumptions

- **Packaging and install.** The published artifact is a plain archive of the extension's
  files, and the install path is the browser's own "load an unpacked extension" facility after
  unpacking. A signed package is deliberately not produced: it would require managing a signing
  key in order to produce something the browser refuses to install outside a store on two of
  the three major platforms, while the unpacked path works everywhere with no key and no
  listing. Updating is "replace the files and reload the extension".
- **One copy of the reader logic.** Because the bookmarklet is removed, nothing loads the
  reader over the network any more, so the application need not serve it. The reader moves into
  the extension's directory and has exactly one home in the repository. There is no copy step
  and nothing that can drift out of sync.
- **Test strategy is split deliberately.** The roughly 158 existing end-to-end tests whose
  entry point is the bookmarklet keep driving the reader directly against the same local vendor
  fixtures, with the bookmarklet click replaced by a direct injection of the reader. A small
  number of *new* tests load the packaged extension for real, and cover only what direct
  injection cannot: that the extension activates on the right addresses, that the options
  screen persists the address, and that a capture started from the extension reaches the
  application with it. Rationale: driving a real extension requires a different browser launch
  mode, and confining that to a handful of new tests buys coverage of the new machinery without
  putting the suite's largest file through a change to how its browser starts.
- **Version agreement is asserted, not generated.** The extension's declared version is
  expected to match the application's declared version, checked by a test rather than stamped
  by a build step, because a test fails loudly in CI and a stamping step adds a build.
- **Entry points.** The toolbar control is the always-available way in; the context-menu entry
  is additional and restricted to the sites the extension reads.
- **The transport is unchanged.** The existing mechanism — building a hidden form on the vendor
  page and submitting it into a new tab — is retained as-is. It is what makes the capture
  endpoint's contract hold, and the secure-address requirement it carries is pre-existing.
- **Single operator, trusted.** As everywhere else in this project, there is one user and no
  hostile party. The extension holds one configuration value and no credentials.

### Why this cost is accepted

The constitution's first principle is Simplicity First, and it is non-negotiable. A second
codebase, a packaging path, a publishing path and a manual install path are exactly the costs
that principle exists to police, so this feature must answer to it rather than skirt it.

The answer is that the problem is bounded and observed rather than speculative. A McMaster
order cannot be captured by any route that exists — not by the bookmarklet, which the vendor's
page refuses outright, and not by the paste-an-address path, which cannot express an order.
That is a measured failure of shipped functionality, which is the standard the principle sets
for accepting work of this size. The alternatives were weighed and rejected by the person who
owns this project: pasting rendered markup, and entering McMaster orders by hand.

The cost is contained in two ways that the specification makes binding. The bookmarklet is
removed rather than kept (FR-017, FR-020), so the project maintains one vendor-page transport
afterwards, not two. And the reader logic keeps exactly one home in the repository, so the
"second codebase" is a manifest, an options screen and a small amount of plumbing around a file
that already exists — not a second copy of the part that does the work.

What is genuinely given up is recorded rather than hidden: editing the reader used to require
nothing to be re-installed, and now requires a new extension version installed by hand
(FR-026). That was judged an acceptable price by the project owner, and the documentation is
required to state it so nobody later mistakes it for a defect.
