"""Tests for generator.photos — EXIF loading, GPS matching, time interpolation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from generator.models import Route, TrackPoint
from PIL import Image as PILImage

from generator.photos import (
    generate_thumbnail,
    interpolate_by_time,
    load_photos,
    match_photos,
    nearest_point_by_coords,
)


# ---------------------------------------------------------------------------
# load_photos
# ---------------------------------------------------------------------------


def test_load_photos_reads_timestamp(photo_gps_path: Path) -> None:
    photos = load_photos(photo_gps_path.parent, tz_offset="+07:00")
    assert len(photos) == 1
    assert photos[0].timestamp_local == datetime(2026, 4, 1, 9, 49, 12)


def test_load_photos_utc_conversion(photo_gps_path: Path) -> None:
    p = load_photos(photo_gps_path.parent, tz_offset="+07:00")[0]
    assert p.timestamp_utc == datetime(2026, 4, 1, 2, 49, 12, tzinfo=timezone.utc)


def test_load_photos_pixel_has_gps(photo_gps_path: Path) -> None:
    p = load_photos(photo_gps_path.parent, tz_offset="+07:00")[0]
    assert p.lat is not None
    assert p.lon is not None
    assert abs(p.lat - 3.5449) < 0.01
    assert abs(p.lon - 98.1242) < 0.01


def test_load_photos_no_gps_is_none(photo_no_gps_path: Path) -> None:
    p = load_photos(photo_no_gps_path.parent, tz_offset="+07:00")[0]
    assert p.lat is None
    assert p.lon is None


def test_load_photos_empty_dir(tmp_path: Path) -> None:
    assert load_photos(tmp_path, tz_offset="+07:00") == []


# ---------------------------------------------------------------------------
# nearest_point_by_coords
# ---------------------------------------------------------------------------


def test_nearest_point_by_coords_finds_close(nearby_photo, single_route: Route) -> None:
    pt = nearest_point_by_coords(nearby_photo, [single_route])
    assert pt is not None
    assert pt.lat == pytest.approx(nearby_photo.lat, abs=0.001)


def test_nearest_point_by_coords_too_far_returns_photo_position(far_photo, single_route: Route) -> None:
    """Off-track GPS photos get a synthetic pin at their own coordinates."""
    pt = nearest_point_by_coords(far_photo, [single_route])
    assert pt is not None
    assert pt.lat == pytest.approx(far_photo.lat)
    assert pt.lon == pytest.approx(far_photo.lon)


def test_nearest_point_by_coords_too_far_time_is_utc(far_photo, single_route: Route) -> None:
    """Synthetic TrackPoint must carry a UTC-aware timestamp."""
    pt = nearest_point_by_coords(far_photo, [single_route])
    assert pt is not None
    assert pt.time.tzinfo is not None
    assert pt.time == far_photo.timestamp_utc


def test_match_photos_far_gps_gets_pin(far_photo, single_route: Route) -> None:
    """A GPS photo outside the snap radius still gets a matched_point."""
    photos = match_photos([far_photo], [single_route])
    assert photos[0].match_method == "gps"
    assert photos[0].matched_point is not None
    assert photos[0].matched_point.lat == pytest.approx(far_photo.lat)
    assert photos[0].matched_point.lon == pytest.approx(far_photo.lon)


# ---------------------------------------------------------------------------
# interpolate_by_time
# ---------------------------------------------------------------------------


def test_interpolate_by_time_exact(single_route: Route) -> None:
    ts = single_route.points[0].time
    pt = interpolate_by_time(ts, [single_route])
    assert pt is not None
    assert pt.lat == pytest.approx(single_route.points[0].lat)


def test_interpolate_by_time_between(single_route: Route) -> None:
    p1, p2 = single_route.points[0], single_route.points[1]
    midpoint_time = p1.time + (p2.time - p1.time) / 2
    pt = interpolate_by_time(midpoint_time, [single_route])
    assert pt is not None
    assert pt.lat == pytest.approx((p1.lat + p2.lat) / 2, abs=1e-5)
    assert pt.lon == pytest.approx((p1.lon + p2.lon) / 2, abs=1e-5)
    assert pt.ele == pytest.approx((p1.ele + p2.ele) / 2, abs=0.1)


def test_interpolate_by_time_outside(single_route: Route) -> None:
    ts = single_route.points[0].time - timedelta(days=365)
    assert interpolate_by_time(ts, [single_route]) is None


# ---------------------------------------------------------------------------
# match_photos
# ---------------------------------------------------------------------------


def test_match_photos_gps_tier(nearby_photo_with_gps, single_route: Route) -> None:
    photos = match_photos([nearby_photo_with_gps], [single_route])
    assert photos[0].match_method == "gps"
    assert photos[0].matched_point is not None


def test_match_photos_timestamp_tier(photo_in_window_no_gps, single_route: Route) -> None:
    photos = match_photos([photo_in_window_no_gps], [single_route])
    assert photos[0].match_method == "timestamp"
    assert photos[0].matched_point is not None


def test_match_photos_unmatched(photo_outside_window, single_route: Route) -> None:
    photos = match_photos([photo_outside_window], [single_route])
    assert photos[0].match_method == "unmatched"
    assert photos[0].matched_point is None


def test_match_photos_mutates_in_place(nearby_photo_with_gps, single_route: Route) -> None:
    original_list = [nearby_photo_with_gps]
    result = match_photos(original_list, [single_route])
    assert result is original_list


# ---------------------------------------------------------------------------
# generate_thumbnail
# ---------------------------------------------------------------------------


def test_generate_thumbnail_creates_file(photo_gps_path: Path, tmp_path: Path) -> None:
    photo = load_photos(photo_gps_path.parent, tz_offset="+07:00")[0]
    thumb = generate_thumbnail(photo, tmp_path / "thumbs")
    assert thumb.exists()


def test_generate_thumbnail_longest_edge_capped(large_photo_path: Path, tmp_path: Path) -> None:
    photo = load_photos(large_photo_path.parent, tz_offset="+07:00")[0]
    thumb = generate_thumbnail(photo, tmp_path / "thumbs", max_px=100)
    img = PILImage.open(thumb)
    assert max(img.size) <= 100


def test_generate_thumbnail_sets_thumb_path(photo_gps_path: Path, tmp_path: Path) -> None:
    photo = load_photos(photo_gps_path.parent, tz_offset="+07:00")[0]
    generate_thumbnail(photo, tmp_path / "thumbs")
    assert photo.thumb_path is not None
    assert photo.thumb_path.name == photo.filename


def test_generate_thumbnail_skips_existing(photo_gps_path: Path, tmp_path: Path) -> None:
    photo = load_photos(photo_gps_path.parent, tz_offset="+07:00")[0]
    out_dir = tmp_path / "thumbs"
    path1 = generate_thumbnail(photo, out_dir)
    mtime = path1.stat().st_mtime
    generate_thumbnail(photo, out_dir)
    assert path1.stat().st_mtime == mtime


def test_generate_thumbnail_returns_path_in_out_dir(photo_gps_path: Path, tmp_path: Path) -> None:
    photo = load_photos(photo_gps_path.parent, tz_offset="+07:00")[0]
    out_dir = tmp_path / "thumbs"
    thumb = generate_thumbnail(photo, out_dir)
    assert thumb.parent == out_dir


def test_generate_thumbnail_sets_dimensions(large_photo_path: Path, tmp_path: Path) -> None:
    photo = load_photos(large_photo_path.parent, tz_offset="+07:00")[0]
    generate_thumbnail(photo, tmp_path / "thumbs", max_px=100)
    assert photo.thumb_width is not None
    assert photo.thumb_height is not None
    assert max(photo.thumb_width, photo.thumb_height) <= 100


def test_generate_thumbnail_dimensions_match_saved_file(large_photo_path: Path, tmp_path: Path) -> None:
    photo = load_photos(large_photo_path.parent, tz_offset="+07:00")[0]
    thumb_path = generate_thumbnail(photo, tmp_path / "thumbs", max_px=100)
    saved = PILImage.open(thumb_path)
    assert photo.thumb_width == saved.width
    assert photo.thumb_height == saved.height


def test_generate_thumbnail_sets_dimensions_on_skip(large_photo_path: Path, tmp_path: Path) -> None:
    photo = load_photos(large_photo_path.parent, tz_offset="+07:00")[0]
    out_dir = tmp_path / "thumbs"
    generate_thumbnail(photo, out_dir, max_px=100)
    # second call hits the skip-write path; dims must still be populated
    photo.thumb_width = None
    photo.thumb_height = None
    generate_thumbnail(photo, out_dir, max_px=100)
    assert photo.thumb_width is not None
    assert photo.thumb_height is not None
