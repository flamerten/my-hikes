# MyHikes

A static site generator that turns GPX tracks and photos into map-based hike pages, deployed to GitHub Pages.

## Status

| Phase | Description | Status |
|---|---|---|
| 1 | Single hike → HTML page with map, photo pins, elevation chart, stats | **Complete** |
| 2 | Multi-hike — homepage with hike cards, `meta.json` sidecars | **Complete** |
| 3 | Polish & deploy — Open Graph, `index.json` search, mobile, GitHub Actions | Planned |

## Adding a new hike

```bash
# 1. Scaffold the directory and hike.toml
uv run hikes new 2026-05-01-trail-name

# 2. Drop files in manually:
#    raw/2026-05-01-trail-name/routes/  ← .gpx exports from Garmin
#    raw/2026-05-01-trail-name/media/   ← original JPEGs and/or MP4/MOV/AVI videos (gitignored)
#    edit raw/2026-05-01-trail-name/hike.toml  ← fill in title, description, tags, cover, tz_offset

# 3. Build and preview
uv run hikes build --hike 2026-05-01-trail-name
uv run hikes build-index
uv run hikes serve
# open http://localhost:8000/hikes/2026-05-01-trail-name/
```

> **Always preview over HTTP, not by opening the file directly.** OSM tile servers
> block `file://` requests, and `/static/` paths resolve incorrectly outside a server.

## Commands

```bash
uv run hikes new <slug>          # scaffold raw/<slug>/ with hike.toml template
uv run hikes build --hike <slug> # parse GPX + photos → site/hikes/<slug>/index.html + meta.json
uv run hikes build-index         # rebuild site/index.html home page from all meta.json sidecars
uv run hikes serve [--port 8000] # serve site/ over HTTP for local preview
```

## Repository layout

```
raw/<slug>/
  routes/*.gpx       # one GPX file per day/activity (Garmin export)
  media/             # original JPEGs and/or MP4/MOV/AVI videos — gitignored
  hike.toml          # title, date, description, tags, cover, tz_offset

generator/
  models.py          # shared dataclasses and haversine helper
  config.py          # hike.toml → HikeMeta
  gpx.py             # GPX parsing, blip filtering, stats
  photos.py          # EXIF extraction, thumbnail generation, photo-to-track matching
  render.py          # GeoJSON helpers and Jinja2 rendering → hike pages, meta.json sidecars, home page
  cli.py             # CLI entry point (build / new / serve)

templates/
  base.html          # CDN links for Leaflet + Chart.js, block structure
  hike.html          # per-hike page
  home.html          # home page (hike cards grid)

static/
  js/hike.js         # Leaflet map, Chart.js elevation profile, photo gallery grid

tests/
  conftest.py        # shared fixtures
  test_config.py
  test_gpx.py
  test_photos.py
  test_render.py
```

### `hike.toml` schema

```toml
title       = "Jungle Trek"
date        = "2026-04-01"
description = "5-day jungle trek through Gunung Leuser with a rafting finish."
tags        = ["jungle", "multi-day", "sumatra", "rafting"]
cover       = "PXL_20260401_013612693.jpg"
tz_offset   = "+07:00"      # local time offset for matching EXIF timestamps to GPX
trim_start_m = 0            # metres to trim from route start (privacy)
trim_end_m   = 0            # metres to trim from route end (privacy)
```

## Data models

```
TrackPoint   lat, lon, ele, time (UTC-aware datetime)
Route        slug, name, points: list[TrackPoint], stats: RouteStats
RouteStats   distance_m, ele_gain_m, ele_loss_m, duration, moving_time,
             avg_pace_min_km, max_ele_m, min_ele_m
Photo        path, filename, timestamp_local, timestamp_utc,
             lat/lon (None for non-GPS cameras),
             matched_point, match_method ("gps"|"timestamp"|"unmatched"),
             thumb_path, thumb_width, thumb_height,
             is_video (True for frames extracted from video files)
HikeMeta     slug, title, date, description, tags, cover, tz_offset,
             trim_start_m, trim_end_m
Hike         meta, routes, photos
```

## Running tests

```bash
uv run pytest tests/
```

## Development setup

```bash
uv sync
```

Requires Python 3.13+. Dependencies are managed with `uv` and locked in `uv.lock`.

**Optional:** Install `ffmpeg` (and `ffprobe`) for video poster-frame extraction. If not on `PATH`, video files in `media/` are silently skipped during build. Videos that lack a `creation_time` metadata tag fall back to the file's modification time instead of being skipped.
