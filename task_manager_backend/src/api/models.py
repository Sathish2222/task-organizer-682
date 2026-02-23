from datetime import datetime
from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email (must be unique).")
    password: str = Field(..., min_length=6, description="User password (min 6 chars).")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email.")
    password: str = Field(..., description="User password.")


class UserOut(BaseModel):
    id: UUID = Field(..., description="User ID (UUID).")
    email: str = Field(..., description="User email.")


class AuthResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token.")
    token_type: str = Field("bearer", description="Token type.")
    user: UserOut = Field(..., description="Authenticated user info.")


TaskPriority = Union[str, int, None]


class TaskOut(BaseModel):
    id: UUID = Field(..., description="Task ID (UUID).")
    title: str = Field(..., description="Task title.")
    description: Optional[str] = Field(None, description="Optional task description.")
    completed: bool = Field(..., description="Completion status.")
    due_date: Optional[str] = Field(None, description="Due date/time ISO string (nullable).")
    priority: Optional[TaskPriority] = Field(None, description="Priority, frontend accepts low/medium/high or number.")
    tags: List[str] = Field(default_factory=list, description="List of tag names.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, description="Task title.")
    description: Optional[str] = Field(None, description="Task description.")
    due_date: Optional[str] = Field(None, description="ISO date or datetime string.")
    priority: Optional[TaskPriority] = Field(None, description="Priority (low/medium/high or 1..5).")
    tags: Optional[List[str]] = Field(None, description="Optional list of tag names.")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, description="Task title.")
    description: Optional[str] = Field(None, description="Task description.")
    due_date: Optional[str] = Field(None, description="ISO date or datetime string.")
    priority: Optional[TaskPriority] = Field(None, description="Priority (low/medium/high or 1..5).")
    tags: Optional[List[str]] = Field(None, description="Replace task tags with this list.")
    completed: Optional[bool] = Field(None, description="Completion status.")


class TagOut(BaseModel):
    id: UUID = Field(..., description="Tag ID.")
    name: str = Field(..., description="Tag name.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")
