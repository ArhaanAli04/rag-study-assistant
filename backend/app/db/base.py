"""The declarative base every ORM model inherits from (T2, Day 13).

The naming convention gives every index and constraint a deterministic name on every backend.
Alembic can only alter or drop a constraint by name; Postgres would otherwise invent names
(users_email_key) and SQLite would leave them unnamed, so a later migration couldn't refer to them.
"""
from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))
