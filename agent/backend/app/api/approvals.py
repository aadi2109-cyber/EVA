"""
Approvals API endpoint: submit approval decisions and resume waiting orchestrator tasks.
"""

from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contracts.models import SubmitApprovalRequest, SubmitApprovalResponse
from app.agent.orchestrator import get_active_task_orchestrator
from app.auth.deps import get_current_user
from app.db.database import get_db_session
from app.db.models import ApprovalIndex, User
from app.guard_client.factory import get_guard_client

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ApprovalSubmissionPayload(BaseModel):
    approved: bool
    edited_args: dict[str, Any] | None = None


@router.post("/{approval_id}", response_model=SubmitApprovalResponse)
async def submit_approval_decision(
    approval_id: str,
    payload: ApprovalSubmissionPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmitApprovalResponse:
    guard = get_guard_client()

    req = SubmitApprovalRequest(
        user_id=current_user.id,
        approved=payload.approved,
        edited_args=payload.edited_args,
    )

    try:
        resp = await guard.submit_approval(approval_id, req)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Guard rejected approval submission: {e}",
        )

    # Update approval index record in DB
    stmt = select(ApprovalIndex).where(ApprovalIndex.id == approval_id)
    res = await session.execute(stmt)
    appr_rec = res.scalar_one_or_none()
    if appr_rec:
        appr_rec.status = resp.status
        await session.commit()

        # Resume waiting orchestrator if active
        orch = get_active_task_orchestrator(appr_rec.task_id)
        if orch:
            orch.resolve_approval(approval_id, resp)

    return resp
