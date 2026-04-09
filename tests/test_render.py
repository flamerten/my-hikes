"""Tests for generator.render — GeoJSON helpers, elevation profile, and HTML output."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from generator.models import Hike, HikeMeta, Route
from generator.render import (
    aggregate_stats,
    elevation_profile,
    per_route_elevation,
    photos_to_gallery,
    photos_to_pins,
    render_hike,
    render_home,
    routes_to_geojson,
    write_meta_json,
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
# photos_to_gallery
# ---------------------------------------------------------------------------


def test_photos_to_gallery_includes_unmatched(unmatched_photo, tmp_path) -> None:
    unmatched_photo.thumb_path = tmp_path / "unmatched.jpg"
    gallery = photos_to_gallery([unmatched_photo], slug="test")
    assert len(gallery) == 1


def test_photos_to_gallery_includes_matched(matched_photo) -> None:
    gallery = photos_to_gallery([matched_photo], slug="test")
    assert len(gallery) == 1


def test_photos_to_gallery_skips_photos_without_thumb(unmatched_photo) -> None:
    gallery = photos_to_gallery([unmatched_photo], slug="test")
    assert gallery == []


def test_photos_to_gallery_thumb_url_path(matched_photo) -> None:
    item = photos_to_gallery([matched_photo], slug="test")[0]
    assert item["thumb_url"] == f"/thumbs/test/{matched_photo.filename}"


def test_photos_to_gallery_includes_dimensions(matched_photo) -> None:
    matched_photo.thumb_width = 800
    matched_photo.thumb_height = 600
    item = photos_to_gallery([matched_photo], slug="test")[0]
    assert item["thumb_width"] == 800
    assert item["thumb_height"] == 600


def test_photos_to_gallery_includes_match_method(matched_photo) -> None:
    item = photos_to_gallery([matched_photo], slug="test")[0]
    assert item["match_method"] == "gps"


def test_photos_to_gallery_unmatched_has_correct_match_method(unmatched_photo, tmp_path) -> None:
    unmatched_photo.thumb_path = tmp_path / "unmatched.jpg"
    item = photos_to_gallery([unmatched_photo], slug="test")[0]
    assert item["match_method"] == "unmatched"


def test_photos_to_gallery_is_video_flag(matched_photo) -> None:
    item = photos_to_gallery([matched_photo], slug="test")[0]
    assert "is_video" in item


def test_photos_to_gallery_empty_list() -> None:
    assert photos_to_gallery([], slug="test") == []


def test_photos_to_gallery_is_json_serialisable(matched_photo) -> None:
    json.dumps(photos_to_gallery([matched_photo], slug="test"))


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


def test_render_hike_html_contains_route_elevation(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert "ROUTE_ELEVATION" in html


def test_render_hike_html_contains_route_panel(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert "route-panel" in html


def test_render_hike_html_contains_gallery_var(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert "GALLERY" in html


def test_render_hike_html_contains_gallery_grid(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert "gallery-grid" in html


def test_render_hike_html_gallery_includes_unmatched(
    sample_hike, unmatched_photo, tmp_path: Path, templates_dir: Path
) -> None:
    unmatched_photo.thumb_path = tmp_path / "unmatched.jpg"
    sample_hike.photos.append(unmatched_photo)
    render_hike(sample_hike, tmp_path, templates_dir)
    html = (tmp_path / "hikes" / sample_hike.meta.slug / "index.html").read_text()
    assert "unmatched.jpg" in html


# ---------------------------------------------------------------------------
# routes_to_geojson — stats in properties
# ---------------------------------------------------------------------------


def test_routes_to_geojson_stats_in_properties(single_route: Route) -> None:
    props = routes_to_geojson([single_route])["features"][0]["properties"]
    assert "distance_m" in props
    assert "ele_gain_m" in props
    assert "ele_loss_m" in props
    assert "max_ele_m" in props
    assert "avg_pace_min_km" in props


def test_routes_to_geojson_distance_matches_route_stats(single_route: Route) -> None:
    props = routes_to_geojson([single_route])["features"][0]["properties"]
    assert props["distance_m"] == pytest.approx(single_route.stats.distance_m, abs=0.1)


# ---------------------------------------------------------------------------
# photos_to_pins — dimensions
# ---------------------------------------------------------------------------


def test_photos_to_pins_includes_thumb_dimensions(matched_photo) -> None:
    matched_photo.thumb_width = 800
    matched_photo.thumb_height = 600
    pin = photos_to_pins([matched_photo], slug="test")[0]
    assert pin["thumb_width"] == 800
    assert pin["thumb_height"] == 600


def test_photos_to_pins_dimensions_none_when_not_set(matched_photo) -> None:
    pin = photos_to_pins([matched_photo], slug="test")[0]
    assert pin["thumb_width"] is None
    assert pin["thumb_height"] is None


# ---------------------------------------------------------------------------
# per_route_elevation
# ---------------------------------------------------------------------------


def test_per_route_elevation_keyed_by_slug(single_route: Route) -> None:
    result = per_route_elevation([single_route])
    assert single_route.slug in result


def test_per_route_elevation_starts_at_zero(single_route: Route) -> None:
    profile = per_route_elevation([single_route])[single_route.slug]
    assert profile[0]["d"] == 0.0


def test_per_route_elevation_distances_ascending(single_route: Route) -> None:
    profile = per_route_elevation([single_route])[single_route.slug]
    ds = [p["d"] for p in profile]
    assert ds == sorted(ds)


def test_per_route_elevation_point_count(single_route: Route) -> None:
    profile = per_route_elevation([single_route])[single_route.slug]
    assert len(profile) == len(single_route.points)


def test_per_route_elevation_resets_per_route(two_routes) -> None:
    result = per_route_elevation(two_routes)
    for route in two_routes:
        assert result[route.slug][0]["d"] == 0.0


def test_per_route_elevation_ele_matches_trackpoints(single_route: Route) -> None:
    profile = per_route_elevation([single_route])[single_route.slug]
    for entry, pt in zip(profile, single_route.points):
        assert entry["ele"] == pytest.approx(pt.ele, abs=0.1)


def test_per_route_elevation_is_json_serialisable(single_route: Route) -> None:
    json.dumps(per_route_elevation([single_route]))


# ---------------------------------------------------------------------------
# write_meta_json
# ---------------------------------------------------------------------------


def test_write_meta_json_creates_file(sample_hike, tmp_path: Path) -> None:
    render_hike(sample_hike, tmp_path, Path(__file__).parent.parent / "templates")
    write_meta_json(sample_hike, tmp_path)
    assert (tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").exists()


def test_write_meta_json_fields(sample_hike, tmp_path: Path) -> None:
    render_hike(sample_hike, tmp_path, Path(__file__).parent.parent / "templates")
    write_meta_json(sample_hike, tmp_path)
    data = json.loads((tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").read_text())
    for field in ("slug", "title", "date", "description", "distance_m", "ele_gain_m", "cover_thumb_url"):
        assert field in data


def test_write_meta_json_cover_thumb_url(sample_hike, tmp_path: Path) -> None:
    render_hike(sample_hike, tmp_path, Path(__file__).parent.parent / "templates")
    write_meta_json(sample_hike, tmp_path)
    data = json.loads((tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").read_text())
    assert data["cover_thumb_url"] == f"/thumbs/{sample_hike.meta.slug}/thumb.jpg"


def test_write_meta_json_no_cover_uses_random_thumb(sample_hike, tmp_path: Path) -> None:
    sample_hike.meta.cover = ""
    render_hike(sample_hike, tmp_path, Path(__file__).parent.parent / "templates")
    write_meta_json(sample_hike, tmp_path)
    data = json.loads((tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").read_text())
    assert data["cover_thumb_url"] is not None
    assert data["cover_thumb_url"].startswith(f"/thumbs/{sample_hike.meta.slug}/")


def test_write_meta_json_no_cover_no_photos(sample_hike, tmp_path: Path) -> None:
    sample_hike.meta.cover = ""
    sample_hike.photos.clear()
    render_hike(sample_hike, tmp_path, Path(__file__).parent.parent / "templates")
    write_meta_json(sample_hike, tmp_path)
    data = json.loads((tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").read_text())
    assert data["cover_thumb_url"] is None


def test_write_meta_json_is_json_serialisable(sample_hike, tmp_path: Path) -> None:
    render_hike(sample_hike, tmp_path, Path(__file__).parent.parent / "templates")
    write_meta_json(sample_hike, tmp_path)
    raw = (tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").read_text()
    json.loads(raw)


# ---------------------------------------------------------------------------
# render_home
# ---------------------------------------------------------------------------


def test_render_home_creates_index_html(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    write_meta_json(sample_hike, tmp_path)
    meta = json.loads((tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").read_text())
    render_home([meta], tmp_path, templates_dir)
    assert (tmp_path / "index.html").exists()


def test_render_home_contains_hike_title(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    write_meta_json(sample_hike, tmp_path)
    meta = json.loads((tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").read_text())
    render_home([meta], tmp_path, templates_dir)
    html = (tmp_path / "index.html").read_text()
    assert sample_hike.meta.title in html


def test_render_home_contains_link_to_hike(sample_hike, tmp_path: Path, templates_dir: Path) -> None:
    render_hike(sample_hike, tmp_path, templates_dir)
    write_meta_json(sample_hike, tmp_path)
    meta = json.loads((tmp_path / "hikes" / sample_hike.meta.slug / "meta.json").read_text())
    render_home([meta], tmp_path, templates_dir)
    html = (tmp_path / "index.html").read_text()
    assert f"/hikes/{sample_hike.meta.slug}/index.html" in html


def test_render_home_sorts_newest_first(tmp_path: Path, templates_dir: Path) -> None:
    older = {"slug": "old-hike", "title": "Old Hike", "date": "2025-01-01",
             "description": "", "tags": [], "cover_thumb_url": None,
             "distance_m": 10000.0, "ele_gain_m": 100.0, "ele_loss_m": 100.0}
    newer = {"slug": "new-hike", "title": "New Hike", "date": "2026-01-01",
             "description": "", "tags": [], "cover_thumb_url": None,
             "distance_m": 10000.0, "ele_gain_m": 100.0, "ele_loss_m": 100.0}
    render_home([older, newer], tmp_path, templates_dir)
    html = (tmp_path / "index.html").read_text()
    assert html.index("New Hike") < html.index("Old Hike")


def test_render_home_empty_list(tmp_path: Path, templates_dir: Path) -> None:
    render_home([], tmp_path, templates_dir)
    html = (tmp_path / "index.html").read_text()
    assert "MyHikes" in html
