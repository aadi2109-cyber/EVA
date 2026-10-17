# Backend runbook (BE)

Scope: `agent/backend/` and `env/`. Spec: `docs/03-environment-and-setup.md`, `docs/roles/backend.md`.

## 1. Run

```bash
# local (from repo root; PYTHONPATH makes `contracts`, `env`, `eva_guard` importable)
cd agent/backend
uv sync                                   # or: pip install -e '.[dev]' pyyaml prometheus-client
export PYTHONPATH=.:../..:../../contracts:../../guard
alembic upgrade head                      # creates ./agent.db (DATABASE_URL, see below)
uvicorn app.main:app --reload --port 8000
curl localhost:8000/api/health
```

**Python version:** supported range is 3.11+. Code must stay valid on 3.11 (no f-strings that reuse their own quote; `tests/test_py311_compat.py` enforces it when the suite runs on 3.12+).

### Windows (PowerShell)
```powershell
cd agent\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -e ".[dev]"
$env:PYTHONPATH = ".;..\..;..\..\contracts;..\..\guard"   # per window; ';' separator
Copy-Item ..\..\env\.env.example ..\..\env\.env          # then edit
alembic upgrade head
uvicorn app.main:app --reload --port 8000
curl.exe localhost:8000/api/health         # PowerShell's `curl` is an alias; use curl.exe
```
`Posture degraded: Tier-2 detector unavailable` banner / `/api/health` shows `tier2_available:false`: `onnxruntime` (and `numpy`) are not installed in the venv (the Tier-2 loader swallows the ImportError and the guard goes fail-closed, side-effect tools disabled). Fix: `git pull`, then `pip install -e ".[dev]"` again, then restart uvicorn.

`ModuleNotFoundError: greenlet` means an old install (before `greenlet` was a declared dependency): `git pull`, then `pip install -e ".[dev]"` again.

Docker (API and the separately running HTTP guard):

```bash
docker compose -f env/docker-compose.yml up --build            # api :8000 + guard :8100
docker compose -f env/docker-compose.yml --profile ui up --build   # + ui :5173
```

The guard image requires `guard/Dockerfile` from SEC-2 (requested in `coordination/requests/backend-to-sec2-01.md`); UI still requires `agent/frontend/Dockerfile` from FE. Compose forces `GUARD_TRANSPORT=http`, so task checks and `/api/admin/*` share the same guard service process and state. The API image runs `alembic upgrade head` on start; DB and per-user workspaces live in the `eva-data` volume (`/data`). Guard SQLite state lives in `guard-data`.
Config: `env/.env.example` (committed defaults) layered under `env/.env` (git-ignored; put real keys there).

Notes
- `DATABASE_URL` may be written `sqlite:///./agent.db` (as in doc 03); it is normalised to the async driver `sqlite+aiosqlite:///`.
- Seeded logins (dev): `user@eva.local` / `UserPassword123!`, `admin@eva.local` / `AdminPassword123!`. Change them for anything shared.
- `TOKEN_ENC_KEY` default is a dev key. Generate a real one for any real Gmail use (section 6).

## 2. Test

```bash
cd /home/user/EVA && PYTHONPATH=.:guard python -m pytest agent/backend/tests -q
# or: cd agent/backend && uv run pytest
```

Tests use `./test_agent.db` relative to the CWD and drop/recreate tables. Two pytest runs from the same directory
at the same time corrupt each other (UNIQUE constraint on users.email, hangs). Run from different directories if
you need parallel runs: `cd /some/tmp/dir && PYTHONPATH=... pytest /path/to/agent/backend/tests`.

Web/Gmail/OAuth tests need no network: Google and the "Internet" are `httpx.MockTransport`s
(`tests/gmail_fakes.py`, `set_web_transport`, `set_google_transport`).

## 3. Reset the mock environment

```bash
python -m env.mock.reset                    # clears sent mail, drafts, outbound/blocked HTTP logs; re-creates missing seed files
python -m env.mock.reset --purge-sandboxes  # also empties WORKSPACE_ROOT/<user_id>/ (files written by files.write)
```

Fixtures in `env/mock/workspace/` and `env/mock/mailbox.json` are read-only seeds and are never overwritten.
Mock state is in process memory. To make the CLI reset a **running** API, export the same
`MOCK_STATE_FILE=/path/state.json` for both (compose does this: `/data/mock_state.json`; run the CLI with
`docker compose -f env/docker-compose.yml exec api python -m env.mock.reset`). Without it the CLI only resets its own process.

## 4. Profiles and eval mode

| Var | Values | Rule |
|---|---|---|
| `APP_ENV` | dev / eval / prod | `eval` = deterministic lab: mock Gmail only, web restricted to mock server |
| `GUARD_PROFILE` | full / basic / off | `basic`/`off` only with `APP_ENV=eval`, otherwise the app refuses to start |
| `GMAIL_MODE` | mock / real | `APP_ENV=eval` with `real` refuses to start |
| `GUARD_TRANSPORT` | inprocess / http | http needs the guard service and `GUARD_SERVICE_URL`/`GUARD_SERVICE_TOKEN` |
| `EVA_FAIL_TIER2_DOWN`, `EVA_FAIL_GUARD_UNREACHABLE`, `EVA_FAIL_LAYA_TIMEOUT` | bool | failure injection, eval only |

