"""Integration tests for CLI build with R2 flag."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from generator.cli import _build


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
    shutil.copytree(_PROJECT_ROOT / "templates", base / "templates")
    shutil.copytree(_PROJECT_ROOT / "static", base / "static")
    return hike_dir


def test_build_with_r2_does_not_call_upload_when_no_photos(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    with patch("generator.cli.upload_thumbnail") as mock_upload, \
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


def test_build_with_r2_missing_env_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold_hike(tmp_path, "test-hike")

    with patch.dict(os.environ, {}, clear=True), \
         pytest.raises(SystemExit):
        _build("test-hike", base_url="/my-hikes", use_r2=True)
