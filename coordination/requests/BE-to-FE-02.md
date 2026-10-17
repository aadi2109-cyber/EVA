# Request BE-to-FE-02
Status: OPEN
From: BE · To: FE · Date: 2026-10-17
Answer to `fe-to-be-live-demo.md` item 11 (file upload). Endpoint is implemented on `role/backend`.

## `POST /api/files/upload?path=<dir>`
- Auth: normal Bearer JWT. Body: `multipart/form-data` with **exactly one** field named `file` (any extra field or a second file => 400).
- `path` = target directory relative to the user's workspace (same form as `GET /api/files`); empty = workspace root. Missing directories are created. `path` may not contain `\`, `..`, hidden (`.x`) or reserved segments.
- **201** `{ "path": "<dir>/<name>", "size": <bytes> }` (path relative to the workspace, POSIX slashes).

| Status | Meaning |
|---|---|
| 400 | bad file name (`/`, `\`, `..`, leading dot, trailing dot/space, control chars, reserved name, > 100 chars), bad target directory, target is a file, empty file, wrong multipart shape |
| 401 | not logged in |
| 409 | a file with that name already exists (never overwritten): offer the user a rename |
| 411 | no `Content-Length` (browser `fetch` + `FormData` always sends one) |
| 413 | file **> 1 MB** (`MAX_UPLOAD_BYTES`), or workspace quota (20 MB / 500 files) |
| 415 | extension not allowed, or content is not UTF-8 text (NUL bytes / binary) |
| 503 | the upload could not be written or audited (nothing is kept) |

- **Allowed extensions:** `.txt .md .csv .tsv .json .log .yaml .yml .xml`. Please set the `accept` attribute accordingly.
- The FE 1 MB pre-check already matches the server limit: no change needed.
- **Agent limit:** the AGENT can read files up to 512 KB only (model context). A 513 KB-1 MB upload is stored and viewable in the Files page, but the agent's `files.read` answers with a clear error. Consider a hint under the upload button ("the assistant can read files up to 512 KB").
- Error bodies are `{ "detail": "..." }`: show `detail` to the user.
- Content is untrusted: the agent's `files.read` of an uploaded file still goes through the guard scan (injection sentences are removed).
## Answer (recipient fills in)
