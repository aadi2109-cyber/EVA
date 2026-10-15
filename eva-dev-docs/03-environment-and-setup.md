# 03 — Environment and Setup

## 1. Hardware target

An ordinary developer laptop with integrated graphics. **No GPU is used anywhere.** Consequences:
- T2 runs on `onnxruntime` `CPUExecutionProvider`, int8-quantized, `max_length=128` tokens per sentence, intra-op threads = 2.
- LAYA runs on CPU (or not at all) and only for gray-band sentences / ALIGN checks, with a hard timeout (default 1500 ms). Its weights download from Hugging Face on first use, so run a warm-up once with network access.
- Whole guard budget: aim for < 2 GB RAM resident. Docker Compose services must start on 8 GB RAM.
- Report latency measured on the laptop that ran the benchmark, with CPU model and core count.

## 2. Model provider — Ollama cloud

The human supplies the API key and model name. Never hard-code them.

```
OLLAMA_BASE_URL=https://ollama.com        # cloud endpoint; use http://localhost:11434 for a local Ollama
OLLAMA_API_KEY=3f1ec5828c604a0e8d171f9350d040f2.YQ4kXuO-aOR85Rwb3phAxl78     # sent as: Authorization: Bearer <key>
OLLAMA_MODEL=openai/gpt-oss:20b       # must support tool calling
```

BE implements `OllamaProvider` against `POST {OLLAMA_BASE_URL}/api/chat` with `stream=true` and `tools=[...]`. **Verify the exact request/response shape against the current Ollama API docs at build time** (this pack does not assume details beyond: chat endpoint, bearer auth, tool calling support). If the supplied model does not return tool calls reliably, record a decision and fall back to a JSON-mode "tool call as JSON" prompt format behind the same `ModelProvider` interface.

`ModelProvider` interface (BE): `async def step(messages, tools) -> AsyncIterator[ModelEvent]` where events are `text_delta`, `tool_call(name,args)`, `done`. A `GeminiProvider` stub may exist but is not built.

Also required: `ScriptedProvider` — replays a fixed list of tool calls and a final text. Used so SEC-2 can test the gateway deterministically without an LLM, and to simulate a "hijacked" model proposing a malicious call.

## 3. Gmail (real from day one) — human prerequisites

Agents cannot do these steps; the human does, once.

| Setting | Value |
|---|---|
| Google account | Dedicated personal Gmail account (not a work or primary account) |
| Cloud project | New Google Cloud project; enable **Gmail API** |
| OAuth consent screen | Audience **External**, Publishing status **Testing** |
| Test users | The human and each team member who needs access (max 100) |
| Scopes (minimum for v1) | `https://www.googleapis.com/auth/gmail.readonly` and `https://www.googleapis.com/auth/gmail.compose` (drafts + send). Nothing broader |
| OAuth client | Type **Web application**; authorized redirect URI `http://localhost:8000/oauth/gmail/callback` |
| Env | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `TOKEN_ENC_KEY` (Fernet key, generate once) |

Behaviour rules for BE:
- `GMAIL_MODE=real|mock`. Default `mock` until credentials exist. Real and mock implement the same tool interface.
- Refresh tokens encrypted at rest with `TOKEN_ENC_KEY`; tokens never appear in model context, logs or SSE.
- Testing-mode refresh tokens expire after about 7 days; the connectors page must show "reconnect needed" cleanly.
- `gmail.send` always requires approval through EVA. In `real` mode, sending is further limited to the connected account's test recipients unless the human changes `GMAIL_SEND_ALLOWLIST`.
- **Security tests and evals run only with `GMAIL_MODE=mock`.** CI must fail if an eval run starts with `GMAIL_MODE=real`.

## 4. Ports and services (Docker Compose, owned by BE)

| Service | Port | Notes |
|---|---|---|
| `ui` | 5173 | Vite dev server (prod build optional) |
| `api` | 8000 | FastAPI agent backend |
| `guard` | 8100 | FastAPI wrapper over `eva_guard` (HTTP mode); `api` can instead import the library in-process (`GUARD_TRANSPORT=inprocess|http`) |

No `ollama` container: models are cloud-hosted.

## 5. Environment variables (`env/.env.example`, BE owns; SEC adds guard keys)

```
# agent
APP_ENV=dev
JWT_SECRET=...
DATABASE_URL=sqlite:///./agent.db
WORKSPACE_ROOT=./workspace
SEED_ADMIN_EMAIL=...  SEED_ADMIN_PASSWORD=...  SEED_USER_EMAIL=...  SEED_USER_PASSWORD=...
GMAIL_MODE=mock
GOOGLE_CLIENT_ID=  GOOGLE_CLIENT_SECRET=  GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/gmail/callback
TOKEN_ENC_KEY=
GMAIL_SEND_ALLOWLIST=
OLLAMA_BASE_URL=https://ollama.com  OLLAMA_API_KEY=  OLLAMA_MODEL=
GUARD_TRANSPORT=inprocess            # inprocess | http
GUARD_SERVICE_URL=http://localhost:8100
GUARD_SERVICE_TOKEN=...
GUARD_PROFILE=full                   # off | basic | full  (off/basic only allowed when APP_ENV=eval)
MAX_STEPS=12
# guard
GUARD_DATABASE_URL=sqlite:///./guard.db
T2_MODEL_PATH=./guard/models/t2.onnx   T2_MODEL_SHA256=...
T2_HIGH_RISK_THRESHOLD=0.85  T3_BAND_LOW=0.30  T3_BAND_HIGH=0.85  BLOCK_THRESHOLD=0.85
T3_ENABLED=true  T3_TIMEOUT_MS=1500  T3_MAX_TEXT_CHARS=2000
ALIGN_ENABLED=true  ALIGN_TIMEOUT_MS=1500
DEFAULT_FAILURE_MODE=fail_closed
```

## 6. Mock environment (`env/`, BE owns fixtures; SEC-2 owns attack content)

- `env/mock/mailbox.json` — ~30 benign emails (invoices, meetings, newsletters) + labelled attack emails (SEC-2 supplies attack texts).
- `env/mock/workspace/` — sample files incl. a poisoned document.
- `env/mock/web/` — local pages served by a mock web server, some poisoned; `web.fetch/search` in `APP_ENV=eval` route here only.
- `env/mock/state.py` — observable state used by `verify_state`: sent mail, drafts, files + hashes, outbound HTTP log.
- Reset command: `python -m env.mock.reset` returns everything to the seed state between runs.

## 7. Run commands (every role file repeats the ones that apply)

```
# backend
cd agent/backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload --port 8000
# guard service
cd guard && uv sync && uv run uvicorn service.main:app --reload --port 8100
# frontend
cd agent/frontend && pnpm install && pnpm dev
# everything
docker compose -f env/docker-compose.yml up --build
# tests
cd agent/backend && uv run pytest ; cd guard && uv run pytest ; cd agent/frontend && pnpm test
```
