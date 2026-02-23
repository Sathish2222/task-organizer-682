from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth import create_access_token, get_current_user, hash_password, verify_password
from src.api.db import execute, execute_returning_one, fetch_all, fetch_one
from src.api.models import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TagOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    UserOut,
)

openapi_tags = [
    {"name": "Health", "description": "Health and diagnostics endpoints."},
    {"name": "Auth", "description": "User registration and login."},
    {"name": "Users", "description": "Current user profile."},
    {"name": "Tasks", "description": "User-scoped task CRUD + filter/search/sort."},
    {"name": "Tags", "description": "User-scoped tags listing and helper endpoints."},
]


def _env_list(name: str) -> List[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    # comma-separated list
    return [p.strip() for p in raw.split(",") if p.strip()]


def _priority_to_db(priority: Any) -> int:
    """Map frontend priority (low/medium/high or number) to DB priority (1..5)."""
    if priority is None:
        return 3
    if isinstance(priority, int):
        return max(1, min(5, priority))
    if isinstance(priority, str):
        p = priority.strip().lower()
        if p == "high":
            return 2
        if p == "medium":
            return 3
        if p == "low":
            return 4
        # allow numeric-like strings
        try:
            return max(1, min(5, int(p)))
        except ValueError:
            return 3
    return 3


def _priority_from_db(priority: int) -> int:
    return int(priority)


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO date/datetime string to aware datetime (UTC) if possible."""
    if not value:
        return None
    v = value.strip()
    try:
        # Support `YYYY-MM-DD` (frontend might send).
        if len(v) == 10 and v[4] == "-" and v[7] == "-":
            dt = datetime.fromisoformat(v)  # naive date -> midnight
            return dt.replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid due_date format. Use ISO string.")


def _task_with_tags_row_to_out(row: Dict[str, Any]) -> TaskOut:
    tags = []
    if row.get("tags"):
        tags = [t for t in str(row["tags"]).split(",") if t]
    return TaskOut(
        id=row["id"],
        title=row["title"],
        description=row.get("description"),
        completed=bool(row["is_completed"]),
        due_date=row["due_at"].isoformat() if row.get("due_at") else None,
        priority=_priority_from_db(row.get("priority", 3)),
        tags=tags,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _get_cors_origins() -> List[str]:
    # If FRONTEND_ORIGIN(S) not set, default to permissive (for dev),
    # but allow operators to restrict in prod.
    origins = _env_list("FRONTEND_ORIGINS") or _env_list("FRONTEND_ORIGIN")
    return origins if origins else ["*"]


def _get_token_exp_minutes() -> int:
    try:
        return int(os.getenv("JWT_EXPIRES_MINUTES", "10080"))  # 7 days default
    except ValueError:
        return 10080


app = FastAPI(
    title="Task Manager API",
    description=(
        "Backend API for a simple task manager.\n\n"
        "Auth uses JWT Bearer tokens. Supply `Authorization: Bearer <token>` "
        "to access user-scoped task/tag endpoints."
    ),
    version="1.0.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"], summary="Health check")
def health_check() -> Dict[str, str]:
    """Health check endpoint.

    Returns:
        Simple JSON payload indicating the API is reachable.
    """
    return {"message": "Healthy"}


@app.get(
    "/docs/auth",
    tags=["Auth"],
    summary="Auth usage help",
    description="Explains how to use login/register + Bearer tokens with this API.",
)
def auth_usage() -> Dict[str, Any]:
    """Returns a small help payload describing auth usage."""
    return {
        "register": {"method": "POST", "path": "/auth/register", "body": {"email": "a@b.com", "password": "secret123"}},
        "login": {"method": "POST", "path": "/auth/login", "body": {"email": "a@b.com", "password": "secret123"}},
        "auth_header": "Authorization: Bearer <access_token>",
    }


# =========================
# Auth
# =========================

@app.post(
    "/auth/register",
    tags=["Auth"],
    response_model=AuthResponse,
    summary="Register a new user",
)
def register(payload: RegisterRequest) -> AuthResponse:
    """Register a new user and return an access token."""
    existing = fetch_one("SELECT id FROM users WHERE email = %s", (payload.email.lower(),))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    row = execute_returning_one(
        "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email",
        (payload.email.lower(), hash_password(payload.password)),
    )
    token = create_access_token(user_id=row["id"], email=row["email"], expires_minutes=_get_token_exp_minutes())
    return AuthResponse(access_token=token, user=UserOut(id=row["id"], email=row["email"]))


@app.post(
    "/auth/login",
    tags=["Auth"],
    response_model=AuthResponse,
    summary="Login and obtain an access token",
)
def login(payload: LoginRequest) -> AuthResponse:
    """Login by verifying email/password and returning an access token."""
    user = fetch_one("SELECT id, email, password_hash FROM users WHERE email = %s", (payload.email.lower(),))
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user_id=user["id"], email=user["email"], expires_minutes=_get_token_exp_minutes())
    return AuthResponse(access_token=token, user=UserOut(id=user["id"], email=user["email"]))


@app.get(
    "/auth/me",
    tags=["Users"],
    response_model=UserOut,
    summary="Get current user",
)
def me(user: Dict[str, Any] = Depends(get_current_user)) -> UserOut:
    """Return current authenticated user."""
    return UserOut(id=user["id"], email=user["email"])


# =========================
# Tags
# =========================

@app.get(
    "/tags",
    tags=["Tags"],
    response_model=List[TagOut],
    summary="List user's tags",
)
def list_tags(user: Dict[str, Any] = Depends(get_current_user)) -> List[TagOut]:
    """List all tags for current user (sorted by name)."""
    rows = fetch_all(
        "SELECT id, name, created_at, updated_at FROM tags WHERE user_id = %s ORDER BY name ASC",
        (user["id"],),
    )
    return [TagOut(**r) for r in rows]


# =========================
# Tasks
# =========================

def _ensure_tags_for_user(user_id: UUID, names: Sequence[str]) -> List[UUID]:
    """Ensure tags exist for user; return tag IDs in same order as unique names."""
    cleaned = []
    seen = set()
    for n in names:
        name = n.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)

    tag_ids: List[UUID] = []
    for name in cleaned:
        row = fetch_one("SELECT id FROM tags WHERE user_id = %s AND name = %s", (user_id, name))
        if row:
            tag_ids.append(row["id"])
            continue
        created = execute_returning_one(
            "INSERT INTO tags (user_id, name) VALUES (%s, %s) RETURNING id",
            (user_id, name),
        )
        tag_ids.append(created["id"])
    return tag_ids


def _replace_task_tags(task_id: UUID, tag_ids: Sequence[UUID]) -> None:
    execute("DELETE FROM task_tags WHERE task_id = %s", (task_id,))
    for tid in tag_ids:
        execute(
            "INSERT INTO task_tags (task_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (task_id, tid),
        )


def _get_task_or_404(task_id: UUID, user_id: UUID) -> Dict[str, Any]:
    row = fetch_one("SELECT id FROM tasks WHERE id = %s AND user_id = %s", (task_id, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


@app.get(
    "/tasks",
    tags=["Tasks"],
    response_model=List[TaskOut],
    summary="List tasks (with optional filters)",
)
def list_tasks(
    user: Dict[str, Any] = Depends(get_current_user),
    q: Optional[str] = Query(None, description="Search query (matches title/description)."),
    tag: Optional[str] = Query(None, description="Filter by tag name."),
    completed: Optional[bool] = Query(None, description="Filter by completion state."),
    priority: Optional[str] = Query(None, description="Filter by priority (1..5 or low/medium/high)."),
    due_before: Optional[str] = Query(None, description="Filter tasks due before this ISO date/datetime."),
    due_after: Optional[str] = Query(None, description="Filter tasks due after this ISO date/datetime."),
    sort: Optional[str] = Query(
        None,
        description="Sort key: created_at, due_at, priority, updated_at. Prefix with '-' for DESC.",
        examples=["-created_at", "due_at"],
    ),
) -> List[TaskOut]:
    """List tasks for the authenticated user with optional filtering and sorting."""
    where = ["t.user_id = %s"]
    params: List[Any] = [user["id"]]

    join = ""
    if tag:
        join = "JOIN task_tags tt ON tt.task_id = t.id JOIN tags tg ON tg.id = tt.tag_id"
        where.append("tg.name = %s")
        params.append(tag)

    if completed is not None:
        where.append("t.is_completed = %s")
        params.append(completed)

    if priority is not None:
        where.append("t.priority = %s")
        params.append(_priority_to_db(priority))

    if due_before:
        where.append("t.due_at IS NOT NULL AND t.due_at <= %s")
        params.append(_parse_iso_datetime(due_before))

    if due_after:
        where.append("t.due_at IS NOT NULL AND t.due_at >= %s")
        params.append(_parse_iso_datetime(due_after))

    if q:
        where.append("(t.title ILIKE %s OR t.description ILIKE %s)")
        like = f"%{q}%"
        params.extend([like, like])

    sort_key = (sort or "-created_at").strip()
    desc = sort_key.startswith("-")
    key = sort_key[1:] if desc else sort_key
    order_expr_map = {
        "created_at": "t.created_at",
        "updated_at": "t.updated_at",
        "due_at": "t.due_at",
        "priority": "t.priority",
    }
    order_expr = order_expr_map.get(key, "t.created_at")
    order_dir = "DESC" if desc else "ASC"
    # Put NULL due_at last when sorting by due_at
    if key == "due_at":
        order_by = f"{order_expr} {order_dir} NULLS LAST, t.created_at DESC"
    else:
        order_by = f"{order_expr} {order_dir}"

    query = f"""
        SELECT
          t.*,
          COALESCE(string_agg(DISTINCT tg2.name, ',' ORDER BY tg2.name), '') AS tags
        FROM tasks t
        {join}
        LEFT JOIN task_tags tt2 ON tt2.task_id = t.id
        LEFT JOIN tags tg2 ON tg2.id = tt2.tag_id
        WHERE {' AND '.join(where)}
        GROUP BY t.id
        ORDER BY {order_by}
    """
    rows = fetch_all(query, params)
    return [_task_with_tags_row_to_out(r) for r in rows]


@app.post(
    "/tasks",
    tags=["Tasks"],
    response_model=TaskOut,
    status_code=201,
    summary="Create a task",
)
def create_task(payload: TaskCreate, user: Dict[str, Any] = Depends(get_current_user)) -> TaskOut:
    """Create a new task for the authenticated user."""
    due_at = _parse_iso_datetime(payload.due_date)
    db_priority = _priority_to_db(payload.priority)

    row = execute_returning_one(
        """
        INSERT INTO tasks (user_id, title, description, due_at, priority)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (user["id"], payload.title, payload.description, due_at, db_priority),
    )

    tag_names = payload.tags or []
    tag_ids = _ensure_tags_for_user(user["id"], tag_names) if tag_names else []
    if tag_ids:
        _replace_task_tags(row["id"], tag_ids)

    # Reload with tags aggregate for consistent response
    full = fetch_one(
        """
        SELECT
          t.*,
          COALESCE(string_agg(DISTINCT tg.name, ',' ORDER BY tg.name), '') AS tags
        FROM tasks t
        LEFT JOIN task_tags tt ON tt.task_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        WHERE t.id = %s AND t.user_id = %s
        GROUP BY t.id
        """,
        (row["id"], user["id"]),
    )
    return _task_with_tags_row_to_out(full)  # type: ignore[arg-type]


