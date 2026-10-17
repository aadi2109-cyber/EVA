# 02 — Contracts v0 (frozen at G0)

`CONTRACT_VERSION = "0.1.0"`. SEC-2 turns this document into the `contracts/` Python package (Pydantic v2), an exported `openapi.json` for the guard service, and TypeScript types for FE (`contracts/ts/`). Until then everyone codes against this text.

Sections: 1 shared types · 2 Guard API · 3 Guard behaviour rules · 4 Tool catalogue · 5 Agent SSE events · 6 Agent REST API (FE ⇄ BE) · 7 Admin API.

## 1. Shared types

```python
class Trust(str, Enum):
    USER = "user"            # typed by the authenticated user in this task
    SYSTEM = "system"        # app-generated constants
    UNTRUSTED = "untrusted"  # anything retrieved: email, file, web, message, tool output

class SourceType(str, Enum):
    USER_REQUEST = "user_request"; EMAIL = "email"; FILE = "file"; WEB = "web"
    MESSAGE = "message"; TOOL_OUTPUT = "tool_output"

class Provenance(BaseModel):
    source_id: str                 # e.g. gmail message id, file path, url
    source_type: SourceType
    field: str | None              # "subject", "body", "snippet", ...
    retrieval_path: list[str]      # tool call ids that led here
    trust: Trust

class ReasonCode(str, Enum):
    TOOL_UNKNOWN; SCHEMA_INVALID; TOOL_NOT_IN_POLICY; TOOL_PROHIBITED
    ARG_OUT_OF_SCOPE; DESTINATION_NOT_ALLOWED; UNTRUSTED_ARG_PROVENANCE
    POSTURE_DEGRADED; APPROVAL_REQUIRED; ALIGN_MISALIGNED; ALIGN_UNCERTAIN
    KILL_SWITCH; GUARD_ERROR; POLICY_EXPIRED; APPROVAL_MISMATCH; STEP_BUDGET
```

## 2. Guard API

All calls are methods on `eva_guard.api.Guard` (library) and POST/GET endpoints on the service (JSON, same models). Service auth: `Authorization: Bearer $GUARD_SERVICE_TOKEN`. Every response includes `contract_version` and `event_id` (audit row).

### 2.1 `build_task_policy` — `POST /v1/policy`

```python
class BuildPolicyRequest(BaseModel):
    task_id: str; user_id: str; user_role: Literal["user","admin"]
    user_request: str                       # ONLY the user's typed request. Never retrieved content.
    available_tools: list[str]              # from the BE tool registry
    template_id: str | None = None

class TaskPolicy(BaseModel):
    task_id: str; user_id: str; version: int; created_at: datetime; expires_at: datetime
    allowed_operations: list[str]           # tool names, e.g. ["gmail.search","gmail.read"]
    allowed_data_scope: list[ScopeRule]     # {tool_prefix, field, pattern}, e.g. gmail.read -> label:INBOX
    allowed_destinations: list[str]         # email addresses / domains / URL patterns the task may send to or fetch
    prohibited_side_effects: list[str]      # e.g. ["gmail.send","files.write","messages.send"]
    approval_required_for: list[str]        # tools that always need exact-action approval
    minimum_detector_posture: Literal["tier2_required","tier1_ok_readonly"]
    failure_mode: Literal["fail_closed","tier1_only_warning"]
    max_steps: int
    origin: Literal["llm_draft_validated","template","restrictive_fallback"]
```

Rule: the LLM may draft; the app validates against the tool registry and templates; on any invalid draft → restrictive read-only fallback. Later content can never widen a policy.

### 2.2 `scan_tool_result` — `POST /v1/scan`

