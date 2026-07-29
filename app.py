#!/usr/bin/env python3
"""
Development server entry point for Workshop Inventory Tracking application.

This script provides a convenient way to run the Flask development server
with debug mode enabled. It uses the centralized create_app factory from
the app module to ensure consistency between development, test, and production
environments.

For production deployment, use wsgi.py with a proper WSGI server like Gunicorn.

Usage:
    python app.py

The server will start on http://127.0.0.1:5000 with debug mode enabled.
"""

import os

if __name__ == '__main__':
    # `app.run(debug=True)` below turns the debugger and reloader on, but it
    # does so LONG after `create_app()` has read the config -- so without this
    # block the app this script builds is configured as a NON-debug app that
    # merely happens to run with the debugger. That incoherence became
    # load-bearing with `app/secret_key_guard.py`: a non-debug app refuses to
    # start on the SECRET_KEY fallback, so `python app.py` on a fresh checkout
    # with no `.env` would die rather than serve, while `flask run` -- which
    # picks `FLASK_DEBUG` up from `.flaskenv`, a file only the Flask CLI reads
    # -- kept working. Declaring the intent in the environment first is what
    # makes this script agree with the app it builds.
    #
    # `.env` is loaded HERE, and not left to `config.py`, because the order
    # decides who wins. `load_dotenv` defaults to `override=False`, so a value
    # this block writes into `os.environ` first would beat the operator's own
    # `FLASK_DEBUG` when `config.py` loads the same file during the import
    # below -- silently, and in the fail-OPEN direction, since DEBUG=True is
    # what downgrades the SECRET_KEY refusal to a log line. Loading `.env`
    # first is what makes "an explicit FLASK_DEBUG=0 wins" true of the `.env`
    # the documentation tells operators to write, and not only of a shell
    # variable. `config.py`'s own `load_dotenv` then finds every value already
    # set and changes nothing.
    #
    # A default, not an override -- and BLANK counts as unset: `FLASK_DEBUG=`
    # is a value as far as `os.environ` (or `setdefault`) is concerned, but
    # `config.py` parses it as OFF, so treating it as "already decided" would
    # leave this script refusing to boot for exactly the reason this block
    # exists to prevent.
    #
    # Inside `__main__`, not at module scope: this mutates the environment of
    # the whole PROCESS, and turning DEBUG on process-wide is precisely what
    # disarms the SECRET_KEY refusal. Confining it to the case where this file
    # is being RUN means no importer of it can flip that switch as a side
    # effect. (The `app/` package shadows this module for a plain
    # `import app`, so such an importer has to reach for the file by path --
    # but the whole point of a security control is not to depend on that.)
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.abspath(os.path.dirname(__file__)),
                             '.env'))
    if not os.environ.get('FLASK_DEBUG', '').strip():
        os.environ['FLASK_DEBUG'] = '1'

    # Imported here for the same reason, and it must stay AFTER the lines
    # above: `config.py` reads FLASK_DEBUG while `class Config` executes, i.e.
    # during this import.
    from app import create_app

    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=5000)
