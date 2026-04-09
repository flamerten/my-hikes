"""Parse hike.toml into a HikeMeta object."""
from __future__ import annotations

import tomllib
from pathlib import Path

from generator.models import HikeMeta


def load_hike_meta(hike_dir: Path) -> HikeMeta:
    """Parse hike.toml from hike_dir. Raises KeyError if required fields are missing."""
    with open(hike_dir / "hike.toml", "rb") as fh:
        data = tomllib.load(fh)
    return HikeMeta(
        slug=hike_dir.name,
        title=data["title"],
        date=data["date"],
        description=data.get("description", ""),
        tags=data.get("tags", []),
        cover=data.get("cover", ""),
        tz_offset=data["tz_offset"],
        trim_start_m=data.get("trim_start_m", 0),
        trim_end_m=data.get("trim_end_m", 0),
    )
