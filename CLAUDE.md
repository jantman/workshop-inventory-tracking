# Project Context

This is a single-user application for tracking materials and supplies in a hobby workshop. It runs on a home network and is reachable only from the LAN. Size every decision to that.

* **Simplicity is the first principle.** Build for the requirement in front of you. No abstraction for a single implementation, no configuration knob for a future that hasn't arrived.
* **Don't optimize without a measurement.** Caching, batching, async, and background jobs require an observed problem. The 1% coverage gate and the sub-second unit suite are deliberate — don't "fix" them.
* **Don't add scale machinery.** No multi-tenancy, user accounts, roles, rate limiting, or queues. The app has no login and doesn't need one.
* **Don't harden against the Internet.** No anonymous attackers, no hostile input, no sanitization layers, no CVE triage as a merge gate. Security effort goes to not losing data and not committing secrets (`.env`, `credentials.json`, `token.json` stay untracked). Validate input because bad data breaks the inventory, not because it might be malicious.
* **The exception:** simplicity never justifies risking data integrity — `Decimal` (never `float`) for measurements, MariaDB as the source of truth with Alembic migrations, and the item history invariants (one active row per JA ID, retained shortening history) are non-negotiable.

Full governance: `.specify/memory/constitution.md`. Stack details and code patterns: `_bmad-output/project-context.md`.

# General

* You must source the virtualenv (`venv/`) before running any commands that rely on project dependencies.

# Testing

* Run tests via the `nox` test runner, not by running `pytest` directly
* The `e2e` test session must have a timeout of 20 minutes set on your bash tool. This timeout is set on your bash tool, not on the command line.
