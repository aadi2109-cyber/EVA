# Role: SEC-2 — Authority-side security (1 of 2 security agents)

You own `contracts/`, `guard/eva_guard/{policy,gateway,align,approvals,audit,verify}`, `guard/eva_guard/{api.py,stub.py}`, `guard/service/`, `guard/admin_api/`, `guard/eval/`. You build everything that decides **what the agent may do**, records **why**, and **measures** whether it works. Your partner SEC-1 owns content detection (`det/`).

Objectives you serve: separate user instructions from external content (task policy), stop successful attacks causing actions (gateway, approvals, verifier), check high-impact actions against the original request (ALIGN + approvals), log security decisions (audit), keep legitimate tasks completing (measured by eval).

## Read first
`00` · `01` · `02` contracts (all) · `03` · `04`. You are the **owner of doc 02's implementation**: your first job is making it executable.

## Stack
Python 3.12, Pydantic v2, FastAPI, SQLAlchemy 2 + Alembic (guard has its **own** SQLite DB `guard.db`), `structlog`, `prometheus-client`, `pytest`, `hypothesis`, `pyyaml`, `uv`.

## What to build

### 0. Contracts package and StubGuard (by H0.75 — blocks everyone)
- `contracts/` Pydantic models exactly per doc 02, `CONTRACT_VERSION`, `CHANGES.md`, exported `openapi.json`, generated TS types in `contracts/ts/` (use `datamodel-code-generator`/`openapi-typescript`; if tooling fails, hand-write and note it).
- `eva_guard/stub.py: StubGuard` implementing the same facade as the real `Guard`: returns canned but schema-valid responses (policy = permissive-for-reads template; scan = pass-through with a fake `[CONTENT SANITISED]` for text containing "ignore the user"; check_action = ALLOW reads, REQUIRE_APPROVAL for send tools, DENY unknown; health ok). Documented as **test-only**; it refuses to load when `APP_ENV=prod`.
- `eva_guard/api.py: class Guard` — single public facade: `build_task_policy`, `scan_tool_result` (delegates to SEC-1's `DetPipeline`), `check_action`, `submit_approval`, `verify_state`, `health`. This is the only import BE uses.

### 1. Task Policy Builder (`policy/`)
- Input is **only** `user_request` + `available_tools` + identity. Never retrieved content.
- Flow: (a) deterministic intent classifier + templates (`policy/templates/*.yaml`: `read_only_mailbox`, `mailbox_summarize`, `draft_reply`, `send_email_to_named_recipient`, `file_work`, `web_research`, `mixed_readonly`) selected by rules; (b) optional LLM draft via the guard's own `PolicyDrafter` client (Ollama cloud, same env vars; a small JSON-schema prompt; timeout 4 s); (c) **validate** the draft against the registry and templates: tools must exist, destinations must be extractable from the *user's* text (emails, domains, URLs they typed) or be in the template, scope can only be ≤ template. Any failure ⇒ restrictive read-only fallback (`origin="restrictive_fallback"`). The orchestrator can never widen a policy; policies are immutable once built (new version only via a new task).
- Always set: `prohibited_side_effects` (everything write-class not needed), `approval_required_for` (defaults in doc 02 §3), `minimum_detector_posture` (`tier2_required` for any task that allows a side effect), `failure_mode`, `max_steps`, `expires_at`.

### 2. Deterministic Policy Gateway (`gateway/`)
Implement doc 02 §3 evaluation order exactly. Pure Python rules, no LLM, no network, fully unit-testable, deny-by-default, collects all failing reasons. Includes destination matching (exact address, domain, URL prefix with scheme/host normalization), data-scope matching, provenance rule (user-typed vs untrusted-origin args; compare normalized values against the user request), posture check using the live `Health` from SEC-1 (`tier2_available`), kill switch lookup, approval reuse check (`approval_id` + `action_hash`). Property tests: random args never produce ALLOW for a prohibited tool; ALIGN cannot raise a decision.

### 3. ALIGN (`align/`)
- `AlignClient.check(original_request, policy_summary, proposed_action) -> AlignVerdict(aligned|misaligned|uncertain|unavailable, score)`. Separate prompt/schema/metrics from DET.
- Implement with LAYA typed questions (`choice`/`noul`): "Does this action serve the user's request?", "Does it send data to a destination the user did not name?" etc., within LAYA's token limits (truncate; the request and the action are the inputs, never retrieved content). Timeout `ALIGN_TIMEOUT_MS`, CPU only.
- Advisory only: gateway rule 10 — it can downgrade ALLOW → REQUIRE_APPROVAL, never upgrade. Log accuracy/FP/latency into `guard/eval/align/` and produce `ALIGN_VALIDATION.md` (same structure as SEC-1's LAYA validation). Keep the `AlignClient` protocol swappable.

### 4. Approvals (`approvals/`)
`ApprovalRequest` binds to `action_hash = sha256(canonical_json({tool,args}))`, expires (default 10 min), single use. Edited args ⇒ old approval void + new request (`re_approval_required`). After approval BE re-calls `check_action(approval_id)`: you re-run the full gateway (policy, posture, kill switch, hash match) before returning ALLOW. Approver must equal the task owner. `arg_sources` rendered human-readable ("typed by you", "from email <subject> by <sender>").

### 5. State verifier (`verify/`)
Compare BE-supplied `observed` state with assertions (`no_new_sent_mail`, `file_unchanged`, `file_written_with_hash`, `draft_created`, `no_outbound_http_to`, `mock_state_equals`). Independent of model output. Failures create audit events and raise `health` warnings.

### 6. Audit (`audit/`)
Append-only table with hash chain (`hash = sha256(prev_hash || canonical_json(row))`); event types in doc 02 §8; secrets redacted; raw text never stored (hash + ≤120-char redacted snippet). `verify_chain()`; export; `/metrics` (Prometheus): `tier2_available`, escalation_rate, p50/p95 latency, decisions by type, held results. If the audit write fails, the action is **denied** (fail-safe audit).

### 7. Service and admin API
- `guard/service/main.py`: FastAPI exposing doc 02 §2 endpoints, bearer-token auth, request size limits, structured errors (never leak stack traces), `GET /metrics`.
- `guard/admin_api/`: doc 02 §7. Config versioning in `config_versions`; **four-eyes**: lowering a posture floor or enabling `tier1_only_warning` for a side-effect template requires proposal by admin A and approval by admin B. Kill switch (tool / template / all write tools) takes effect on the next `check_action`. Review queue records human decisions and never grants tool authority.

### 8. Evaluation harness (`guard/eval/`) — your largest deliverable
- Corpus per doc 04 §3 (authored attacks + benign + hard negatives; fixed splits; licence column). Share with SEC-1 by H2.
- Scenario runner: YAML scenarios S1–S14 (doc 04 §4) executed via BE's CLI (`python -m app.eval.run_scenario`) in `APP_ENV=eval`, with `GMAIL_MODE=mock`; refuses to run otherwise. Scripted-model scenarios test the gateway deterministically; LLM scenarios test end-to-end utility.
- Compares Baseline / Basic / Full; stores each run (config, versions, hardware, seed, failed traces) in `eval_runs`; produces `guard/eval/REPORT.md` and the admin Eval page data: ASR / unauthorized side effects, clean-task completion, task-under-attack completion, sanitization precision/recall, FP rate, T2/T3 latency, escalation rate, fail-closed rate, audit completeness.
- Degradation drills: force tier2 down, guard unreachable, LAYA timeout, audit write failure.

## Layout
```
contracts/  {models.py, openapi.json, ts/, CHANGES.md}
guard/
  pyproject.toml
  eva_guard/{api.py,stub.py,policy/,gateway/,align/,approvals/,audit/,verify/,det/(SEC-1)}
  service/main.py  admin_api/  alembic/
  eval/{corpus/,scenarios/,runner.py,REPORT.md,align/}
  tests/{policy,gateway,approvals,audit,verify,api}
```

## Milestones
- **H0.75 (gate G0):** `contracts/` + `StubGuard` + empty `Guard` facade importable. Announce in STATUS.
- **H3.5:** policy builder + templates, gateway complete, audit chain, approvals, verifier; `Guard.scan_tool_result` wired to SEC-1; corpus v1 shared.
- **CP-A (H4):** real `Guard` replaces StubGuard in BE; S1, S2 pass.
- **CP-B (H7):** ALIGN, admin API, HTTP service, S4, S12, S13, S14; harness running S1–S14.
- **CP-C (H9):** Baseline/Basic/Full report, drills, `ALIGN_VALIDATION.md`, known limits.

## Definition of done
`pytest guard/tests` passes; gateway has 100% rule coverage in tests; every tool call in the demo has a gateway decision and an audit row; hash-chain verify works and detects tampering; `REPORT.md` contains the metrics table with N, hardware, config version; STATUS current.

## Do not
Do not let any LLM/LAYA output decide ALLOW; do not feed retrieved content into the policy builder or ALIGN; do not edit SEC-1's `det/`; do not run evals against real Gmail; do not claim immunity.
