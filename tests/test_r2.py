"""Tests for generator.r2 — R2 upload helpers."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from generator.r2 import object_key, r2_configured, thumb_url, upload_thumbnail


R2_ENV = {
    "CF_R2_BUCKET": "my-bucket",
    "CF_R2_ENDPOINT_URL": "https://abc.r2.cloudflarestorage.com",
    "CF_R2_ACCESS_KEY_ID": "key",
    "CF_R2_SECRET_ACCESS_KEY": "secret",
    "CF_R2_PUBLIC_URL": "https://pub-hash.r2.dev",
}


def _make_client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": ""}}, "HeadObject")


# ---------------------------------------------------------------------------
# object_key
# ---------------------------------------------------------------------------


def test_object_key_format() -> None:
    assert object_key("laos-2026", "IMG_001.jpg") == "thumbs/laos-2026/IMG_001.jpg"


# ---------------------------------------------------------------------------
# thumb_url
# ---------------------------------------------------------------------------


def test_thumb_url_format() -> None:
    with patch.dict(os.environ, R2_ENV):
        url = thumb_url("laos-2026", "IMG_001.jpg")
    assert url == "https://pub-hash.r2.dev/thumbs/laos-2026/IMG_001.jpg"


def test_thumb_url_strips_trailing_slash() -> None:
    env = {**R2_ENV, "CF_R2_PUBLIC_URL": "https://pub-hash.r2.dev/"}
    with patch.dict(os.environ, env):
        url = thumb_url("slug", "file.jpg")
    assert url == "https://pub-hash.r2.dev/thumbs/slug/file.jpg"


# ---------------------------------------------------------------------------
# upload_thumbnail
# ---------------------------------------------------------------------------


def test_upload_skips_when_object_exists(tmp_path: Path) -> None:
    local = tmp_path / "thumb.jpg"
    local.write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.head_object.return_value = {}

    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch.dict(os.environ, R2_ENV):
        upload_thumbnail(local, "slug", "thumb.jpg")

    mock_client.upload_file.assert_not_called()


def test_upload_calls_upload_file_when_missing(tmp_path: Path) -> None:
    local = tmp_path / "thumb.jpg"
    local.write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _make_client_error("404")

    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch.dict(os.environ, R2_ENV):
        upload_thumbnail(local, "slug", "thumb.jpg")

    mock_client.upload_file.assert_called_once_with(
        str(local),
        "my-bucket",
        "thumbs/slug/thumb.jpg",
        ExtraArgs={"ContentType": "image/jpeg"},
    )


def test_upload_prefixes_key_with_public_url_path(tmp_path: Path) -> None:
    local = tmp_path / "thumb.jpg"
    local.write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _make_client_error("404")

    env = {**R2_ENV, "CF_R2_PUBLIC_URL": "https://pub-hash.r2.dev/myhikes"}
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch.dict(os.environ, env):
        upload_thumbnail(local, "slug", "thumb.jpg")

    mock_client.upload_file.assert_called_once_with(
        str(local),
        "my-bucket",
        "myhikes/thumbs/slug/thumb.jpg",
        ExtraArgs={"ContentType": "image/jpeg"},
    )


def test_upload_reraises_non_404_client_error(tmp_path: Path) -> None:
    local = tmp_path / "thumb.jpg"
    local.write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _make_client_error("403")

    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch.dict(os.environ, R2_ENV), \
         pytest.raises(ClientError):
        upload_thumbnail(local, "slug", "thumb.jpg")


def test_upload_uses_correct_bucket(tmp_path: Path) -> None:
    local = tmp_path / "thumb.jpg"
    local.write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _make_client_error("404")

    env = {**R2_ENV, "CF_R2_BUCKET": "other-bucket"}
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch.dict(os.environ, env):
        upload_thumbnail(local, "slug", "thumb.jpg")

    assert mock_client.upload_file.call_args[0][1] == "other-bucket"


# ---------------------------------------------------------------------------
# r2_configured
# ---------------------------------------------------------------------------


def test_r2_configured_true_when_all_vars_set() -> None:
    with patch.dict(os.environ, R2_ENV):
        assert r2_configured() is True


def test_r2_configured_false_when_var_missing() -> None:
    env = {k: v for k, v in R2_ENV.items() if k != "CF_R2_PUBLIC_URL"}
    with patch.dict(os.environ, env, clear=True):
        assert r2_configured() is False


def test_r2_configured_false_when_var_empty() -> None:
    env = {**R2_ENV, "CF_R2_BUCKET": ""}
    with patch.dict(os.environ, env):
        assert r2_configured() is False