```python
class ScanField(BaseModel):
    name: str; text: str; provenance: Provenance

class ScanRequest(BaseModel):
    task_id: str; call_id: str; tool: str; fields: list[ScanField]

class SanitizedField(BaseModel):
    name: str; text: str                    # sanitized text, structure kept, markers inserted
    sentences_total: int; sentences_removed: int; quarantined: bool

class DetSummary(BaseModel):
    t1_signals: list[str]; t2_max_score: float | None
    t3_used: bool; t3_verdict: Literal["malicious","benign","uncertain","unavailable"] | None
    latency_ms: dict[str, float]            # t1, t2, t3, total

class ScanResponse(BaseModel):
    disposition: Literal["pass","sanitized","quarantined","held"]
    fields: list[SanitizedField]            # empty when held
    det_summary: DetSummary
    tier2_available: bool
    warnings: list[str]
    contract_version: str; event_id: str
```

Marker text inserted in place of a removed sentence: `[CONTENT SANITISED]`. `held` = nothing may reach the model (Tier 2 down under `fail_closed`, or scan error).

### 2.3 `check_action` — `POST /v1/check-action`

```python
class CheckActionRequest(BaseModel):
    task_id: str; call_id: str
    tool: str; args: dict[str, Any]
    arg_provenance: dict[str, Provenance]   # per top-level arg name; unknown args = UNTRUSTED
    read_only: bool                         # from the tool registry, not from the model
    approval_id: str | None = None          # set on the post-approval revalidation call

class ApprovalRequest(BaseModel):
    approval_id: str; task_id: str
    exact_action: dict                      # {tool, args} exactly as it will run
    arg_sources: dict[str, str]             # human-readable source of each arg ("typed by you", "from email X")
    action_hash: str; expires_at: datetime

class CheckActionResponse(BaseModel):
    decision: Literal["ALLOW","REQUIRE_APPROVAL","DENY"]
    reasons: list[ReasonCode]; reason_text: str   # reason_text is safe, guard-generated, fine to show the model and user
    align: dict                             # {verdict: aligned|misaligned|uncertain|unavailable, score: float|None}
    approval: ApprovalRequest | None
    contract_version: str; event_id: str
```

### 2.4 `submit_approval` — `POST /v1/approvals/{approval_id}`

```python
class SubmitApprovalRequest(BaseModel):
    user_id: str; approved: bool
    edited_args: dict[str, Any] | None = None   # any edit voids this approval and creates a new ApprovalRequest

class SubmitApprovalResponse(BaseModel):
    status: Literal["approved","denied","re_approval_required","expired"]
    approval: ApprovalRequest | None            # present for re_approval_required
    event_id: str
```

After `approved`, BE calls `check_action` again with `approval_id`; the guard re-validates the exact `action_hash`, policy, posture and kill switch. Only then may the tool run.

### 2.5 `verify_state` — `POST /v1/verify-state`

```python
class StateAssertion(BaseModel):
    kind: Literal["no_new_sent_mail","file_unchanged","file_written_with_hash","draft_created","no_outbound_http_to","mock_state_equals"]
    target: str; expected: Any = None

class VerifyStateRequest(BaseModel):
    task_id: str; call_id: str | None
    assertions: list[StateAssertion]; observed: dict[str, Any]   # BE collects observed state from the tool/mock, NOT from the model

class VerifyStateResponse(BaseModel):
    passed: bool; failures: list[str]; event_id: str
```

### 2.6 `health` — `GET /v1/health`

```python
class Health(BaseModel):
    status: Literal["ok","degraded","down"]
    tier2_available: bool; t3_available: bool; align_available: bool
    t2_model_hash: str | None; config_version: int; contract_version: str
    kill_switch: dict[str, bool]               # {"all_write_tools": false, "tools": [...]}
    metrics: dict[str, float]                  # escalation_rate, p50_ms, p95_ms
```

## 3. Guard behaviour rules (SEC teams implement; BE relies on them)

