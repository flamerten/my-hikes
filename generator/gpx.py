"""GPX parsing, GPS blip filtering, and route statistics."""
from __future__ import annotations

from datetime import timedelta, timezone
from pathlib import Path

import gpxpy

from generator.models import Route, RouteStats, TrackPoint, haversine_m

_MOVING_SPEED_THRESHOLD_MS = 0.3  # intervals below this are treated as stationary


def load_routes(routes_dir: Path) -> list[Route]:
    """Parse every *.gpx in routes_dir into Route objects.

    Args:
        routes_dir: Directory containing GPX files.

    Returns:
        Routes sorted by the timestamp of their first trackpoint (ascending).
    """
    routes = [parse_gpx(p) for p in sorted(routes_dir.glob("*.gpx"))]
    return sorted(routes, key=lambda r: r.points[0].time)


def parse_gpx(path: Path) -> Route:
    """Parse a single GPX file into a Route.

    Applies filter_blips immediately after parsing, then computes stats.

    Args:
        path: Path to a .gpx file.

    Returns:
        Route whose slug is path.stem and name comes from <trk><name>.
    """
    with path.open() as fh:
        gpx = gpxpy.parse(fh)

    track = gpx.tracks[0]
    raw_points = [
        TrackPoint(
            lat=pt.latitude,
            lon=pt.longitude,
            ele=pt.elevation or 0.0,
            time=pt.time.replace(tzinfo=timezone.utc) if pt.time.tzinfo is None else pt.time.astimezone(timezone.utc),
        )
        for seg in track.segments
        for pt in seg.points
    ]

    points = filter_blips(raw_points)
    return Route(
        slug=path.stem,
        name=track.name or path.stem,
        points=points,
        stats=compute_stats(points),
    )


def filter_blips(points: list[TrackPoint], max_speed_ms: float = 55.0) -> list[TrackPoint]:
    """Remove trackpoints that imply an unrealistic speed from the previous point.

    Args:
        points: Ordered list of TrackPoints.
        max_speed_ms: Speed threshold in m/s above which a point is a blip.

    Returns:
        Filtered list preserving original order. The first point is always kept.
    """
    if not points:
        return []

    kept = [points[0]]
    for pt in points[1:]:
        prev = kept[-1]
        elapsed = (pt.time - prev.time).total_seconds()
        if elapsed <= 0:
            continue
        speed = haversine_m(prev.lat, prev.lon, pt.lat, pt.lon) / elapsed
        if speed <= max_speed_ms:
            kept.append(pt)
        else:
            print(f"skipping {pt} - speed {speed}")

    return kept


def compute_stats(points: list[TrackPoint]) -> RouteStats:
    """Compute aggregated statistics from a list of TrackPoints.

    Args:
        points: Ordered list of TrackPoints (after blip filtering).

    Returns:
        RouteStats with distance, elevation, duration, moving time, and pace.
    """
    if len(points) < 2:
        zero = timedelta(0)
        ele = points[0].ele if points else 0.0
        return RouteStats(
            distance_m=0.0,
            ele_gain_m=0.0,
            ele_loss_m=0.0,
            duration=zero,
            moving_time=zero,
            avg_pace_min_km=0.0,
            max_ele_m=ele,
            min_ele_m=ele,
        )

    distance_m = 0.0
    ele_gain_m = 0.0
    ele_loss_m = 0.0
    moving_seconds = 0.0

    for prev, curr in zip(points, points[1:]):
        segment_m = haversine_m(prev.lat, prev.lon, curr.lat, curr.lon)
        distance_m += segment_m

        ele_delta = curr.ele - prev.ele
        if ele_delta > 0:
            ele_gain_m += ele_delta
        else:
            ele_loss_m += abs(ele_delta)

        elapsed = (curr.time - prev.time).total_seconds()
        if elapsed > 0 and (segment_m / elapsed) >= _MOVING_SPEED_THRESHOLD_MS:
            moving_seconds += elapsed

    duration = points[-1].time - points[0].time
    moving_time = timedelta(seconds=moving_seconds)

    if distance_m > 0 and moving_seconds > 0:
        avg_pace_min_km = (moving_seconds / 60) / (distance_m / 1000)
    else:
        avg_pace_min_km = 0.0

    return RouteStats(
        distance_m=distance_m,
        ele_gain_m=ele_gain_m,
        ele_loss_m=ele_loss_m,
        duration=duration,
        moving_time=moving_time,
        avg_pace_min_km=avg_pace_min_km,
        max_ele_m=max(p.ele for p in points),
        min_ele_m=min(p.ele for p in points),
    )
