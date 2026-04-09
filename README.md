# MyHikes

A static site generator that turns GPX tracks and photos into map-based hike pages, deployed to GitHub Pages.

## Status

| Phase | Description | Status |
|---|---|---|
| 1 | Data processing — GPX parsing, photo EXIF loading, photo-to-track matching | **Complete** |
| 2 | Templating & multi-hike — Jinja2 templates, `hike.toml`, homepage, search index | Planned |
| 3 | Polish & deploy — Open Graph, lightbox, mobile, GitHub Actions | Planned |

## Usage

```bash
uv run hikes build --hike <slug> --tz-offset <offset>
```

Example:

```bash
uv run hikes build --hike 2026-04-jungle-trek --tz-offset +07:00
```

## Repository layout

```
raw/<slug>/
  routes/*.gpx       # one GPX file per day/activity (Garmin export)
  photos/*.jpg       # originals — gitignored

generator/
  models.py          # shared dataclasses and haversine helper
  gpx.py             # GPX parsing, blip filtering, stats
  photos.py          # EXIF extraction, photo-to-track matching
  cli.py             # CLI entry point

tests/
  conftest.py        # shared fixtures
  test_gpx.py
  test_photos.py
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
             thumb_path
HikeMeta     slug, title, date, description, tags, cover, tz_offset,
             trim_start_m, trim_end_m
Hike         meta, routes, photos
```

## Phase 1 — Data processing interfaces

### `generator.gpx`

```python
def load_routes(routes_dir: Path) -> list[Route]
```
Parse every `*.gpx` in `routes_dir`. Applies blip filtering and stat computation. Returns routes sorted by first trackpoint timestamp.

```python
def parse_gpx(path: Path) -> Route
```
Parse a single GPX file. `slug` = `path.stem`, `name` from `<trk><name>`.

```python
def filter_blips(points: list[TrackPoint], max_speed_ms: float = 55.0) -> list[TrackPoint]
```
Remove points implying speed above `max_speed_ms` (default 55 m/s ≈ 200 km/h) from the previous retained point. First point is always kept.

```python
def compute_stats(points: list[TrackPoint]) -> RouteStats
```
Compute distance, elevation gain/loss, total duration, moving time (speed > 0.3 m/s), average pace, and min/max elevation.

### `generator.photos`

```python
def load_photos(photos_dir: Path, tz_offset: str) -> list[Photo]
```
Read EXIF from every JPEG in `photos_dir`. Converts `DateTimeOriginal` to UTC using `tz_offset` (e.g. `"+07:00"`). Populates `lat`/`lon` from GPS EXIF where present.

```python
def match_photos(photos: list[Photo], routes: list[Route]) -> list[Photo]
```
Two-tier matching, mutates each `Photo` in-place and returns the same list:
- **Tier 1 (GPS):** photos with `lat`/`lon` snap to the nearest trackpoint (Haversine, max 500 m).
- **Tier 2 (timestamp):** photos without GPS interpolate position linearly from `timestamp_utc`.
- Photos outside every route window are marked `unmatched`.

```python
def nearest_point_by_coords(photo: Photo, routes: list[Route]) -> TrackPoint | None
```
Returns the closest `TrackPoint` by Haversine distance, or `None` if the minimum exceeds 500 m.

```python
def interpolate_by_time(timestamp_utc: datetime, routes: list[Route]) -> TrackPoint | None
```
Linearly interpolates `lat`, `lon`, `ele` between the two bracketing trackpoints. Returns `None` if the timestamp falls outside every route window.

### `generator.models`

```python
def haversine_m(lat1, lon1, lat2, lon2) -> float
```
Great-circle distance in metres (Haversine formula). Used internally by `gpx.py` and `photos.py`.

## Running tests

```bash
uv run pytest tests/
```

## Development setup

```bash
uv sync
```

Requires Python 3.13+. Dependencies are managed with `uv` and locked in `uv.lock`.
