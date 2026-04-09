"""GeoJSON/elevation serialisation helpers and Jinja2 rendering."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from generator.models import Hike, Photo, Route, RouteStats, haversine_m


def routes_to_geojson(routes: list[Route]) -> dict:
    """Serialise routes as a GeoJSON FeatureCollection (one LineString per route).

    Per-route stats are embedded in each feature's properties so the JS layer
    can display them on click without a separate data structure.
    """
    features = []
    for r in routes:
        s = r.stats
        features.append({
            "type": "Feature",
            "properties": {
                "slug": r.slug,
                "name": r.name,
                "distance_m": round(s.distance_m, 1),
                "ele_gain_m": round(s.ele_gain_m, 1),
                "ele_loss_m": round(s.ele_loss_m, 1),
                "max_ele_m": round(s.max_ele_m, 1),
                "avg_pace_min_km": round(s.avg_pace_min_km, 2),
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[pt.lon, pt.lat, pt.ele] for pt in r.points],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def photos_to_pins(photos: list[Photo], slug: str) -> list[dict]:
    """Return one dict per matched photo with lat, lon, filename, thumb_url, and dimensions."""
    pins = []
    for p in photos:
        if p.matched_point is None:
            continue
        pins.append({
            "lat": p.matched_point.lat,
            "lon": p.matched_point.lon,
            "filename": p.filename,
            "thumb_url": f"/thumbs/{slug}/{p.filename}" if p.thumb_path else None,
            "thumb_width": p.thumb_width,
            "thumb_height": p.thumb_height,
            "match_method": p.match_method,
        })
    return pins


def elevation_profile(routes: list[Route]) -> list[dict]:
    """Return [{d: cumulative_metres, ele: metres}, ...] across all routes in order."""
    profile: list[dict] = []
    cumulative_m = 0.0
    for route in routes:
        for i, pt in enumerate(route.points):
            if i > 0:
                prev = route.points[i - 1]
                cumulative_m += haversine_m(prev.lat, prev.lon, pt.lat, pt.lon)
            profile.append({"d": round(cumulative_m, 1), "ele": round(pt.ele, 1)})
    return profile


def per_route_elevation(routes: list[Route]) -> dict[str, list[dict]]:
    """Return {slug: [{d, ele}, ...]} with d resetting to 0 at the start of each route."""
    result: dict[str, list[dict]] = {}
    for route in routes:
        profile: list[dict] = []
        cum = 0.0
        for i, pt in enumerate(route.points):
            if i > 0:
                prev = route.points[i - 1]
                cum += haversine_m(prev.lat, prev.lon, pt.lat, pt.lon)
            profile.append({"d": round(cum, 1), "ele": round(pt.ele, 1)})
        result[route.slug] = profile
    return result


def aggregate_stats(routes: list[Route]) -> RouteStats:
    """Roll up per-route stats into a single RouteStats for the headline bar."""
    total_dist = sum(r.stats.distance_m for r in routes)
    total_moving_s = sum(r.stats.moving_time.total_seconds() for r in routes)
    return RouteStats(
        distance_m=total_dist,
        ele_gain_m=sum(r.stats.ele_gain_m for r in routes),
        ele_loss_m=sum(r.stats.ele_loss_m for r in routes),
        duration=sum((r.stats.duration for r in routes), timedelta()),
        moving_time=timedelta(seconds=total_moving_s),
        avg_pace_min_km=(total_moving_s / 60) / (total_dist / 1000) if total_dist else 0.0,
        max_ele_m=max(r.stats.max_ele_m for r in routes),
        min_ele_m=min(r.stats.min_ele_m for r in routes),
    )


def render_hike(hike: Hike, out_dir: Path, templates_dir: Path) -> None:
    """Render site/hikes/<slug>/index.html from templates/hike.html."""
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    tmpl = env.get_template("hike.html")
    out_path = out_dir / "hikes" / hike.meta.slug / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = tmpl.render(
        meta=hike.meta,
        routes_geojson=json.dumps(routes_to_geojson(hike.routes)),
        photo_pins=json.dumps(photos_to_pins(hike.photos, hike.meta.slug)),
        elevation_profile=json.dumps(elevation_profile(hike.routes)),
        per_route_elevation=json.dumps(per_route_elevation(hike.routes)),
        stats=aggregate_stats(hike.routes),
    )
    out_path.write_text(html, encoding="utf-8")
