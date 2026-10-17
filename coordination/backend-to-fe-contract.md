# BE → FE API and SSE note

Contract source: `eva-dev-docs/02-contracts-v0.md` §§5–6. API responses are JSON unless marked SSE. Auth uses `Authorization: Bearer <access_token>`; EventSource may use `?access_token=`.

## REST endpoints

| Method + path | Shape |
|---|---|
| `POST /api/auth/login` | `{email,password}` → `{access_token,user}` |
| `GET /api/me` | authenticated user and role |
| `POST /api/tasks` | `{request}` → `{task_id}` |
| `GET /api/tasks` | task summary array |
| `GET /api/tasks/{id}` | task detail: status, policy, final text, summary, messages, event count, timestamps |
| `POST /api/tasks/{id}/cancel` | cancellation status and task id |
| `GET /api/tasks/{id}/events` | SSE stream; resume with `Last-Event-ID` or `last_event_id` |
| `POST /api/approvals/{approval_id}` | `{approved,edited_args?}` → guard approval response |
| `GET /api/connectors` | connector status array |
| `GET /api/connectors/gmail/auth-url` | OAuth URL response |
| `GET /oauth/gmail/callback` | OAuth redirect target |
| `DELETE /api/connectors/gmail` | disconnect result |
| `GET /api/files?path=` | workspace file listing |
| `GET /api/files/content?path=` | file content |
| `GET /api/health` | `{backend,guard}` health status |
| `/api/admin/*` | admin JWT only; proxies guard `/admin/v1/*` in HTTP transport mode |

## SSE

Each frame has `id: <seq>`, `event: <event-name>`, and JSON `data` containing `{task_id,seq,ts,...payload}`. `seq` strictly increases per task; replay returns events with `seq > Last-Event-ID`.

| Event | Payload |
|---|---|
| `task.started` | `{policy,guard_health}` |
| `model.delta` | `{text}` |
| `plan.step` | `{index,title,status}` |
| `tool.requested` | `{call_id,tool,args,arg_sources}` |
| `guard.decision` | `{call_id,decision,reasons,reason_text,align}` |
| `approval.required` | `{approval}` |
| `approval.resolved` | `{approval_id,status}` |
| `tool.started` | `{call_id,tool}` |
| `tool.output` | `{call_id,tool,sanitized_output,scan}` (sanitized result only) |
| `guard.scan` | `{call_id,disposition,sentences_removed,tier2_available,warnings}` |
| `state.verified` | `{call_id,passed,failures}` |
| `health.degraded` | `{tier2_available,t3_available,failure_mode}` |
| `guard.error` | `{call_id?,where?,error}` |
| `task.completed`, `task.failed`, `task.held`, `task.cancelled` | `{final_text?,summary:{sentences_removed,actions_denied,approvals}}` |

Errors currently use FastAPI's `{detail: ...}` envelope for endpoint errors; guard admin error bodies are passed through unchanged.
