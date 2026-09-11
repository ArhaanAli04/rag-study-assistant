"""Shared stdin/stdout and path helpers for this repo's Claude Code hook scripts."""

from __future__ import annotations

import io
import json
import os
import sys
from typing import Any


def configure_utf8_streams() -> None:
    """Force UTF-8 on stdout/stderr so a non-ASCII command or path can't crash a hook on Windows."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


def read_payload() -> dict[str, Any]:
    """Parse the hook input JSON that Claude Code writes to stdin.

    Raises:
        json.JSONDecodeError: if stdin is not valid JSON.
    """
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    data = json.loads(raw) if raw.strip() else {}
    return data if isinstance(data, dict) else {}


def tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the tool_input object of a Pre/PostToolUse payload, or an empty dict."""
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def project_dir(payload: dict[str, Any]) -> str:
    """Return the project root: CLAUDE_PROJECT_DIR when set, else the session's cwd."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or os.getcwd())


def to_msys_path(windows_path: str) -> str:
    """Convert `C:/Users/x` to `/c/Users/x`, the form Git Bash commands often use."""
    if len(windows_path) >= 2 and windows_path[1] == ":":
        return f"/{windows_path[0].lower()}{windows_path[2:]}"
    return windows_path


def relative_to_project(path: str, root: str) -> str | None:
    """Return `path` relative to `root` with forward slashes, or None if it lies outside `root`.

    The comparison is case-insensitive because Windows paths are.
    """
    normalized = path.replace("\\", "/")
    root_normalized = root.replace("\\", "/").rstrip("/")
    for prefix in (root_normalized, to_msys_path(root_normalized)):
        if not prefix:
            continue
        if normalized.lower() == prefix.lower():
            return "."
        if normalized.lower().startswith(prefix.lower() + "/"):
            return normalized[len(prefix) + 1 :]
    return None
