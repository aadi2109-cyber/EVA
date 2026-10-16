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
