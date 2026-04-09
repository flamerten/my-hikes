"""Shared pytest fixtures for all test modules."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import piexif
import pytest
from PIL import Image

from generator.models import Photo, Route, RouteStats, TrackPoint

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# GPX path fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_gpx() -> Path:
    """Path to the 3-point, no-blip GPX fixture."""
    return FIXTURES / "simple.gpx"


@pytest.fixture
def blip_gpx() -> Path:
    """Path to the GPX fixture containing one GPS blip."""
    return FIXTURES / "blip.gpx"


@pytest.fixture
def two_routes_dir() -> Path:
    """Directory containing early.gpx and late.gpx."""
    return FIXTURES / "two_routes"


@pytest.fixture
def blip_dir(tmp_path: Path) -> Path:
    """Directory containing only blip.gpx, for load_routes tests."""
    import shutil
    shutil.copy(FIXTURES / "blip.gpx", tmp_path / "blip.gpx")
    return tmp_path


# ---------------------------------------------------------------------------
# JPEG fixtures (generated in-memory, written to tmp_path)
# ---------------------------------------------------------------------------

def _make_jpeg_exif(
    tmp_path: Path,
    filename: str,
    datetime_original: str,
    with_gps: bool,
) -> Path:
    """Write a 1x1 white JPEG with the given EXIF fields."""
    exif_dict: dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = datetime_original.encode()

    if with_gps:
        # lat=3.5449°N, lon=98.1242°E expressed as rational DMS tuples
        def to_rational(value: float) -> tuple[int, int]:
            return (int(value * 1_000_000), 1_000_000)

        lat_deg, lat_min, lat_sec = 3, 32, 41.64  # ≈ 3.5449°
        lon_deg, lon_min, lon_sec = 98, 7, 27.12   # ≈ 98.1242°

        exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N"
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = (
            (lat_deg, 1),
            (lat_min, 1),
            (int(lat_sec * 100), 100),
        )
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E"
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = (
            (lon_deg, 1),
            (lon_min, 1),
            (int(lon_sec * 100), 100),
        )

    exif_bytes = piexif.dump(exif_dict)
    out = tmp_path / filename
    img = Image.new("RGB", (1, 1), (255, 255, 255))
    img.save(str(out), "JPEG", exif=exif_bytes)
    return out


@pytest.fixture
def photo_gps_path(tmp_path: Path) -> Path:
    """1×1 JPEG with DateTimeOriginal=2026:04:01 09:49:12 and GPS coords."""
    return _make_jpeg_exif(
        tmp_path, "photo_gps.jpg", "2026:04:01 09:49:12", with_gps=True
    )


@pytest.fixture
def photo_no_gps_path(tmp_path: Path) -> Path:
    """1×1 JPEG with DateTimeOriginal=2026:04:01 09:49:19 and no GPS."""
    return _make_jpeg_exif(
        tmp_path, "photo_no_gps.jpg", "2026:04:01 09:49:19", with_gps=False
    )


# ---------------------------------------------------------------------------
# In-memory photo/route fixtures for matching tests
# ---------------------------------------------------------------------------

def _make_route(start_time: datetime) -> Route:
    """Build a minimal 3-point Route starting at start_time."""
    points = [
        TrackPoint(lat=3.5449, lon=98.1242, ele=194.6, time=start_time),
        TrackPoint(lat=3.5450, lon=98.1243, ele=195.4, time=start_time + timedelta(seconds=7)),
        TrackPoint(lat=3.5451, lon=98.1244, ele=196.2, time=start_time + timedelta(seconds=14)),
    ]
    stats = RouteStats(
        distance_m=28.0,
        ele_gain_m=1.6,
        ele_loss_m=0.0,
        duration=timedelta(seconds=14),
        moving_time=timedelta(seconds=14),
        avg_pace_min_km=8.0,
        max_ele_m=196.2,
        min_ele_m=194.6,
    )
    return Route(slug="test-route", name="Test Route", points=points, stats=stats)


@pytest.fixture
def single_route() -> Route:
    """A 3-point route starting at 2026-04-01T02:49:12Z."""
    return _make_route(datetime(2026, 4, 1, 2, 49, 12, tzinfo=timezone.utc))


def _make_photo(
    lat: float | None,
    lon: float | None,
    timestamp_utc: datetime,
    tmp_path: Path,
    filename: str = "test.jpg",
) -> Photo:
    """Build a minimal Photo dataclass."""
    return Photo(
        path=tmp_path / filename,
        filename=filename,
        timestamp_local=timestamp_utc.replace(tzinfo=None),
        timestamp_utc=timestamp_utc,
        lat=lat,
        lon=lon,
    )


@pytest.fixture
def nearby_photo(tmp_path: Path, single_route: Route) -> Photo:
    """Photo with GPS matching the first trackpoint of single_route."""
    pt = single_route.points[0]
    return _make_photo(pt.lat, pt.lon, pt.time, tmp_path)


@pytest.fixture
def nearby_photo_with_gps(tmp_path: Path, single_route: Route) -> Photo:
    """Photo with GPS coordinates near single_route's first trackpoint."""
    pt = single_route.points[0]
    return _make_photo(pt.lat + 0.00001, pt.lon + 0.00001, pt.time, tmp_path)


@pytest.fixture
def far_photo(tmp_path: Path, single_route: Route) -> Photo:
    """Photo with GPS coordinates >500 m from every trackpoint."""
    pt = single_route.points[0]
    return _make_photo(pt.lat + 1.0, pt.lon + 1.0, pt.time, tmp_path)


@pytest.fixture
def photo_in_window_no_gps(tmp_path: Path, single_route: Route) -> Photo:
    """Photo without GPS whose timestamp falls inside single_route's window."""
    midpoint = single_route.points[0].time + timedelta(seconds=7)
    return _make_photo(None, None, midpoint, tmp_path)


@pytest.fixture
def photo_outside_window(tmp_path: Path, single_route: Route) -> Photo:
    """Photo without GPS whose timestamp is outside every route window."""
    far_time = single_route.points[0].time - timedelta(days=365)
    return _make_photo(None, None, far_time, tmp_path)
