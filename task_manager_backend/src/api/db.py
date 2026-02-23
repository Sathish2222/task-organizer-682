import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence

import psycopg
from psycopg.rows import dict_row


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            f"Please set it in the backend container .env."
        )
    return value


# PUBLIC_INTERFACE
def get_db_dsn() -> str:
    """Builds a Postgres DSN from environment variables.

    Uses the database container env var names:
      POSTGRES_URL, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT

    Returns:
        A connection string suitable for psycopg, e.g.:
        postgresql://user:pass@host:port/db
    """
    host = _required_env("POSTGRES_URL")
    user = _required_env("POSTGRES_USER")
    password = _required_env("POSTGRES_PASSWORD")
    db = _required_env("POSTGRES_DB")
    port = _required_env("POSTGRES_PORT")

    # Keep it explicit (and avoid assuming POSTGRES_URL already contains scheme).
    # If POSTGRES_URL includes scheme already, psycopg will reject this; expected
    # from platform is host-like value. If that changes, update here.
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Context manager returning a psycopg connection with dict rows."""
    conn = psycopg.connect(get_db_dsn(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def fetch_one(query: str, params: Optional[Sequence[Any]] = None) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_all(query: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()
            return [dict(r) for r in rows]


def execute(query: str, params: Optional[Sequence[Any]] = None) -> int:
    """Execute a statement and return affected rowcount."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            conn.commit()
            return cur.rowcount


def execute_returning_one(query: str, params: Optional[Sequence[Any]] = None) -> Dict[str, Any]:
    """Execute a statement with RETURNING and return the returned row (dict)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            conn.commit()
            if not row:
                raise RuntimeError("Expected a row to be returned but got none.")
            return dict(row)
