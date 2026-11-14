"""G7 + Day 15: uploads get a server-generated key inside the user's own prefix, and both storage
backends (local disk, Supabase S3) store, read, and delete by that key and nothing outside it."""
import re
from pathlib import Path
from typing import Any

import pytest

from app.ingestion.upload_storage import (
    LocalFileStorage,
    S3FileStorage,
    StorageError,
    UnsafeUploadPath,
    check_key,
    display_name,
    file_extension,
    is_user_key,
    new_upload_key,
    normalize_key,
)
from tests.fakes import FakeS3Client

KEY = re.compile(r"^uploads/7/[0-9a-f]{32}\.(pdf|docx|pptx)$")

CRAFTED_NAMES = [
    "../evil.pdf",
    "..\\..\\evil.PDF",
    "/etc/passwd.pdf",
    "C:\\Windows\\System32\\x.docx",
    "../../src/main.pptx",
]

UNSAFE_KEYS = [
    "uploads/../evil.pdf",
    "uploads/7/../../evil.pdf",
    "/uploads/7/x.pdf",
    "uploads2/7/x.pdf",  # a string startswith check would accept it
    "C:/uploads/7/x.pdf",
    "uploads//x.pdf",
    "uploads",
    "notes.pdf",
]


# --- names and keys ------------------------------------------------------------------------------

@pytest.mark.parametrize("client_name", CRAFTED_NAMES)
def test_crafted_name_gets_a_key_inside_the_users_prefix(client_name: str) -> None:
    assert KEY.match(new_upload_key(7, file_extension(client_name)))


@pytest.mark.parametrize("client_name", CRAFTED_NAMES)
def test_display_name_is_the_bare_basename(client_name: str) -> None:
    name = display_name(client_name)

    assert "/" not in name and "\\" not in name and ".." not in name
    assert name == re.split(r"[\\/]", client_name)[-1]


def test_display_name_strips_control_characters_and_falls_back() -> None:
    assert display_name("notes\r\n.pdf") == "notes.pdf"
    assert display_name("../") == "document"
    assert display_name(None) == "document"


def test_two_uploads_of_the_same_name_get_different_keys() -> None:
    assert new_upload_key(1, ".pdf") != new_upload_key(1, ".pdf")


@pytest.mark.parametrize("key", UNSAFE_KEYS)
def test_keys_outside_uploads_are_refused(key: str) -> None:
    with pytest.raises(UnsafeUploadPath):
        check_key(key)


def test_rows_written_on_windows_are_read_as_keys() -> None:
    # Before Day 15 file_path was str(Path), so a Windows dev database holds backslashes.
    assert normalize_key("uploads\\7\\a.pdf") == "uploads/7/a.pdf"
    assert is_user_key(7, "uploads\\7\\a.pdf")


def test_only_the_users_own_prefix_counts_as_theirs() -> None:
    assert is_user_key(7, "uploads/7/a.pdf")
    assert not is_user_key(7, "uploads/70/a.pdf")
    assert not is_user_key(7, "uploads/a.pdf")  # pre-G7 flat key, possibly shared
    assert not is_user_key(7, "uploads/7/../8/a.pdf")


# --- both backends, one contract -----------------------------------------------------------------

@pytest.fixture(params=["local", "s3"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    if request.param == "local":
        return LocalFileStorage(tmp_path)
    return S3FileStorage(FakeS3Client(), "rag-test")


def test_put_exists_read_and_delete(storage: Any) -> None:
    key = new_upload_key(7, ".pdf")

    storage.put(key, b"%PDF-1.4 notes")

    assert storage.exists(key)
    with storage.local_copy(key) as path:
        assert path.suffix == ".pdf"  # the parsers choose PDF / PPTX / DOCX by extension
        assert path.read_bytes() == b"%PDF-1.4 notes"
    assert storage.delete(key) is True
    assert storage.exists(key) is False
    assert storage.delete(key) is False


def test_delete_prefix_removes_one_users_files_only(storage: Any) -> None:
    mine = [new_upload_key(7, ".pdf") for _ in range(3)]
    theirs = new_upload_key(70, ".pdf")
    for key in [*mine, theirs]:
        storage.put(key, b"x")

    assert storage.delete_prefix("uploads/7/") == 3

    assert not any(storage.exists(k) for k in mine)
    assert storage.exists(theirs)


def test_reading_a_missing_file_is_a_storage_error(storage: Any) -> None:
    with pytest.raises(StorageError):
        with storage.local_copy(new_upload_key(7, ".pdf")):
            pass


@pytest.mark.parametrize("key", UNSAFE_KEYS[:4])
def test_no_backend_touches_a_key_outside_uploads(storage: Any, key: str) -> None:
    with pytest.raises(UnsafeUploadPath):
        storage.put(key, b"x")


def test_s3_failures_become_storage_errors_without_credentials() -> None:
    client = FakeS3Client()
    client.fail_with = "AccessDenied"
    storage = S3FileStorage(client, "rag-test")

    with pytest.raises(StorageError, match="ClientError") as raised:
        storage.put(new_upload_key(7, ".pdf"), b"x")

    assert "secret" not in str(raised.value).lower()
