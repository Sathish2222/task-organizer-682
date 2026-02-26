"""
task_manager_backend entrypoint.

This module defines the FastAPI application object (`app`) that can be served by
an ASGI server (e.g., uvicorn). It is intentionally minimal so other modules
(routers, DB setup, auth, etc.) can be added without breaking imports.

Run locally (example):
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI


def _create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    openapi_tags = [
        {
            "name": "Health",
            "description": "Service health and readiness endpoints.",
        }
    ]

    app = FastAPI(
        title="Task Manager Backend API",
        description="REST API for task management and authentication.",
        version="0.1.0",
        openapi_tags=openapi_tags,
    )

    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check",
        description="Returns a simple health status for monitoring and load balancers.",
        operation_id="health_check",
    )
    async def health() -> dict:
        # PUBLIC_INTERFACE
        """Health check endpoint.

        Returns:
            dict: A simple status payload.
        """
        return {"status": "ok"}

    return app


# PUBLIC_INTERFACE
def get_app() -> FastAPI:
    """Public accessor for the FastAPI app instance.

    This pattern makes it easy to extend initialization later (DB, routers, middleware)
    while keeping import sites stable.

    Returns:
        FastAPI: Configured FastAPI application.
    """
    return _create_app()


# The ASGI application expected by uvicorn/gunicorn.
app = get_app()
