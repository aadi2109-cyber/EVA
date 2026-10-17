"""
Main API Router for EVA Agent Backend.
Mounts authentication, tasks, approvals, connectors, files, health, and admin proxy routes.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.approvals import router as approvals_router
from app.api.connectors import router as connectors_router
from app.api.files import router as files_router
from app.api.health import router as health_router
from app.api.tasks import router as tasks_router
from app.auth.router import router as auth_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(tasks_router)
api_router.include_router(approvals_router)
api_router.include_router(connectors_router)
api_router.include_router(files_router)
api_router.include_router(health_router)
api_router.include_router(admin_router)
