# Feature Specification: Build Version Suffix

**Feature Branch**: `robot-army/issue-164-build-version-exposed-in-ui`

**Created**: 2026-09-20

**Status**: Draft

**Input**: GitHub issue #164, "Build version exposed in UI"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identify which build a container is running (Priority: P1)

The workshop owner runs the application from a container image. Images are published
from two different automated build paths: every CI build of a branch or pull request
publishes an image, and a version bump merged to the main line publishes a release
image. When the owner looks at the page footer or asks the health endpoint what is
running, they need to know *which* of those builds they are looking at — not merely
which release number it is descended from.

**Why this priority**: This is the only mandatory outcome of the issue. Without it, two
different images built weeks apart both report `0.1.1`, and the owner cannot tell
whether a fix they are hunting for is present in the running container.

**Independent Test**: Build an image through the CI build path and start it; the footer
and the health endpoint both report the release number followed by the seven-character
short form of the commit the image was built from. Build an image through the release
path and start it; both report the bare release number.

**Acceptance Scenarios**:

1. **Given** an image produced by the CI build path from commit
   `6d15bde4d4cda7c8ec7a0e277cf926ad2bf7881c` while the declared release number is
   `0.1.1`, **When** the owner loads any page, **Then** the footer shows `v0.1.1-6d15bde`.
2. **Given** that same image, **When** the owner requests the health endpoint, **Then**
   the reported version is `0.1.1-6d15bde` — the same string the footer shows, without
   the display-only `v` prefix.
3. **Given** an image produced by the release path for release `0.1.1`, **When** the
   owner loads any page or requests the health endpoint, **Then** the version reported is
   `0.1.1` with no commit suffix.
4. **Given** any container image, **When** the version is determined, **Then** it is
   determined without the container needing a copy of the source history, and without
   network access.

---

### User Story 2 - Identify what a working copy is running (Priority: P2)

The owner also runs the application directly from a checked-out working copy while
developing or testing. In that situation the same question applies, plus one more: has
the running code been edited beyond what is committed?

**Why this priority**: Explicitly secondary in the issue, and conditional — worth doing
only if it does not significantly complicate the work. It gives the same benefit as
Story 1 for the case where the owner is most likely to be confused about what is
running, but the container case is what actually ships.

**Independent Test**: Start the application from a working copy in each of three states
— positioned exactly on a release tag, positioned on an untagged commit, and positioned
on an untagged commit with edited files — and confirm the footer reports the three
distinct forms.

**Acceptance Scenarios**:

1. **Given** a working copy positioned exactly on the tag for the declared release
   number, with no edits, **When** the owner loads any page, **Then** the footer shows
   the bare release number.
2. **Given** a working copy positioned on a commit that carries no release tag, with no
   edits, **When** the owner loads any page, **Then** the footer shows the release number
   followed by that commit's seven-character short form.
3. **Given** a working copy positioned on an untagged commit **and** carrying edits to
   tracked files, **When** the owner loads any page, **Then** the footer shows the release
   number, the short commit form, and a trailing `dirty` marker.
4. **Given** a working copy positioned exactly on a release tag but carrying edits,
   **When** the owner loads any page, **Then** the reported version carries the `dirty`
   marker, because the running code is not the tagged code.

---

### Edge Cases

- **No build stamp and no history available** — for example the code is unpacked from an
  archive, or run from a container built outside the automated paths. The bare release
  number MUST be reported. Reporting a version is never allowed to fail; an
  indeterminate provenance degrades to the number that is always knowable.
- **History tooling absent or failing** at runtime (no history tool installed, the
  directory is not a working copy, the tool errors or hangs). Same outcome: bare release
  number, no error surfaced to the owner, no traceback on a page render.
- **A build stamp is present and history is also available.** The build stamp wins. A
  container that happens to be started inside a working copy must not report that
  working copy's state.
- **The build stamp is present but empty or malformed.** Treated as absent.
- **Determining the version is on the path of every page render.** It must not add
  perceptible latency to each request, and must not shell out to a history tool once per
  request.
- **The declared release number is unchanged between two CI builds.** The two builds
  must still be distinguishable from each other, which is the whole point of the suffix.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The application MUST report a single version string, used identically by
  the page footer and by the health endpoint. There MUST NOT be two version strings that
  can disagree. The footer's leading `v` is presentation only and is not part of the
  string.
