"""Where uploaded files live on disk (G7).

The client never chooses a server path: files are stored as
``<root>/<user_id>/<uuid4 hex><ext>`` and the client's filename is kept only as display
metadata (``Document.file_name``).
"""
import os
import re
import uuid
from pathlib import Path

UPLOAD_ROOT = Path("uploads")

# Control characters would corrupt log lines and the Content-Disposition of a future download.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_DISPLAY_NAME_LENGTH = 255


class UnsafeUploadPath(Exception):
    """A computed upload path resolved outside the upload root."""


def file_extension(client_name: str) -> str:
    """Lower-cased extension of the client's filename, e.g. ``".pdf"``; ``""`` if none."""
    return os.path.splitext(display_name(client_name))[1].lower()


def display_name(client_name: str | None) -> str:
    """The bare basename of a client filename, safe to store and show.

    Browsers and crafted requests can send ``../x.pdf`` or ``C:\\a\\x.pdf``; only the last
    path component is the user's actual filename.
    """
    name = re.split(r"[\\/]", client_name or "")[-1]
    name = _CONTROL_CHARS.sub("", name).strip().strip(".")
    return name[:_MAX_DISPLAY_NAME_LENGTH] if name else "document"


def user_upload_dir(root: Path, user_id: int) -> Path:
    return root / str(user_id)


def is_inside_user_dir(root: Path, user_id: int, path: Path) -> bool:
    """True if ``path`` is a per-user upload of ``user_id`` (not a legacy flat path)."""
    return path.resolve().is_relative_to(user_upload_dir(root, user_id).resolve())


def ensure_inside_root(root: Path, path: Path) -> Path:
    """Resolve ``path`` and refuse it unless it lies inside ``root``.

    ``Path.is_relative_to`` compares path components, so ``uploads2/`` does not pass as
    inside ``uploads/`` the way a string ``startswith`` check would.
    """
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise UnsafeUploadPath(f"Upload path {resolved} is outside {root.resolve()}")
    return resolved


def new_upload_path(root: Path, user_id: int, extension: str) -> Path:
    """A fresh, server-generated path for one upload; creates the user's directory.

    Returns the path relative to the working directory, like the existing
    ``Document.file_path`` values, so stored paths survive moving the checkout or container.
    """
    user_dir = user_upload_dir(root, user_id)
    path = user_dir / f"{uuid.uuid4().hex}{extension}"
    ensure_inside_root(root, path)
    user_dir.mkdir(parents=True, exist_ok=True)
    return path
