"""CLI entry point — exposes the `hikes` command via argparse."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import sys
from pathlib import Path

from alive_progress import alive_it

from dotenv import load_dotenv

from generator.config import get_base_url, load_hike_meta
from generator.gpx import load_routes
from generator.models import Hike
from generator.photos import generate_thumbnail, load_photos, match_photos
from generator.r2 import r2_configured, sync_r2_thumbnails, upload_thumbnail
from generator.render import render_hike, render_home, write_meta_json

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


def _read_base_url() -> str:
    return get_base_url()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="hikes")
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="Build one hike.")
    build_p.add_argument("--hike", required=True, metavar="SLUG")
    build_p.add_argument(
        "--base-url", default=None, metavar="URL",
        help="URL prefix for all asset paths. Defaults to base_url in site.toml.",
    )
    build_p.add_argument(
        "--no-r2", dest="r2", action="store_false", default=True,
        help="Skip R2 upload and use local thumbnail paths.",
    )

    build_all_p = sub.add_parser(
        "build-all",
        help="Build every hike in raw/ then rebuild the home page index.",
    )
    build_all_p.add_argument(
        "--base-url", default=None, metavar="URL",
        help="URL prefix for all asset paths. Defaults to base_url in site.toml.",
    )
    build_all_p.add_argument(
        "--no-r2", dest="r2", action="store_false", default=True,
        help="Skip R2 upload and use local thumbnail paths.",
    )

    sub.add_parser("r2-check", help="Verify R2 credentials and bucket access.")

    build_index_p = sub.add_parser(
        "build-index",
        help="Build site/index.html from already-built hike sidecars.",
    )
    build_index_p.add_argument(
        "--base-url", default=None, metavar="URL",
        help="URL prefix for all asset paths. Defaults to base_url in site.toml.",
    )

    new_p = sub.add_parser("new", help="Scaffold a new hike directory.")
    new_p.add_argument("slug", metavar="SLUG")

    serve_p = sub.add_parser("serve", help="Serve site/ over HTTP for local preview.")
    serve_p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if args.command == "build":
        _build(args.hike, args.base_url, use_r2=args.r2)
    elif args.command == "build-all":
        _build_all(args.base_url, use_r2=args.r2)
    elif args.command == "build-index":
        _build_index(args.base_url)
    elif args.command == "new":
        _new(args.slug)
    elif args.command == "serve":
        _serve(args.port)
    elif args.command == "r2-check":
        _r2_check()


def _build(slug: str, base_url: str | None = None, use_r2: bool = True) -> None:
    if base_url is None:
        base_url = _read_base_url()

    if use_r2 and not r2_configured():
        print("error: R2 requested but CF_R2_* environment variables are not set. Use --no-r2 for a local build.")
        sys.exit(1)

    hike_dir = Path("raw") / slug
    out_dir = Path("site")

    meta = load_hike_meta(hike_dir)
    routes = load_routes(hike_dir / "routes")
    photos = load_photos(hike_dir / "media", tz_offset=meta.tz_offset)

    n_photos = len(photos)
    match_photos(photos, routes)
    print(f"Match Photos Done {len(photos)}/{n_photos}")

    thumbs_dir = out_dir / "thumbs" / slug
    for p in alive_it(photos, title="Generating Thumbnails"):
        generate_thumbnail(p, thumbs_dir)

    thumb_url_base: str | None = None
    if use_r2:
        for p in alive_it(photos, title="Uploading to R2"):
            if p.thumb_path:
                upload_thumbnail(p.thumb_path, slug, p.filename)
        n_pruned = sync_r2_thumbnails(slug, photos)
        if n_pruned:
            print(f"  pruned {n_pruned} orphaned R2 object(s)")
        thumb_url_base = f"{os.environ['CF_R2_PUBLIC_URL'].rstrip('/')}/thumbs/{slug}"

    gpx_out = out_dir / "hikes" / slug
    gpx_out.mkdir(parents=True, exist_ok=True)
    for gpx_file in (hike_dir / "routes").glob("*.gpx"):
        shutil.copy(gpx_file, gpx_out / gpx_file.name)

    hike = Hike(meta=meta, routes=routes, photos=photos)
    render_hike(hike, out_dir, Path("templates"), base_url, thumb_url_base)
    write_meta_json(hike, out_dir, base_url, thumb_url_base)

    static_src = Path("static")
    if static_src.exists():
        shutil.copytree(static_src, out_dir / "static", dirs_exist_ok=True)

    print(f"built → {out_dir}/hikes/{slug}/index.html")


def _build_all(base_url: str | None = None, use_r2: bool = True) -> None:
    if base_url is None:
        base_url = _read_base_url()
    raw_dir = Path("raw")
    slugs = sorted(p.name for p in raw_dir.iterdir() if p.is_dir())
    if not slugs:
        print("warning: no hike directories found in raw/ — nothing to build")
        _build_index(base_url)
        return
    for slug in slugs:
        _build(slug, base_url, use_r2)
    _build_index(base_url)


def _build_index(base_url: str | None = None) -> None:
    if base_url is None:
        base_url = _read_base_url()
    out_dir = Path("site")
    out_dir.mkdir(parents=True, exist_ok=True)
    hike_metas = []
    for meta_file in sorted((out_dir / "hikes").glob("*/meta.json")):
        with open(meta_file, encoding="utf-8") as fh:
            hike_metas.append(json.load(fh))
    if not hike_metas:
        print("warning: no meta.json files found in site/hikes/ — build at least one hike first")
    render_home(hike_metas, out_dir, Path("templates"), base_url)
    static_src = Path("static")
    if static_src.exists():
        shutil.copytree(static_src, out_dir / "static", dirs_exist_ok=True)
    print(f"built → {out_dir}/index.html  ({len(hike_metas)} hike(s))")


def _new(slug: str) -> None:
    hike_dir = Path("raw") / slug
    if hike_dir.exists():
        print(f"error: {hike_dir} already exists")
        return
    (hike_dir / "routes").mkdir(parents=True)
    (hike_dir / "media").mkdir(parents=True)
    title = slug.replace("-", " ").title()
    date = slug[:10] if len(slug) >= 10 and slug[4] == "-" and slug[7] == "-" else "YYYY-MM-DD"
    (hike_dir / "hike.toml").write_text(_TOML_TEMPLATE.format(title=title, date=date))
    print(f"scaffolded {hike_dir}/")
    print(f"  edit {hike_dir}/hike.toml, drop GPX files into routes/, photos/videos into media/")


def _r2_check() -> None:
    from generator.r2 import get_r2_client
    if not r2_configured():
        print("error: one or more CF_R2_* environment variables are not set")
        return
    client = get_r2_client()
    bucket = os.environ["CF_R2_BUCKET"]
    try:
        resp = client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        count = resp.get("KeyCount", 0)
        print(f"ok: connected to bucket '{bucket}' ({count} object(s) sampled)")
    except Exception as exc:
        print(f"error: {exc}")


def _make_serve_handler(site_dir: Path, strip_prefix: str):
    class _Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            if strip_prefix:
                if path == strip_prefix or path == strip_prefix + "/":
                    path = "/"
                elif path.startswith(strip_prefix + "/"):
                    path = path[len(strip_prefix):]
            return super().translate_path(path)

        def log_message(self, fmt, *args):
            pass

    return _Handler


def _serve(port: int = 8000) -> None:
    site_dir = Path("site")
    if not site_dir.exists():
        print("error: site/ does not exist — run `hikes build` first")
        return
    strip_prefix = _read_base_url().rstrip("/")
    HandlerClass = _make_serve_handler(site_dir, strip_prefix)
    handler = functools.partial(HandlerClass, directory=str(site_dir))
    with http.server.HTTPServer(("", port), handler) as httpd:
        print(f"serving site/ at http://localhost:{port}{strip_prefix}/")
        print("press Ctrl+C to stop")
        httpd.serve_forever()