@app.patch(
    "/tasks/{task_id}",
    tags=["Tasks"],
    response_model=TaskOut,
    summary="Update a task",
)
@app.put(
    "/tasks/{task_id}",
    tags=["Tasks"],
    response_model=TaskOut,
    summary="Replace/update a task",
)
def update_task(task_id: UUID, payload: TaskUpdate, user: Dict[str, Any] = Depends(get_current_user)) -> TaskOut:
    """Update fields of a task (PATCH/PUT accepted)."""
    _get_task_or_404(task_id, user["id"])

    fields: List[str] = []
    params: List[Any] = []

    if payload.title is not None:
        fields.append("title = %s")
        params.append(payload.title)
    if payload.description is not None:
        fields.append("description = %s")
        params.append(payload.description)
    if payload.due_date is not None:
        fields.append("due_at = %s")
        params.append(_parse_iso_datetime(payload.due_date))
    if payload.priority is not None:
        fields.append("priority = %s")
        params.append(_priority_to_db(payload.priority))
    if payload.completed is not None:
        fields.append("is_completed = %s")
        params.append(payload.completed)
        fields.append("completed_at = %s")
        params.append(datetime.now(timezone.utc) if payload.completed else None)

    if fields:
        params.extend([task_id, user["id"]])
        execute(
            f"UPDATE tasks SET {', '.join(fields)} WHERE id = %s AND user_id = %s",
            params,
        )

    if payload.tags is not None:
        tag_ids = _ensure_tags_for_user(user["id"], payload.tags)
        _replace_task_tags(task_id, tag_ids)

    full = fetch_one(
        """
        SELECT
          t.*,
          COALESCE(string_agg(DISTINCT tg.name, ',' ORDER BY tg.name), '') AS tags
        FROM tasks t
        LEFT JOIN task_tags tt ON tt.task_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        WHERE t.id = %s AND t.user_id = %s
        GROUP BY t.id
        """,
        (task_id, user["id"]),
    )
    if not full:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_with_tags_row_to_out(full)


@app.delete(
    "/tasks/{task_id}",
    tags=["Tasks"],
    summary="Delete a task",
)
def delete_task(task_id: UUID, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    """Delete a task owned by the authenticated user."""
    _get_task_or_404(task_id, user["id"])
    execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, user["id"]))
    return {"ok": True}
