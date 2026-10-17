# Request BE-to-SEC2-03
Status: OPEN
From: BE · To: SEC-2 · Date: 2026-10-17

## Need
1. **Doc 02 §6** needs a new row (currently "workspace browsing (read-only for UI)"):
   `POST /api/files/upload?path=<dir>`: multipart field `file`; 201 `{path,size}`; 400/409/411/413/415/503 (see `coordination/requests/BE-to-FE-02.md`). Uploads are text-only, <= 512 KB, never overwrite, written only into the caller's own workspace.
2. **A public way to write an audit event through the Guard facade** (e.g. `Guard.record_event(type, actor, payload)` that appends to the hash-chained audit log, mirrored on the HTTP service as `POST /v1/audit-event`).
## Why
BE must audit uploads, but BE may not use guard internals (`Guard._audit`). Today BE records each upload attempt (accepted and rejected: user, path, size, sha256, outcome, reason; never the content) in its OWN table `file_audit_events` and in the log. That is durable but NOT tamper-evident and NOT visible in the admin audit explorer / `audit/verify`. With (2) BE would mirror each upload into the guard chain (`file.uploaded` / `file.upload_rejected`).
## Security notes (no action needed)
Upload is user-initiated, so it is not a `check_action`. The agent reading an uploaded file is a normal `files.read` (read-only, ALLOW) whose output goes through `scan_tool_result`, so an upload cannot bypass the scan: pinned by `tests/test_files_upload.py::test_agent_reading_an_uploaded_file_still_goes_through_the_guard_scan`.
## Answer (recipient fills in)
