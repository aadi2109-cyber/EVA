"""
Admin API proxy: exposes /api/admin/* and proxies requests to Guard admin endpoints.
Strictly protected by JWT role=admin requirement.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
import httpx

from app.auth.deps import require_admin
from app.config import settings
from app.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_admin_request(
    path: str,
    request: Request,
    current_user: Annotated[User, Depends(require_admin)],
) -> Response:
    """
    Proxies all /api/admin/* calls to Guard /admin/v1/*
    """
    body = await request.body()
    query_params = dict(request.query_params)
    method = request.method

    if settings.GUARD_TRANSPORT == "http":
        target_url = f"{settings.GUARD_SERVICE_URL.rstrip('/')}/admin/v1/{path}"
        headers = {
            "Authorization": f"Bearer {settings.GUARD_SERVICE_TOKEN}",
            "Content-Type": request.headers.get("content-type", "application/json"),
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.request(
                    method=method,
                    url=target_url,
                    params=query_params,
                    content=body,
                    headers=headers,
                )
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json"),
                )
        except Exception as e:
            logger.error("HTTP Guard admin proxy failed: %s", e)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Guard service unreachable: {e}")

    else:
        # In-process transport: invoke the guard's admin router or service
        target_url = f"{settings.GUARD_SERVICE_URL.rstrip('/')}/admin/v1/{path}"
        # If guard service is running, proxy to it; otherwise call admin_router handler
        try:
            from guard.admin_api.routes import router as guard_admin_router
            # We can use httpx ASGITransport over the FastAPI guard app or dispatch internally
            from fastapi import FastAPI
            app_temp = FastAPI()
            app_temp.include_router(guard_admin_router)

            transport = httpx.ASGITransport(app=app_temp)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.request(
                    method=method,
                    url=f"/admin/v1/{path}",
                    params=query_params,
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json"),
                )
        except Exception as e:
            logger.error("In-process Guard admin proxy failed: %s", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
