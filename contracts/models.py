"""
EVA Contracts v0 - Frozen API models and schemas.
Contract Version: 0.1.0
Author: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "0.1.0"


# ==============================================================================
# 1. Shared Types
# ==============================================================================

class Trust(str, Enum):
    USER = "user"            # typed by the authenticated user in this task
    SYSTEM = "system"        # app-generated constants
    UNTRUSTED = "untrusted"  # anything retrieved: email, file, web, message, tool output


class SourceType(str, Enum):
    USER_REQUEST = "user_request"
    EMAIL = "email"
    FILE = "file"
    WEB = "web"
    MESSAGE = "message"
    TOOL_OUTPUT = "tool_output"


class Provenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str                          # e.g. gmail message id, file path, url
    source_type: SourceType
    field: str | None = None                # "subject", "body", "snippet", ...
    retrieval_path: list[str] = Field(default_factory=list)  # tool call ids that led here
    trust: Trust


class ReasonCode(str, Enum):
    TOOL_UNKNOWN = "TOOL_UNKNOWN"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    TOOL_NOT_IN_POLICY = "TOOL_NOT_IN_POLICY"
    TOOL_PROHIBITED = "TOOL_PROHIBITED"
    ARG_OUT_OF_SCOPE = "ARG_OUT_OF_SCOPE"
    DESTINATION_NOT_ALLOWED = "DESTINATION_NOT_ALLOWED"
    UNTRUSTED_ARG_PROVENANCE = "UNTRUSTED_ARG_PROVENANCE"
    POSTURE_DEGRADED = "POSTURE_DEGRADED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ALIGN_MISALIGNED = "ALIGN_MISALIGNED"
    ALIGN_UNCERTAIN = "ALIGN_UNCERTAIN"
    KILL_SWITCH = "KILL_SWITCH"
    GUARD_ERROR = "GUARD_ERROR"
    POLICY_EXPIRED = "POLICY_EXPIRED"
    APPROVAL_MISMATCH = "APPROVAL_MISMATCH"
    STEP_BUDGET = "STEP_BUDGET"


# ==============================================================================
# 2. Guard API
# ==============================================================================

# 2.1 build_task_policy
class ScopeRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_prefix: str
    field: str
    pattern: str


class BuildPolicyRequest(BaseModel):
    task_id: str
    user_id: str
    user_role: Literal["user", "admin"]
    user_request: str                       # ONLY the user's typed request. Never retrieved content.
    available_tools: list[str]              # from the BE tool registry
    template_id: str | None = None


class TaskPolicy(BaseModel):
    task_id: str
    user_id: str
    version: int = 1
    created_at: datetime
    expires_at: datetime
    allowed_operations: list[str]           # tool names, e.g. ["gmail.search","gmail.read"]
    allowed_data_scope: list[ScopeRule] = Field(default_factory=list)     # {tool_prefix, field, pattern}
    allowed_destinations: list[str] = Field(default_factory=list)         # email addresses / domains / URL patterns
    prohibited_side_effects: list[str] = Field(default_factory=list)      # e.g. ["gmail.send","files.write"]
    approval_required_for: list[str] = Field(default_factory=list)        # tools that always need exact-action approval
    minimum_detector_posture: Literal["tier2_required", "tier1_ok_readonly"] = "tier2_required"
    failure_mode: Literal["fail_closed", "tier1_only_warning"] = "fail_closed"
    max_steps: int = 12
    origin: Literal["llm_draft_validated", "template", "restrictive_fallback"] = "template"


# 2.2 scan_tool_result
class ScanField(BaseModel):
    name: str
    text: str
    provenance: Provenance


class ScanRequest(BaseModel):
    task_id: str
    call_id: str
    tool: str
    fields: list[ScanField]


class SanitizedField(BaseModel):
    name: str
    text: str                               # sanitized text, structure kept, markers inserted
    sentences_total: int
    sentences_removed: int
    quarantined: bool = False


class DetSummary(BaseModel):
    t1_signals: list[str] = Field(default_factory=list)
    t2_max_score: float | None = None
    t3_used: bool = False
    t3_verdict: Literal["malicious", "benign", "uncertain", "unavailable"] | None = None
    latency_ms: dict[str, float] = Field(default_factory=dict)            # t1, t2, t3, total


class ScanResponse(BaseModel):
    disposition: Literal["pass", "sanitized", "quarantined", "held"]
    fields: list[SanitizedField] = Field(default_factory=list)            # empty when held
    det_summary: DetSummary
    tier2_available: bool
    warnings: list[str] = Field(default_factory=list)
    contract_version: str = CONTRACT_VERSION
    event_id: str


# 2.3 check_action
class CheckActionRequest(BaseModel):
    task_id: str
    call_id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    arg_provenance: dict[str, Provenance] = Field(default_factory=dict)   # per top-level arg name; unknown args = UNTRUSTED
    read_only: bool                         # from the tool registry, not from the model
    approval_id: str | None = None          # set on the post-approval revalidation call


class ApprovalRequest(BaseModel):
    approval_id: str
    task_id: str
    exact_action: dict[str, Any]            # {tool, args} exactly as it will run
    arg_sources: dict[str, str] = Field(default_factory=dict)             # human-readable source of each arg
    action_hash: str
    expires_at: datetime


class AlignVerdict(BaseModel):
    verdict: Literal["aligned", "misaligned", "uncertain", "unavailable"]
    score: float | None = None


class CheckActionResponse(BaseModel):
    decision: Literal["ALLOW", "REQUIRE_APPROVAL", "DENY"]
    reasons: list[ReasonCode] = Field(default_factory=list)
    reason_text: str                        # reason_text is safe, guard-generated, fine to show the model and user
    align: dict[str, Any] = Field(default_factory=dict)                   # {verdict: ..., score: ...}
    approval: ApprovalRequest | None = None
    contract_version: str = CONTRACT_VERSION
    event_id: str


# 2.4 submit_approval
class SubmitApprovalRequest(BaseModel):
    user_id: str
    approved: bool
    edited_args: dict[str, Any] | None = None   # any edit voids this approval and creates a new ApprovalRequest


class SubmitApprovalResponse(BaseModel):
    status: Literal["approved", "denied", "re_approval_required", "expired"]
    approval: ApprovalRequest | None = None     # present for re_approval_required
    event_id: str


# 2.5 verify_state
class StateAssertion(BaseModel):
    kind: Literal[
        "no_new_sent_mail",
        "file_unchanged",
        "file_written_with_hash",
        "draft_created",
        "no_outbound_http_to",
        "mock_state_equals",
    ]
    target: str
    expected: Any = None


class VerifyStateRequest(BaseModel):
    task_id: str
    call_id: str | None = None
    assertions: list[StateAssertion]
    observed: dict[str, Any]                # BE collects observed state from the tool/mock, NOT from the model


class VerifyStateResponse(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)
    event_id: str


# 2.6 health
class KillSwitchState(BaseModel):
    all_write_tools: bool = False
    tools: list[str] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=list)


class Health(BaseModel):
    status: Literal["ok", "degraded", "down"]
    tier2_available: bool
    t3_available: bool
    align_available: bool
    t2_model_hash: str | None = None
    config_version: int = 1
    contract_version: str = CONTRACT_VERSION
    kill_switch: dict[str, Any] | KillSwitchState
    metrics: dict[str, float] = Field(default_factory=dict)


# ==============================================================================
# 5. Agent SSE Events (BE -> FE)
# ==============================================================================

class SSEEventType(str, Enum):
    TASK_STARTED = "task.started"
    MODEL_DELTA = "model.delta"
    PLAN_STEP = "plan.step"
    TOOL_REQUESTED = "tool.requested"
    GUARD_DECISION = "guard.decision"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_RESOLVED = "approval.resolved"
    TOOL_STARTED = "tool.started"
    TOOL_OUTPUT = "tool.output"
    GUARD_SCAN = "guard.scan"
    STATE_VERIFIED = "state.verified"
    HEALTH_DEGRADED = "health.degraded"
    GUARD_ERROR = "guard.error"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_HELD = "task.held"
    TASK_CANCELLED = "task.cancelled"


class SSEMessage(BaseModel):
    task_id: str
    seq: int
    ts: datetime
    type: SSEEventType
    payload: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# 7. Admin API Models
# ==============================================================================

class KillSwitchScope(str, Enum):
    TOOL = "tool"
    TEMPLATE = "template"
    ALL_WRITE_TOOLS = "all_write_tools"


class KillSwitchRequest(BaseModel):
    scope: KillSwitchScope
    target: str | None = None
    enabled: bool


class ConfigProposalRequest(BaseModel):
    proposed_by: str
    changes: dict[str, Any]
    justification: str


class ConfigProposalResponse(BaseModel):
    proposal_id: str
    proposed_by: str
    changes: dict[str, Any]
    justification: str
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None


class ReviewDecisionRequest(BaseModel):
    reviewer_id: str
    decision: Literal["approved", "rejected", "investigate"]
    notes: str


class AuditEvent(BaseModel):
    id: str
    ts: datetime
    task_id: str
    type: str
    actor: str
    payload_json: dict[str, Any]
    config_version: int
    model_versions: dict[str, str] = Field(default_factory=dict)
    prev_hash: str
    hash: str


class AuditVerifyResponse(BaseModel):
    valid: bool
    chain_length: int
    tampered_event_id: str | None = None
    message: str
