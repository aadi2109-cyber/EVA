/**
 * EVA Contracts v0 - Frozen TypeScript Type Definitions
 * Contract Version: 0.1.0
 * Generated and maintained by SEC-2 (Authority-side Security)
 */

export const CONTRACT_VERSION = "0.1.0";

// ==============================================================================
// 1. Shared Types
// ==============================================================================

export type Trust = "user" | "system" | "untrusted";

export type SourceType =
  | "user_request"
  | "email"
  | "file"
  | "web"
  | "message"
  | "telegram"
  | "tool_output";

export interface Provenance {
  source_id: string;
  source_type: SourceType;
  field?: string | null;
  retrieval_path: string[];
  trust: Trust;
}

export type ReasonCode =
  | "TOOL_UNKNOWN"
  | "SCHEMA_INVALID"
  | "TOOL_NOT_IN_POLICY"
  | "TOOL_PROHIBITED"
  | "ARG_OUT_OF_SCOPE"
  | "DESTINATION_NOT_ALLOWED"
  | "UNTRUSTED_ARG_PROVENANCE"
  | "POSTURE_DEGRADED"
  | "APPROVAL_REQUIRED"
  | "ALIGN_MISALIGNED"
  | "ALIGN_UNCERTAIN"
  | "KILL_SWITCH"
  | "GUARD_ERROR"
  | "POLICY_EXPIRED"
  | "APPROVAL_MISMATCH"
  | "STEP_BUDGET";

// ==============================================================================
// 2. Guard API
// ==============================================================================

// 2.1 build_task_policy
export interface ScopeRule {
  tool_prefix: string;
  field: string;
  pattern: string;
}

export interface BuildPolicyRequest {
  task_id: string;
  user_id: string;
  user_role: "user" | "admin";
  user_request: string;
  available_tools: string[];
  template_id?: string | null;
}

export interface TaskPolicy {
  task_id: string;
  user_id: string;
  version: number;
  created_at: string;
  expires_at: string;
  allowed_operations: string[];
  allowed_data_scope: ScopeRule[];
  allowed_destinations: string[];
  prohibited_side_effects: string[];
  approval_required_for: string[];
  minimum_detector_posture: "tier2_required" | "tier1_ok_readonly";
  failure_mode: "fail_closed" | "tier1_only_warning";
  max_steps: number;
  origin: "llm_draft_validated" | "template" | "restrictive_fallback";
}

// 2.2 scan_tool_result
export interface ScanField {
  name: string;
  text: string;
  provenance: Provenance;
}

export interface ScanRequest {
  task_id: string;
  call_id: string;
  tool: string;
  fields: ScanField[];
}

export interface SanitizedField {
  name: string;
  text: string;
  sentences_total: number;
  sentences_removed: number;
  quarantined: boolean;
}

export interface DetSummary {
  t1_signals: string[];
  t2_max_score?: number | null;
  t3_used: boolean;
  t3_verdict?: "malicious" | "benign" | "uncertain" | "unavailable" | null;
  latency_ms: Record<string, number>;
}

export interface ScanResponse {
  disposition: "pass" | "sanitized" | "quarantined" | "held";
  fields: SanitizedField[];
  det_summary: DetSummary;
  tier2_available: boolean;
  warnings: string[];
  contract_version: string;
  event_id: string;
}

// 2.3 check_action
export interface CheckActionRequest {
  task_id: string;
  call_id: string;
  tool: string;
  args: Record<string, any>;
  arg_provenance: Record<string, Provenance>;
  read_only: boolean;
  approval_id?: string | null;
}

export interface ApprovalRequest {
  approval_id: string;
  task_id: string;
  exact_action: {
    tool: string;
    args: Record<string, any>;
  };
  arg_sources: Record<string, string>;
  action_hash: string;
  expires_at: string;
}

export interface AlignVerdict {
  verdict: "aligned" | "misaligned" | "uncertain" | "unavailable";
  score?: number | null;
}

export interface CheckActionResponse {
  decision: "ALLOW" | "REQUIRE_APPROVAL" | "DENY";
  reasons: ReasonCode[];
  reason_text: string;
  align: {
    verdict?: "aligned" | "misaligned" | "uncertain" | "unavailable";
    score?: number | null;
    [key: string]: any;
  };
  approval?: ApprovalRequest | null;
  contract_version: string;
  event_id: string;
}

// 2.4 submit_approval
export interface SubmitApprovalRequest {
  user_id: string;
  approved: boolean;
  edited_args?: Record<string, any> | null;
}

export interface SubmitApprovalResponse {
  status: "approved" | "denied" | "re_approval_required" | "expired";
  approval?: ApprovalRequest | null;
  event_id: string;
}

// 2.5 verify_state
export interface StateAssertion {
  kind:
    | "no_new_sent_mail"
    | "file_unchanged"
    | "file_written_with_hash"
    | "draft_created"
    | "no_outbound_http_to"
    | "mock_state_equals";
  target: string;
  expected?: any;
}

export interface VerifyStateRequest {
  task_id: string;
  call_id?: string | null;
  assertions: StateAssertion[];
  observed: Record<string, any>;
}

export interface VerifyStateResponse {
  passed: boolean;
  failures: string[];
  event_id: string;
}

// 2.6 health
export interface KillSwitchState {
  all_write_tools: boolean;
  tools: string[];
  templates: string[];
}

export interface Health {
  status: "ok" | "degraded" | "down";
  tier2_available: boolean;
  t3_available: boolean;
  align_available: boolean;
  t2_model_hash?: string | null;
  config_version: number;
  contract_version: string;
  kill_switch: KillSwitchState | Record<string, any>;
  metrics: Record<string, number>;
}

// ==============================================================================
// 5. Agent SSE Events (BE -> FE)
// ==============================================================================

export type SSEEventType =
  | "task.started"
  | "model.delta"
  | "plan.step"
  | "tool.requested"
  | "guard.decision"
  | "approval.required"
  | "approval.resolved"
  | "tool.started"
  | "tool.output"
  | "guard.scan"
  | "state.verified"
  | "health.degraded"
  | "guard.error"
  | "task.completed"
  | "task.failed"
  | "task.held"
  | "task.cancelled";

export interface SSEMessage {
  task_id: string;
  seq: number;
  ts: string;
  type: SSEEventType;
  payload: Record<string, any>;
}

// ==============================================================================
// 7. Admin API Models
// ==============================================================================

export type KillSwitchScope = "tool" | "template" | "all_write_tools";

export interface KillSwitchRequest {
  scope: KillSwitchScope;
  target?: string | null;
  enabled: boolean;
}

export interface ConfigProposalRequest {
  proposed_by: string;
  changes: Record<string, any>;
  justification: string;
}

export interface ConfigProposalResponse {
  proposal_id: string;
  proposed_by: string;
  changes: Record<string, any>;
  justification: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  approved_by?: string | null;
  approved_at?: string | null;
}

export interface ReviewDecisionRequest {
  reviewer_id: string;
  decision: "approved" | "rejected" | "investigate";
  notes: string;
}

export interface AuditEvent {
  id: string;
  ts: string;
  task_id: string;
  type: string;
  actor: string;
  payload_json: Record<string, any>;
  config_version: number;
  model_versions: Record<string, string>;
  prev_hash: string;
  hash: string;
}

export interface AuditVerifyResponse {
  valid: boolean;
  chain_length: number;
  tampered_event_id?: string | null;
  message: string;
}