- **FR-002**: When the application carries a build stamp identifying the commit it was
  built from and indicating a non-release build, the reported version MUST be the
  declared release number, a hyphen, and the first seven characters of that commit
  identifier.
- **FR-003**: When the application carries a build stamp indicating a release build, the
  reported version MUST be the declared release number alone, with no suffix.
- **FR-004**: The CI image build path MUST stamp the image it produces as a non-release
  build of the commit the source was taken from. For a pull request, that MUST be the
  commit under review, not the throwaway merge commit the CI system synthesizes — the
  suffix has to name a commit that exists in the repository's history.
- **FR-005**: The release image build path MUST NOT stamp a commit onto the image it
  produces, so that a release image reports the bare release number. (Revised during
  planning: the original wording asked for a positive "this is a release" stamp. Two
  stamps where one suffices is a knob Principle I does not allow, and the observable
  outcome — FR-003 — is identical either way. See research.md R2.)
- **FR-006**: When no build stamp is present, the application MUST attempt to determine
  its version from the source history of the directory it is running from, and MUST
  report: the bare release number when positioned exactly on the tag matching that
  release number with no edits to tracked files; otherwise the release number plus the
  first seven characters of the current commit; plus a trailing `-dirty` marker whenever
  tracked files are edited.
- **FR-007**: When neither a build stamp nor usable source history is available, the
  application MUST report the declared release number alone.
- **FR-008**: Determining the version MUST NOT raise an error that reaches a page render
  or the health endpoint under any of the conditions in FR-006 and FR-007.
- **FR-009**: The version MUST be determined once per application start, not once per
  request.
- **FR-010**: The declared release number MUST remain the existing single source of
  truth for the project's release number; this feature adds a suffix to it and does not
  introduce a second place to record it.
- **FR-011**: The two image build paths MUST stay consistent with each other in how they
  stamp, in the same way the project already requires their build configuration to be
  kept in step.

### Key Entities

- **Declared release number**: the project's `MAJOR.MINOR.PATCH` release number, recorded
  in one place in the project metadata and already the basis of the version shown today.
- **Build stamp**: information baked into a built artifact at build time recording which
  commit it was built from and whether the build was a release. Absent from a plain
  working copy.
- **Reported version**: what the owner sees — the declared release number with at most a
  commit suffix and at most a dirty marker.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given two images built from two different commits with the same declared
  release number, the owner can tell them apart by reading the footer of either one —
  the reported versions differ.
- **SC-002**: The owner can take the suffix shown in the footer and locate the exact
  commit it names in the project history, in one lookup, with no other information.
- **SC-003**: An image built for a release reports a version that contains nothing but
  the release number, so a release build is distinguishable from a CI build at a glance.
- **SC-004**: The version shown in the footer and the version returned by the health
  endpoint are identical in every one of the situations enumerated in the requirements.
- **SC-005**: In all five provenance situations (CI build, release build, tagged working
  copy, untagged working copy, edited working copy) and all three failure situations (no
  stamp and no history, history tooling absent, history tooling failing), the application
  starts and serves pages without error.
- **SC-006**: Page render time is unchanged — no per-request work is added to determine
  the version.

## Assumptions

- The footer's `v` prefix is presentation and stays in the page template; the version
  string itself does not carry it. This matches what the page renders today.
- The commit suffix uses seven characters, as in the issue's worked example.
- The separator between release number and suffix is a hyphen, as in the issue's worked
  example (`0.1.1-6d15bde`).
- A "release" working copy state means positioned exactly on the tag whose name
  corresponds to the declared release number — the project's release process already
  creates exactly such a tag per release.
- The existing project rule that the two image build paths be kept in step applies to
  this change as well.
- The `versionfinder` package named in the issue is offered as prior art rather than as a
  required dependency. Whether to depend on it is a planning decision, weighed against
  the project's standing preference for the standard library and existing dependencies.
- Story 2 is conditional. If planning finds it cannot be delivered without materially
  complicating the work, it is dropped and Story 1 ships alone; that decision and its
  reasoning are recorded in the plan.
