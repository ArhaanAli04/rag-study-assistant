"""PostToolUse hook: run ruff on a Python file Claude just edited.

The rules come from the repo's ruff.toml (ruff finds it by walking up from the file), the same
file CI enforces, so the hook can never pass what CI rejects. That set is bug-only today —
syntax errors, undefined names, invalid comparisons — and was clean repo-wide when adopted, so a
hit almost certainly comes from the edit itself. There is no --fix and no formatting: rewriting
whole legacy files would bury the real change in an unrelated diff. Exit 2 sends the findings
back to Claude.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import site
import subprocess
import sys
from pathlib import Path

from hook_io import configure_utf8_streams, read_payload, tool_input

FINDINGS_EXIT_CODE = 2


def find_ruff() -> list[str] | None:
    """Locate ruff: on PATH, in this Python's user Scripts folder, or as an importable module."""
    on_path = shutil.which("ruff")
    if on_path:
        return [on_path]
    version_dir = f"Python{sys.version_info.major}{sys.version_info.minor}"
    user_install = Path(site.getuserbase()) / version_dir / "Scripts" / "ruff.exe"
    if user_install.is_file():
        return [str(user_install)]
    if importlib.util.find_spec("ruff") is not None:
        return [sys.executable, "-m", "ruff"]
    return None


def main() -> int:
    """Lint the edited .py file and exit 2 with the findings if there are any."""
    configure_utf8_streams()
    try:
        payload = read_payload()
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"ruff_check.py could not parse hook input: {exc}\n")
        return 1
    file_path = tool_input(payload).get("file_path")
    if not isinstance(file_path, str) or not file_path.lower().endswith(".py"):
        return 0
    path = Path(file_path)
    if not path.is_file():
        return 0

    ruff = find_ruff()
    if ruff is None:
        sys.stderr.write("ruff_check.py: ruff not found on PATH or in the user Python Scripts folder.\n")
        return 1
    try:
        result = subprocess.run(
            [*ruff, "check", "--no-cache", "--output-format", "concise", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"ruff_check.py: could not run ruff: {exc}\n")
        return 1

    if result.returncode == 0:
        return 0
    if result.returncode == 1:
        sys.stderr.write(
            f"ruff found errors in {path.name} after this edit (rules from ruff.toml):\n"
            f"{result.stdout.strip()}\n"
            "Fix these before moving on.\n"
        )
        return FINDINGS_EXIT_CODE
    sys.stderr.write(f"ruff_check.py: ruff exited with {result.returncode}: {result.stderr.strip()}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
