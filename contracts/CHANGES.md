# Contracts Changelog

## [0.2.0] - 2026-10-16
- Shared types: Added `SourceType.TELEGRAM` ("telegram") for incoming Telegram content provenance.
- Tools: Documented `telegram.read` / `telegram.history` and `telegram.send` tool definitions and destination mapping.

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
