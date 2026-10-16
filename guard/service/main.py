"""
EVA Guard HTTP Service.
FastAPI service exposing Guard library methods and Admin endpoints.
Contract Version: 0.1.0
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from contracts.models import (
    CONTRACT_VERSION,
    BuildPolicyRequest,
    CheckActionRequest,
    CheckActionResponse,
    Health,
    ScanRequest,
    ScanResponse,
    SubmitApprovalRequest,
    SubmitApprovalResponse,
    TaskPolicy,
    VerifyStateRequest,
    VerifyStateResponse,
)
from admin_api.routes import admin_router
from eva_guard.api import Guard


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("guard.service")

# Prometheus Metrics
DECISION_COUNTER = Counter(
    "guard_decisions_total",
    "Total security gateway decisions",
    ["decision", "tool"],
)
SCAN_COUNTER = Counter(
    "guard_scans_total",
    "Total tool result scans",
    ["disposition"],
)
LATENCY_HISTOGRAM = Histogram(
    "guard_request_duration_seconds",
    "Guard API request duration in seconds",
    ["endpoint"],
)

app = FastAPI(
    title="EVA Guard Service",
    version=CONTRACT_VERSION,
    description="Deterministic security gateway, content scanner, and policy engine for EVA Agent",
)

# Shared Guard instance
guard_instance = Guard()
import admin_api.routes as admin_routes
admin_routes._guard_singleton = guard_instance


# Request size limit (rejects before the body is parsed). Scan fields are capped at 1 MB by DET.
MAX_BODY_BYTES = int(os.getenv("GUARD_MAX_BODY_BYTES", str(4 * 1024 * 1024)))


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    declared = request.headers.get("content-length")
    too_big = False
    if declared is not None:
        try:
            too_big = int(declared) > MAX_BODY_BYTES
        except ValueError:
            too_big = True
    elif request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        too_big = len(body) > MAX_BODY_BYTES
    if too_big:
        return JSONResponse(status_code=413, content={
            "error": "REQUEST_TOO_LARGE", "message": "Request body exceeds limit",
            "contract_version": CONTRACT_VERSION})
    return await call_next(request)


# Auth dependency
SERVICE_TOKEN = os.getenv("GUARD_SERVICE_TOKEN", "dev-guard-token")


def verify_bearer_token(authorization: str = Header(None)) -> str:
    # Allow local development bypass if token is explicitly disabled
    if not SERVICE_TOKEN:
        return "unauthenticated"
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]


# Structured error handler ensuring no stack traces leak
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Internal guard error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "GUARD_ERROR",
            "message": "Internal security system error",
            "contract_version": CONTRACT_VERSION,
        },
    )


# Mount Admin routes
app.include_router(admin_router, dependencies=[Depends(verify_bearer_token)])


# 2.1 build_task_policy
@app.post("/v1/policy", response_model=TaskPolicy, summary="Build Task Policy")
async def build_task_policy(
    req: BuildPolicyRequest,
    token: str = Depends(verify_bearer_token),
) -> TaskPolicy:
    with LATENCY_HISTOGRAM.labels(endpoint="policy").time():
        return guard_instance.build_task_policy(req)


# 2.2 scan_tool_result
@app.post("/v1/scan", response_model=ScanResponse, summary="Scan Tool Result")
async def scan_tool_result(
    req: ScanRequest,
    token: str = Depends(verify_bearer_token),
) -> ScanResponse:
    with LATENCY_HISTOGRAM.labels(endpoint="scan").time():
        resp = guard_instance.scan_tool_result(req)
        SCAN_COUNTER.labels(disposition=resp.disposition).inc()
        return resp


# 2.3 check_action
@app.post("/v1/check-action", response_model=CheckActionResponse, summary="Check Proposed Action")
async def check_action(
    req: CheckActionRequest,
    token: str = Depends(verify_bearer_token),
) -> CheckActionResponse:
    with LATENCY_HISTOGRAM.labels(endpoint="check_action").time():
        resp = guard_instance.check_action(req)
        DECISION_COUNTER.labels(decision=resp.decision, tool=req.tool).inc()
        return resp


# 2.4 submit_approval
@app.post("/v1/approvals/{approval_id}", response_model=SubmitApprovalResponse, summary="Submit Approval Decision")
async def submit_approval(
    approval_id: str,
    req: SubmitApprovalRequest,
    token: str = Depends(verify_bearer_token),
) -> SubmitApprovalResponse:
    with LATENCY_HISTOGRAM.labels(endpoint="submit_approval").time():
        return guard_instance.submit_approval(approval_id, req)


# 2.5 verify_state
@app.post("/v1/verify-state", response_model=VerifyStateResponse, summary="Verify Post-Execution State")
async def verify_state(
    req: VerifyStateRequest,
    token: str = Depends(verify_bearer_token),
) -> VerifyStateResponse:
    with LATENCY_HISTOGRAM.labels(endpoint="verify_state").time():
        return guard_instance.verify_state(req)


# 2.6 health
@app.get("/v1/health", response_model=Health, summary="Guard Health and Posture")
async def health() -> Health:
    return guard_instance.health()


# Prometheus Metrics
@app.get("/metrics", summary="Prometheus Metrics")
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
