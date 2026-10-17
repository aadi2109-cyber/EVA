"""
EVA Agent Backend - Main Application Entrypoint.
FastAPI application with async lifespan, SQLite WAL initialization, and user seeding.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.files import MAX_UPLOAD_BYTES
from app.api.limits import OVERHEAD_BYTES, UploadSizeLimitMiddleware
from app.api.router import api_router
from app.auth.seeder import seed_users
from app.config import settings
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eva.backend")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting EVA Agent Backend (APP_ENV=%s, GUARD_TRANSPORT=%s)", settings.APP_ENV, settings.GUARD_TRANSPORT)
    # Initialize DB tables and seed accounts
    await init_db()
    await seed_users()
    logger.info("Database initialized and default accounts seeded.")
    yield
    logger.info("Shutting down EVA Agent Backend.")


app = FastAPI(
    title="EVA Agent Backend API",
    description="Tool-using AI agent orchestrator protected by deterministic guard system",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS setup for Frontend UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(UploadSizeLimitMiddleware, path="/api/files/upload", max_body_bytes=MAX_UPLOAD_BYTES + OVERHEAD_BYTES)
app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "name": "EVA Agent Backend",
        "version": "0.1.0",
        "status": "online",
        "docs": "/docs",
    }
