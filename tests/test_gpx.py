"""Tests for generator.gpx — parsing, blip filtering, stats, load_routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from generator.gpx import compute_stats, filter_blips, load_routes, parse_gpx
from generator.models import Route, TrackPoint


# ---------------------------------------------------------------------------
# parse_gpx
# ---------------------------------------------------------------------------


def test_parse_gpx_returns_route(simple_gpx: Path) -> None:
    route = parse_gpx(simple_gpx)
    assert isinstance(route, Route)
    assert len(route.points) == 3


def test_parse_gpx_slug_from_filename(simple_gpx: Path) -> None:
    assert parse_gpx(simple_gpx).slug == "simple"


def test_parse_gpx_name_from_track(simple_gpx: Path) -> None:
    assert parse_gpx(simple_gpx).name == "Test Hike"


def test_parse_gpx_points_are_utc_aware(simple_gpx: Path) -> None:
    for pt in parse_gpx(simple_gpx).points:
        assert pt.time.tzinfo is not None
        assert pt.time.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# filter_blips
# ---------------------------------------------------------------------------


def test_filter_blips_removes_blip(blip_gpx: Path) -> None:
    assert len(parse_gpx(blip_gpx).points) == 2


def test_filter_blips_keeps_slow_points(simple_gpx: Path) -> None:
    assert len(parse_gpx(simple_gpx).points) == 3


def test_filter_blips_empty_list() -> None:
    assert filter_blips([]) == []


def test_filter_blips_single_point(simple_gpx: Path) -> None:
    pt = parse_gpx(simple_gpx).points[0]
    assert len(filter_blips([pt])) == 1


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------


def test_compute_stats_distance(simple_gpx: Path) -> None:
    stats = parse_gpx(simple_gpx).stats
    assert 20 < stats.distance_m < 40


def test_compute_stats_elevation_gain(simple_gpx: Path) -> None:
    assert abs(parse_gpx(simple_gpx).stats.ele_gain_m - 1.6) < 0.1


def test_compute_stats_elevation_loss(simple_gpx: Path) -> None:
    assert parse_gpx(simple_gpx).stats.ele_loss_m == 0.0


def test_compute_stats_duration(simple_gpx: Path) -> None:
    assert parse_gpx(simple_gpx).stats.duration == timedelta(seconds=14)


def test_compute_stats_flat_track() -> None:
    t = datetime(2026, 4, 1, tzinfo=timezone.utc)
    points = [
        TrackPoint(lat=0.0, lon=0.0, ele=100.0, time=t),
        TrackPoint(lat=0.0001, lon=0.0, ele=100.0, time=t + timedelta(seconds=10)),
    ]
    stats = compute_stats(points)
    assert stats.ele_gain_m == 0.0
    assert stats.ele_loss_m == 0.0


# ---------------------------------------------------------------------------
# load_routes
# ---------------------------------------------------------------------------


def test_load_routes_returns_sorted(two_routes_dir: Path) -> None:
    routes = load_routes(two_routes_dir)
    assert routes[0].slug == "early"
    assert routes[1].slug == "late"


def test_load_routes_empty_dir(tmp_path: Path) -> None:
    assert load_routes(tmp_path) == []


def test_load_routes_applies_filter_blips(blip_dir: Path) -> None:
    routes = load_routes(blip_dir)
    assert len(routes[0].points) == 2
