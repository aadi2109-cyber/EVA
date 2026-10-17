# FE -> BE requests (from live integration, CP-A)

1. **Demo model switch.** Live tasks use OllamaProvider only; without `OLLAMA_API_KEY` every task ends with `403 Forbidden`. Please add an env switch (e.g. `MODEL_PROVIDER=scripted`) that picks a ScriptedProvider keyed on the request text so S1/S2/S4/S7 can be demoed through the UI. FE verified against a test-only launcher that does this.
2. **`tool.output` payload.** Contract §5 says "sanitized result"; BE sends `sanitized_output` (string). FE now reads `sanitized_output ?? result`. Please confirm `sanitized_output` is the contract field and update doc 02.
3. **`plan.step` status.** BE only emits `status: "running"` and never completes a step. FE infers completion (next step starts / task terminal). Emit `completed` explicitly if possible. Indexes are 1-based on BE.
4. **Approval expiry.** `ApprovalRequest.expires_at` is ~2h out in the live run; spec says 10 minutes.
5. **`/api/admin/eval/runs`** returns 404 (guard has no such route); FE shows "not available".
6. **Health metrics** `p50_ms`/`p95_ms` come from guard `metrics`; FE shows them when present.

## Admin review queue / config proposals (found while building them)

7. **`reviewer_id` is client-supplied.** The admin proxy overwrites `proposed_by` from the JWT but not `reviewer_id` on `POST /review-queue/{id}/decision`, and `X-Admin-User-Id` is only added for the approve route. FE sends the JWT user's id, but a client could send any id. Please inject `reviewer_id` from the JWT in the proxy like `proposed_by`.
8. **No `GET /config/proposals`.** The second admin has no way to list pending proposals. FE derives them from the audit log (`config.proposed` without a matching `config.changed` for the same `task_id`). Please add a proper list endpoint (SEC-2); FE will switch to it.
9. **Review queue is never populated.** Only `POST /review-queue/{id}/decision` creates items (on demand); quarantined/held scans do not enqueue anything. FE therefore lets an admin record a decision against an entered ID as well as listed items.
10. **Config proposals never reject.** `status` allows `rejected` but there is no reject endpoint, and any proposal (not only posture-lowering ones) needs a second admin. FE does not guess which are "lowering"; it says all proposals need a different admin.

## Files upload (FE built, BE endpoint needed)

11. **`POST /api/files/upload?path=<dir>`** — FE now has an Upload button on the Files page that sends `multipart/form-data` with one field `file` and expects `201 {path, size}` (path relative to the user's workspace, same form as `GET /api/files`). Until this exists the FE shows "This backend does not support uploads yet" (on 404/405). Suggested server rules (BE/SEC-2 decide):
    - resolve `path` with the same traversal-safe `_resolve_safe_path` as the read routes; reject names with `/`, `\`, `..`, or a leading dot;
    - `409` if the file exists (no silent overwrite), `413` above the limit (FE pre-checks 1 MB), write into the per-user workspace only, never the shared mock workspace;
    - audit-log the upload; uploaded content is untrusted and must still pass `scan_tool_result` when the agent reads it (an upload must not bypass the guard);
    - the doc 02 §6 table needs the new row.
