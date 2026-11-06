"""PostToolUse hook: remind Claude of this repo's traps right after it edits certain files.

The reminder is returned as additionalContext, which Claude sees immediately. It never blocks
and checks nothing — /pre-commit does the real review.
"""

from __future__ import annotations

import json
import re
import sys

from hook_io import configure_utf8_streams, project_dir, read_payload, relative_to_project, tool_input

REMINDER_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^(src/)?requirements\.txt$"),
        "Requirements files are UTF-16LE with CRLF — confirm the encoding survived this edit. "
        "Dependency changes need the user's approval. The two files differ; Docker installs the "
        "root requirements.txt.",
    ),
    (
        re.compile(r"^alembic/versions/"),
        "Alembic is misconfigured (T2): it targets ./data/app.db and misses the concept-map "
        "models. Review this revision for drop_table and don't run it without the user.",
    ),
    (
        re.compile(r"^backend/app/main\.py$"),
        "POST /chat and GET /chat/stream duplicate the chat pipeline. If this edit changed "
        "pipeline logic, mirror it in the other endpoint; ignore this if it didn't.",
    ),
    (
        # (.+/)? keeps matching after Day 8 moves these into retrieval/ and services/caches/.
        re.compile(
            r"^backend/app/(.+/)?(semantic_cache|cache|query_cache|web_cache|vector_store|keyword_index|retrieval_service)\.py$"
        ),
        "Scope user data by user_id (filters and cache keys; index metadata stores it as a "
        "string), and bump User.doc_version when a user's document set changes (G6).",
    ),
    (
        re.compile(r"^backend/app/(.+/)?llm_client\.py$"),
        "Keep the system instruction stable across turns (CO4) and keep retrieved or web text out "
        "of it — untrusted content belongs only in the final user turn (G5).",
    ),
)


def reminders_for(relative_path: str) -> list[str]:
    """Return the reminder messages whose pattern matches the project-relative path."""
    lowered = relative_path.lower()
    return [message for pattern, message in REMINDER_RULES if pattern.search(lowered)]


def main() -> int:
    """Emit additionalContext for trap files; stay silent for everything else."""
    configure_utf8_streams()
    try:
        payload = read_payload()
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"edit_reminders.py could not parse hook input: {exc}\n")
        return 1
    file_path = tool_input(payload).get("file_path")
    if not isinstance(file_path, str):
        return 0
    relative_path = relative_to_project(file_path, project_dir(payload))
    if relative_path is None:
        return 0
    messages = reminders_for(relative_path)
    if not messages:
        return 0
    context = f"Reminder after editing {relative_path} (.claude/hooks/edit_reminders.py):\n" + "\n".join(
        f"- {message}" for message in messages
    )
    json.dump(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}},
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