```bash
cd agent/backend
APP_ENV=eval GUARD_PROFILE=basic python -m app.eval.run_scenario S2 --profile basic --json
python -m env.mock.reset      # between runs
```

`web.fetch` in eval: only `localhost`, `127.0.0.1`, `mock.eva.local`, `example.com` (+ www/docs) resolve, and they are
served from `env/mock/web/` by an in-process transport (no sockets). Everything else, including redirect targets, is
refused before any request is made and logged under `blocked_http_requests` in the observed state.
Test helper: `http://localhost:8000/redirect?to=<url>` answers a 302.
Outside eval, other hosts use the real network with: http/https only, no URL credentials, no private/internal addresses,
ports 80/443, 5 redirects max (each hop re-validated), 3 s connect / 5 s read / 10 s total, 512 KB body cap
(truncated and flagged), text-like content types only, no cookies or auth headers sent or stored.

## 5. Tools quick reference

`gmail.*`, `files.*`, `web.search|fetch`, `messages.*`; registry in `app/tools/registry.py` (the only source of `read_only`).
Email/web HTML becomes text via `app/tools/htmltext.py`: visible text first, then `[HTML_COMMENT: ...]` and
`[HIDDEN_TEXT: ...]` sections (display:none, visibility:hidden, zero font-size, opacity:0, `hidden`, aria-hidden,
off-screen). Nothing hidden is dropped, so the guard scanner sees it. `<script>`/`<style>` bodies are omitted.
`web.search` is simulated (fixed example.com results); there is no search backend.

- **Check the Ollama key/model/search:** `python -m app.eval.check_live` (never prints the key). It tests that *chat* is authorised, that the model emits a tool call on its own, and that web search answers. Note `GET /api/tags` returns 200 with no key at all (public listing), so it is NOT a key check. 401 on chat = key rejected (create a new one); 404 = wrong model name (use `gpt-oss:20b`).

### Where configuration comes from
The backend loads, lowest to highest priority: `env/.env.example` (defaults) < `env/.env` (git-ignored secrets) < `./.env` < real process environment variables. The **guard service reads only its process environment** (e.g. `GUARD_SERVICE_TOKEN`), not `env/.env`: start it with the same values, e.g. `set -a; . env/.env; set +a; uvicorn service.main:app --port 8100` from `guard/`. A token mismatch between the two shows up as 401/502 from `/api/health` and `/api/admin/*`. Docker compose layers `env/.env` for both services.

### Web, search and model provider notes
- **web.fetch SSRF:** every non-mock host is DNS-resolved on every redirect hop; all returned addresses must be public (loopback, private, link-local, CGNAT, metadata, IPv4-mapped IPv6 and odd numeric forms like `2130706433` are refused), then the connection is pinned to the checked IP (Host header and TLS SNI preserved) so DNS rebinding can't swap the target. Unresolvable hosts are refused.
- **web.search:** `WEB_SEARCH_PROVIDER=mock` (default, always used in eval) or `ollama` (Ollama web-search API, `OLLAMA_API_KEY`). Queries are capped at 256 chars; results are capped, scheme-filtered and treated as untrusted. The search *query* is an egress channel the gateway does not currently police: see `coordination/requests/BE-to-SEC2-01.md`.
- **Ollama model provider:** an HTTP error, error chunk, timeout (180 s total) or empty stream ends the task as `failed` ("Model unavailable"); provider error text is never fed back to the model. Verified live on 2026-10-16 against ollama.com (streaming text, tool calls, `/api/web_search`). Model names on the direct cloud API have no provider prefix and no `-cloud` suffix (e.g. `gpt-oss:20b`, not `openai/gpt-oss:20b`): list yours with `curl -H "Authorization: Bearer $OLLAMA_API_KEY" https://ollama.com/api/tags`.
- **Gmail real mode caps:** text parts 256 KB each, 512 KB per message, MIME depth 12, 200 parts; truncation is written into the body so it is visible to the scanner. A transient Google/token-endpoint outage does NOT flag the account; a rejected refresh token or a still-401 fresh token does (`status=reconnect_needed`).

## 6. Gmail setup (real mode)

