"""CLI entry point — exposes the `hikes` command via argparse."""
from __future__ import annotations

import argparse
from pathlib import Path

from generator.gpx import load_routes
from generator.photos import load_photos, match_photos


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate command."""
    parser = argparse.ArgumentParser(prog="hikes")
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="Build one or all hikes.")
    build_p.add_argument("--hike", required=True, metavar="SLUG",
                         help="Slug of the hike directory under raw/.")
    build_p.add_argument("--tz-offset", default="+00:00", metavar="OFFSET",
                         help="Local timezone offset, e.g. +07:00.")

    args = parser.parse_args()

    if args.command == "build":
        _build(args.hike, args.tz_offset)


def _build(slug: str, tz_offset: str) -> None:
    """Load, match, and summarise a single hike from raw/<slug>/.

    Args:
        slug: Hike directory name under raw/.
        tz_offset: Local timezone offset string, e.g. "+07:00".
    """
    hike_dir = Path("raw") / slug

    routes = load_routes(hike_dir / "routes")
    print(f"{len(routes)} routes loaded")
    for r in routes:
        print(
            f"  {r.slug}: {r.stats.distance_m / 1000:.1f} km, "
            f"{r.stats.ele_gain_m:.0f} m gain, {len(r.points)} pts"
        )

    photos = load_photos(hike_dir / "photos", tz_offset=tz_offset)
    print(f"{len(photos)} photos loaded")

    match_photos(photos, routes)
    by_method: dict[str, int] = {}
    for p in photos:
        by_method[p.match_method] = by_method.get(p.match_method, 0) + 1
    print("match breakdown:", by_method)
