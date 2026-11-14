"""Where uploaded files live (G7, Day 3; object storage since Day 15).

The client never chooses where a file goes: each upload is stored under a server-generated key,
``uploads/<user_id>/<uuid4 hex><ext>``, and the client's filename is kept only as display metadata
(``Document.file_name``). ``Document.file_path`` holds that key.

Two backends behind one protocol (Decision 6A):
- LocalFileStorage: the key is a path under the backend's working directory (dev, tests, Docker volume).
- S3FileStorage: a private Supabase Storage bucket over its S3 API (Render: its disk is wiped on
  every restart, deploy and idle spin-down).
"""
import logging
import re
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Protocol

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("rag_assistant.upload_storage")

UPLOAD_PREFIX = "uploads"

# Control characters would corrupt log lines and the Content-Disposition of a future download.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_DISPLAY_NAME_LENGTH = 255


class UnsafeUploadPath(Exception):
    """A key that would land outside uploads/ (traversal, absolute path, sibling directory)."""


class StorageError(RuntimeError):
    """The storage backend failed (network, permissions, disk). Messages never include credentials."""


# --- names and keys ------------------------------------------------------------------------------

def display_name(client_name: str | None) -> str:
    """The bare basename of a client filename, safe to store and show.

    Browsers and crafted requests can send ``../x.pdf`` or ``C:\\a\\x.pdf``; only the last
    path component is the user's actual filename.
    """
    name = re.split(r"[\\/]", client_name or "")[-1]
    name = _CONTROL_CHARS.sub("", name).strip().strip(".")
    return name[:_MAX_DISPLAY_NAME_LENGTH] if name else "document"


def file_extension(client_name: str) -> str:
    """Lower-cased extension of the client's filename, e.g. ``".pdf"``; ``""`` if none."""
    return PurePosixPath(display_name(client_name)).suffix.lower()


def normalize_key(raw: str) -> str:
    """A stored file_path as a key: forward slashes (rows written on Windows hold backslashes)."""
    key = raw.replace("\\", "/")
    while key.startswith("./"):
        key = key[2:]
    return key


def check_key(raw: str) -> str:
    """The normalized key, or UnsafeUploadPath if it isn't a plain path inside uploads/."""
    key = normalize_key(raw)
    parts = key.split("/")
    # Component checks, not startswith: "uploads2/x" and "uploads/../x" must both be refused.
    if key.startswith("/") or ":" in parts[0] or parts[0] != UPLOAD_PREFIX or len(parts) < 2:
        raise UnsafeUploadPath(f"Upload key {key!r} is not inside {UPLOAD_PREFIX}/")
    if any(part in ("", ".", "..") for part in parts):
        raise UnsafeUploadPath(f"Upload key {key!r} has an empty or relative component")
    return key


def user_prefix(user_id: int) -> str:
    return f"{UPLOAD_PREFIX}/{user_id}/"


def is_user_key(user_id: int, raw: str) -> bool:
    """True for a per-user key of ``user_id``; False for a pre-G7 flat key (uploads/<name>)."""
    try:
        return check_key(raw).startswith(user_prefix(user_id))
    except UnsafeUploadPath:
        return False


def new_upload_key(user_id: int, extension: str) -> str:
    """A fresh, server-generated key for one upload."""
    return check_key(f"{user_prefix(user_id)}{uuid.uuid4().hex}{extension}")


# --- backends --------------------------------------------------------------------------------------

class FileStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def exists(self, key: str) -> bool: ...

    def local_copy(self, key: str) -> Any:
        """A context manager yielding a local Path to read the file from (parsers need a file)."""
        ...

    def delete(self, key: str) -> bool:
        """True if the file existed and is now gone."""
        ...

    def delete_prefix(self, prefix: str) -> int:
        """Delete every file under ``prefix`` (e.g. a user's directory); returns how many."""
        ...


class LocalFileStorage:
    def __init__(self, base_dir: Path = Path(".")) -> None:
        # Keys are relative to the working directory (backend/ in the app, a temp dir in tests), so
        # stored keys survive moving the checkout or container, as before Day 15.
        self.base_dir = base_dir

    def _path(self, raw: str) -> Path:
        key = check_key(raw)
        path = (self.base_dir / key).resolve()
        if not path.is_relative_to((self.base_dir / UPLOAD_PREFIX).resolve()):
            raise UnsafeUploadPath(f"Upload key {key!r} resolves outside {UPLOAD_PREFIX}/")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as error:
            raise StorageError(f"could not write {key}") from error

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"{key} does not exist")
        yield path

    def delete(self, key: str) -> bool:
        path = self._path(key)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as error:
            raise StorageError(f"could not delete {key}") from error

    def delete_prefix(self, prefix: str) -> int:
        directory = self._path(prefix.rstrip("/"))
        if not directory.is_dir():
            return 0
        count = sum(1 for p in directory.rglob("*") if p.is_file())
        try:
            shutil.rmtree(directory)
        except OSError as error:
            raise StorageError(f"could not delete {prefix}") from error
        return count


class S3FileStorage:
    """A private bucket over the S3 API. ``client`` is a boto3 S3 client (built in services/container.py)."""

    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put(self, key: str, data: bytes) -> None:
        key = check_key(key)
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        except (BotoCoreError, ClientError) as error:
            raise StorageError(f"could not upload {key}: {type(error).__name__}") from error

    def exists(self, key: str) -> bool:
        key = check_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise StorageError(f"could not check {key}: {type(error).__name__}") from error
        except BotoCoreError as error:
            raise StorageError(f"could not check {key}: {type(error).__name__}") from error

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        key = check_key(key)
        with tempfile.TemporaryDirectory(prefix="rag-upload-") as tmp:
            # Same extension: the parsers pick PDF / PPTX / DOCX by it.
            path = Path(tmp) / f"document{PurePosixPath(key).suffix}"
            try:
                body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
                path.write_bytes(body.read())
            except (BotoCoreError, ClientError) as error:
                raise StorageError(f"could not download {key}: {type(error).__name__}") from error
            yield path

    def delete(self, key: str) -> bool:
        if not self.exists(key):
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=check_key(key))
            return True
        except (BotoCoreError, ClientError) as error:
            raise StorageError(f"could not delete {key}: {type(error).__name__}") from error

    def delete_prefix(self, prefix: str) -> int:
        # One DeleteObject per key, not one DeleteObjects per 1000: Supabase's S3 endpoint rejects
        # DeleteObjects from boto3 1.44 with InvalidRequest (Day 15, live check on rag-staging). Only
        # account deletion calls this, for one user's uploads, so the extra requests are few.
        prefix = check_key(prefix.rstrip("/")) + "/"
        deleted = 0
        try:
            pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
            keys = [obj["Key"] for page in pages for obj in page.get("Contents", [])]
            for key in keys:
                self.client.delete_object(Bucket=self.bucket, Key=key)
                deleted += 1
        except (BotoCoreError, ClientError) as error:
            raise StorageError(f"could not delete {prefix}: {type(error).__name__}") from error
        return deleted
