"""
Minimal FastAPI backend entrypoint for the Task Manager application.

This module defines the FastAPI `app` object that ASGI servers (e.g., uvicorn)
can import as `main:app`.
"""

from fastapi import FastAPI

app = FastAPI(title="Task Manager Backend", version="0.1.0")

print("Task Manager backend started")  # single requested print statement


@app.get("/health", tags=["health"])
def health_check() -> dict:
    """Basic health endpoint for verifying the backend is running."""
    return {"status": "ok"}
