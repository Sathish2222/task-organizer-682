"""
FastAPI application entrypoint.

This module is intended to be used with:
    uvicorn main:app

It registers a lifespan (startup/shutdown) handler so that we can run code when
the server starts (e.g., printing a startup message).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Run application startup/shutdown logic.

    Prints a message on startup as requested.
    """
    print("Task Manager FastAPI app starting up...")
    yield
    print("Task Manager FastAPI app shutting down...")


app = FastAPI(
    title="Task Manager Backend API",
    description="Backend API for the Task Manager application.",
    version="0.1.0",
    lifespan=_lifespan,
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint.

    Returns:
        A simple JSON payload indicating the server is running.
    """
    return {"status": "ok"}
