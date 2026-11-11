#!/bin/sh
# Local and CI parity with the Supabase setup (scripts/supabase/setup_rag_schemas.sql): the app
# connects as rag_app, which owns schema `rag` and nothing else, and whose role-level search_path
# puts `rag` first and Supabase's `extensions` (pgvector, Day 15) second.
#
# Runs as the database superuser:
#   - docker compose: once, from /docker-entrypoint-initdb.d, when the pgdata volume is empty
#   - CI: `sh scripts/postgres/init-rag-schema.sh` with PGHOST / PGPASSWORD pointing at the service
# Needs POSTGRES_USER, POSTGRES_DB and RAG_APP_PASSWORD in the environment.
set -eu

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${RAG_APP_PASSWORD:?RAG_APP_PASSWORD must be set}"

# Quoted heredoc: the shell expands nothing inside; psql substitutes :'rag_app_password' as a
# quoted literal, so the password never needs escaping.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v rag_app_password="$RAG_APP_PASSWORD" <<'SQL'
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

CREATE ROLE rag_app LOGIN PASSWORD :'rag_app_password' CONNECTION LIMIT 10;
CREATE SCHEMA rag AUTHORIZATION rag_app;
REVOKE ALL ON SCHEMA rag FROM PUBLIC;
GRANT USAGE ON SCHEMA extensions TO rag_app;
ALTER ROLE rag_app SET search_path = rag, extensions;
SQL
