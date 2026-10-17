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

## Status of all requests (2026-10-17): all implemented

| # | Request | Done in |
|---|---|---|
| 1 | Demo model switch | BE: `MODEL_PROVIDER=scripted` (`app/model/factory.py`; refused when `APP_ENV=prod`). Scripts for S1/S2/S4 keyed on the request text. |
| 2 | `tool.output` payload doc | doc 02 §5 (both copies) + `contracts/CHANGES.md`: `sanitized_output` string. |
| 3 | `plan.step` completion | BE orchestrator: each step `running` -> `completed`, or `failed` when held/failed/cancelled mid-step. FE shows failed steps. |
| 4 | Approval expiry | Guard gateway: `min(now + 10 min, policy.expires_at)`; no policy -> born expired (fail closed). Live: modal starts at ~10:00. |
| 5 | Eval runs | Guard `GET /admin/v1/eval/runs[/{id}]` read run files from `$EVA_EVAL_RESULTS_DIR` (default `guard/eval/results`, git-ignored); `python -m app.eval.run_scenario <S> --save [DIR]` writes them; FE shows a table. |
| 6 | Health metrics | Informational, nothing to do. |
| 7 | `reviewer_id` spoofing | BE admin proxy overwrites `reviewer_id` from the JWT (like `proposed_by`). |
| 8 | List proposals | Guard `GET /admin/v1/config/proposals[?status=]`; FE uses it instead of deriving from the audit log. |
| 9 | Review queue never filled | Guard facade enqueues every `quarantined`/`held` scan (ids, tool, counts, field names; never text). Queue lives on the `Guard` instance. |
| 10 | Reject proposals | Guard `POST /config/proposals/{id}/reject` (any admin, proposer may withdraw; audit `config.rejected`); FE Reject/Withdraw buttons. Still true: every proposal needs a second admin; the UI does not guess which are "lowering". |
| 11 | Upload follow-ups | Audit entry via new guard `POST /v1/audit/events` (allowlist `files.uploaded`, fail closed: upload rolled back with 503 if it cannot be recorded); hard request-size cap (ASGI middleware, 413 before buffering, also for chunked bodies); doc 02 §6 row. |

Notes for the owners
- BE tests must run with `GMAIL_MODE=mock`. A shell that exports `GMAIL_MODE=real` (this sandbox does) makes 19 Gmail tool tests fail with `ReconnectNeeded`; they are environment failures, not regressions.
- The guard's default audit DB is `./guard.db` relative to the working directory and is never reset; the admin UI shows everything ever written to it.
- Not done on purpose: content-type allowlist for uploads; a rule for which config proposals need a second admin.
