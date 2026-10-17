"""
EVA Agent Backend - Main Application Entrypoint.
FastAPI application with async lifespan, SQLite WAL initialization, and user seeding.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.router import api_router
from app.auth.seeder import seed_users
from app.config import settings
from app.db.database import async_session_factory, init_db
from app.db.models import ApprovalIndex, Task
from app.sse.broadcaster import get_task_broadcaster
from contracts.models import SSEEventType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eva.backend")


async def recover_inflight_tasks() -> int:
    """Fail closed on tasks that lost their orchestrator during an API restart."""
    async with async_session_factory() as session:
        result = await session.execute(select(Task).where(Task.status == "running"))
        tasks = result.scalars().all()
        for task in tasks:
            pending_result = await session.execute(
                select(ApprovalIndex).where(
                    ApprovalIndex.task_id == task.id,
                    ApprovalIndex.status == "pending",
                )
            )
            for approval in pending_result.scalars().all():
                approval.status = "expired"

            task.status = "held"
            task.final_text = "Task held because the backend restarted while it was in progress."
            task.summary_json = {"sentences_removed": 0, "actions_denied": 0, "approvals": 0}
        await session.commit()

    for task in tasks:
        broadcaster = await get_task_broadcaster(task.id)
        await broadcaster.emit(
            SSEEventType.TASK_HELD,
            {
                "final_text": task.final_text,
                "summary": task.summary_json,
                "reason": "backend_restart",
            },
        )
    return len(tasks)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting EVA Agent Backend (APP_ENV=%s, GUARD_TRANSPORT=%s)", settings.APP_ENV, settings.GUARD_TRANSPORT)
    # Initialize DB tables and seed accounts
    await init_db()
    await seed_users()
    recovered = await recover_inflight_tasks()
    if recovered:
        logger.warning("Held %d in-flight task(s) after backend restart", recovered)
    logger.info("Database initialized and default accounts seeded.")
    yield
    logger.info("Shutting down EVA Agent Backend.")


app = FastAPI(
    title="EVA Agent Backend API",
    description="Tool-using AI agent orchestrator protected by deterministic guard system",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def sanitize_otp_validation_errors(request: Request, exc: RequestValidationError):
    if request.url.path in {"/api/auth/otp/send", "/api/auth/otp/verify"}:
        # Pydantic errors contain submitted input values; never echo phone numbers or OTPs.
        safe_errors = [
            {key: error[key] for key in ("loc", "msg", "type") if key in error}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})
    return await request_validation_exception_handler(request, exc)

# CORS setup for Frontend UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.FRONTEND_ORIGINS.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "name": "EVA Agent Backend",
        "version": "0.1.0",
        "status": "online",
        "docs": "/docs",
    }
