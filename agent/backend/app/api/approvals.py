"""
Approvals API endpoint: submit approval decisions and resume waiting orchestrator tasks.
"""

from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contracts.models import SSEEventType, SubmitApprovalRequest, SubmitApprovalResponse
from app.agent.orchestrator import get_active_task_orchestrator
from app.auth.deps import get_current_user
from app.db.database import get_db_session
from app.db.models import ApprovalIndex, Task, User
from app.guard_client.factory import get_guard_client
from app.sse.broadcaster import get_task_broadcaster

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

    # Ownership: only the task owner may answer an approval (identity from JWT).
    res = await session.execute(select(ApprovalIndex).where(ApprovalIndex.id == approval_id))
    appr_rec = res.scalar_one_or_none()
    if appr_rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    task = (await session.execute(select(Task).where(Task.id == appr_rec.task_id))).scalar_one_or_none()
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if appr_rec.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Approval already {appr_rec.status}")

    req = SubmitApprovalRequest(
        user_id=current_user.id,
        approved=payload.approved,
        edited_args=payload.edited_args,
    )

    try:
        resp = await guard.submit_approval(approval_id, req)
    except Exception as e:
        # Fail closed: the approval stays pending/unresolved, nothing runs.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Guard rejected approval submission: {e}",
        )

    appr_rec.status = resp.status
    orch = get_active_task_orchestrator(appr_rec.task_id)

    if resp.status == "re_approval_required" and resp.approval is not None:
        # Edited args void the old approval; a fresh approval must be answered.
        new = resp.approval
        session.add(
            ApprovalIndex(
                id=new.approval_id,
                task_id=appr_rec.task_id,
                call_id=appr_rec.call_id,
                tool=appr_rec.tool,
                exact_action_json=new.exact_action,
                action_hash=new.action_hash,
                status="pending",
                expires_at=new.expires_at,
            )
        )
        await session.commit()
        broadcaster = await get_task_broadcaster(appr_rec.task_id)
        await broadcaster.emit(
            SSEEventType.APPROVAL_RESOLVED, {"approval_id": approval_id, "status": "re_approval_required"}
        )
        await broadcaster.emit(SSEEventType.APPROVAL_REQUIRED, {"approval": new.model_dump(mode="json")})
        if orch and orch.pending_approval_id == approval_id:
            # Keep the loop paused; it now waits on the new approval.
            orch.pending_approval_id = new.approval_id
            orch.pending_approval = new
        return resp

    await session.commit()
    if orch:
        orch.resolve_approval(approval_id, resp)
    return resp