**Gateway evaluation order (SEC-2).** First failing rule decides DENY; collect all reasons for the audit.
1. Kill switch (tool / template / all write tools) → DENY `KILL_SWITCH`
2. Tool known in registry and args validate against schema → else DENY `TOOL_UNKNOWN` / `SCHEMA_INVALID`
3. Policy present, not expired → else DENY `POLICY_EXPIRED`
4. Tool in `allowed_operations` and not in `prohibited_side_effects` → else DENY `TOOL_NOT_IN_POLICY` / `TOOL_PROHIBITED`
5. Args within `allowed_data_scope` → else DENY `ARG_OUT_OF_SCOPE`
6. Destination args (recipient, URL, path) within `allowed_destinations` → else DENY `DESTINATION_NOT_ALLOWED`
7. Provenance: a destination/recipient/URL arg whose provenance is `UNTRUSTED` and was not typed by the user → DENY if outside the policy's destinations, otherwise REQUIRE_APPROVAL `UNTRUSTED_ARG_PROVENANCE`
8. Posture: if `minimum_detector_posture == "tier2_required"` and Tier 2 is down and the tool is a side effect → DENY `POSTURE_DEGRADED`
9. Tool in `approval_required_for` (and not already validly approved) → REQUIRE_APPROVAL `APPROVAL_REQUIRED`
10. ALIGN (advisory): `misaligned` on an otherwise ALLOW → downgrade to REQUIRE_APPROVAL (`ALIGN_MISALIGNED`); `uncertain`/`unavailable` on a **side-effect** tool → REQUIRE_APPROVAL (`ALIGN_UNCERTAIN`). ALIGN can never turn DENY/REQUIRE_APPROVAL into ALLOW.
11. Otherwise ALLOW.

**Defaults:** `gmail.send`, `messages.send`, `files.write`(outside scratch) are always in `approval_required_for`. Read tools do not need approval but still pass rules 1–8.

**DET failure modes (SEC-1).** `fail_closed`: Tier 2 unavailable → `held`. `tier1_only_warning` (read-only restricted tasks only): proceed on T1 with `warnings=["TIER2_UNAVAILABLE"]`, and the task's side-effect tools are denied by rule 8. The orchestrator cannot lower the floor the policy sets.

**T3 (LAYA) outcomes:** timeout / malformed / `uncertain` → conservative disposition: quarantine the sentence (drop it, mark `[CONTENT SANITISED]`), audited. T3 never overrides T2 toward "benign" when T2 ≥ block threshold.

**BE obligations:**
- Call `check_action` for **every** tool call (reads too) and `scan_tool_result` for **every** tool result before it enters the model context.
- Any exception, timeout (default 3 s check, 5 s scan) or non-2xx from the guard ⇒ treat as `DENY` / `held`, emit `guard.error`.
- Never pass retrieved content to `build_task_policy`.
- Pass `read_only` from the tool registry; never from model output.

## 4. Tool catalogue (BE implements; SEC-2 seeds default policies for these names)

| Tool | Kind | Args (summary) | Default approval | Notes |
|---|---|---|---|---|
| `gmail.search` | read | `query`, `max_results` | no | Gmail API / mock |
| `gmail.read` | read | `message_id` | no | Returns subject, from, date, body, snippet as separate scan fields |
| `gmail.draft` | write (low) | `to`, `subject`, `body` | yes | creates draft only |
| `gmail.send` | write (high) | `to`, `subject`, `body`, `draft_id?` | **always** | mock mode: writes to mock sent-box |
| `files.list` / `files.read` / `files.search` | read | `path` / `query` | no | sandbox workspace only |
| `files.write` | write | `path`, `content` | yes | sandbox only |
| `web.search` | read | `query` | no | results are untrusted |
| `web.fetch` | read | `url` | no | URL is a destination arg; untrusted-origin URLs follow rule 7; strip query-string exfil |
| `messages.history` | read | `thread_id?` | no | in-app conversation history |
| `messages.send` | write | `channel`, `text` | **always** | **mock** channel |
| `telegram.read` / `telegram.history` | read | `chat_id`, `limit?` | no | external Telegram chat history (mock adapter; untrusted scanned) |
| `telegram.send` | write | `chat_id`, `text` | **always** | external Telegram message (mock adapter; requires exact human approval) |

Tool outputs from any tool, including these, are `UNTRUSTED` and pass `scan_tool_result`.

## 5. Agent SSE events (BE → FE), `GET /api/tasks/{id}/events`

