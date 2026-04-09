"""Tests for generator.render — GeoJSON helpers, elevation profile, and HTML output."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from generator.models import Route
from generator.render import (
    aggregate_stats,
    elevation_profile,
    photos_to_pins,
    render_hike,
    routes_to_geojson,
)


# ---------------------------------------------------------------------------
# routes_to_geojson
# ---------------------------------------------------------------------------


def test_routes_to_geojson_type(single_route: Route) -> None:
    assert routes_to_geojson([single_route])["type"] == "FeatureCollection"


def test_routes_to_geojson_one_feature_per_route(single_route: Route) -> None:
    assert len(routes_to_geojson([single_route])["features"]) == 1


def test_routes_to_geojson_linestring_geometry(single_route: Route) -> None:
    feat = routes_to_geojson([single_route])["features"][0]
    assert feat["geometry"]["type"] == "LineString"


def test_routes_to_geojson_coord_order_lon_lat(single_route: Route) -> None:
    coords = routes_to_geojson([single_route])["features"][0]["geometry"]["coordinates"]
    assert coords[0][0] == pytest.approx(single_route.points[0].lon)
    assert coords[0][1] == pytest.approx(single_route.points[0].lat)


def test_routes_to_geojson_slug_in_properties(single_route: Route) -> None:
    feat = routes_to_geojson([single_route])["features"][0]
    assert feat["properties"]["slug"] == single_route.slug


def test_routes_to_geojson_coord_count(single_route: Route) -> None:
    coords = routes_to_geojson([single_route])["features"][0]["geometry"]["coordinates"]
    assert len(coords) == len(single_route.points)


def test_routes_to_geojson_is_json_serialisable(single_route: Route) -> None:
    json.dumps(routes_to_geojson([single_route]))


# ---------------------------------------------------------------------------
# photos_to_pins
# ---------------------------------------------------------------------------


def test_photos_to_pins_excludes_unmatched(matched_photo, unmatched_photo) -> None:
    pins = photos_to_pins([matched_photo, unmatched_photo], slug="test")
    assert len(pins) == 1


def test_photos_to_pins_lat_lon_present(matched_photo) -> None:
    pin = photos_to_pins([matched_photo], slug="test")[0]
    assert "lat" in pin and "lon" in pin


def test_photos_to_pins_thumb_url_path(matched_photo) -> None:
    pin = photos_to_pins([matched_photo], slug="test")[0]
    assert pin["thumb_url"] == f"/thumbs/test/{matched_photo.filename}"


def test_photos_to_pins_no_thumb_url_when_no_thumb_path(matched_photo) -> None:
    matched_photo.thumb_path = None
    pin = photos_to_pins([matched_photo], slug="test")[0]
    assert pin["thumb_url"] is None


def test_photos_to_pins_empty_list() -> None:
    assert photos_to_pins([], slug="test") == []


# ---------------------------------------------------------------------------
# elevation_profile
# ---------------------------------------------------------------------------


def test_elevation_profile_starts_at_zero(single_route: Route) -> None:
    assert elevation_profile([single_route])[0]["d"] == 0.0


def test_elevation_profile_distances_are_ascending(single_route: Route) -> None:
    ds = [p["d"] for p in elevation_profile([single_route])]
    assert ds == sorted(ds)


def test_elevation_profile_point_count(single_route: Route) -> None:
    assert len(elevation_profile([single_route])) == len(single_route.points)


def test_elevation_profile_ele_matches_trackpoint(single_route: Route) -> None:
    profile = elevation_profile([single_route])
    assert profile[0]["ele"] == pytest.approx(single_route.points[0].ele)


def test_elevation_profile_two_routes_continuous(two_routes) -> None:
    ds = [p["d"] for p in elevation_profile(two_routes)]
    assert ds == sorted(ds)


# ---------------------------------------------------------------------------
# aggregate_stats
# ---------------------------------------------------------------------------


def test_aggregate_stats_sums_distance(two_routes) -> None:
    agg = aggregate_stats(two_routes)
    assert agg.distance_m == pytest.approx(sum(r.stats.distance_m for r in two_routes))


def test_aggregate_stats_sums_ele_gain(two_routes) -> None:
    agg = aggregate_stats(two_routes)
    assert agg.ele_gain_m == pytest.approx(sum(r.stats.ele_gain_m for r in two_routes))


def test_aggregate_stats_max_ele(two_routes) -> None:
    agg = aggregate_stats(two_routes)
    assert agg.max_ele_m == pytest.approx(max(r.stats.max_ele_m for r in two_routes))


def test_aggregate_stats_min_ele(two_routes) -> None:
    agg = aggregate_stats(two_routes)
    assert agg.min_ele_m == pytest.approx(min(r.stats.min_ele_m for r in two_routes))


# ---------------------------------------------------------------------------
# render_hike
# ---------------------------------------------------------------------------


def test_render_hike_creates_index_html(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    out = tmp_path / "hikes" / sample_hike.meta.slug / "index.html"
    assert out.exists()


def test_render_hike_html_contains_geojson(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert "FeatureCollection" in html


def test_render_hike_html_contains_leaflet(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert "leaflet" in html.lower()


def test_render_hike_html_contains_title(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert sample_hike.meta.title in html


def test_render_hike_html_contains_elevation_data(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert "ELEVATION" in html


def test_render_hike_html_is_valid_utf8(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    path = tmp_path / "hikes" / sample_hike.meta.slug / "index.html"
    path.read_text(encoding="utf-8")
