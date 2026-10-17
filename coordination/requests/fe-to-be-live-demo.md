# FE -> BE requests (from live integration, CP-A)

1. **Demo model switch.** Live tasks use OllamaProvider only; without `OLLAMA_API_KEY` every task ends with `403 Forbidden`. Please add an env switch (e.g. `MODEL_PROVIDER=scripted`) that picks a ScriptedProvider keyed on the request text so S1/S2/S4/S7 can be demoed through the UI. FE verified against a test-only launcher that does this.
2. **`tool.output` payload.** Contract §5 says "sanitized result"; BE sends `sanitized_output` (string). FE now reads `sanitized_output ?? result`. Please confirm `sanitized_output` is the contract field and update doc 02.
3. **`plan.step` status.** BE only emits `status: "running"` and never completes a step. FE infers completion (next step starts / task terminal). Emit `completed` explicitly if possible. Indexes are 1-based on BE.
4. **Approval expiry (verified, SEC-2).** `ApprovalRequest.expires_at` is ~2h out. Root cause: `guard/eva_guard/gateway/gateway.py:311` sets it to the *task policy's* `expires_at` (`now + (policy.expires_at - now)`), and `ApprovalEngine.register_approval` stores that value. The engine's `ttl_minutes=10` is only applied when an edited approval is re-issued (`engine.py:99`). An approval should expire after 10 minutes, not live as long as the task policy.
5. **`/api/admin/eval/runs`** returns 404 (guard has no such route); FE shows "not available".
6. **Health metrics** `p50_ms`/`p95_ms` come from guard `metrics`; FE shows them when present.

## Admin review queue / config proposals (found while building them)

7. **`reviewer_id` is client-supplied.** The admin proxy overwrites `proposed_by` from the JWT but not `reviewer_id` on `POST /review-queue/{id}/decision`, and `X-Admin-User-Id` is only added for the approve route. FE sends the JWT user's id, but a client could send any id. Please inject `reviewer_id` from the JWT in the proxy like `proposed_by`.
8. **No `GET /config/proposals`.** The second admin has no way to list pending proposals. FE derives them from the audit log (`config.proposed` without a matching `config.changed` for the same `task_id`). Please add a proper list endpoint (SEC-2); FE will switch to it.
9. **Review queue is never populated.** Only `POST /review-queue/{id}/decision` creates items (on demand); quarantined/held scans do not enqueue anything. FE therefore lets an admin record a decision against an entered ID as well as listed items.
10. **Config proposals never reject.** `status` allows `rejected` but there is no reject endpoint, and any proposal (not only posture-lowering ones) needs a second admin. FE does not guess which are "lowering"; it says all proposals need a different admin.

## Files upload — DONE on BE (implemented from the FE side, please review)

11. **`POST /api/files/upload?path=<dir>`** is implemented in `agent/backend/app/api/files.py` (multipart field `file`, `201 {path, size}`). Differences from the original proposal, please confirm or change:
    - **Cap is 512 KB**, not 1 MB: equal to the agent's `files.read` cap, so every uploaded file can be viewed and read back. FE constant changed to match.
    - **Per-user quota** of 25 MB (`413 Workspace quota exceeded`).
    - **Missing folder -> 404**, never created implicitly (creating one could shadow the read-only mock folders shown by `GET /api/files`).
    - Names: plain names only; `/`, `\`, `..`, leading dot, control chars, >255 chars -> 400. Existing file (incl. a symlink at the destination) -> 409; written with `O_EXCL`, so no overwrite and no symlink following.
    - **Audit:** logged through the backend logger (`file.uploaded user path size sha256`), NOT in the guard's tamper-evident audit log, because the backend has no way to write guard audit events. Request to SEC-2: add an audit-write endpoint (or accept `files.uploaded` events) if upload should be in the hash chain.
    - Uploaded text is untrusted: tested that `files.read` returns it with `Trust.UNTRUSTED`, so it goes through `scan_tool_result` like any other file.
    - Not done: content-type/extension allowlist (viewer decodes as text with replacement), and Starlette spools the multipart body before our 512 KB check, so the size check limits what is stored, not what is received; add a request-size limit at the proxy/ASGI server for a hard cap.
    - doc 02 §6 still needs the new row (contract owner: SEC-2).

## Verification of requests 1-10 against the code (2026-10-17)

| # | Status |
|---|---|
| 1 | Confirmed: `orchestrator.py:63` defaults to `OllamaProvider()`; no env switch. |
| 2 | Confirmed: orchestrator emits `sanitized_output` (line ~407); doc 02 §5 says "sanitized result". Doc fix only. |
| 3 | Confirmed: only `status: "running"` is ever emitted (`orchestrator.py:157`), index is `step_count` (1-based). |
| 4 | Confirmed, root cause above. |
| 5 | Confirmed: no `/eval/runs` route in `guard/admin_api/routes.py`. |
| 6 | Informational. |
| 7 | Confirmed: proxy sets `proposed_by` and `X-Admin-User-Id` only; `reviewer_id` is taken from the body. |
| 8 | Confirmed: only `POST /config/proposals` and `POST .../approve` exist. |
| 9 | Confirmed: `_review_queue[id]` is only assigned in the decision handler (`routes.py:201`). |
| 10 | Confirmed: no reject route. |
