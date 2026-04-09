"""Shared dataclasses and the Haversine distance helper used across modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Literal


@dataclass
class TrackPoint:
    """A single recorded GPS point with elevation and UTC timestamp."""

    lat: float
    lon: float
    ele: float
    time: datetime


@dataclass
class RouteStats:
    """Aggregated statistics derived from a sequence of TrackPoints."""

    distance_m: float
    ele_gain_m: float
    ele_loss_m: float
    duration: timedelta
    moving_time: timedelta
    avg_pace_min_km: float
    max_ele_m: float
    min_ele_m: float


@dataclass
class Route:
    """One GPX file parsed into trackpoints plus computed stats."""

    slug: str
    name: str
    points: list[TrackPoint]
    stats: RouteStats


@dataclass
class Photo:
    """A single photo with EXIF-derived metadata and optional track match."""

    path: Path
    filename: str
    timestamp_local: datetime
    timestamp_utc: datetime
    lat: float | None
    lon: float | None
    matched_point: TrackPoint | None = None
    match_method: Literal["gps", "timestamp", "unmatched"] = "unmatched"
    thumb_path: Path | None = None
    thumb_width: int | None = None
    thumb_height: int | None = None
    is_video: bool = False


@dataclass
class HikeMeta:
    """Metadata from hike.toml describing a single hike."""

    slug: str
    title: str
    date: str
    description: str
    tags: list[str]
    cover: str
    tz_offset: str
    trim_start_m: int = 0
    trim_end_m: int = 0


@dataclass
class Hike:
    """Top-level object combining metadata, routes, and photos for one hike."""

    meta: HikeMeta
    routes: list[Route]
    photos: list[Photo]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in metres between two WGS-84 coordinates.

    Args:
        lat1: Latitude of the first point in decimal degrees.
        lon1: Longitude of the first point in decimal degrees.
        lat2: Latitude of the second point in decimal degrees.
        lon2: Longitude of the second point in decimal degrees.

    Returns:
        Distance in metres.
    """
    R = 6_371_000
    lat1_r, lat2_r = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))
