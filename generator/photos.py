"""EXIF extraction, thumbnail generation, and two-tier photo-to-track matching."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import piexif
from PIL import Image as PILImage

from generator.models import Photo, Route, TrackPoint, haversine_m

MAX_SNAP_DISTANCE_M = 500


def load_photos(photos_dir: Path, tz_offset: str) -> list[Photo]:
    """Read EXIF data from every JPEG in photos_dir and return Photo objects.

    Args:
        photos_dir: Directory containing JPEG files.
        tz_offset: Local timezone offset string, e.g. "+07:00".

    Returns:
        List of Photo objects. Files with unreadable EXIF are skipped.
    """
    tz_delta = _parse_tz_offset(tz_offset)
    photos = []
    for path in sorted(photos_dir.glob("*.[Jj][Pp][Gg]")):
        try:
            exif = piexif.load(str(path))
        except Exception:
            continue

        raw_dt = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
        if not raw_dt:
            continue

        timestamp_local = datetime.strptime(raw_dt.decode(), "%Y:%m:%d %H:%M:%S")
        timestamp_utc = (timestamp_local - tz_delta).replace(tzinfo=timezone.utc)

        lat, lon = _extract_gps(exif)

        photos.append(Photo(
            path=path,
            filename=path.name,
            timestamp_local=timestamp_local,
            timestamp_utc=timestamp_utc,
            lat=lat,
            lon=lon,
        ))

    return photos


def match_photos(photos: list[Photo], routes: list[Route]) -> list[Photo]:
    """Run the two-tier matching pipeline, mutating each Photo in-place.

    Tier 1 (GPS): photos with lat/lon snap to the nearest trackpoint.
    Tier 2 (timestamp): photos without GPS interpolate from timestamp_utc.

    Args:
        photos: List of Photo objects to match.
        routes: All routes for this hike, sorted by start time.

    Returns:
        The same list with matched_point and match_method set on each photo.
    """
    for photo in photos:
        if photo.lat is not None and photo.lon is not None:
            photo.matched_point = nearest_point_by_coords(photo, routes)
            photo.match_method = "gps" if photo.matched_point else "unmatched"
        else:
            photo.matched_point = interpolate_by_time(photo.timestamp_utc, routes)
            photo.match_method = "timestamp" if photo.matched_point else "unmatched"

    return photos


def nearest_point_by_coords(photo: Photo, routes: list[Route]) -> TrackPoint | None:
    """Find the closest TrackPoint to photo's GPS coordinates.

    Args:
        photo: Photo with non-None lat and lon.
        routes: All routes to search.

    Returns:
        Closest TrackPoint, or None if the minimum distance exceeds MAX_SNAP_DISTANCE_M.
    """
    best_pt: TrackPoint | None = None
    best_dist = float("inf")

    assert photo.lat is not None and photo.lon is not None
    for route in routes:
        for pt in route.points:
            dist = haversine_m(photo.lat, photo.lon, pt.lat, pt.lon)
            if dist < best_dist:
                best_dist = dist
                best_pt = pt

    return best_pt if best_dist <= MAX_SNAP_DISTANCE_M else None


def interpolate_by_time(
    timestamp_utc: datetime, routes: list[Route]
) -> TrackPoint | None:
    """Linearly interpolate a position from timestamp across all route windows.

    Args:
        timestamp_utc: UTC-aware datetime to locate on the track.
        routes: All routes to search.

    Returns:
        Interpolated TrackPoint, or None if timestamp is outside every route window.
    """
    for route in routes:
        pts = route.points
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            if p1.time <= timestamp_utc <= p2.time:
                span = (p2.time - p1.time).total_seconds()
                fraction = (timestamp_utc - p1.time).total_seconds() / span
                return TrackPoint(
                    lat=p1.lat + fraction * (p2.lat - p1.lat),
                    lon=p1.lon + fraction * (p2.lon - p1.lon),
                    ele=p1.ele + fraction * (p2.ele - p1.ele),
                    time=timestamp_utc,
                )

    return None


def generate_thumbnail(photo: Photo, out_dir: Path, max_px: int = 800) -> Path:
    """Write a JPEG thumbnail (longest edge ≤ max_px) to out_dir/<filename>.

    Sets photo.thumb_path. Skips writing if the file already exists.
    Returns the output path.
    """
    out_path = out_dir / photo.filename
    if not out_path.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        img = PILImage.open(photo.path)
        img.thumbnail((max_px, max_px))
        img.save(str(out_path), "JPEG", quality=85)
    photo.thumb_path = out_path
    return out_path


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_tz_offset(tz_offset: str) -> timedelta:
    """Convert a tz_offset string like '+07:00' into a timedelta.

    Args:
        tz_offset: Offset string in the form ±HH:MM.

    Returns:
        timedelta representing the offset (positive = ahead of UTC).
    """
    sign = 1 if tz_offset[0] != "-" else -1
    hours, minutes = int(tz_offset[1:3]), int(tz_offset[4:6])
    return sign * timedelta(hours=hours, minutes=minutes)


def _dms_to_decimal(dms_rationals: tuple, ref: bytes) -> float:
    """Convert GPS DMS rational tuples from EXIF to a signed decimal degree.

    Args:
        dms_rationals: Three (numerator, denominator) pairs for degrees, minutes, seconds.
        ref: Hemisphere reference byte, e.g. b'N', b'S', b'E', b'W'.

    Returns:
        Decimal degrees, negative for south or west.
    """
    degrees = dms_rationals[0][0] / dms_rationals[0][1]
    minutes = dms_rationals[1][0] / dms_rationals[1][1]
    seconds = dms_rationals[2][0] / dms_rationals[2][1]
    decimal = degrees + minutes / 60 + seconds / 3600
    return -decimal if ref in (b"S", b"W") else decimal


def _extract_gps(exif: dict) -> tuple[float | None, float | None]:
    """Extract decimal lat/lon from a piexif EXIF dict.

    Args:
        exif: Dict returned by piexif.load().

    Returns:
        (lat, lon) as floats, or (None, None) if GPS data is absent or incomplete.
    """
    gps = exif.get("GPS", {})
    lat_ref = gps.get(piexif.GPSIFD.GPSLatitudeRef)
    lat_dms = gps.get(piexif.GPSIFD.GPSLatitude)
    lon_ref = gps.get(piexif.GPSIFD.GPSLongitudeRef)
    lon_dms = gps.get(piexif.GPSIFD.GPSLongitude)

    if not (lat_ref and lat_dms and lon_ref and lon_dms):
        return None, None

    return _dms_to_decimal(lat_dms, lat_ref), _dms_to_decimal(lon_dms, lon_ref)
