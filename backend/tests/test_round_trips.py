"""CO6 (Day 16): database round trips per request, counted the way they cross the network.

Every round trip from Render (Singapore) to Supabase (Mumbai) costs ~63 ms, and the server-side
statement time is ≤ 0.05 ms (Day 14), so the count is the latency. Counted per wire message, not per
SQLAlchemy call, because several of them never reach a cursor event:
- statements: every cursor execute;
- BEGIN: psycopg sends it on its own before the first statement of a transaction (not in autocommit);
- COMMIT / ROLLBACK: sent only when a transaction is open, whether the session or the pool's
  reset-on-return asks for it;
- pre-ping: `SELECT 1` through dialect.do_ping, which no cursor event sees.
Checked once against the compose Postgres's own log (log_statement=all) on Day 16; see the brief.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List

import pytest
from psycopg.pq import TransactionStatus
from sqlalchemy import event

from app.db.session import engine
from tests.conftest import Account
from tests.test_api_smoke import assert_contract, chat, upload

logger = logging.getLogger("tests.round_trips")


@dataclass
class RoundTrips:
    statements: int = 0
    begins: int = 0
    commits: int = 0
    rollbacks: int = 0
    pings: int = 0
    log: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.statements + self.begins + self.commits + self.rollbacks + self.pings

    def breakdown(self) -> Dict[str, int]:
        return {"total": self.total, "statements": self.statements, "begin": self.begins,
                "commit": self.commits, "rollback": self.rollbacks, "ping": self.pings}

    def reset(self) -> None:
        self.statements = self.begins = self.commits = self.rollbacks = self.pings = 0
        self.log.clear()


def _in_transaction(dbapi_connection: Any) -> bool:
    return dbapi_connection.info.transaction_status != TransactionStatus.IDLE


@pytest.fixture
def round_trips(monkeypatch: pytest.MonkeyPatch) -> Iterator[RoundTrips]:
    counts = RoundTrips()

    def before_cursor_execute(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        dbapi = conn.connection.dbapi_connection
        if not dbapi.autocommit and not _in_transaction(dbapi):
            counts.begins += 1
            counts.log.append("BEGIN")
        counts.statements += 1
        counts.log.append(" ".join(statement.split())[:80])

    def on_commit(conn: Any) -> None:
        if _in_transaction(conn.connection.dbapi_connection):
            counts.commits += 1
            counts.log.append("COMMIT")

    def on_rollback(conn: Any) -> None:
        dbapi = conn.connection.dbapi_connection if not conn.closed else None
        if dbapi is not None and _in_transaction(dbapi):
            counts.rollbacks += 1
            counts.log.append("ROLLBACK")

    def on_reset(dbapi_connection: Any, record: Any, reset_state: Any) -> None:
        # The pool rolls back a connection returned mid-transaction (a read that never committed).
        if _in_transaction(dbapi_connection):
            counts.rollbacks += 1
            counts.log.append("ROLLBACK (pool reset)")

    dialect = engine.pool._dialect
    real_ping = dialect.do_ping

    def counting_ping(dbapi_connection: Any) -> bool:
        counts.pings += 1
        counts.log.append("SELECT 1 (pre-ping)")
        return real_ping(dbapi_connection)

    monkeypatch.setattr(dialect, "do_ping", counting_ping)
    listeners = [
        (engine, "before_cursor_execute", before_cursor_execute),
        (engine, "commit", on_commit),
        (engine, "rollback", on_rollback),
        (engine.pool, "reset", on_reset),
    ]
    for target, name, fn in listeners:
        event.listen(target, name, fn)
    yield counts
    for target, name, fn in listeners:
        event.remove(target, name, fn)


def _measure(round_trips: RoundTrips, label: str, request: Any) -> Dict[str, int]:
    round_trips.reset()
    request()
    breakdown = round_trips.breakdown()
    logger.info("%s: %s\n  %s", label, breakdown, "\n  ".join(round_trips.log))
    return breakdown


def test_me_round_trips(client: Any, account: Account, round_trips: RoundTrips) -> None:
    client.get("/me", headers=account.headers)  # warm the pool: a fresh connection skips the ping

    me = _measure(round_trips, "/me", lambda: client.get("/me", headers=account.headers))

    assert me["total"] == ME_BUDGET, me


def test_chat_turn_round_trips(client: Any, account: Account, round_trips: RoundTrips) -> None:
    upload(client, account)
    client.get("/me", headers=account.headers)

    first = _measure(round_trips, "chat, first turn (new session)", lambda: assert_contract(chat(client, account)))
    session_id = _last_session_id(client, account)
    follow_up = _measure(
        round_trips, "chat, follow-up turn",
        lambda: assert_contract(chat(client, account, "What does the reranker do with the chunks?", session_id)),
    )

    # Exact, not "at most": a drop is worth noticing too, so the budget gets updated on purpose.
    assert first["total"] == CHAT_FIRST_TURN_BUDGET, first
    assert follow_up["total"] == CHAT_FOLLOW_UP_BUDGET, follow_up
    assert first["ping"] == follow_up["ping"] == 0


def _last_session_id(client: Any, account: Account) -> int:
    return client.get("/sessions", headers=account.headers).json()[0]["id"]


# Measured on Day 16 and matched against the server's own log (log_statement=all); docs/briefs/day16.md.
# Before: /me 4 (ping, BEGIN, SELECT, ROLLBACK), first turn 33, follow-up 23.
# /me: BEGIN, the user, ROLLBACK.
ME_BUDGET = 3
# BEGIN, user, INSERT session, INSERT message, COMMIT | vector + keyword search (autocommit) |
# BEGIN, UPDATE topic, INSERT message, COMMIT.
CHAT_FIRST_TURN_BUDGET = 11
# The same with the session lookup + history instead of the INSERT session, and no topic UPDATE.
CHAT_FOLLOW_UP_BUDGET = 11
