# Contracts Changelog

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

## Behaviour clarifications (no schema change) — persistence
- Task policies, approvals and the kill switch are stored in the guard SQLite DB (`task_policies`, `approvals`, `kill_switch`) and survive restarts. `GUARD_DB_PATH` selects the file (default `./guard.db`).
- `build_task_policy` is idempotent per `task_id`: a repeat call returns the stored policy unchanged (audited as `policy.rebuild_ignored`); a policy can never be replaced or widened.
- Approvals are bound to the task they were issued for; only the task owner (`policy.user_id`) can resolve them. Single use is persisted before ALLOW is returned; if persistence fails the action is DENIED (`GUARD_ERROR`).
