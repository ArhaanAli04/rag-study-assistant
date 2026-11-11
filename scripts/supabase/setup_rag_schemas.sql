-- =================================================================================================
-- RAG Study Assistant: production and staging schemas in the existing Supabase project (T2, Day 13)
-- =================================================================================================
--
-- What it creates (and nothing else; no other schema, table or role is touched):
--   rag          owned by rag_app          production   search_path = rag, extensions
--   rag_staging  owned by rag_staging_app  staging      search_path = rag_staging, extensions
--   the pgvector extension in Supabase's `extensions` schema (Day 15 needs it; app roles can't
--   create extensions)
--
-- Isolation: each role owns only its own schema and gets USAGE on `extensions` (for pgvector's type
-- and operators). No grants to anon / authenticated / service_role. Keep both schemas OUT of
-- Settings -> API -> Exposed schemas. Tables are created later by Alembic, connected as the role,
-- so the role owns them and the search_path decides where they go.
--
-- NO PLAINTEXT PASSWORDS IN THIS FILE, EVER. The SQL editor sends the whole script as ONE query
-- string, and this project has log_statement = 'ddl': Postgres then logs the entire string, step 1
-- included (proved on Day 13 in a throwaway container: both test passwords appeared in the server
-- log). Step 1 therefore takes SCRAM-SHA-256 verifiers, which Postgres stores as they are; the
-- passwords themselves never leave your machine.
--
-- HOW TO RUN (as `postgres`, the SQL editor's default role)
--   1. Generate two passwords (letters/digits/-/_ only; they go into connection URLs):
--        python -c "import secrets; print(secrets.token_urlsafe(32))"
--      Keep them in your password manager; they are what goes into the connection URLs later.
--   2. Turn each into its verifier, locally (prompts without echo, prints only the verifier):
--        python scripts/supabase/scram_verifier.py rag_app
--        python scripts/supabase/scram_verifier.py rag_staging_app
--   3. Paste the two verifiers (each starts with SCRAM-SHA-256$4096:) into step 1, replacing the
--      <...> placeholders. Never paste a password into this file: step 3 refuses anything that
--      isn't a verifier, but Postgres has already logged the whole script by then. If a password
--      was ever run in here, treat it as exposed and generate a new one.
--   4. Run the whole script once. It is one transaction: any error rolls everything back.
--      The last statement prints a summary (no secrets) - check it.
--   5. Check Settings -> API -> Exposed schemas: rag and rag_staging must not be listed.
--   6. Don't keep this as a saved snippet. A verifier can't be used to log in, but it allows an
--      offline guessing attack, so treat it as sensitive (the long random password is the defence).
--
-- Re-running is safe: existing roles get their limit and verifier reset to the values in step 1;
-- existing schemas are left as they are.
--
-- Connecting afterwards (Supavisor session pooler, IPv4, port 5432; the username is role.project-ref):
--   app:   postgresql+psycopg://rag_app.<project-ref>:<password>@<pooler-host>:5432/postgres   DATABASE_SCHEMA=rag
--   psql:  postgresql://rag_app.<project-ref>:<password>@<pooler-host>:5432/postgres
-- <pooler-host> is the host in Connect -> Session pooler (aws-0-<region>.pooler.supabase.com).
-- =================================================================================================

BEGIN;

-- Step 1: SCRAM-SHA-256 verifiers from scram_verifier.py (transaction-local, gone at COMMIT) -------
SELECT count(*) AS verifiers_set FROM (VALUES
    (set_config('rag_setup.rag_app_verifier',         '<RAG_APP_SCRAM_VERIFIER>',         true)),
    (set_config('rag_setup.rag_staging_app_verifier', '<RAG_STAGING_APP_SCRAM_VERIFIER>', true))
) AS step_1(value);

-- Step 2: pgvector, in the schema Supabase keeps extensions in --------------------------------------
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- Step 3: one login role + one schema per environment ----------------------------------------------
DO $setup$
DECLARE
    env record;
    verifier text;
BEGIN
    FOR env IN
        SELECT * FROM (VALUES
            -- production allows 20 connections: during a zero-downtime deploy the old and the new
            -- instance (app pool 5 + overflow 5 each) briefly run side by side
            ('rag_app',         'rag',         20),
            ('rag_staging_app', 'rag_staging', 10)
        ) AS t(role_name, schema_name, connection_limit)
    LOOP
        verifier := current_setting('rag_setup.' || env.role_name || '_verifier');
        -- Only a well-formed verifier gets through: a pasted plaintext password (or a leftover
        -- placeholder) is refused before anything is created.
        IF verifier !~ '^SCRAM-SHA-256\$[0-9]+:[A-Za-z0-9+/]+=*\$[A-Za-z0-9+/]+=*:[A-Za-z0-9+/]+=*$' THEN
            RAISE EXCEPTION 'Step 1: the value for % must be a SCRAM-SHA-256 verifier from scram_verifier.py (starting SCRAM-SHA-256$), not a password or placeholder. Nothing was changed.', env.role_name;
        END IF;

        -- On a re-run only LOGIN and the limit are reasserted: a non-superuser may not even name
        -- NOSUPERUSER / NOREPLICATION / NOBYPASSRLS in ALTER ROLE.
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = env.role_name) THEN
            EXECUTE format('ALTER ROLE %I LOGIN CONNECTION LIMIT %s', env.role_name, env.connection_limit);
        ELSE
            EXECUTE format(
                'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT %s',
                env.role_name, env.connection_limit);
        END IF;

        -- Postgres recognises a SCRAM verifier and stores it as is (password_encryption doesn't apply).
        EXECUTE format('ALTER ROLE %I PASSWORD %L', env.role_name, verifier);

        -- Postgres 16+: the creator of a role may administer it but not SET ROLE to it unless
        -- createrole_self_grant says so (empty in this project), and CREATE SCHEMA ... AUTHORIZATION
        -- requires SET. INHERIT FALSE: postgres does not silently gain the role's privileges.
        EXECUTE format('GRANT %I TO postgres WITH INHERIT FALSE, SET TRUE', env.role_name);

        EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I', env.schema_name, env.role_name);

        -- Explicit even though nothing is granted today: the API roles and PUBLIC get nothing here.
        -- Only the owner may revoke on the schema, and postgres doesn't inherit the role's rights
        -- (INHERIT FALSE above), so this one statement runs as the owner.
        EXECUTE format('SET LOCAL ROLE %I', env.role_name);
        EXECUTE format('REVOKE ALL ON SCHEMA %I FROM PUBLIC, anon, authenticated, service_role', env.schema_name);
        RESET ROLE;

        -- pgvector's type and operators live in `extensions`; the role may use them, not create there.
        EXECUTE format('GRANT USAGE ON SCHEMA extensions TO %I', env.role_name);

        -- Set on the role, not in the URL, so it applies through the pooler. The app and Alembic
        -- refuse to run if current_schema() isn't DATABASE_SCHEMA (app/db/migrations.py).
        EXECUTE format('ALTER ROLE %I SET search_path = %I, extensions', env.role_name, env.schema_name);

        -- A runaway query can't hold a connection forever. Migrations that need longer (e.g. an HNSW
        -- index build on Day 15) can SET LOCAL statement_timeout inside their own transaction.
        EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', env.role_name, '60s');
    END LOOP;
END
$setup$;

-- Step 4: summary to check before closing the editor (no secrets) -----------------------------------
SELECT
    r.rolname                                              AS role,
    r.rolcanlogin                                          AS can_login,
    r.rolconnlimit                                         AS connection_limit,
    n.nspname                                              AS owns_schema,
    (SELECT string_agg(c, '; ') FROM unnest(r.rolconfig) AS c) AS role_settings,
    has_schema_privilege(r.rolname, 'extensions', 'USAGE') AS extensions_usage,
    (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS vector_version
FROM pg_roles r
LEFT JOIN pg_namespace n ON n.nspowner = r.oid AND n.nspname IN ('rag', 'rag_staging')
WHERE r.rolname IN ('rag_app', 'rag_staging_app')
ORDER BY r.rolname;

COMMIT;
