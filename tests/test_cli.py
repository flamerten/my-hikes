"""Integration tests for CLI build with R2 flag."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from generator.cli import _build, _build_all, _build_index


R2_ENV = {
    "CF_R2_BUCKET": "my-bucket",
    "CF_R2_ENDPOINT_URL": "https://abc.r2.cloudflarestorage.com",
    "CF_R2_ACCESS_KEY_ID": "key",
    "CF_R2_SECRET_ACCESS_KEY": "secret",
    "CF_R2_PUBLIC_URL": "https://pub-hash.r2.dev",
}

_MINIMAL_GPX = """\
<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="3.5" lon="98.1"><ele>100</ele><time>2026-04-01T02:00:00Z</time></trkpt>
    <trkpt lat="3.6" lon="98.2"><ele>110</ele><time>2026-04-01T03:00:00Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


_PROJECT_ROOT = Path(__file__).parent.parent


def _scaffold_hike(base: Path, slug: str) -> Path:
    import shutil
    hike_dir = base / "raw" / slug
    (hike_dir / "routes").mkdir(parents=True)
    (hike_dir / "media").mkdir(parents=True)
    (hike_dir / "hike.toml").write_text(
        'title = "Test"\ndate = "2026-04-01"\ndescription = ""\n'
        'tags = []\ncover = ""\ntz_offset = "+00:00"\n'
        'trim_start_m = 0\ntrim_end_m = 0\n'
    )
    (hike_dir / "routes" / "day1.gpx").write_text(_MINIMAL_GPX)
    shutil.copytree(_PROJECT_ROOT / "templates", base / "templates", dirs_exist_ok=True)
    shutil.copytree(_PROJECT_ROOT / "static", base / "static", dirs_exist_ok=True)
    return hike_dir


