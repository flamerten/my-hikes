"""CLI entry point — exposes the `hikes` command via argparse."""
from __future__ import annotations

import argparse
import functools
import http.server
import shutil
from pathlib import Path

from generator.config import load_hike_meta
from generator.gpx import load_routes
from generator.models import Hike
from generator.photos import generate_thumbnail, load_photos, match_photos
from generator.render import render_hike

_TOML_TEMPLATE = """\
title = "{title}"
date = "{date}"
description = ""
tags = []
cover = ""
tz_offset = "+00:00"
trim_start_m = 0
trim_end_m = 0
"""


def main() -> None:
    parser = argparse.ArgumentParser(prog="hikes")
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="Build one hike.")
    build_p.add_argument("--hike", required=True, metavar="SLUG")

    new_p = sub.add_parser("new", help="Scaffold a new hike directory.")
    new_p.add_argument("slug", metavar="SLUG",
                       help="Directory name, e.g. 2026-05-01-trail-name")

    serve_p = sub.add_parser("serve", help="Serve site/ over HTTP for local preview.")
    serve_p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if args.command == "build":
        _build(args.hike)
    elif args.command == "new":
        _new(args.slug)
    elif args.command == "serve":
        _serve(args.port)


def _build(slug: str) -> None:
    hike_dir = Path("raw") / slug
    out_dir = Path("site")

    meta = load_hike_meta(hike_dir)
    routes = load_routes(hike_dir / "routes")
    photos = load_photos(hike_dir / "photos", tz_offset=meta.tz_offset)
    match_photos(photos, routes)

    thumbs_dir = out_dir / "thumbs" / slug
    for p in photos:
        generate_thumbnail(p, thumbs_dir)

    gpx_out = out_dir / "hikes" / slug
    gpx_out.mkdir(parents=True, exist_ok=True)
    for gpx_file in (hike_dir / "routes").glob("*.gpx"):
        shutil.copy(gpx_file, gpx_out / gpx_file.name)

    render_hike(Hike(meta=meta, routes=routes, photos=photos), out_dir, Path("templates"))

    static_src = Path("static")
    if static_src.exists():
        shutil.copytree(static_src, out_dir / "static", dirs_exist_ok=True)

    print(f"built → {out_dir}/hikes/{slug}/index.html")


def _new(slug: str) -> None:
    hike_dir = Path("raw") / slug
    if hike_dir.exists():
        print(f"error: {hike_dir} already exists")
        return
    (hike_dir / "routes").mkdir(parents=True)
    (hike_dir / "photos").mkdir(parents=True)
    title = slug.replace("-", " ").title()
    # derive date from slug prefix if it looks like YYYY-MM-DD-...
    date = slug[:10] if len(slug) >= 10 and slug[4] == "-" and slug[7] == "-" else "YYYY-MM-DD"
    (hike_dir / "hike.toml").write_text(_TOML_TEMPLATE.format(title=title, date=date))
    print(f"scaffolded {hike_dir}/")
    print(f"  edit {hike_dir}/hike.toml, drop GPX files into routes/, photos into photos/")


def _serve(port: int = 8000) -> None:
    site_dir = Path("site")
    if not site_dir.exists():
        print("error: site/ does not exist — run `hikes build` first")
        return
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site_dir))
    with http.server.HTTPServer(("", port), handler) as httpd:
        print(f"serving site/ at http://localhost:{port}/")
        print("press Ctrl+C to stop")
        httpd.serve_forever()
