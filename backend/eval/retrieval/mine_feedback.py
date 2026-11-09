"""One-off: export real hard queries as candidates for the next dataset version (run from backend/).

    python -m eval.retrieval.mine_feedback

Reads the local database: failed_queries rows (low confidence or negative feedback) and the user
question behind every thumbs-down answer. Writes datasets/hard_candidates.jsonl, which is
gitignored: these are real users' questions, and they become dataset lines only after the owner
rewrites or labels them.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.db.database import FailedQuery, Message, SessionLocal

logger = logging.getLogger("eval.mine")

OUTPUT = Path(__file__).resolve().parent.parent / "datasets" / "hard_candidates.jsonl"


def failed_query_candidates(db: Session) -> List[Dict[str, Any]]:
    return [
        {
            "source": f"failed_queries:{row.reason}",
            "query": row.query,
            "confidence": row.confidence,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        }
        for row in db.query(FailedQuery).order_by(FailedQuery.id)
    ]


def thumbs_down_candidates(db: Session) -> List[Dict[str, Any]]:
    candidates = []
    for answer in db.query(Message).filter(Message.feedback == "down").order_by(Message.id):
        question = (
            db.query(Message)
            .filter(Message.session_id == answer.session_id, Message.role == "user", Message.id < answer.id)
            .order_by(Message.id.desc())
            .first()
        )
        if question is None:
            continue
        candidates.append({
            "source": "thumbs_down",
            "query": question.content,
            "comment": answer.feedback_comment,
            "timestamp": answer.timestamp.isoformat() if answer.timestamp else None,
        })
    return candidates


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = SessionLocal()
    try:
        candidates = failed_query_candidates(db) + thumbs_down_candidates(db)
    finally:
        db.close()

    seen = set()
    unique = []
    for c in candidates:
        key = " ".join(str(c["query"]).lower().split())
        if key not in seen:
            seen.add(key)
            unique.append(c)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as handle:
        for c in unique:
            handle.write(json.dumps(c, ensure_ascii=False) + "\n")
    logger.info("wrote %d candidates (%d before de-duplication) to %s", len(unique), len(candidates), OUTPUT)


if __name__ == "__main__":
    main()
