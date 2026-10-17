"""
Guard Admin API implementation.
Contract Version: 0.1.0
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import logging
import uuid
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


def get_guard_instance():
    # Will be assigned from service main
    from eva_guard.api import Guard
    global _guard_singleton

    if "_guard_singleton" not in globals():
        _guard_singleton = Guard()
    return _guard_singleton


@router.get("/config", summary="Get Active Guard Configuration")
def get_config():
    return get_guard_instance().get_config()


@router.get("/config/history", summary="Config Version History")
def config_history():
    return get_guard_instance()._store.config_history()


@router.post("/config/proposals", response_model=ConfigProposalResponse, summary="Propose Config Change")
def propose_config_change(req: ConfigProposalRequest):
    """
    Submits a configuration change proposal.
    Sensitive changes (lowering posture floor) strictly require a second admin approval.
    """
    guard = get_guard_instance()
    try:
        guard.validate_config_changes(req.changes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
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
    proposal["lowers_security"] = guard.is_lowering(guard.get_config(), req.changes)
    guard._store.put_proposal(proposal)

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


@router.get("/config/proposals", summary="List Config Proposals")
def list_config_proposals(status: str | None = Query(None, pattern="^(pending|approved|rejected)$")):
    return get_guard_instance()._store.list_proposals(status if isinstance(status, str) else None)


@router.post("/config/proposals/{proposal_id}/reject", response_model=ConfigProposalResponse, summary="Reject / Withdraw Config Proposal")
def reject_config_proposal(proposal_id: str, rejecter_id: str = Header(..., alias="X-Admin-User-Id")):
    """Any admin (including the proposer, i.e. withdrawal) may reject a pending proposal. Rejecting never changes config."""
    guard = get_guard_instance()
    proposal = guard._store.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Proposal is already {proposal['status']}")
    proposal["status"] = "rejected"
    proposal["approved_by"] = None
    proposal["rejected_by"] = rejecter_id
    proposal["rejected_at"] = datetime.now(timezone.utc).isoformat()
    guard._store.put_proposal(proposal)
    guard._audit_safe(proposal_id, "config.rejected", f"admin:{rejecter_id}", {"proposal_id": proposal_id, "proposed_by": proposal["proposed_by"]})
    return ConfigProposalResponse(**proposal)


@router.post("/config/proposals/{proposal_id}/approve", response_model=ConfigProposalResponse, summary="Approve Config Proposal (Four-Eyes)")
def approve_config_proposal(proposal_id: str, approver_id: str = Header(..., alias="X-Admin-User-Id")):
    """
    Four-eyes approval requirement:
    The approver MUST be a different admin than the proposer.
    """
    guard = get_guard_instance()
    proposal = guard._store.get_proposal(proposal_id)
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
    # Commit the new version first (append-only); only then mark approved. Store failure => 500, nothing applied.
    new_cfg = guard.commit_config(proposal["changes"], proposal["proposed_by"], approver_id, proposal_id)
    proposal["status"] = "approved"
    proposal["approved_by"] = approver_id
    proposal["approved_at"] = now.isoformat()
    guard._store.put_proposal(proposal)

    try:
        guard._audit.log_event(
            task_id=proposal_id,
            event_type="config.changed",
            actor=f"admin:{approver_id}",
            payload={"proposal_id": proposal_id, "new_version": new_cfg["version"], "changes": proposal["changes"]},
            config_version=new_cfg["version"],
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
    # Persist first: if it cannot be stored, fail loudly rather than appear switched while a restart would forget it.
    guard._store.put_kill_switch(updated_ks)
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
def list_review_queue(status: str | None = Query(None, pattern="^(pending|decided)$")):
    status = status if isinstance(status, str) else None  # direct calls (tests) pass the Query default object
    items = get_guard_instance()._store.list_review_items()
    return [i for i in items if status is None or i.get("status", "decided" if i.get("decision") else "pending") == status]


@router.get("/templates", summary="List Policy Templates (read-only)")
def list_templates():
    b = get_guard_instance()._policy_builder
    return [{"template_id": k, **{f: v.get(f) for f in ("description", "allowed_operations", "prohibited_side_effects", "approval_required_for", "allowed_destinations", "minimum_detector_posture", "failure_mode", "max_steps")}}
            for k, v in sorted(b._templates.items())]


@router.get("/templates/{template_id}", summary="Get Policy Template (read-only)")
def get_template(template_id: str):
    t = get_guard_instance()._policy_builder._templates.get(template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="template not found")
    return {"template_id": template_id, **t}


@router.api_route("/templates", methods=["POST"], summary="Templates are not editable at runtime")
@router.api_route("/templates/{template_id}", methods=["PUT"], summary="Templates are not editable at runtime")
def templates_not_editable(template_id: str | None = None):
    # Policy templates define what a task may ever do; they change through code review, not a runtime API.
    raise HTTPException(status_code=405, detail="Policy templates are versioned in the repository and cannot be edited at runtime")


@router.post("/review-queue/{id}/decision", summary="Submit Human Review Decision")
def submit_review_decision(id: str, req: ReviewDecisionRequest, admin_id: str | None = Header(None, alias="X-Admin-User-Id")):
    """
    Records a human review decision on flagged or held content.
    CRITICAL PRINCIPLE: Review decisions NEVER grant tool execution authority.
    """
    guard = get_guard_instance()
    item = guard._store.get_review_item(id)
    if not item:
        # Create an on-demand record if needed
        item = {"id": id, "created_at": datetime.now(timezone.utc).isoformat()}

    # The authenticated admin identity (header from the BE proxy) overrides any client-supplied reviewer_id.
    reviewer = admin_id or req.reviewer_id
    item["reviewer_id"] = reviewer
    item["status"] = "decided"
    item["decision"] = req.decision
    item["notes"] = req.notes
    item["decided_at"] = datetime.now(timezone.utc).isoformat()
    guard._store.put_review_item(item)

    try:
        guard._audit.log_event(
            task_id=id,
            event_type="review.decision",
            actor=f"reviewer:{reviewer}",
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


def _eval_store():
    from eval.store import EvalStore
    # Same DB file as the audit log, so the page reads what this guard instance wrote/sees.
    return EvalStore(get_guard_instance()._audit.db_path)


@router.get("/eval/runs", summary="List Evaluation Runs")
def list_eval_runs(kind: str | None = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    from eval.store import KINDS
    if kind is not None and kind not in KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {list(KINDS)}")
    return _eval_store().list_runs(kind=kind, limit=limit, offset=offset)


@router.get("/eval/summary", summary="Eval Page Payload (latest per kind + Baseline/Basic/Full table)")
def eval_summary():
    return _eval_store().summary()


@router.get("/eval/runs/{run_id}", summary="Evaluation Run Detail (config, versions, failed traces)")
def get_eval_run(run_id: str):
    run = _eval_store().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="eval run not found")
    return run
