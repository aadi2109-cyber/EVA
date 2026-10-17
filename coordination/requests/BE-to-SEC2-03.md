# Request BE-to-SEC2-03
Status: RESOLVED (SEC-2, role/sec2)
From: BE · To: SEC-2 · Date: 2026-10-17

## Need
1. **Doc 02 §6** needs a new row (currently "workspace browsing (read-only for UI)"):
   `POST /api/files/upload?path=<dir>`: multipart field `file`; 201 `{path,size}`; 400/409/411/413/415/503 (see `coordination/requests/BE-to-FE-02.md`). Uploads are text-only, <= 1 MB, never overwrite, written only into the caller's own workspace.
2. **A public way to write an audit event through the Guard facade** (e.g. `Guard.record_event(type, actor, payload)` that appends to the hash-chained audit log, mirrored on the HTTP service as `POST /v1/audit-event`).
## Why
BE must audit uploads, but BE may not use guard internals (`Guard._audit`). Today BE records each upload attempt (accepted and rejected: user, path, size, sha256, outcome, reason; never the content) in its OWN table `file_audit_events` and in the log. That is durable but NOT tamper-evident and NOT visible in the admin audit explorer / `audit/verify`. With (2) BE would mirror each upload into the guard chain (`file.uploaded` / `file.upload_rejected`).
## Security notes (no action needed)
Upload is user-initiated, so it is not a `check_action`. The agent reading an uploaded file is a normal `files.read` (read-only, ALLOW) whose output goes through `scan_tool_result`, so an upload cannot bypass the scan: pinned by `tests/test_files_upload.py::test_agent_reading_an_uploaded_file_still_goes_through_the_guard_scan`.
## Answer (SEC-2)

**1. Doc 02 §6 row: approved and added** (with §5 `tool.output` now documenting `sanitized_output`). Approval is conditional on the following, which are now written into the row:
- Upload is a user action, not an agent tool call, so it is correctly NOT a `check_action`. It must stay unreachable from the agent (no tool maps to it).
- **Kill switch:** while `all_write_tools` is on (`GET /v1/health` -> `kill_switch.all_write_tools`), BE must refuse uploads with 503. An admin emergency stop that still lets files be written would be a gap. BE already checks guard health elsewhere; reuse that.
- Uploaded text is untrusted data: `files.read` of it stays `UNTRUSTED` and scanned (your pinned test). Recommend BE also treats a file read failure of the scan (guard down) as held, as for any other file.
- Keep the 1 MB / no-overwrite / own-workspace-only / no-symlink rules. You noted the multipart body is spooled before the size check; set a proxy-level body limit (e.g. `client_max_body_size` / uvicorn `--limit-max-requests` is not enough) if the API is ever exposed beyond localhost.

**2. `Guard.record_event` + `POST /v1/audit-event`: implemented.**
```
Guard.record_event(RecordEventRequest{type, actor, task_id="files", payload}) -> RecordEventResponse{event_id, hash}
POST /v1/audit-event   (bearer auth)   200 | 401 | 422 (rejected request) | 500 (audit write failed)
```
Deliberate limits, so BE cannot forge security evidence: `type` is a closed enum, currently only `file.uploaded` and `file.upload_rejected` (the model rejects anything else); `actor` must start with `user:`, `system:` or `service:`; `payload` is metadata only (keys `content/text/body/data/raw/snippet` refused, 4 KB cap, secrets redacted by the logger as for all events); entries are hash-chained so they show up in the admin audit explorer and `audit/verify`. Treat 500 as "not logged": record it in your own table (keep `file_audit_events` as the fallback) and surface the failure, do not report the upload as audited. Models are additive in `contracts/` (`RecordEventRequest/Response`, TS types, `openapi.json`); contract stays 0.1.0. BE: add `record_event` to `GuardClient` (in-process calls `Guard.record_event`, HTTP posts to `/v1/audit-event`) and call it with `type=file.uploaded|file.upload_rejected`, `actor=user:<id>`, payload `{path, size, sha256, outcome, reason}`. Tests: `guard/tests/test_be_requests.py::test_record_event_*`.
