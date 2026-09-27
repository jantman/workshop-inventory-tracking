# Implementation Plan: Application Logo

**Branch**: `robot-army/issue-169-design-a-logo-for-the-application-and` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/053-application-logo/spec.md`

## Summary

Draw one logo by hand as a 16-unit SVG: a white hex nut on a rounded, dark-blue tile.
Check it in as `app/static/img/logo.svg`. It is the master. Derive fixed-size PNGs from it
once with `rsvg-convert`, and commit them: a multi-size `favicon.ico` for browsers and the
extension's three `icon-{16,48,128}.png`. `base.html` gains `<link rel="icon">` (SVG first,
ICO fallback). The navbar brand and the home banner swap the `bi-tools` glyph for an
`<img>` of the logo. One route serves `/favicon.ico` for clients that ask the root path
directly. Regenerate the documentation screenshots and commit only the ones whose content
changed.

## Technical Context

**Language/Version**: Python 3.13 (Flask route), Jinja2 templates, hand-written SVG

**Primary Dependencies**: Flask 3.1, Bootstrap 5.3. Nothing new. `rsvg-convert` and
ImageMagick are used once, on the developer's machine, to derive the rasters. They are not
dependencies of the application or of CI. Pillow (already in `requirements.txt`) reads PNG
sizes in the tests.

**Storage**: N/A

**Testing**: pytest via `nox -s tests` (unit), `nox -s e2e`; screenshots via `nox -s screenshots_headless`

**Target Platform**: Linux server on a home LAN; Chrome/Firefox; Chrome MV3 extension

**Project Type**: Server-rendered web application plus a browser extension

**Performance Goals**: N/A

**Constraints**: The logo must be legible at 16 px (FR-002). Chrome MV3 manifest icons must
be PNG, so the extension cannot use the SVG directly.

**Scale/Scope**: 1 SVG, 4 derived rasters, 2 template edits, 1 CSS rule, 1 route, a unit test
file, screenshot refresh

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Simplicity First | ✅ Static files and one line of `<link>`. No build step: the rasters are committed, and the command that made them is written in a comment inside the SVG. No new dependency: the render tools are one-off developer tools, like an image editor. The one route (`/favicon.ico`) is three lines. |
| II. Layered Architecture | ✅ The route only serves a static file. No storage or service is involved. |
| III. Exact Numerics | ✅ Not touched. |
| IV. Test Discipline | ✅ Unit tests cover the head declaration, the favicon being served, the navbar image, and the extension icon sizes. No new e2e test: nothing is interactive. The existing e2e suite still has to pass because it loads the extension and every page. Everything runs through `nox`. |
| V. MariaDB Source of Truth | ✅ No schema change. |
| VI. Item History Invariants | ✅ Not touched. |
| Technology Constraints | ✅ Server-rendered, no frontend framework or build step. |
| Screenshots gate | ⚠️→✅ `app/templates/**` and `app/static/css/**` change, so screenshots are regenerated with `nox -s screenshots_headless` and must pass `screenshots_verify`. Following #77, commit only the files whose pixels changed in the navbar/banner, not the files that differ only by the build-version footer. |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/053-application-logo/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── logo-assets.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
app/static/img/logo.svg          # NEW — the master (hand-written SVG; regen command in a comment)
app/static/img/favicon.ico       # NEW — derived: 16, 32, 48 px
extension/icons/icon-16.png      # REPLACED — derived
extension/icons/icon-48.png      # REPLACED — derived
extension/icons/icon-128.png     # REPLACED — derived
app/templates/base.html          # <link rel="icon"> ×2; navbar brand <img> replaces bi-tools
app/templates/index.html         # banner heading <img> replaces bi-tools
app/static/css/main.css          # .brand-logo sizing (navbar + banner)
app/main/routes.py               # GET /favicon.ico → static favicon.ico
tests/unit/test_logo.py          # NEW — head declaration, served icon, navbar, extension sizes
docs/images/screenshots/**       # regenerated; only really-changed files committed
```

**Structure Decision**: The master is placed where the application serves it
(`app/static/img/`), so the navbar and the SVG favicon use the master itself and nothing
there can drift. The extension cannot reference files outside its own directory and needs
PNGs, so it keeps its own derived copies at the paths the manifest already declares. The
manifest does not change.

## Complexity Tracking

None.