Human prerequisites (once), per `docs/03` section 3: dedicated Gmail account; Google Cloud project with Gmail API enabled;
OAuth consent screen External + Testing with test users added; OAuth client type Web application with redirect URI
`http://localhost:8000/oauth/gmail/callback`. Scopes are exactly `gmail.readonly` and `gmail.compose`.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> TOKEN_ENC_KEY
```

`env/.env`:
```
GMAIL_MODE=real
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/gmail/callback
TOKEN_ENC_KEY=<generated>
GMAIL_SEND_ALLOWLIST=you@gmail.com          # optional; empty = only the connected account itself
```

Connect: log in, `GET /api/connectors/gmail/auth-url` (Bearer token) -> open the returned URL -> Google redirects to
`/oauth/gmail/callback`. The `state` is a signed 10-minute JWT bound to your user; callbacks with a bad/expired state,
a missing refresh token, missing scopes or any extra scope are rejected and nothing is stored.
Refresh tokens are Fernet-encrypted in `connector_accounts`; access tokens are cached in memory only.
`GET /api/connectors` shows `connected`, `reconnect_needed` or `disconnected`. `DELETE /api/connectors/gmail` disconnects locally
(revoke at myaccount.google.com/permissions too). `gmail.send` always needs approval through EVA, and in real mode
additionally only goes to `GMAIL_SEND_ALLOWLIST` (default: the connected account).
Never run security tests or evals with `GMAIL_MODE=real`.

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| App exits at boot: `GUARD_PROFILE ... forbidden` | `off`/`basic` need `APP_ENV=eval` |
| App exits: `APP_ENV=eval cannot run with GMAIL_MODE=real` | intended; set `GMAIL_MODE=mock` |
| `alembic upgrade head` -> import errors | export `PYTHONPATH=.:../..:../../contracts:../../guard` and run from `agent/backend` |
| `sqlite3.IntegrityError users.email` / pytest hangs | stale `test_agent.db*` from an older checkout; delete it (tests now use a per-process temp DB) |
| Gmail tool error "reconnect needed" / connector shows `reconnect_needed` | Testing-mode refresh tokens last ~7 days, or access was revoked. Run the connect flow again |
| Callback returns 400 "Invalid or expired OAuth state" | the auth URL is valid 10 min and only for the user who requested it; request a new one. Also check `JWT_SECRET` did not change/differ between workers |
| Callback 400 "did not return a refresh token" | revoke EVA at myaccount.google.com/permissions, reconnect (consent screen must appear) |
| Callback 400 `redirect_uri_mismatch` (in Google page) | `GOOGLE_REDIRECT_URI` must equal the console value exactly |
| Stored tokens suddenly "reconnect needed" after config change | `TOKEN_ENC_KEY` changed; old ciphertext is unreadable by design. Reconnect |
| `web.fetch` "not reachable in eval mode" | expected in eval; use `http://localhost:8000/mock/web/<page>.html` |
| `web.fetch` "Non-public address" / "Port N is not allowed" | SSRF policy; only public hosts on 80/443 |
| API reset does not clear a running server | export the same `MOCK_STATE_FILE` for server and CLI (section 3) |
| `docker compose up` fails building `guard` | `guard/Dockerfile` is SEC-2-owned and requested; local Compose cannot start until that file lands |
| `docker compose --profile ui up` fails building `ui` | `agent/frontend/Dockerfile` is FE-owned and not part of the backend request |
| `/api/admin/*` returns 503 | Admin routes need the HTTP guard facade. Set `GUARD_TRANSPORT=http` and point `GUARD_SERVICE_URL` at the same service used by the API. In-process mode has no public admin facade and cannot safely apply kill switches/config through this proxy. |
| Guard health shows down in HTTP mode | Check `GUARD_SERVICE_URL`, matching `GUARD_SERVICE_TOKEN`, and that `service.main:app` is running. HTTP health timeouts/malformed bodies fail closed and are reported as guard errors. |
| A task is held immediately after API restart | Expected recovery behavior: running tasks are not replayed because model/side-effect state is not transactionally resumable. Pending approvals are expired and a `task.held` SSE event with reason `backend_restart` is persisted. Start a new task after inspecting any already completed side effects. |
| SSE client disconnects | Reconnect to the same task endpoint with the last received SSE `id` in `Last-Event-ID`; the API replays persisted events with larger sequence numbers. |
| `pytest` sees duplicate email / SQLite locks | Run from a private working directory. `tests/conftest.py` allocates a separate temporary database per pytest process; do not manually set a shared `DATABASE_URL`. |

## 8. CP-C verification notes

Run backend tests from a private directory as described in section 2. To exercise the real HTTP transport, start `uvicorn service.main:app --host 127.0.0.1 --port 8100` from `guard/` with the same `GUARD_SERVICE_TOKEN` as the API, then run `S1`, `S2`, `S4`, `S7`, and `S12` with `GUARD_TRANSPORT=http`. Scenario counts and environment limits belong in the handoff; Docker build status must be reported separately when Docker is unavailable.

Validation on 2026-10-16: Docker CLI and `uv` are not installed on this host. Dependencies were installed into a disposable scratch virtualenv. `pytest --collect-only` collected 135 cases, but the first pytest fixture and an independent async SQLite `init_db()` smoke check stalled on database connection before any test body ran. The API/guard processes and S1/S2/S4/S7/S12 were therefore not run; no passing-test count is claimed. Seven new backend test cases were added for contract routes/errors/SSE disconnect-resume, restart recovery, approval cancellation, in-process admin refusal, and concurrent HTTP-guard tasks. `python -m compileall` and `git diff --check` passed.
