"""SessionStart hook: give Claude the live repo state at startup, resume, /clear, and /compact.

Plain stdout from a SessionStart hook is added to Claude's context. CLAUDE.md is already loaded
automatically, so this adds only what CLAUDE.md can't know: git state and which tracker items
are in progress, with their briefs.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from hook_io import configure_utf8_streams, project_dir, read_payload

MAX_STATUS_LINES = 15
TRACKER_PATH = Path("docs") / "improvement-tracker.md"
BRIEFS_DIR = Path("docs") / "briefs"
IN_PROGRESS = "in progress"


def run_git(root: Path, *args: str) -> str | None:
    """Run a read-only git command in `root`; return its stdout, or None if git failed."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.rstrip() if result.returncode == 0 else None


def in_progress_items(root: Path) -> list[tuple[str, str]]:
    """Return (ID, title) for tracker rows whose Status column is `In Progress`.

    Rows look like `| ID | title | Status | Notes |`; Status is the second-to-last cell.
    """
    try:
        text = (root / TRACKER_PATH).read_text(encoding="utf-8")
    except OSError:
        return []
    items: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[-2].lower() == IN_PROGRESS:
            items.append((cells[0], " | ".join(cells[1:-2])))
    return items


def brief_for(root: Path, item_id: str) -> str | None:
    """Find the brief for `item_id`: `docs/briefs/<ID>.md`, or a brief whose title line names the ID."""
    briefs = root / BRIEFS_DIR
    exact = briefs / f"{item_id}.md"
    if exact.is_file():
        return exact.relative_to(root).as_posix()
    if not briefs.is_dir():
        return None
    id_pattern = re.compile(rf"\b{re.escape(item_id)}\b")
    for path in sorted(briefs.glob("*.md")):
        try:
            title_line = path.read_text(encoding="utf-8").partition("\n")[0]
        except OSError:
            continue
        if id_pattern.search(title_line):
            return path.relative_to(root).as_posix()
    return None


def build_context(root: Path) -> list[str]:
    """Assemble the lines injected into Claude's context."""
    lines = ["[Session context from .claude/hooks/session_context.py]"]

    status = run_git(root, "status", "--short")
    if status is None:
        lines.append("Git: status unavailable")
    elif not status:
        lines.append("Git: working tree clean")
    else:
        entries = status.splitlines()
        untracked = sum(1 for entry in entries if entry.startswith("??"))
        lines.append(f"Git: {len(entries) - untracked} changed, {untracked} untracked")
        lines.extend(f"  {entry}" for entry in entries[:MAX_STATUS_LINES])
        if len(entries) > MAX_STATUS_LINES:
            lines.append(f"  ... and {len(entries) - MAX_STATUS_LINES} more")

    last_commit = run_git(root, "log", "--oneline", "-1")
    if last_commit:
        lines.append(f"Last commit: {last_commit}")

    items = in_progress_items(root)
    if not items:
        lines.append("In progress: no item is marked In Progress in docs/improvement-tracker.md")
    else:
        lines.append("In progress (docs/improvement-tracker.md):")
        for item_id, title in items:
            brief = brief_for(root, item_id)
            detail = f"brief: {brief}" if brief else f"no brief yet; start with /run-item {item_id}"
            lines.append(f"  {item_id} — {title} ({detail})")
    return lines


def main() -> int:
    """Print the session context; never blocks the session."""
    configure_utf8_streams()
    try:
        payload = read_payload()
    except json.JSONDecodeError:
        payload = {}
    root = Path(project_dir(payload))
    sys.stdout.write("\n".join(build_context(root)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
