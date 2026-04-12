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
| `UNIFY_BUILD_PLAN.md` | Unified build plan: `site.toml` config, `build-all` command, prefix-stripping `serve`. **Complete.** |

When working on this project, read the relevant `claude_docs/` file before modifying a module.

## Commands

```bash
uv run hikes build-all                         # build all hikes + home page (reads site.toml for base_url)
uv run hikes build --hike SLUG                 # build one hike (reads site.toml for base_url)
uv run hikes build-index                       # rebuild home page only
uv run hikes build-all --no-r2                 # build without R2 (local thumbs, works offline)
uv run hikes build --hike SLUG --no-r2         # build one hike without R2
uv run hikes build --hike SLUG --base-url URL  # override base_url from site.toml
uv run hikes serve [--port N]                  # serve site/ — strips base_url prefix automatically
uv run hikes new SLUG                          # scaffold raw/<slug>/ with hike.toml template
uv run hikes r2-check                          # verify R2 credentials and bucket connectivity
uv run pytest tests/                           # run all tests
```

`base_url` is stored once in `site.toml` (committed). No `--base-url` flag needed in normal use.

Typical workflow when adding a hike:
```bash
uv run hikes build --hike <slug>   # reads site.toml, uploads thumbnails to R2, writes meta.json
uv run hikes build-index           # rebuilds home page
uv run hikes serve                 # preview at http://localhost:8000/my-hikes/
git add site/ && git commit -m "build: <slug>" && git push
```

Full rebuild and deploy:
```bash
uv run hikes build-all
uv run hikes serve                 # verify locally
git add site/ && git commit -m "build: rebuild all" && git push
```

Offline preview (no R2 credentials needed, do not deploy this build):
```bash
uv run hikes build-all --no-r2
uv run hikes serve
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
| `cli.py` | argparse entry point; `build`, `build-all`, `build-index`, `new`, `serve`, `r2-check` commands | Done |
| `config.py` | Parses `hike.toml` → `HikeMeta`; reads `site.toml` → `base_url` | Done |
| `gpx.py` | Parses GPX → `Route`/`TrackPoint`; filters GPS blips; computes `RouteStats` | Done |
| `photos.py` | Reads EXIF, extracts video poster frames (ffmpeg), matches media to track positions, generates thumbnails | Done |
| `render.py` | GeoJSON helpers + Jinja2 rendering → hike pages, meta.json sidecars, home page | Done |
| `r2.py` | Cloudflare R2 upload helpers: `upload_thumbnail`, `thumb_url`, `r2_configured`, `get_r2_client` | Done |
| `index.py` | Builds `site/index.json` for client-side Fuse.js search | **Pending** |

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
