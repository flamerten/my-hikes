# MyHikes

A static site generator that turns GPX tracks and photos into map-based hike pages, deployed to GitHub Pages. Thumbnails are stored in Cloudflare R2 and served directly from there — they are never committed to the repo.

## Status

| Phase | Description | Status |
|---|---|---|
| 1 | Single hike → HTML page with map, photo pins, elevation chart, stats | **Complete** |
| 2 | Multi-hike — homepage with hike cards, `meta.json` sidecars | **Complete** |
| 3 | Polish & deploy — Open Graph, `index.json` search, mobile, GitHub Actions | **In progress** |

---

## One-time setup

### R2 bucket

1. In the Cloudflare dashboard: **R2 → Create bucket** (e.g. `myhikes-thumbs`).
2. Enable **Public access** on the bucket (Bucket Settings → Public Access → Allow).
3. Create an API token: **R2 → Manage R2 API Tokens → Create API Token**, with Object Read & Write on the bucket.

### Local environment

Create a `.env` file in the project root (already gitignored) with these values:

```bash
CF_R2_BUCKET=myhikes-thumbs
CF_R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
CF_R2_ACCESS_KEY_ID=<access_key>
CF_R2_SECRET_ACCESS_KEY=<secret_key>
CF_R2_PUBLIC_URL=https://pub-<hash>.r2.dev
```

Verify the credentials work before running a real build:

```bash
source .env   # or: set -a && . .env && set +a
uv run hikes r2-check
# ok: connected to bucket 'myhikes-thumbs' (0 object(s) sampled)
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

# 2. Drop files in manually:
#    raw/2026-05-01-trail-name/routes/  ← .gpx exports from Garmin
#    raw/2026-05-01-trail-name/media/   ← original JPEGs and/or MP4/MOV/AVI videos (gitignored)
#    edit raw/2026-05-01-trail-name/hike.toml  ← fill in title, description, tags, cover, tz_offset
```

### Preview locally (thumbnails served from R2)

```bash
source .env   # load R2 credentials
uv run hikes build --hike 2026-05-01-trail-name
uv run hikes build-index
uv run hikes serve
# open http://localhost:8000/hikes/2026-05-01-trail-name/
# thumbnails load from R2 — internet access required
```

### Preview locally (thumbnails served locally, no R2 needed)

```bash
uv run hikes build --hike 2026-05-01-trail-name --no-r2
uv run hikes build-index
uv run hikes serve
# open http://localhost:8000/hikes/2026-05-01-trail-name/
# thumbnails load from site/thumbs/ — works fully offline
```

> **Always preview over HTTP, not by opening the file directly.** OSM tile servers
> block `file://` requests, and `/static/` paths resolve incorrectly outside a server.

---

## Deploying to GitHub Pages

The build must be run locally because `raw/` (original media) is gitignored and unavailable in CI. CI only uploads the pre-built `site/` directory.

```bash
# 1. Load R2 credentials
source .env

# 2. Build each hike (uploads thumbnails to R2, writes R2 URLs into HTML)
uv run hikes build --hike <slug> --base-url /my-hikes

# 3. Rebuild the home page
uv run hikes build-index --base-url /my-hikes

# 4. Commit site/ (site/thumbs/ is gitignored — only HTML + GPX + static assets)
git add site/
git commit -m "build: <slug>"
git push
```

GitHub Actions picks up the push, uploads `site/` to Pages, and the live site is updated. Thumbnails are already in R2 from step 2 and load directly in the browser from there.

---

## Commands

```bash
uv run hikes new <slug>                             # scaffold raw/<slug>/ with hike.toml template
uv run hikes build --hike <slug>                    # build hike, upload thumbs to R2, embed R2 URLs
uv run hikes build --hike <slug> --no-r2            # build hike with local thumbnail paths (no upload)
uv run hikes build --hike <slug> --base-url <url>   # prefix all asset paths (required for GitHub Pages)
uv run hikes build-index                            # rebuild site/index.html from all meta.json sidecars
uv run hikes build-index --base-url <url>           # same, with asset path prefix
uv run hikes serve [--port 8000]                    # serve site/ over HTTP for local preview
uv run hikes r2-check                               # verify R2 credentials and bucket connectivity
```

---

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
  r2.py              # Cloudflare R2 upload helpers (boto3 S3-compatible)
  cli.py             # CLI entry point (build / build-index / new / serve / r2-check)

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
  test_r2.py
  test_cli.py
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

**Optional:** Install `ffmpeg` (and `ffprobe`) for video poster-frame extraction. If not on `PATH`, video files in `media/` are silently skipped during build. Videos that lack a `creation_time` metadata tag fall back to the file's modification time instead of being skipped.
