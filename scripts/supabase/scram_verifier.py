"""Print the SCRAM-SHA-256 verifier for a Postgres role password, without the password ever being
echoed, stored or sent anywhere (T2, Day 13). Standard library only.

    python scripts/supabase/scram_verifier.py rag_app

Why: setup_rag_schemas.sql runs in Supabase's SQL editor, which sends the whole script as ONE
query string; with log_statement = 'ddl' Postgres logs that entire string, so any plaintext
password in it would land in the server log. Postgres accepts a ready-made verifier in
ALTER ROLE ... PASSWORD '<verifier>' and stores it as is, so only the verifier is ever in the SQL.

The verifier is what Postgres keeps in pg_authid: it lets the server check a login but can't be
used to log in. It still allows an offline guessing attack, which is why the password must be
long and random (secrets.token_urlsafe(32) gives 43 characters).

Format (RFC 5802 / RFC 7677, as Postgres's scram_build_secret writes it):
    SCRAM-SHA-256$<iterations>:<base64 salt>$<base64 StoredKey>:<base64 ServerKey>
"""
import argparse
import base64
import getpass
import hashlib
import hmac
import secrets
import string
import sys

ITERATIONS = 4096  # Postgres's default scram_iterations
SALT_BYTES = 16  # Postgres's SCRAM_DEFAULT_SALT_LEN
MIN_LENGTH = 20
# The password goes into a connection URL as is, and ASCII sidesteps SASLprep normalisation,
# which this script (like most clients' fallbacks) doesn't implement.
ALLOWED = frozenset(string.ascii_letters + string.digits + "-_")


def scram_sha256_verifier(password: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> str:
    salt = salt if salt is not None else secrets.token_bytes(SALT_BYTES)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()

    def b64(raw: bytes) -> str:
        return base64.b64encode(raw).decode("ascii")

    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


def password_problem(password: str) -> str | None:
    if len(password) < MIN_LENGTH:
        return f"must be at least {MIN_LENGTH} characters"
    if not set(password) <= ALLOWED:
        return "may contain only letters, digits, '-' and '_' (it goes into a connection URL)"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a Postgres SCRAM-SHA-256 verifier for a password typed without echo.")
    parser.add_argument("role", help="role the password is for (only shown in the prompt)")
    role = parser.parse_args().role

    password = getpass.getpass(f"Password for {role} (not echoed): ")
    problem = password_problem(password)
    if problem is not None:
        sys.stderr.write(f"Refused: the password {problem}. Generate one with:\n"
                         '  python -c "import secrets; print(secrets.token_urlsafe(32))"\n')
        return 1
    if getpass.getpass("Repeat it: ") != password:
        sys.stderr.write("Refused: the two entries differ.\n")
        return 1

    sys.stdout.write(scram_sha256_verifier(password) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
