"""G7: uploads are stored under a server-generated name inside the user's own directory."""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from upload_storage import (
    UnsafeUploadPath,
    display_name,
    ensure_inside_root,
    file_extension,
    new_upload_path,
)

UUID_NAME = re.compile(r"^[0-9a-f]{32}\.(pdf|docx|pptx)$")

CRAFTED_NAMES = [
    "../evil.pdf",
    "..\\..\\evil.PDF",
    "/etc/passwd.pdf",
    "C:\\Windows\\System32\\x.docx",
    "../../src/main.pptx",
]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Stored paths are relative to the working directory, like in the app (run from src/).
    monkeypatch.chdir(tmp_path)
    return Path("uploads")


@pytest.mark.parametrize("client_name", CRAFTED_NAMES)
def test_crafted_name_lands_inside_the_users_directory(root: Path, client_name: str) -> None:
    path = new_upload_path(root, 7, file_extension(client_name))

    assert path.resolve().parent == (root / "7").resolve()
    assert UUID_NAME.match(path.name)


@pytest.mark.parametrize("client_name", CRAFTED_NAMES)
def test_display_name_is_the_bare_basename(client_name: str) -> None:
    name = display_name(client_name)

    assert "/" not in name and "\\" not in name and ".." not in name
    assert name == re.split(r"[\\/]", client_name)[-1]


def test_display_name_strips_control_characters_and_falls_back() -> None:
    assert display_name("notes\r\n.pdf") == "notes.pdf"
    assert display_name("../") == "document"
    assert display_name(None) == "document"


def test_two_uploads_of_the_same_name_get_different_paths(root: Path) -> None:
    first = new_upload_path(root, 1, ".pdf")
    second = new_upload_path(root, 1, ".pdf")

    assert first != second


def test_users_get_separate_directories(root: Path) -> None:
    assert new_upload_path(root, 1, ".pdf").parent != new_upload_path(root, 2, ".pdf").parent


def test_path_outside_root_is_refused(root: Path) -> None:
    with pytest.raises(UnsafeUploadPath):
        ensure_inside_root(root, root / ".." / "evil.pdf")


def test_sibling_directory_with_shared_prefix_is_refused(root: Path) -> None:
    # A string startswith check would accept uploads2/ as inside uploads/.
    with pytest.raises(UnsafeUploadPath):
        ensure_inside_root(root, Path("uploads2") / "evil.pdf")
