/**
 * EVA API Types — Generated against CONTRACT_VERSION = "0.1.0"
 * Defined in docs/02-contracts-v0.md
 */

export type Trust = "user" | "system" | "untrusted";

export type SourceType =
  | "user_request"
  | "email"
  | "file"
  | "web"
  | "message"
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

export interface ScopeRule {
  tool_prefix: string;
  field: string;
  pattern: string;
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

export interface ScanField {
  name: string;
  text: string;
  provenance: Provenance;
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
  t2_max_score: number | null;
  t3_used: boolean;
  t3_verdict: "malicious" | "benign" | "uncertain" | "unavailable" | null;
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

export interface CheckActionResponse {
  decision: "ALLOW" | "REQUIRE_APPROVAL" | "DENY";
  reasons: ReasonCode[];
  reason_text: string;
  align: {
    verdict: "aligned" | "misaligned" | "uncertain" | "unavailable";
    score: number | null;
  };
  approval?: ApprovalRequest | null;
  contract_version: string;
  event_id: string;
}

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

export interface Health {
  status: "ok" | "degraded" | "down";
  tier2_available: boolean;
  t3_available: boolean;
  align_available: boolean;
  t2_model_hash: string | null;
  config_version: number;
  contract_version: string;
  kill_switch: {
    all_write_tools: boolean;
    tools: string[];
  };
  metrics: {
    escalation_rate: number;
    p50_ms: number;
    p95_ms: number;
  };
}

// SSE Event Stream Types
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

export interface SSEMessage<T = any> {
  event: SSEEventType;
  data: {
    task_id: string;
    seq: number;
    ts: string;
  } & T;
}

export interface PlanStepPayload {
  index: number;
  title: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
}

export interface ToolRequestedPayload {
  call_id: string;
  tool: string;
  args: Record<string, any>;
  arg_sources: Record<string, string>;
}

export interface GuardDecisionPayload {
  call_id: string;
  decision: "ALLOW" | "REQUIRE_APPROVAL" | "DENY";
  reasons: ReasonCode[];
  reason_text: string;
  align: {
    verdict: string;
    score?: number | null;
  };
}

export interface ToolOutputPayload {
  call_id: string;
  tool: string;
  result?: Record<string, any> | string;
  /** Sanitized tool result as sent by the backend (never raw flagged text). */
  sanitized_output?: string;
  scan: ScanResponse;
}

export interface GuardScanPayload {
  call_id: string;
  disposition: "pass" | "sanitized" | "quarantined" | "held";
  sentences_removed: number;
  tier2_available: boolean;
  warnings: string[];
}

export interface StateVerifiedPayload {
  call_id?: string | null;
  passed: boolean;
  failures: string[];
}

export interface HealthDegradedPayload {
  tier2_available: boolean;
  t3_available: boolean;
  failure_mode: "fail_closed" | "tier1_only_warning";
  reason?: string;
}

export interface GuardErrorPayload {
  call_id?: string;
  where: string;
  error?: string;
}

export interface TaskOutcomePayload {
  final_text?: string;
  summary: {
    sentences_removed: number;
    actions_denied: number;
    approvals: number;
  };
}

// REST & State Models
export interface User {
  id: string;
  email: string;
  name: string;
  role: "user" | "admin";
}

export interface LoginResponse {
  access_token: string;
  user: User;
}

export interface ConnectorInfo {
  id: string;
  name: string;
  status: "connected" | "disconnected" | "reconnect_needed";
  mode: "real" | "mock";
  account?: string;
  scopes: string[];
  expires_hint?: string;
}

export interface WorkspaceFile {
  path: string;
  name: string;
  size: number;
  is_directory: boolean;
  modified_at: string;
}

export interface AuditRecord {
  id: string;
  ts: string;
  task_id: string;
  type: string;
  actor: string;
  payload: any;
  config_version: number;
  prev_hash: string;
  hash: string;
}

export interface SecurityTraceItem {
  id: string;
  seq: number;
  timestamp: string;
  type: "decision" | "scan" | "state" | "health" | "error";
  event: SSEEventType;
  badge: "PASS" | "SANITIZED" | "QUARANTINED" | "HELD" | "ALLOW" | "REQUIRE_APPROVAL" | "DENY" | "guard.error";
  origin: string;
  title: string;
  reasonCode: string;
  plainEnglishReason: string;
  call_id?: string;
  details?: any;
}

export type ReviewDecision = "approved" | "rejected" | "investigate";

/** Review decisions are records only: they never grant tool authority. */
export interface ReviewItem {
  id: string;
  created_at?: string;
  reviewer_id?: string;
  decision?: ReviewDecision;
  notes?: string;
  decided_at?: string;
  [extra: string]: unknown;
}

export interface ConfigProposal {
  proposal_id: string;
  proposed_by: string;
  changes: Record<string, any>;
  justification: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  approved_by?: string | null;
  approved_at?: string | null;
}