def test_build_with_r2_does_not_call_upload_when_no_photos(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    with patch("generator.cli.upload_thumbnail") as mock_upload, \
         patch("generator.cli.sync_r2_thumbnails", return_value=0), \
         patch.dict(os.environ, R2_ENV):
        _build("test-hike", base_url="/my-hikes", use_r2=True)

    mock_upload.assert_not_called()


def test_build_without_r2_does_not_call_upload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    with patch("generator.cli.upload_thumbnail") as mock_upload:
        _build("test-hike", base_url="/my-hikes", use_r2=False)

    mock_upload.assert_not_called()


def test_build_with_r2_embeds_r2_url_in_html(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    with patch("generator.cli.upload_thumbnail", return_value=None), \
         patch("generator.cli.sync_r2_thumbnails", return_value=0), \
         patch.dict(os.environ, R2_ENV):
        _build("test-hike", base_url="/my-hikes", use_r2=True)

    html = (tmp_path / "site" / "hikes" / "test-hike" / "index.html").read_text()
    assert "/my-hikes/thumbs/test-hike" not in html


def test_build_without_r2_uses_local_thumb_url_in_meta(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    _build("test-hike", base_url="/my-hikes", use_r2=False)

    meta = json.loads((tmp_path / "site" / "hikes" / "test-hike" / "meta.json").read_text())
    assert "r2.dev" not in (meta.get("cover_thumb_url") or "")


def test_build_prunes_orphaned_r2_thumbnails(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    with patch("generator.cli.upload_thumbnail", return_value=None), \
         patch("generator.cli.sync_r2_thumbnails", return_value=3) as mock_sync, \
         patch.dict(os.environ, R2_ENV):
        _build("test-hike", base_url="/my-hikes", use_r2=True)

    mock_sync.assert_called_once()
    slug_arg, photos_arg = mock_sync.call_args[0]
    assert slug_arg == "test-hike"
    assert isinstance(photos_arg, list)
    assert "pruned 3 orphaned R2 object(s)" in capsys.readouterr().out


def test_build_with_r2_missing_env_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    with patch.dict(os.environ, {}, clear=True), \
         pytest.raises(SystemExit):
        _build("test-hike", base_url="/my-hikes", use_r2=True)


# ---------------------------------------------------------------------------
# build — reads base_url from site.toml when --base-url is not given
# ---------------------------------------------------------------------------


def test_build_reads_base_url_from_site_toml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")
    (tmp_path / "site.toml").write_text('base_url = "/my-hikes"\n')

    _build("test-hike", base_url=None, use_r2=False)

    html = (tmp_path / "site" / "hikes" / "test-hike" / "index.html").read_text()
    assert "/my-hikes/static/js/hike.js" in html


def test_build_explicit_base_url_overrides_site_toml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")
    (tmp_path / "site.toml").write_text('base_url = "/wrong"\n')

    _build("test-hike", base_url="/correct", use_r2=False)

    html = (tmp_path / "site" / "hikes" / "test-hike" / "index.html").read_text()
    assert "/correct/static/js/hike.js" in html
    assert "/wrong/" not in html


def test_build_no_site_toml_uses_empty_base_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    _build("test-hike", base_url=None, use_r2=False)

    html = (tmp_path / "site" / "hikes" / "test-hike" / "index.html").read_text()
    assert 'src="/static/js/hike.js"' in html


def test_build_index_reads_base_url_from_site_toml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")
    (tmp_path / "site.toml").write_text('base_url = "/my-hikes"\n')

    _build("test-hike", base_url="/my-hikes", use_r2=False)
    _build_index(base_url=None)

    html = (tmp_path / "site" / "index.html").read_text()
    assert "/my-hikes/hikes/test-hike/index.html" in html


# ---------------------------------------------------------------------------
# build-all
# ---------------------------------------------------------------------------


def test_build_all_builds_every_slug(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "hike-a")
    _scaffold_hike(tmp_path, "hike-b")
    (tmp_path / "site.toml").write_text('base_url = ""\n')

    _build_all(base_url=None, use_r2=False)

    assert (tmp_path / "site" / "hikes" / "hike-a" / "index.html").exists()
    assert (tmp_path / "site" / "hikes" / "hike-b" / "index.html").exists()


def test_build_all_also_builds_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "hike-a")
    (tmp_path / "site.toml").write_text('base_url = ""\n')

    _build_all(base_url=None, use_r2=False)

    assert (tmp_path / "site" / "index.html").exists()


def test_build_all_uses_site_toml_base_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "hike-a")
    (tmp_path / "site.toml").write_text('base_url = "/my-hikes"\n')

    _build_all(base_url=None, use_r2=False)

    html = (tmp_path / "site" / "hikes" / "hike-a" / "index.html").read_text()
    assert "/my-hikes/static/js/hike.js" in html


def test_build_all_explicit_base_url_overrides_site_toml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "hike-a")
    (tmp_path / "site.toml").write_text('base_url = "/wrong"\n')

    _build_all(base_url="/correct", use_r2=False)

    html = (tmp_path / "site" / "hikes" / "hike-a" / "index.html").read_text()
    assert "/correct/static/js/hike.js" in html


def test_build_all_empty_raw_dir_prints_warning(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "raw").mkdir()
    (tmp_path / "site.toml").write_text('base_url = ""\n')
    import shutil
    shutil.copytree(Path(__file__).parent.parent / "templates", tmp_path / "templates")

    _build_all(base_url=None, use_r2=False)

    out = capsys.readouterr().out
    assert "warning" in out.lower()


# ---------------------------------------------------------------------------
# serve — prefix-stripping handler
# ---------------------------------------------------------------------------


def test_serve_strips_base_url_prefix_in_translate_path(tmp_path: Path) -> None:
    from generator.cli import _make_serve_handler

    site_dir = tmp_path / "site"
    (site_dir / "static" / "js").mkdir(parents=True)
    (site_dir / "static" / "js" / "hike.js").write_text("// js")

    HandlerClass = _make_serve_handler(site_dir, strip_prefix="/my-hikes")
    handler = HandlerClass.__new__(HandlerClass)
    handler.directory = str(site_dir)

    result = handler.translate_path("/my-hikes/static/js/hike.js")
    assert result.replace("\\", "/").endswith("static/js/hike.js")


def test_serve_translate_path_no_prefix_unchanged(tmp_path: Path) -> None:
    from generator.cli import _make_serve_handler

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    HandlerClass = _make_serve_handler(site_dir, strip_prefix="")
    handler = HandlerClass.__new__(HandlerClass)
    handler.directory = str(site_dir)

    result = handler.translate_path("/static/js/hike.js")
    assert "static" in result


def test_serve_translate_path_exact_prefix_maps_to_root(tmp_path: Path) -> None:
    from generator.cli import _make_serve_handler

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    HandlerClass = _make_serve_handler(site_dir, strip_prefix="/my-hikes")
    handler = HandlerClass.__new__(HandlerClass)
    handler.directory = str(site_dir)

    result = handler.translate_path("/my-hikes")
    assert result.rstrip("/\\") == str(site_dir).rstrip("/\\")
