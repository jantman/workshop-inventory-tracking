# General

* You must source the virtualenv (`venv/`) before running any commands that rely on project dependencies.

# Testing

* Run tests via the `nox` test runner, not by running `pytest` directly
* The `e2e` test session must have a timeout of 20 minutes set on your bash tool. This timeout is set on your bash tool, not on the command line.
