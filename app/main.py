"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.config import get_settings
from app.drive.routes import router as drive_router
from app.queue.routes import router as queue_router
from app.queue.worker import get_queue_worker
from app.youtube.routes import router as youtube_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting application...")
    settings = get_settings()
    logger.info("App: %s, Environment: %s", settings.app_name, settings.app_env)

    yield

    # Shutdown
    logger.info("Shutting down application...")
    worker = get_queue_worker()
    if worker.is_running():
        await worker.stop()


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "FastAPI backend for uploading videos from Google Drive to YouTube. "
            "Supports Google OAuth authentication, Drive folder scanning, "
            "upload queue management, and resumable uploads."
        ),
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # CORS middleware for frontend integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth_router)
    app.include_router(drive_router)
    app.include_router(youtube_router)
    app.include_router(queue_router)

    @app.get("/", tags=["root"])
    async def root() -> dict:
        """Root endpoint with API information."""
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "status": "running",
            "docs_url": "/docs",
            "redoc_url": "/redoc",
        }

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Create application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
