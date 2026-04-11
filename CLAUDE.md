# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation

The `claude_docs/` directory contains design documents for Claude's reference:

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | Detailed module interfaces, data flow diagram, and design decisions. The authoritative spec for how all generator modules interact. |
| `PROJECT_PLAN.md` | High-level goals, feature list, tech stack, repo structure, and execution phases. Useful for understanding scope and future direction. |
| `RENDER_PLAN.md` | TDD implementation plan for Phase 1 rendering. Covers `config.py`, `generate_thumbnail`, `render.py`, templates, and CLI wiring. **Phase 1 is complete** — this file is a record of decisions made. |
| `IMRPVOVE_VISUAL.md` | Visualization enhancement plan (marker clustering, photo lightbox, per-route selection). **All three features are complete.** |
| `HOME_PAGE_PLAN.md` | Home page implementation plan (hike cards, cover photo, meta.json sidecar, `build-index` command). **Complete.** |
| `CLOUDFLARE_PORT.md` | R2 thumbnail storage migration plan (boto3 upload, `--no-r2` flag, `r2-check` command). **Complete.** |

When working on this project, read the relevant `claude_docs/` file before modifying a module.

## Commands

```bash
uv run hikes build --hike SLUG                   # build one hike → uploads thumbs to R2, writes R2 URLs into HTML
uv run hikes build --hike SLUG --no-r2           # build without R2 — thumbnails stay in site/thumbs/, local URLs
uv run hikes build --hike SLUG --base-url /REPO  # prefix all asset paths for GitHub Pages
uv run hikes build-index                         # build site/index.html home page from all meta.json sidecars
uv run hikes build-index --base-url /REPO        # same, with asset path prefix
uv run hikes new SLUG                            # scaffold raw/<slug>/ with hike.toml template
uv run hikes serve [--port N]                    # serve site/ over HTTP (default port 8000)
uv run hikes r2-check                            # verify R2 credentials and bucket connectivity
uv run pytest tests/                             # run all tests
```

Typical workflow when adding a hike (with R2):
```bash
source .env                                      # load CF_R2_* environment variables
uv run hikes build --hike <slug>                 # uploads thumbnails to R2, writes meta.json
uv run hikes build-index                         # rebuilds home page
uv run hikes serve                               # preview at http://localhost:8000/
```

Typical workflow for local-only preview (no R2 upload, thumbnails in site/thumbs/):
```bash
uv run hikes build --hike <slug> --no-r2
uv run hikes build-index
uv run hikes serve
```

Workflow when building for GitHub Pages deployment (repo is `my-hikes`):
```bash
source .env
uv run hikes build --hike <slug> --base-url /my-hikes   # uploads to R2, HTML uses R2 URLs
uv run hikes build-index --base-url /my-hikes
git add site/   # site/thumbs/ is gitignored — only HTML + GPX + static assets are committed
git commit -m "build: <slug>"
git push        # GitHub Actions uploads site/ to Pages; thumbnails already in R2
```

Always use `uv run python` — never bare `python` or `python3`.

## Architecture

This is a static site generator that turns GPX tracks + photos into map-based hike pages deployed to GitHub Pages.

**Input:** `raw/<slug>/` directories, each containing:
- `routes/*.gpx` — one GPX file per day/activity (exported from Garmin)
- `media/` — original JPEGs and/or MP4/MOV/AVI videos (gitignored)
- `hike.toml` — title, date, description, tags, cover photo, `tz_offset`

**Output:** `site/` (committed to `main`, deployed via GitHub Actions to GitHub Pages)

**Thumbnail storage:** Thumbnails are generated locally into `site/thumbs/` (gitignored build cache) and uploaded to Cloudflare R2 during build. The rendered HTML embeds R2 public URLs. Original photos are gitignored and never uploaded anywhere.

### Module responsibilities (`generator/`)

| Module | Role | Status |
|---|---|---|
| `cli.py` | argparse entry point; `build`, `build-index`, `new`, `serve`, `r2-check` commands | Done |
| `config.py` | Parses `hike.toml` → `HikeMeta` | Done |
| `gpx.py` | Parses GPX → `Route`/`TrackPoint`; filters GPS blips; computes `RouteStats` | Done |
| `photos.py` | Reads EXIF, extracts video poster frames (ffmpeg), matches media to track positions, generates thumbnails | Done |
| `render.py` | GeoJSON helpers + Jinja2 rendering → hike pages, meta.json sidecars, home page | Done |
| `r2.py` | Cloudflare R2 upload helpers: `upload_thumbnail`, `thumb_url`, `r2_configured`, `get_r2_client` | Done |
| `index.py` | Builds `site/index.json` for client-side Fuse.js search | **Phase 3** |

### Core data models

```
TrackPoint: lat, lon, ele, time (UTC-aware datetime)
Route: slug, name, points: list[TrackPoint], stats: RouteStats
Photo: path, filename, timestamp_local, timestamp_utc, lat/lon (optional), matched_point, match_method ("gps"|"timestamp"|"unmatched"), thumb_path, thumb_width, thumb_height, is_video
HikeMeta: slug, title, date, description, tags, cover, tz_offset, trim_start_m, trim_end_m
Hike: meta, routes: list[Route], photos: list[Photo]
```

### Key design decisions

- **Multiple routes per hike:** A hike is always `list[Route]`. Photo matching runs across the combined timeline of all routes, sorted by start time.
- **GPS blip filtering:** `filter_blips()` removes points implying speed > 55 m/s (~200 km/h). Runs immediately after GPX parsing, before stats or photo matching.
- **Two-tier photo matching:** Photos with GPS EXIF (Pixel) snap to nearest trackpoint by Haversine distance (max 500 m). Photos without GPS (OnePlus) interpolate position from `timestamp_utc`. Unmatched photos still appear in the gallery without a map pin.
- **UTC normalisation:** All internal datetimes are UTC-aware. `tz_offset` is applied once in `load_photos` when converting `DateTimeOriginal` → UTC and when deriving `timestamp_local` from video `creation_time`. No timezone arithmetic elsewhere.
- **Video poster frames:** `load_photos` also processes MP4/MOV/AVI files in `media/`. It uses `ffprobe` to read `creation_time` (UTC) and duration, then `ffmpeg` to extract the middle frame into `media/.frames/<stem>.jpg`. If `ffmpeg` is not on `PATH`, videos are silently skipped. The extracted JPEG flows through the existing thumbnail and matching pipeline unchanged; `Photo.is_video = True` marks its origin.
- **Stats are per-route and aggregate:** Templates receive both per-route stats (day breakdown table) and a rolled-up aggregate (headline stats bar).
- **R2 thumbnail storage:** `generate_thumbnail()` writes a local JPEG to `site/thumbs/<slug>/` (used as a build cache; gitignored). When R2 is enabled (default), `upload_thumbnail()` checks `head_object` first and skips the upload if the object already exists — re-building an unchanged hike does zero uploads. The rendered HTML embeds the R2 public URL via `thumb_url_base`, not a local path. Pass `--no-r2` to build with local paths instead (useful for offline preview).

### Frontend stack

Leaflet + OpenStreetMap (map), Leaflet.markercluster (photo marker clustering), Chart.js (elevation profile), PhotoSwipe v5 (photo lightbox, loaded as ES module in `hike.js`), Fuse.js (search, Phase 2). Templates live in `templates/`, static JS in `static/js/`.

`hike.js` is loaded as `type="module"` so it can import PhotoSwipe via ESM. Inline data in `hike.html` uses `var` (not `const`) so the globals are accessible from the module scope.
