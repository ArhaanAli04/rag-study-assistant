"""Repositories (T2, Day 13): the one place each table's queries live.

Conventions:
- Plain functions that take the SQLAlchemy Session first; no classes, no Depends.
- The caller owns the transaction: repositories add, flush and query, but never commit, so a
  request that touches several tables commits or rolls back as one unit.
- user_id is always an int and every "owned" lookup filters by it: Postgres compares types
  strictly, and ownership is how the app isolates users (CLAUDE.md: scope all user data).
- No HTTP here: a missing row is None, and the router decides it is a 404.
"""