Each SSE message: `event: <type>`, `data: {task_id, seq, ts, ...payload}`. `seq` is monotonic; FE can resume with `Last-Event-ID`.

| Type | Payload |
|---|---|
| `task.started` | `{policy: TaskPolicy summary, guard_health}` |
| `model.delta` | `{text}` (assistant text stream) |
| `plan.step` | `{index: 0-based int, title, status: running\|completed\|failed}`; one `running` and one terminal event per step, always closed before the task's terminal event |
| `tool.requested` | `{call_id, tool, args, arg_sources}` |
| `guard.decision` | `{call_id, decision, reasons, reason_text, align}` |
| `approval.required` | `{approval: ApprovalRequest}` |
| `approval.resolved` | `{approval_id, status}` |
| `tool.started` / `tool.output` | `{call_id, ...}`; `tool.output` carries the **sanitized** result and `scan: ScanResponse` summary (never raw flagged text) |
| `guard.scan` | `{call_id, disposition, sentences_removed, tier2_available, warnings}` |
| `state.verified` | `{call_id, passed, failures}` |
| `health.degraded` | `{tier2_available, t3_available, failure_mode}` |
| `guard.error` | `{call_id, where}` |
| `task.completed` / `task.failed` / `task.held` / `task.cancelled` | `{final_text?, summary: {sentences_removed, actions_denied, approvals}}` |

## 6. Agent REST API (FE ⇄ BE)

JWT bearer (login returns `access_token`). All JSON.

| Method + path | Purpose |
|---|---|
| `POST /api/auth/login` `{email,password}` | → `{access_token, user}` |
| `GET /api/me` | current user + role |
| `POST /api/tasks` `{request}` | create + start task → `{task_id}` |
| `GET /api/tasks`, `GET /api/tasks/{id}` | list / detail (messages, events, policy, outcome) |
| `POST /api/tasks/{id}/cancel` | cancel |
| `GET /api/tasks/{id}/events` | SSE |
| `POST /api/approvals/{approval_id}` `{approved, edited_args?}` | proxy to guard `submit_approval`, then resumes the task |
| `GET /api/connectors` | `[{id:"gmail",status,mode:"real"|"mock",account,scopes,expires_hint}]` |
| `GET /api/connectors/gmail/auth-url` | start OAuth |
| `GET /oauth/gmail/callback` | OAuth redirect target |
| `DELETE /api/connectors/gmail` | disconnect + delete stored tokens |
| `GET /api/files?path=` / `GET /api/files/content?path=` | workspace browsing (read-only for UI) |
| `GET /api/health` | `{backend, guard: Health}` |
| `/api/admin/*` | admin only; BE proxies to guard `/admin/v1/*` unchanged (JWT role=admin required) |

## 7. Guard admin API (`/admin/v1/*`, SEC-2)

`GET/POST /config` (versioned; **lowering a posture floor requires a second admin's approval**: `POST /config/proposals`, `POST /config/proposals/{id}/approve`), `GET/POST/PUT /templates`, `GET /review-queue`, `POST /review-queue/{id}/decision` (records a decision; **never grants tool authority**), `GET /audit?task_id=&tool=&decision=&from=&to=`, `GET /audit/verify` (hash-chain check), `GET /audit/export`, `POST /kill-switch` `{scope: tool|template|all_write_tools, target, enabled}`, `GET /health`, `GET /eval/runs`, `GET /eval/runs/{id}`.

## 8. Audit event types (all components emit; SEC-2 stores)

`policy.built`, `det.scan` (per field: t1 signals, t2 scores summary, t3 verdict, removed sentence offsets, **not** the full raw text — store a hash and a ≤120-char redacted snippet), `det.degraded`, `align.check`, `gateway.decision`, `approval.requested`, `approval.resolved`, `tool.executed` (from BE), `state.verified`, `config.changed`, `kill_switch.changed`, `review.decision`, `guard.error`. Row fields: `id, ts, task_id, type, actor, payload_json, config_version, model_versions, prev_hash, hash`.
