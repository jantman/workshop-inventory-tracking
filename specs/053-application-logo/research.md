# Research: Application Logo

## 1. Motif

- **Decision**: A white hex nut (a regular hexagon with a round hole), point up, on a
  rounded-square tile in dark Bootstrap blue `#0a58ca`.
- **Rationale**: A hex nut is the most recognizable piece of workshop hardware, and it
  survives 16 px: at that size it is a white hexagon ring about 10 px across with a 5 px hole,
  and nothing finer. We prototyped it on a 16-unit grid and viewed it at 16/32/128 px on the
  navbar's `#0d6efd`, on white and on `#202124` (a dark tab strip). The ring stays readable at
  16 px, and the tile stands slightly apart from the navbar's own blue without clashing. The
  tile also gives the white nut a background of its own, which it needs on a light tab strip.
- **Alternatives considered**:
  - *Small-parts drawer cabinet* (three drawers with pulls): it says "inventory", but at
    16 px it reads as a list, menu or server-rack icon.
  - *Nut plus a tag or a letter*: two ideas do not fit in 16 px; the extra detail turns to
    mush.
  - *Bootstrap's `bi-nut` glyph*: it is a stock glyph, which FR-003 excludes. Our own shape
    is also bolder at 16 px.

## 2. Master format and where it lives

- **Decision**: A hand-written SVG with `viewBox="0 0 16 16"`, two elements, at
  `app/static/img/logo.svg`. The flat vertical sides fall on whole units (x = 3 and 13), so
  every render that is a multiple of 16 px (16, 32, 48, 128) puts those edges on pixel
  boundaries.
- **Rationale**: The issue asks for "a real asset checked into the repository" rather than
  a script's output. A two-element SVG is a real asset, can be edited by hand, and the
  application serves it as-is.
- **Alternatives**: a PNG master (not editable, and blurry when scaled up); a generator
  script (what the issue is replacing).

## 3. Deriving rasters

- **Decision**: Render with `rsvg-convert -w N -h N logo.svg`, and pack the ICO with
  `magick 16.png 32.png 48.png favicon.ico`. The exact commands go in an XML comment at the
  top of `logo.svg`. The outputs are committed.
- **Rationale**: This is one-off asset production, like exporting from an image editor.
  Committing the outputs keeps "load the extension directory unpacked" and "run the app"
  free of any build step (048 took the same position on the manifest version).
- **Alternatives**: rendering at runtime or build time with a new Python dependency such as
  cairosvg. Rejected: that is a dependency and a build step for four files that change once.

## 4. Favicon declaration

- **Decision**: In `base.html`:
  `<link rel="icon" href="img/logo.svg" type="image/svg+xml">`, then
  `<link rel="icon" href="img/favicon.ico" sizes="16x16 32x32 48x48">`. Also a route
  `GET /favicon.ico` that sends the same ICO.
- **Rationale**: Current Chrome and Firefox use the SVG. Browsers without SVG favicons take
  the ICO. Some requests never read a page's `<head>`: a JSON endpoint opened directly, a
  PDF, a bookmark import. Those ask for `/favicon.ico`, and today they 404, which also puts
  noise in the log. The route is the smallest thing that answers them.
- **Alternatives**: an `apple-touch-icon` or web manifest (not a requirement: the
  application is used on the LAN, not installed as a PWA); a redirect (sending the file is
  no more code).

## 5. Navbar and banner

- **Decision**: `<img src="img/logo.svg" class="brand-logo" alt="">` in place of
  `<i class="bi bi-tools">`, in both places. `.brand-logo` is sized in `em` (1.5em, aligned
  to the middle), so it follows the brand's font size, including the smaller brand below
  768 px and the banner's `display-4` heading. `alt=""` because the text beside it already
  names the application; a screen reader should not say it twice.
- **Rationale**: This keeps the brand's existing size and layout. Only the mark changes.

## 6. The extension

- **Decision**: Overwrite `extension/icons/icon-{16,48,128}.png` in place. The manifest is
  unchanged. Add no documentation text: `docs/capture-extension.md` already says to reload
  the extension whenever the application is upgraded, and the new icon arrives by that same
  reload.
