# MyHikes

A static site generator that turns GPX tracks and photos into map-based hike pages, deployed to GitHub Pages. Thumbnails are stored in Cloudflare R2 and served directly from there — they are never committed to the repo.

## Status

| Phase | Description | Status |
|---|---|---|
| 1 | Single hike → HTML page with map, photo pins, elevation chart, stats | **Complete** |
| 2 | Multi-hike — homepage with hike cards, `meta.json` sidecars | **Complete** |
| 3 | Polish & deploy — Open Graph, `index.json` search, mobile, GitHub Actions | **Complete** |

---

## One-time setup

### R2 bucket

1. In the Cloudflare dashboard: **R2 → Create bucket** (e.g. `myhikes`).
2. Enable **Public access** on the bucket (Bucket Settings → Public Access → Allow).
3. Create an API token: **R2 → Manage R2 API Tokens → Create API Token**, with Object Read & Write on the bucket.

### Local environment

Create a `.env` file in the project root (already gitignored) with these values:

```bash
CF_R2_BUCKET=myhikes
CF_R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
CF_R2_ACCESS_KEY_ID=<access_key>
CF_R2_SECRET_ACCESS_KEY=<secret_key>
CF_R2_PUBLIC_URL=https://pub-<hash>.r2.dev/<bucket>
```

Verify the credentials work before running a real build:

```bash
uv run hikes r2-check
# ok: connected to bucket 'myhikes' (0 object(s) sampled)
```

### GitHub secrets

Add the same five values as repository secrets (**Settings → Secrets and variables → Actions**):
`CF_R2_BUCKET`, `CF_R2_ENDPOINT_URL`, `CF_R2_ACCESS_KEY_ID`, `CF_R2_SECRET_ACCESS_KEY`, `CF_R2_PUBLIC_URL`.

In **Settings → Pages → Source**, select **GitHub Actions**.

---

## Adding a new hike

```bash
# 1. Scaffold the directory and hike.toml
uv run hikes new 2026-05-01-trail-name

# 2. Drop files in:
#    raw/2026-05-01-trail-name/routes/  ← .gpx exports from Garmin
#    raw/2026-05-01-trail-name/media/   ← original JPEGs and/or MP4/MOV/AVI videos (gitignored)
#    Edit raw/2026-05-01-trail-name/hike.toml — fill in title, description, tags, cover, tz_offset

# 3. Build and preview
uv run hikes build --hike 2026-05-01-trail-name
uv run hikes build-index
uv run hikes serve
# open http://localhost:8000/my-hikes/hikes/2026-05-01-trail-name/
# thumbnails load from R2 — internet access required for preview
```

> **Always preview over HTTP, not by opening the file directly.** OSM tile servers
> block `file://` requests, and asset paths resolve incorrectly outside a server.

### Preview without R2 (offline / no credentials)

```bash
uv run hikes build --hike 2026-05-01-trail-name --no-r2
uv run hikes build-index
uv run hikes serve
# thumbnails served from site/thumbs/ — works fully offline
# do not deploy a --no-r2 build to GitHub Pages
```

---

## Deploying to GitHub Pages

The build must run locally because `raw/media/` (original photos/videos) is gitignored and unavailable to CI. The GitHub Actions workflow only uploads the pre-built `site/` directory.

`base_url` is configured once in `site.toml` (committed). Every build command reads it automatically — no flags to remember.

```bash
# Rebuild every hike and the home page, then deploy
uv run hikes build-all
git add site/
git commit -m "build: <description>"
git push
# CI uploads site/ to Pages; thumbnails are already in R2
```

Or, if you only changed one hike:

```bash
uv run hikes build --hike <slug>
uv run hikes build-index
git add site/
git commit -m "build: <slug>"
git push
```

GitHub Actions picks up the push, uploads `site/` to Pages, and the live site is updated.

---

## Commands

### Common workflows

```bash
uv run hikes build-all                      # build all hikes + home page, upload thumbs to R2
uv run hikes build --hike <slug>            # build one hike, upload its thumbs to R2
uv run hikes build-index                    # rebuild home page from existing meta.json sidecars
uv run hikes serve                          # preview site/ at http://localhost:8000/my-hikes/
```

`base_url` is read automatically from `site.toml` — you never need to pass `--base-url` in normal use.

### Flags

```bash
uv run hikes build --hike <slug> --no-r2       # build with local thumbnails (no upload, works offline)
uv run hikes build-all --no-r2                 # same, for all hikes
uv run hikes build --hike <slug> --base-url /override   # override base_url from site.toml
```

### Other

```bash
uv run hikes new <slug>                     # scaffold raw/<slug>/ with hike.toml template
uv run hikes r2-check                       # verify R2 credentials and bucket connectivity
uv run pytest tests/                        # run all tests
```

### R2 bucket management (direct CLI)

```bash
uv run generator/r2.py list                          # list all objects in the bucket
uv run generator/r2.py list --prefix myhikes/thumbs/ # filter by key prefix
uv run generator/r2.py delete <prefix>               # delete all objects matching a key prefix (prompts per page)
```

---

## Repository layout

```
site.toml          # committed project config — sets base_url for all build commands

raw/<slug>/
  routes/*.gpx     # one GPX file per day/activity (Garmin export)
  media/           # original JPEGs and/or MP4/MOV/AVI videos — gitignored
  hike.toml        # title, date, description, tags, cover, tz_offset

generator/
  models.py        # shared dataclasses and haversine helper
  config.py        # hike.toml → HikeMeta; site.toml → project config
  gpx.py           # GPX parsing, blip filtering, stats
  photos.py        # EXIF extraction, thumbnail generation, photo-to-track matching
  render.py        # GeoJSON helpers and Jinja2 rendering → hike pages, meta.json sidecars, home page
  r2.py            # Cloudflare R2 upload helpers (boto3 S3-compatible)
  cli.py           # CLI entry point (build / build-all / build-index / new / serve / r2-check)

templates/
  base.html        # CDN links for Leaflet + Chart.js, block structure
  hike.html        # per-hike page
  home.html        # home page (hike cards grid)

static/
  js/hike.js       # Leaflet map, Chart.js elevation profile, photo gallery grid

tests/
  conftest.py      # shared fixtures
  test_config.py
  test_gpx.py
  test_photos.py
  test_render.py
  test_r2.py
  test_cli.py
  test_site_config.py
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

### `site.toml` schema

```toml
base_url = "/my-hikes"   # repository name as deployed on GitHub Pages
```

---

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

---

## Running tests

```bash
uv run pytest tests/
```

---

## Development setup

```bash
uv sync
```

Requires Python 3.13+. Dependencies are managed with `uv` and locked in `uv.lock`.

**Optional:** Install `ffmpeg` (and `ffprobe`) for video poster-frame extraction. If not on `PATH`, video files in `media/` are silently skipped during build.
