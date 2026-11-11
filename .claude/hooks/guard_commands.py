"""PreToolUse hook: block destructive shell commands before Claude runs them.

Claude Code sends the pending Bash or PowerShell call as JSON on stdin. Exit code 2 blocks the
call and shows stderr to Claude. This guards against accidents, not attacks: a command such as
`python -c "import shutil; shutil.rmtree('src')"` is not detected. Quoted strings and heredoc or
here-string bodies are treated as data, so `bash -c "rm -rf src"` is not detected either.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from hook_io import (
    configure_utf8_streams,
    project_dir,
    read_payload,
    relative_to_project,
    tool_input,
)

BLOCK_EXIT_CODE = 2

DELETE_COMMANDS: frozenset[str] = frozenset({"rm", "remove-item", "ri", "del", "erase", "rd", "rmdir"})
# Commands that merely mention SQL keywords while searching, so a DROP match there is harmless.
SEARCH_COMMANDS: frozenset[str] = frozenset({"grep", "rg", "findstr", "select-string", "sls", "git"})
PROTECTED_DIRS: frozenset[str] = frozenset(
    {".", "*", "/", "~", "src", "backend", "backend/app", "backend/tests", "frontend", "docs",
     "docs/briefs", "tests", "alembic", ".claude", ".git"}
)

# Matched against each command segment with quoted strings blanked out, so text inside a
# commit message or echo can't trigger a block.
PATTERN_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bgit\b.*\breset\b.*--hard\b"), "`git reset --hard` discards uncommitted work"),
    (
        re.compile(r"\bgit\b.*\bcheckout\b(\s+--)?\s+\.(\s|$)"),
        "`git checkout .` discards every working-tree change",
    ),
    (re.compile(r"\bgit\b.*\brestore\b.*\s\.(\s|$)"), "`git restore .` discards every working-tree change"),
    (
        re.compile(r"\bgit\b.*\bclean\b.*(\s-[a-zA-Z]*f|\s--force\b)"),
        "`git clean -f` deletes untracked files, and CLAUDE.md, docs/ and .claude/ may be untracked",
    ),
    (
        re.compile(r"\bgit\b.*\bpush\b.*(\s--force(-with-lease)?\b|\s-[a-zA-Z]*f\b|\s\+\S)"),
        "force-pushing rewrites remote history",
    ),
    (re.compile(r"\bgit\b.*\bstash\s+(drop|clear)\b"), "`git stash drop/clear` deletes stashed work"),
    (re.compile(r"\bgit\b.*\bbranch\b.*\s-D\b"), "`git branch -D` force-deletes a branch"),
    (re.compile(r"\bredis-cli\b.*\bflush(all|db)\b", re.IGNORECASE), "FLUSHALL/FLUSHDB wipes every Redis cache"),
)
DROP_SQL = re.compile(r"\bdrop\s+(table|database)\b", re.IGNORECASE)
QUOTED_STRING = re.compile(r"\"[^\"]*\"|'[^']*'")
HEREDOC_START = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
HERE_STRING_START = re.compile(r"@['\"]\s*$")
SHORT_FLAG = re.compile(r"-[a-z]{1,4}")
DRIVE_ROOT = re.compile(r"[a-z]:")

# `alembic downgrade` (T2, Day 13): allowed only against throwaway databases.
ALEMBIC_DOWNGRADE = re.compile(r"\balembic\b.*\bdowngrade\b", re.IGNORECASE)
# `$env:DATABASE_URL = …` (PowerShell), `export DATABASE_URL=…`, `set DATABASE_URL=…`, `DATABASE_URL=… cmd`
DATABASE_URL_ASSIGNMENT = re.compile(
    r"(?:\$env:|\bexport\s+|\bset\s+|(?<![\w$:]))DATABASE_URL\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s;]+)", re.IGNORECASE
)
# Any mention of a hosted database keeps a downgrade blocked, however the URL is built.
HOSTED_DATABASE_MARKERS = re.compile(
    r"supabase\.(?:co|com)\b|\bRAG_STAGING_DATABASE_URL\b|\bSUPABASE_\w*URL\b", re.IGNORECASE
)
# Loopback, plus the compose service and container name of the local Postgres.
LOCAL_DATABASE_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1", "postgres", "rag-postgres"})
# The app's real SQLite files: backend/data/app.db on the host, /app/backend/data/app.db in Docker.
REAL_SQLITE_DATABASE = re.compile(r"(^|/)(backend/)?data/app\.db$|(^|/)app\.db$", re.IGNORECASE)


def tokenize(segment: str) -> list[str]:
    """Split a command segment into words, unquoting them; backslashes are treated as path separators."""
    text = segment.replace("\\", "/")
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()


def command_name(token: str) -> str:
    """Return a bare, lower-case command name: `/usr/bin/rm` -> `rm`, `del.exe` -> `del`."""
    name = PurePosixPath(token).name.lower()
    return name[:-4] if name.endswith(".exe") else name


def is_recursive_flag(arg: str) -> bool:
    """True for `-r`, `-rf`, `-fr`, `--recursive`, PowerShell `-Recurse`, or cmd-style `/s`."""
    lowered = arg.lower()
    if lowered in ("-recurse", "--recursive", "/s"):
        return True
    return bool(SHORT_FLAG.fullmatch(lowered)) and "r" in lowered


def normalize_target(raw: str, root: str) -> str:
    """Express a delete target relative to the project root when it points inside it."""
    target = raw.replace("\\", "/")
    relative = relative_to_project(target, root)
    if relative is not None:
        target = relative
    while target.startswith("./"):
        target = target[2:]
    if not target:
        target = "."
    stripped = target.rstrip("/")
    return stripped if stripped else target


def is_app_data(target: str) -> bool:
    """True for the SQLite database or anything under backend/data/ (users, sessions, messages).

    src/data stays covered: checkouts from before Day 7 still keep their database there.
    """
    lowered = target.lower()
    return lowered.endswith("app.db") or any(
        lowered == root or lowered.startswith(f"{root}/") for root in ("backend/data", "src/data")
    )


def is_protected_dir(target: str) -> bool:
    """True for source directories, the repo root, or a whole drive, including `dir/*` globs."""
    lowered = target.lower()
    base = lowered[:-2] if lowered.endswith("/*") else lowered
    return base in PROTECTED_DIRS or base.startswith(".git/") or bool(DRIVE_ROOT.fullmatch(base))


def delete_block_reason(tokens: list[str], root: str) -> str | None:
    """Return why a delete command must be blocked, or None if it is allowed."""
    if not tokens or command_name(tokens[0]) not in DELETE_COMMANDS:
        return None
    args = tokens[1:]
    recursive = any(is_recursive_flag(arg) for arg in args)
    for arg in args:
        if arg.startswith("-") or arg.lower() == "/s":
            continue
        target = normalize_target(arg, root)
        if is_app_data(target):
            return f"deleting `{target}` destroys application data that has no backup and isn't in git"
        if recursive and is_protected_dir(target):
            return f"recursive delete of `{target}`"
    return None


def strip_heredoc_bodies(command: str) -> str:
    """Remove heredoc and PowerShell here-string bodies, keeping the line that starts each one.

    A body is data handed to a program (a script, a commit message), not a command to inspect.
    """
    kept: list[str] = []
    heredoc_delimiter: str | None = None
    in_here_string = False
    for line in command.splitlines():
        if heredoc_delimiter is not None:
            if line.strip() == heredoc_delimiter:
                heredoc_delimiter = None
            continue
        if in_here_string:
            if line.startswith(("'@", '"@')):
                in_here_string = False
            continue
        kept.append(line)
        heredoc = HEREDOC_START.search(line)
        if heredoc is not None:
            heredoc_delimiter = heredoc.group(2)
        elif HERE_STRING_START.search(line):
            in_here_string = True
    return "\n".join(kept)


def split_segments(command: str) -> list[str]:
    """Split a command line on `&&`, `||`, `;`, `|`, and newlines that appear outside quotes."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            current.append(char)
            if char == "\\" and quote == '"' and index + 1 < len(command):
                current.append(command[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
            index += 1
            continue
        if command.startswith(("&&", "||"), index):
            segments.append("".join(current))
            current = []
            index += 2
            continue
        if char in ";|\n":
            segments.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]


def database_url_problem(url: str | None) -> str | None:
    """None if the URL is a throwaway database; otherwise why a downgrade there must be blocked.

    Throwaway means a temporary SQLite file (not the app's real app.db) or a Postgres on this machine
    (loopback or the compose service). No URL at all is the app's default: the real SQLite file.
    """
    if url is None:
        return "no DATABASE_URL is set, so the target is the app's real SQLite database (backend/data/app.db)"
    value = url.strip().strip("\"'")
    if "://" not in value:
        return "DATABASE_URL is built from an expression the guard can't read"
    parts = urlsplit(value)
    if parts.scheme.lower().startswith("sqlite"):
        path = value.split("://", 1)[1].lstrip("/").replace("\\", "/")
        if REAL_SQLITE_DATABASE.search(path):
            return "DATABASE_URL is the app's real SQLite database (app.db)"
        return None
    host = (parts.hostname or "").lower()
    if host in LOCAL_DATABASE_HOSTS:
        return None
    return f"DATABASE_URL points at a non-local host ({host or 'unknown'})"


def dotenv_database_url(root: str) -> str | None:
    """DATABASE_URL from the repo-root .env, if set there. Only that one line is read."""
    try:
        lines = (Path(root) / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        name, separator, value = line.strip().partition("=")
        if separator and name.strip() == "DATABASE_URL":
            return value.strip()
    return None


def downgrade_block_reason(command: str, root: str) -> str | None:
    """Why an `alembic downgrade` in `command` must be blocked, or None for a throwaway target.

    The hook runs in its own process and can't see variables the command sets for itself, so the
    target is resolved the way the app's Settings resolves it: an assignment in the command, then
    this process's environment, then .env, then the default (the real SQLite file). Anything hosted,
    real or unreadable stays blocked.
    """
    if HOSTED_DATABASE_MARKERS.search(command):
        return "`alembic downgrade` against a hosted database (Supabase rag / rag_staging) drops real schema"
    assigned = [match.group(1) for match in DATABASE_URL_ASSIGNMENT.finditer(command)]
    candidates: list[str | None] = list(assigned) or [os.environ.get("DATABASE_URL") or dotenv_database_url(root)]
    for url in candidates:
        problem = database_url_problem(url)
        if problem is not None:
            return f"`alembic downgrade` drops schema, and {problem}"
    return None


def find_block_reason(command: str, root: str) -> str | None:
    """Return the reason the first dangerous segment of `command` must be blocked, or None."""
    segments = split_segments(strip_heredoc_bodies(command))
    if any(ALEMBIC_DOWNGRADE.search(QUOTED_STRING.sub('""', segment)) for segment in segments):
        reason = downgrade_block_reason(command, root)
        if reason is not None:
            return reason
    for segment in segments:
        unquoted = QUOTED_STRING.sub('""', segment)
        for pattern, reason in PATTERN_RULES:
            if pattern.search(unquoted):
                return reason
        tokens = tokenize(segment)
        first = command_name(tokens[0]) if tokens else ""
        if DROP_SQL.search(segment) and first not in SEARCH_COMMANDS:
            return "SQL `DROP TABLE/DATABASE` destroys data"
        reason = delete_block_reason(tokens, root)
        if reason is not None:
            return reason
    return None


def main() -> int:
    """Read the pending tool call and exit 2 with a reason if it is destructive."""
    configure_utf8_streams()
    try:
        payload = read_payload()
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"guard_commands.py could not parse hook input: {exc}\n")
        return 1
    command = tool_input(payload).get("command")
    if not isinstance(command, str) or not command.strip():
        return 0
    reason = find_block_reason(command, project_dir(payload))
    if reason is None:
        return 0
    sys.stderr.write(
        f"Blocked by .claude/hooks/guard_commands.py: {reason}.\n"
        f"Command: {command}\n"
        "Do not retry it or work around the block. Tell the user what you were trying to do; "
        "if they want it done, they can run the command themselves in their own terminal.\n"
    )
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
