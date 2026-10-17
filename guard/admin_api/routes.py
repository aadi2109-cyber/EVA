"""
Guard Admin API implementation.
Contract Version: 0.1.0
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Header
from contracts.models import (
    AuditVerifyResponse,
    ConfigProposalRequest,
    ConfigProposalResponse,
    Health,
    KillSwitchRequest,
    KillSwitchScope,
    KillSwitchState,
    ReviewDecisionRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/v1", tags=["Guard Admin"])
admin_router = router


# In-memory admin state (also persisted in SQLite)
_active_config: dict[str, Any] = {
    "version": 1,
    "minimum_detector_posture": "tier2_required",
    "failure_mode": "fail_closed",
    "block_threshold": 0.85,
    "t3_enabled": True,
    "align_enabled": True,
}

_proposals: dict[str, dict[str, Any]] = {}

# Eval run records (one JSON file each), written by the eval runners.
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def eval_results_dir() -> Path:
    return Path(os.getenv("EVA_EVAL_RESULTS_DIR") or Path(__file__).resolve().parents[1] / "eval" / "results")


def get_guard_instance():
    # Will be assigned from service main
    from eva_guard.api import Guard
    global _guard_singleton

    if "_guard_singleton" not in globals():
        _guard_singleton = Guard()
    return _guard_singleton


@router.get("/config", summary="Get Active Guard Configuration")
def get_config():
    return _active_config


@router.post("/config/proposals", response_model=ConfigProposalResponse, summary="Propose Config Change")
def propose_config_change(req: ConfigProposalRequest):
    """
    Submits a configuration change proposal.
    Sensitive changes (lowering posture floor) strictly require a second admin approval.
    """
    prop_id = f"prop-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)

    proposal = {
        "proposal_id": prop_id,
        "proposed_by": req.proposed_by,
        "changes": req.changes,
        "justification": req.justification,
        "status": "pending",
        "created_at": now,
        "approved_by": None,
        "approved_at": None,
    }
    _proposals[prop_id] = proposal

    guard = get_guard_instance()
    try:
        guard._audit.log_event(
            task_id=prop_id,
            event_type="config.proposed",
            actor=f"admin:{req.proposed_by}",
            payload={"changes": req.changes, "justification": req.justification},
        )
    except Exception as e:
        logger.error(f"Audit failure for config proposal: {e}")

    return ConfigProposalResponse(**proposal)


@router.get("/config/proposals", response_model=list[ConfigProposalResponse], summary="List Config Proposals")
def list_config_proposals(status: str | None = Query(None, pattern="^(pending|approved|rejected)$")):
    rows = [p for p in _proposals.values() if status is None or p["status"] == status]
    rows.sort(key=lambda p: p["created_at"], reverse=True)
    return [ConfigProposalResponse(**p) for p in rows]


@router.post("/config/proposals/{proposal_id}/reject", response_model=ConfigProposalResponse, summary="Reject Config Proposal")
def reject_config_proposal(proposal_id: str, rejecter_id: str = Header(..., alias="X-Admin-User-Id")):
    """Any admin (including the proposer, to withdraw it) may reject a pending proposal. Nothing is applied."""
    proposal = _proposals.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Proposal is already {proposal['status']}")

    proposal["status"] = "rejected"
    proposal["approved_by"] = None
    proposal["approved_at"] = None

    guard = get_guard_instance()
    try:
        guard._audit.log_event(
            task_id=proposal_id,
            event_type="config.rejected",
            actor=f"admin:{rejecter_id}",
            payload={"proposal_id": proposal_id, "changes": proposal["changes"]},
        )
    except Exception as e:
        logger.error(f"Audit failure for config rejection: {e}")

    return ConfigProposalResponse(**proposal)


@router.post("/config/proposals/{proposal_id}/approve", response_model=ConfigProposalResponse, summary="Approve Config Proposal (Four-Eyes)")
def approve_config_proposal(proposal_id: str, approver_id: str = Header(..., alias="X-Admin-User-Id")):
    """
    Four-eyes approval requirement:
    The approver MUST be a different admin than the proposer.
    """
    proposal = _proposals.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Proposal is already {proposal['status']}")

    # Four-Eyes check: Admin A proposed, Admin B must approve
    if proposal["proposed_by"] == approver_id:
        raise HTTPException(
            status_code=400,
            detail="Four-eyes rule violation: Proposer cannot approve their own configuration proposal",
        )

    now = datetime.now(timezone.utc)
    proposal["status"] = "approved"
    proposal["approved_by"] = approver_id
    proposal["approved_at"] = now

    # Apply configuration changes
    for k, v in proposal["changes"].items():
        _active_config[k] = v
    _active_config["version"] += 1

    guard = get_guard_instance()
    try:
        guard._audit.log_event(
            task_id=proposal_id,
            event_type="config.changed",
            actor=f"admin:{approver_id}",
            payload={"proposal_id": proposal_id, "new_version": _active_config["version"], "changes": proposal["changes"]},
            config_version=_active_config["version"],
        )
    except Exception as e:
        logger.error(f"Audit failure for config change: {e}")

    return ConfigProposalResponse(**proposal)


@router.post("/kill-switch", response_model=Health, summary="Set Kill Switch")
def set_kill_switch(req: KillSwitchRequest):
    """
    Activates or deactivates kill switches taking immediate effect on the next check_action.
    """
    guard = get_guard_instance()
    current_ks = guard._gateway.kill_switch

    new_all_write = current_ks.all_write_tools
    new_tools = list(current_ks.tools)
    new_templates = list(current_ks.templates)

    if req.scope == KillSwitchScope.ALL_WRITE_TOOLS:
        new_all_write = req.enabled
    elif req.scope == KillSwitchScope.TOOL and req.target:
        if req.enabled and req.target not in new_tools:
            new_tools.append(req.target)
        elif not req.enabled and req.target in new_tools:
            new_tools.remove(req.target)
    elif req.scope == KillSwitchScope.TEMPLATE and req.target:
        if req.enabled and req.target not in new_templates:
            new_templates.append(req.target)
        elif not req.enabled and req.target in new_templates:
            new_templates.remove(req.target)

    updated_ks = KillSwitchState(
        all_write_tools=new_all_write,
        tools=new_tools,
        templates=new_templates,
    )
    guard._gateway.set_kill_switch(updated_ks)

    try:
        guard._audit.log_event(
            task_id="admin-killswitch",
            event_type="kill_switch.changed",
            actor="admin",
            payload={"scope": req.scope.value, "target": req.target, "enabled": req.enabled},
        )
    except Exception as e:
        logger.error(f"Audit failure for kill switch change: {e}")

    return guard.health()


@router.get("/review-queue", summary="List Quarantined/Held Review Items")
def list_review_queue():
    queue = get_guard_instance()._review_queue
    return sorted(queue.values(), key=lambda i: i.get("created_at", ""), reverse=True)


@router.post("/review-queue/{id}/decision", summary="Submit Human Review Decision")
def submit_review_decision(id: str, req: ReviewDecisionRequest):
    """
    Records a human review decision on flagged or held content.
    CRITICAL PRINCIPLE: Review decisions NEVER grant tool execution authority.
    """
    queue = get_guard_instance()._review_queue
    item = queue.get(id)
    if not item:
        # Create an on-demand record if needed
        item = {"id": id, "created_at": datetime.now(timezone.utc).isoformat()}
        queue[id] = item

    item["reviewer_id"] = req.reviewer_id
    item["decision"] = req.decision
    item["notes"] = req.notes
    item["decided_at"] = datetime.now(timezone.utc).isoformat()

    guard = get_guard_instance()
    try:
        guard._audit.log_event(
            task_id=id,
            event_type="review.decision",
            actor=f"reviewer:{req.reviewer_id}",
            payload={"decision": req.decision, "notes": req.notes},
        )
    except Exception as e:
        logger.error(f"Audit failure for review decision: {e}")

    return {"status": "recorded", "item": item}


@router.get("/audit", summary="Query Audit Log")
def query_audit(
    task_id: str | None = Query(None),
    event_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    guard = get_guard_instance()
    events = guard._audit.query(task_id=task_id, event_type=event_type, limit=limit, offset=offset)
    return events


@router.get("/audit/verify", response_model=AuditVerifyResponse, summary="Verify Audit Hash Chain Integrity")
def verify_audit_chain():
    guard = get_guard_instance()
    return guard._audit.verify_chain()


@router.get("/audit/export", summary="Export Entire Audit Log")
def export_audit():
    guard = get_guard_instance()
    events = guard._audit.query(limit=10000)
    return {"count": len(events), "events": events}


@router.get("/health", response_model=Health, summary="Admin Health Check")
def admin_health():
    guard = get_guard_instance()
    return guard.health()


def _read_run(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@router.get("/eval/runs", summary="List Eval Runs")
def list_eval_runs():
    """Summaries of eval runs saved by the eval runners (newest first). Empty list when none."""
    d = eval_results_dir()
    runs = []
    if d.is_dir():
        for f in d.glob("*.json"):
            data = _read_run(f)
            if data is None:
                continue
            results = data.get("results", [])
            runs.append(
                {
                    "id": f.stem,
                    "ts": data.get("ts"),
                    "profile": data.get("profile"),
                    "scenarios": [r.get("scenario") for r in results],
                    "passed": sum(1 for r in results if r.get("passed") is True),
                    "failed": sum(1 for r in results if r.get("passed") is False),
                    "total": len(results),
                }
            )
    runs.sort(key=lambda r: r.get("ts") or "", reverse=True)
    return runs


@router.get("/eval/runs/{run_id}", summary="Get Eval Run")
def get_eval_run(run_id: str):
    if not _RUN_ID_RE.match(run_id) or run_id in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid run id")
    data = _read_run(eval_results_dir() / f"{run_id}.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return {"id": run_id, **data}
