"""Tests for generator.r2 — R2 upload helpers."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from generator.models import Photo
from generator.r2 import (
    _full_key,
    _slug_r2_prefix,
    list_objects,
    object_key,
    r2_configured,
    sync_r2_thumbnails,
    thumb_url,
    upload_thumbnail,
)


def _make_photo(filename: str, has_thumb: bool = True) -> Photo:
    p = Photo(
        path=Path(f"/raw/test-hike/media/{filename}"),
        filename=filename,
        timestamp_local=datetime(2026, 4, 1, 12, 0, 0),
        timestamp_utc=datetime(2026, 4, 1, 5, 0, 0, tzinfo=timezone.utc),
        lat=None,
        lon=None,
    )
    if has_thumb:
        p.thumb_path = Path(f"/site/thumbs/test-hike/{filename}")
    return p


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


# ---------------------------------------------------------------------------
# list_objects — refactored to return list[str]
# ---------------------------------------------------------------------------


def test_list_objects_returns_keys() -> None:
    page = {"Contents": [{"Key": "thumbs/slug/a.jpg"}, {"Key": "thumbs/slug/b.jpg"}]}
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = iter([page])
    mock_client = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch.dict(os.environ, R2_ENV):
        result = list_objects("thumbs/slug/")
    assert sorted(result) == ["thumbs/slug/a.jpg", "thumbs/slug/b.jpg"]


def test_list_objects_passes_prefix_to_paginator() -> None:
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = iter([{}])
    mock_client = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch.dict(os.environ, R2_ENV):
        list_objects("myhikes/thumbs/jungle-trek/")
    mock_paginator.paginate.assert_called_once_with(
        Bucket="my-bucket", Prefix="myhikes/thumbs/jungle-trek/",
    )


# ---------------------------------------------------------------------------
# _slug_r2_prefix
# ---------------------------------------------------------------------------


def test_slug_r2_prefix_no_url_prefix() -> None:
    env = {**R2_ENV, "CF_R2_PUBLIC_URL": "https://pub-hash.r2.dev"}
    with patch.dict(os.environ, env):
        assert _slug_r2_prefix("jungle-trek") == "thumbs/jungle-trek/"


def test_slug_r2_prefix_with_url_prefix() -> None:
    env = {**R2_ENV, "CF_R2_PUBLIC_URL": "https://pub-hash.r2.dev/myhikes"}
    with patch.dict(os.environ, env):
        assert _slug_r2_prefix("jungle-trek") == "myhikes/thumbs/jungle-trek/"


# ---------------------------------------------------------------------------
# sync_r2_thumbnails
# ---------------------------------------------------------------------------


def test_sync_deletes_orphaned_keys() -> None:
    photos = [_make_photo("IMG_001.jpg"), _make_photo("IMG_002.jpg")]
    existing_keys = [
        "thumbs/test-hike/IMG_001.jpg",
        "thumbs/test-hike/IMG_002.jpg",
        "thumbs/test-hike/IMG_DELETED.jpg",  # orphan
    ]
    mock_client = MagicMock()
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch("generator.r2.list_objects", return_value=existing_keys), \
         patch.dict(os.environ, R2_ENV):
        sync_r2_thumbnails("test-hike", photos)
    mock_client.delete_objects.assert_called_once_with(
        Bucket="my-bucket",
        Delete={"Objects": [{"Key": "thumbs/test-hike/IMG_DELETED.jpg"}]},
    )


def test_sync_returns_count() -> None:
    photos = [_make_photo("IMG_001.jpg")]
    existing_keys = [
        "thumbs/test-hike/IMG_001.jpg",
        "thumbs/test-hike/STALE_A.jpg",
        "thumbs/test-hike/STALE_B.jpg",
    ]
    mock_client = MagicMock()
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch("generator.r2.list_objects", return_value=existing_keys), \
         patch.dict(os.environ, R2_ENV):
        n = sync_r2_thumbnails("test-hike", photos)
    assert n == 2


def test_sync_skips_delete_when_no_orphans() -> None:
    photos = [_make_photo("IMG_001.jpg")]
    mock_client = MagicMock()
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch("generator.r2.list_objects", return_value=["thumbs/test-hike/IMG_001.jpg"]), \
         patch.dict(os.environ, R2_ENV):
        n = sync_r2_thumbnails("test-hike", photos)
    mock_client.delete_objects.assert_not_called()
    assert n == 0


def test_sync_no_existing_objects() -> None:
    photos = [_make_photo("IMG_001.jpg")]
    mock_client = MagicMock()
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch("generator.r2.list_objects", return_value=[]), \
         patch.dict(os.environ, R2_ENV):
        n = sync_r2_thumbnails("test-hike", photos)
    mock_client.delete_objects.assert_not_called()
    assert n == 0


def test_sync_batches_large_deletes() -> None:
    """sync_r2_thumbnails splits deletions into batches of 1000 (S3 limit)."""
    photos = [_make_photo("keep.jpg")]
    # 1050 orphaned keys — should produce 2 delete_objects calls (1000 + 50)
    existing_keys = ["thumbs/test-hike/keep.jpg"] + [
        f"thumbs/test-hike/stale_{i:04d}.jpg" for i in range(1050)
    ]
    mock_client = MagicMock()
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch("generator.r2.list_objects", return_value=existing_keys), \
         patch.dict(os.environ, R2_ENV):
        n = sync_r2_thumbnails("test-hike", photos)
    assert n == 1050
    assert mock_client.delete_objects.call_count == 2
    first_batch = mock_client.delete_objects.call_args_list[0][1]["Delete"]["Objects"]
    second_batch = mock_client.delete_objects.call_args_list[1][1]["Delete"]["Objects"]
    assert len(first_batch) == 1000
    assert len(second_batch) == 50


def test_sync_ignores_photos_without_thumbs() -> None:
    """Photos with thumb_path=None are excluded from expected set, so their R2 key is deleted."""
    photos = [
        _make_photo("IMG_001.jpg", has_thumb=True),
        _make_photo("IMG_002.jpg", has_thumb=False),  # thumbnail generation failed
    ]
    existing_keys = [
        "thumbs/test-hike/IMG_001.jpg",
        "thumbs/test-hike/IMG_002.jpg",  # orphan — not in expected set
        "thumbs/test-hike/IMG_003.jpg",  # orphan — photo no longer exists
    ]
    mock_client = MagicMock()
    with patch("generator.r2.get_r2_client", return_value=mock_client), \
         patch("generator.r2.list_objects", return_value=existing_keys), \
         patch.dict(os.environ, R2_ENV):
        n = sync_r2_thumbnails("test-hike", photos)
    assert n == 2
    deleted_keys = {
        obj["Key"]
        for obj in mock_client.delete_objects.call_args[1]["Delete"]["Objects"]
    }
    assert deleted_keys == {
        "thumbs/test-hike/IMG_002.jpg",
        "thumbs/test-hike/IMG_003.jpg",
    }
