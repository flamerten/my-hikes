"""Tests for site.toml project-level config loading."""
from __future__ import annotations

from pathlib import Path

from generator.config import get_base_url, load_site_config


def test_load_site_config_returns_empty_dict_when_file_missing(tmp_path: Path) -> None:
    assert load_site_config(tmp_path) == {}


def test_load_site_config_reads_base_url(tmp_path: Path) -> None:
    (tmp_path / "site.toml").write_text('base_url = "/my-hikes"\n')
    assert load_site_config(tmp_path)["base_url"] == "/my-hikes"


def test_load_site_config_empty_file_gives_empty_dict(tmp_path: Path) -> None:
    (tmp_path / "site.toml").write_text("")
    assert load_site_config(tmp_path) == {}


def test_get_base_url_defaults_to_empty_string_when_no_file(tmp_path: Path) -> None:
    assert get_base_url(tmp_path) == ""


def test_get_base_url_returns_configured_value(tmp_path: Path) -> None:
    (tmp_path / "site.toml").write_text('base_url = "/my-hikes"\n')
    assert get_base_url(tmp_path) == "/my-hikes"


def test_get_base_url_missing_key_returns_empty_string(tmp_path: Path) -> None:
    (tmp_path / "site.toml").write_text('[other]\nkey = "value"\n')
    assert get_base_url(tmp_path) == ""
