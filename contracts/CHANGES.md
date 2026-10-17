# Contracts Changelog

## [Unreleased] (documentation and additive endpoints; no schema changes)
- Doc 02 §5: `tool.output.sanitized_output` (string) is the field; `plan.step` is 0-based and each step ends `completed`/`failed`.
- Approval `expires_at` is now `min(now + 10 min, policy.expires_at)` (was the task policy expiry).
- New: `POST /api/files/upload`; admin `GET /config/proposals`, `POST /config/proposals/{id}/reject`; review queue is populated by flagged scans; guard `POST /v1/audit/events` (allowlist: `files.uploaded`).
- BE: `MODEL_PROVIDER=ollama|scripted` (scripted is refused when `APP_ENV=prod`).

## [0.1.0] - 2026-10-15 (G0 Freeze)

### Initial Frozen Contract
- Shared types: `Trust`, `SourceType`, `Provenance`, `ReasonCode`
- Policy endpoints and schemas: `BuildPolicyRequest`, `TaskPolicy`, `ScopeRule`
- Content scanning schemas: `ScanField`, `ScanRequest`, `SanitizedField`, `DetSummary`, `ScanResponse`
- Action gating schemas: `CheckActionRequest`, `ApprovalRequest`, `AlignVerdict`, `CheckActionResponse`
- Approvals submission: `SubmitApprovalRequest`, `SubmitApprovalResponse`
- Post-state verification: `StateAssertion`, `VerifyStateRequest`, `VerifyStateResponse`
- Guard health & status: `Health`, `KillSwitchState`
- Agent SSE event types: `SSEEventType`, `SSEMessage`
- Admin & Audit contracts: `KillSwitchRequest`, `ConfigProposalRequest`, `ConfigProposalResponse`, `ReviewDecisionRequest`, `AuditEvent`, `AuditVerifyResponse`

## Behaviour clarifications (no schema change, contract stays 0.1.0) — 2026-10-16
- `files.*` path args are validated as sandbox-relative, non-traversing paths; policies for file tasks carry the sentinel destination `workspace:*`.
- `files.write` is only allowed by a policy when the user's own request contains a write intent verb.
- `gmail.draft` with a recipient outside `allowed_destinations` returns `REQUIRE_APPROVAL` (`UNTRUSTED_ARG_PROVENANCE`) instead of `DENY`; nothing is sent and the human sees the exact recipient. `gmail.send` is unchanged (DENY).
- `scan_tool_result` adds warning `DET_PIPELINE_ABSENT` when SEC-1's `DetPipeline` is not installed (StubGuard fallback scan).
