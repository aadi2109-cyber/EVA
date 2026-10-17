"""
Admin API proxy: exposes /api/admin/* and proxies requests unchanged to the
Guard service /admin/v1/*. Strictly protected by the JWT role=admin requirement.
The proxy never grants authority itself; the guard decides everything.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.deps import require_admin
from app.config import settings
from app.db.models import User

logger = logging.getLogger(__name__)

_REVIEW_DECISION_RE = re.compile(r"^review-queue/[^/]+/decision$")

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Tests may point the proxy at an in-process ASGI guard service.
_admin_transport: httpx.AsyncBaseTransport | None = None


def set_admin_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _admin_transport
    _admin_transport = transport


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_admin_request(
    path: str,
    request: Request,
    current_user: Annotated[User, Depends(require_admin)],
) -> Response:
    """Proxies /api/admin/<path> to Guard /admin/v1/<path>."""
    if settings.GUARD_TRANSPORT != "http":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Guard admin API requires GUARD_TRANSPORT=http; in-process mode has no admin HTTP facade",
        )
    if any(seg in ("..", ".") for seg in path.split("/")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid admin path")

    body = await request.body()
    target_url = f"{settings.GUARD_SERVICE_URL.rstrip('/')}/admin/v1/{path}"
    headers = {"Authorization": f"Bearer {settings.GUARD_SERVICE_TOKEN}"}
    if request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]

    # Admin identity always comes from the JWT, never from client-supplied fields:
    # four-eyes approval is only meaningful if proposer/approver cannot be spoofed.
    headers["X-Admin-User-Id"] = current_user.id
    # Body fields that name the acting admin are always overwritten from the JWT.
    clean_path = path.strip("/")
    identity_field = None
    if request.method == "POST" and clean_path == "config/proposals":
        identity_field = "proposed_by"
    elif request.method == "POST" and _REVIEW_DECISION_RE.match(clean_path):
        identity_field = "reviewer_id"
    if identity_field:
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")
        payload[identity_field] = current_user.id
        body = json.dumps(payload).encode()

    try:
        async with httpx.AsyncClient(timeout=10.0, transport=_admin_transport) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                params=list(request.query_params.multi_items()),
                content=body,
                headers=headers,
            )
    except Exception as e:
        logger.error("Guard admin proxy failed: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Guard service unreachable")

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
