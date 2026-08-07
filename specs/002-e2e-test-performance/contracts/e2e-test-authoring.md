# Contract: Writing E2E Tests — superseded

**Feature**: `specs/002-e2e-test-performance` | **Superseded**: 2026-08-06 by
`specs/003-e2e-remove-timed-waits`

**The rules for writing e2e tests now live in the "Writing e2e tests" section of `CLAUDE.md`.**
Go there. Nothing on this page is maintained.

This document was the normative source when feature 002 landed. Feature 003 moved it, for two
reasons:

- Four documents stated the rules and three of them pointed here, so the rules had four places to
  drift apart in. There is now one: `CLAUDE.md` for practice, `.specify/memory/constitution.md`
  §IV for the governing rule and its one exception, and no sentence in both.
- Sending a contributor into a closed feature's spec directory to learn how to write a test made
  the rules look like a record of one change rather than a standing requirement.

The original text is in git history — `git log --follow` this path — along with the measurements
each rule traced to. It is preserved as evidence, not as instructions: it describes 127 fixed waits
as tolerated-for-now, which stopped being true when feature 003 removed them.
