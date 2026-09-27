# Quickstart: Application Logo

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests      # tests/unit/test_logo.py
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e        # detached; ~20 min
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

## By eye

1. Start the app and open any page. The tab shows the nut on a blue tile (FR-004, SC-001).
2. The navbar shows the nut beside "Workshop Inventory"; clicking it goes home (FR-005).
   Narrow the window below 768 px: the logo shrinks with the text and stays on one line.
3. The home banner heading shows the nut (FR-005).
4. Open `http://<host>/favicon.ico`: the logo (FR-004).
5. On `chrome://extensions`, reload *Workshop Capture*. Its card and the toolbar show the nut
   (FR-006, SC-004).
6. View `extension/icons/icon-16.png` magnified: a hexagon ring with a hole, legible (SC-003).
