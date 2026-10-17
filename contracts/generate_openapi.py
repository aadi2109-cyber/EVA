"""
Generate openapi.json from contracts models and endpoint definitions.
"""

import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from contracts.models import (
    CONTRACT_VERSION,
    BuildPolicyRequest,
    TaskPolicy,
    ScanRequest,
    ScanResponse,
    CheckActionRequest,
    CheckActionResponse,
    SubmitApprovalRequest,
    SubmitApprovalResponse,
    VerifyStateRequest,
    VerifyStateResponse,
    Health,
    KillSwitchRequest,
    ConfigProposalRequest,
    ConfigProposalResponse,
    ReviewDecisionRequest,
    AuditEvent,
    AuditVerifyResponse,
    RecordEventRequest,
    RecordEventResponse,
)

app = FastAPI(
    title="EVA Guard API",
    version=CONTRACT_VERSION,
    description="Deterministic security gateway, content scanner, and policy engine for EVA Agent",
)

# 2.1 build_task_policy
@app.post("/v1/policy", response_model=TaskPolicy, summary="Build Task Policy")
def build_task_policy(req: BuildPolicyRequest):
    ...

# 2.2 scan_tool_result
@app.post("/v1/scan", response_model=ScanResponse, summary="Scan Tool Result")
def scan_tool_result(req: ScanRequest):
    ...

# 2.3 check_action
@app.post("/v1/check-action", response_model=CheckActionResponse, summary="Check Proposed Action")
def check_action(req: CheckActionRequest):
    ...

# 2.4 submit_approval
@app.post("/v1/approvals/{approval_id}", response_model=SubmitApprovalResponse, summary="Submit Approval Decision")
def submit_approval(approval_id: str, req: SubmitApprovalRequest):
    ...

# 2.5 verify_state
@app.post("/v1/verify-state", response_model=VerifyStateResponse, summary="Verify Post-Execution State")
def verify_state(req: VerifyStateRequest):
    ...

# 2.7 record_event (allow-listed, metadata only)
@app.post("/v1/audit-event", response_model=RecordEventResponse, summary="Append an allow-listed metadata event to the audit chain")
def record_event(req: RecordEventRequest):
    ...

# 2.6 health
@app.get("/v1/health", response_model=Health, summary="Guard Health and Posture")
def get_health():
    ...

# Admin API
@app.get("/admin/v1/config", summary="Get Active Config")
def get_config():
    ...

@app.post("/admin/v1/config/proposals", response_model=ConfigProposalResponse, summary="Propose Config Change")
def propose_config(req: ConfigProposalRequest):
    ...

@app.post("/admin/v1/config/proposals/{proposal_id}/approve", response_model=ConfigProposalResponse, summary="Approve Config Change (Four-Eyes)")
def approve_config_proposal(proposal_id: str):
    ...

@app.get("/admin/v1/templates", summary="List Policy Templates")
def list_templates():
    ...

@app.get("/admin/v1/review-queue", summary="List Quarantined/Held Review Items")
def list_review_queue():
    ...

@app.post("/admin/v1/review-queue/{id}/decision", summary="Submit Human Review Decision")
def submit_review_decision(id: str, req: ReviewDecisionRequest):
    ...

@app.get("/admin/v1/audit", response_model=list[AuditEvent], summary="Query Audit Log")
def query_audit():
    ...

@app.get("/admin/v1/audit/verify", response_model=AuditVerifyResponse, summary="Verify Audit Hash Chain Integrity")
def verify_audit_chain():
    ...

@app.get("/admin/v1/audit/export", summary="Export Audit Log")
def export_audit():
    ...

@app.post("/admin/v1/kill-switch", response_model=Health, summary="Set Kill Switch")
def set_kill_switch(req: KillSwitchRequest):
    ...

@app.get("/admin/v1/health", response_model=Health, summary="Admin Health Check")
def admin_health():
    ...

def main():
    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    out_path = Path(__file__).parent / "openapi.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"Exported OpenAPI schema to {out_path}")

if __name__ == "__main__":
    main()
