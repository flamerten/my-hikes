# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation

The `claude_docs/` directory contains design documents for Claude's reference:

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | Detailed module interfaces, data flow diagram, and design decisions. The authoritative spec for how all generator modules interact. |
| `PROJECT_PLAN.md` | High-level goals, feature list, tech stack, repo structure, and execution phases. Useful for understanding scope and future direction. |

When working on this project, read the relevant `claude_docs/` file before modifying a module.

## Commands

```bash
# Run the CLI
uv run hikes build              # build all hikes
uv run hikes build --hike SLUG  # build one hike
uv run hikes new                # scaffold a new hike directory
uv run hikes deploy             # build + push to gh-pages

# Run main entry point (stub only, real entry is generator/cli.py)
uv run python main.py
```

Always use `uv run python` — never bare `python` or `python3`.

## Architecture

This is a static site generator that turns GPX tracks + photos into map-based hike pages deployed to GitHub Pages.

**Input:** `raw/<slug>/` directories, each containing:
- `routes/*.gpx` — one GPX file per day/activity (exported from Garmin)
- `photos/*.jpg` — originals (gitignored)
- `hike.toml` — title, date, description, tags, cover photo, `tz_offset`

**Output:** `site/` (gitignored, deployed via GitHub Actions to `gh-pages`)

**Photo storage:** Only compressed thumbnails are stored. Thumbnails are generated during the build and deployed to GitHub Pages alongside the HTML. Original photos are gitignored and never uploaded anywhere.

### Module responsibilities (`generator/`)

| Module | Role |
|---|---|
| `cli.py` | argparse entry point; orchestrates the build pipeline |
| `config.py` | Parses `hike.toml` → `HikeMeta` |
| `gpx.py` | Parses GPX → `Route`/`TrackPoint`; filters GPS blips; computes `RouteStats` |
| `photos.py` | Reads EXIF, matches photos to track positions, generates thumbnails |
| `render.py` | Jinja2 rendering → `site/hikes/<slug>/index.html`, homepage, search page |
| `index.py` | Builds `site/index.json` for client-side Fuse.js search |

### Core data models

```
TrackPoint: lat, lon, ele, time (UTC-aware datetime)
Route: slug, name, points: list[TrackPoint], stats: RouteStats
Photo: path, timestamp_local, timestamp_utc, lat/lon (optional), matched_point, match_method ("gps"|"timestamp"|"unmatched"), thumb_path
HikeMeta: slug, title, date, description, tags, cover, tz_offset, trim_start_m, trim_end_m
Hike: meta, routes: list[Route], photos: list[Photo]
```

### Key design decisions

- **Multiple routes per hike:** A hike is always `list[Route]`. Photo matching runs across the combined timeline of all routes, sorted by start time.
- **GPS blip filtering:** `filter_blips()` removes points implying speed > 55 m/s (~200 km/h). Runs immediately after GPX parsing, before stats or photo matching.
- **Two-tier photo matching:** Photos with GPS EXIF (Pixel) snap to nearest trackpoint by Haversine distance (max 500 m). Photos without GPS (OnePlus) interpolate position from `timestamp_utc`. Unmatched photos still appear in the gallery without a map pin.
- **UTC normalisation:** All internal datetimes are UTC-aware. `tz_offset` is applied once in `load_photos` when converting `DateTimeOriginal` → UTC. No timezone arithmetic elsewhere.
- **Stats are per-route and aggregate:** Templates receive both per-route stats (day breakdown table) and a rolled-up aggregate (headline stats bar).

### Frontend stack

Leaflet + OpenStreetMap (map), Chart.js or uPlot (elevation profile), PhotoSwipe (lightbox), Fuse.js (search). Templates live in `templates/`, vendored JS/CSS in `static/`.
