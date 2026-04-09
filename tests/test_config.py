"""Tests for generator.config — hike.toml parsing."""
from __future__ import annotations

from pathlib import Path

import pytest

from generator.config import load_hike_meta


def test_load_hike_meta_parses_title(hike_dir: Path) -> None:
    assert load_hike_meta(hike_dir).title == "Test Hike"


def test_load_hike_meta_parses_tz_offset(hike_dir: Path) -> None:
    assert load_hike_meta(hike_dir).tz_offset == "+07:00"


def test_load_hike_meta_parses_tags(hike_dir: Path) -> None:
    assert "jungle" in load_hike_meta(hike_dir).tags


def test_load_hike_meta_parses_date(hike_dir: Path) -> None:
    assert load_hike_meta(hike_dir).date == "2026-04-01"


def test_load_hike_meta_parses_description(hike_dir: Path) -> None:
    assert load_hike_meta(hike_dir).description == "A test hike."


def test_load_hike_meta_slug_from_dirname(hike_dir: Path) -> None:
    assert load_hike_meta(hike_dir).slug == hike_dir.name


def test_load_hike_meta_trim_defaults_to_zero(hike_dir: Path) -> None:
    meta = load_hike_meta(hike_dir)
    assert meta.trim_start_m == 0
    assert meta.trim_end_m == 0


def test_load_hike_meta_missing_title_raises(tmp_path: Path) -> None:
    (tmp_path / "hike.toml").write_text('tz_offset = "+07:00"\n')
    with pytest.raises(KeyError):
        load_hike_meta(tmp_path)


def test_load_hike_meta_missing_tz_offset_raises(tmp_path: Path) -> None:
    (tmp_path / "hike.toml").write_text('title = "X"\ndate = "2026-01-01"\n')
    with pytest.raises(KeyError):
        load_hike_meta(tmp_path)
