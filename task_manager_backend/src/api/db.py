import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence
from urllib.parse import urlparse, urlunparse

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


def _looks_like_url(value: str) -> bool:
    """Return True if value looks like a postgres URL (has a scheme)."""
    try:
        return bool(urlparse(value).scheme)
    except Exception:
        return False


# PUBLIC_INTERFACE
def get_db_dsn() -> str:
    """Build a Postgres DSN from environment variables.

    This backend runs against the `task_manager_database` container and therefore
    expects the standard env var names:
      POSTGRES_URL, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT

    IMPORTANT:
    - Some environments provide `POSTGRES_URL` as a *host* (e.g. `localhost`).
    - Other environments provide `POSTGRES_URL` as a *full URL*
      (e.g. `postgresql://localhost:5000/myapp`).

    This function supports both shapes:
    - If POSTGRES_URL is a full URL, we will use it and inject credentials if missing.
    - If POSTGRES_URL is host-like, we build a full DSN explicitly.

    Returns:
        A connection string suitable for psycopg, e.g.:
        `postgresql://user:pass@host:port/db`
    """
    postgres_url = _required_env("POSTGRES_URL").strip()
    user = _required_env("POSTGRES_USER")
    password = _required_env("POSTGRES_PASSWORD")
    db = _required_env("POSTGRES_DB")
    port = _required_env("POSTGRES_PORT")

    if _looks_like_url(postgres_url):
        parsed = urlparse(postgres_url)
        scheme = parsed.scheme or "postgresql"

        # If the provided URL already includes creds, keep them; otherwise inject.
        netloc = parsed.netloc
        if "@" not in netloc:
            netloc = f"{user}:{password}@{netloc}"

        # If path is empty (or `/`), ensure we set DB name from POSTGRES_DB.
        path = parsed.path or ""
        if path in ("", "/"):
            path = f"/{db}"

        # If the URL has no port and POSTGRES_PORT exists, inject it.
        # urlparse puts host:port in netloc, so we do a light touch here.
        if ":" not in netloc.split("@")[-1] and port:
            host_part = netloc.split("@")[-1]
            prefix = netloc[: -len(host_part)]
            netloc = f"{prefix}{host_part}:{port}"

        return urlunparse((scheme, netloc, path, "", "", ""))

    # Host-like POSTGRES_URL: build DSN explicitly.
    host = postgres_url
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
