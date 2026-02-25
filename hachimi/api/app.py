"""FastAPI application for Hachimi Music."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hachimi.api.routes import router
from hachimi.core.config import get_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    config = get_config()
    output_dir = config.get_output_dir()
    logging.info("Hachimi Music server starting...")
    logging.info("Output directory: %s", output_dir)
    yield
    logging.info("Hachimi Music server shutting down...")


app = FastAPI(
    title="Hachimi Music",
    description="AI-powered music generation: from natural language prompts to audio",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated audio files
output_dir = config.get_output_dir()
app.mount("/static/output", StaticFiles(directory=str(output_dir)), name="output")

# API routes
app.include_router(router, prefix="/api")

# Serve frontend static files
if _FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


@app.get("/")
async def root():
    """Redirect to frontend or show API info."""
    if _FRONTEND_DIR.exists():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/app/index.html")
    return {
        "name": "Hachimi Music",
        "version": "0.1.0",
        "docs": "/docs",
    }
