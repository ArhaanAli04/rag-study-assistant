"""On-disk cache of generated answers and judge verdicts (sqlite, eval/.cache/, gitignored).

Both are quota-bound (500 requests a day for gemini-3.5-flash-lite on the eval project, 20 for
2.5-flash-lite), and 3.5 Flash-Lite ignores a custom temperature, so a repeat call would not even
reproduce the first. Caching makes a re-run free and deterministic, and lets a run stopped by the
daily quota resume where it stopped.

A key is a hash of everything that could change the output: the kind of call, the model, the full
prompt, the generation config (mode, temperature setting) and, for the judge, its prompt version
and replica number. Changing any of them misses the cache instead of returning a stale result.
"""
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent / ".cache" / "generation.sqlite"


def cache_key(parts: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class ResultCache:
    def __init__(self, path: Path = DEFAULT_CACHE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, kind TEXT NOT NULL, value TEXT NOT NULL)"
        )
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[str]:
        row = self._db.execute("SELECT value FROM results WHERE key = ?", (key,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return str(row[0])

    def put(self, key: str, kind: str, value: str) -> None:
        # Committed one at a time, so a run stopped mid-way keeps everything it paid for.
        self._db.execute("INSERT OR REPLACE INTO results (key, kind, value) VALUES (?, ?, ?)", (key, kind, value))
        self._db.commit()

    def close(self) -> None:
        self._db.close()
