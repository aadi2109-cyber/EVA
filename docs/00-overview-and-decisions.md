# 00 — Overview and Decisions

## 1. What we are building

Two products with one narrow contract:

1. **EVA Agent** — web app + backend. User gives a task in chat; the agent completes it in multiple steps using tools: Gmail, files (sandboxed workspace), web search/fetch, messages, and the outputs of other tools. Clean UI that shows what the agent is doing and what the security system did about it.
2. **EVA Guard** — modular, lightweight security system. Python library (`eva_guard`) plus a thin HTTP service over it. Everything the agent reads goes through it before the model sees it; every action the agent wants to take goes through it before it runs.

Source architecture: `aegisagent_architecture_brief.md` (now EVA). This pack changes two things from the brief: **security is Python-native (no Node sidecar)** and **Gmail is real from day one** (security testing still mock-only).

## 2. Security objectives and who delivers them

| # | Objective | Mechanism | Owner |
|---|---|---|---|
| 1 | Separate user instructions from instructions inside external content | Task policy built only from the user's request; provenance tags on all content and tool arguments; orchestrator plans only from the user request; external content delivered to the model as delimited, labelled data | SEC-2 (policy), SEC-1 (provenance), BE (orchestrator discipline) |
| 2 | Detect and neutralize malicious instructions in tool outputs | DET pipeline T1 → T2 → T3, sentence-level sanitizer | SEC-1 |
| 3 | Stop successful attacks causing unwanted actions | Deterministic gateway: deny by default, scope/destination/provenance checks, approvals, state verifier | SEC-2 |
| 4 | Keep completing legitimate tasks during an attack | Surgical sentence removal (not whole-document blocking); utility measured in eval | SEC-1, SEC-2 |
| 5 | Check high-impact actions against the original request | ALIGN advisory check + `approval_required_for` + exact-action human approval | SEC-2 |
| 6 | Log security decisions for investigation | Hash-chained audit log, per-stage events, audit explorer | SEC-2 (log), all (emit events) |

## 3. Principles (from the brief; non-negotiable)

1. External content is data, never authority.
2. Model proposes; gateway disposes. No tool runs without `ALLOW`.
3. T1/T2/T3 and ALIGN are **advisory**; none can grant a permission. ALIGN may only make a decision stricter, never looser.
4. Deny by default. Fail closed on unknown tools, bad arguments, guard errors, timeouts, degraded security state.
5. Degradation is visible: `tier2_available=false` is logged, shown in the UI, and read by policy.
6. Verify real post-state after execution; never trust the agent's self-report.

## 4. Confirmed decisions (15 Oct 2026)

| Topic | Decision |
|---|---|
| Frontend | React 18 + Vite + TypeScript, Tailwind + shadcn/ui, TanStack Query, SSE |
| Agent backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, SQLite (WAL) |
| Guard | Python-native. T1 rules, T2 ONNX sentence classifier (onnxruntime, CPU), T3 = LAYA advisory |
| Integration | Both: `eva_guard` library + `guard/service` HTTP wrapper. Agent talks to one `GuardClient` interface with two implementations (`InProcessGuardClient`, `HttpGuardClient`) |
| Model provider | **Ollama cloud models**; API key and model name supplied by the human via env. `ModelProvider` interface kept so Gemini can be added later (not built now) |
| Hardware target | Ordinary developer laptop, **no GPU use**, integrated graphics only. Everything must run on CPU |
| Gmail | Dedicated personal Gmail account; OAuth app audience External, status Testing; test users = the human + team; minimum scopes; **send always requires explicit approval through EVA**; security testing on mock Gmail only |
| LAYA | Validate during iterative development. Start as advisory component for T3 (content) and ALIGN (action intent); measure accuracy, false positives, latency; refine or replace; the deterministic gateway remains the final authority |
| Team and time | 4 agents (FE, BE, SEC-1, SEC-2), one-day multi-agent workflow, working in parallel |
| Security split | SEC-1 content side (detection/sanitization); SEC-2 authority side (policy/gateway/ALIGN/approvals/audit/admin/eval). Treated as equal seniority |

## 5. Assumptions (flagged — change them if wrong)

- "Messages" = the in-app conversation history plus a `messages.send` tool to a **mock** messaging channel (no real chat platform in v1).
- Web = `web.search` and `web.fetch` over the real internet in normal use; scripted local mock pages in tests/evals.
- Files = a sandboxed per-user workspace directory; no access outside it.
- Users are seeded (one `admin`, one or more `user`s). No self-signup.
- Guard LLM-style calls (policy drafting) use the same Ollama cloud credentials but through the guard's own client; the guard never imports agent code.

## 6. Known technical risks (everyone should know these)

| Risk | Impact | Handling |
|---|---|---|
| LAYA is a 322M–421M encoder (not a generative LLM), reported at ~33 ms on a T4 GPU. On CPU it will be much slower | T3/ALIGN latency on laptops | Gray-band only, hard timeout, conservative fallback; measure CPU latency in the validation report; weights download on first use (needs network once) |
| LAYA has no documented "action/intent alignment" feature; the README documents typed questions (`choice`/`score`/`noul`) and a guard-question preset for injections | ALIGN quality unknown | Frame ALIGN as typed yes/no questions on (task, action); validate; replace if it fails |
| Python-native T2 needs an openly licensed model we may legally use | Blocks T2 | SEC-1 spike first: choose an open-licensed base, check dataset licenses, fine-tune/evaluate on our corpus. Interim: T1-driven placeholder scorer behind the same interface so the pipeline works from hour 1 |
| Gmail OAuth in Testing mode: refresh tokens expire after about 7 days; test users only | Reconnect needed | Document in UI; connectors page shows status |
| One-day schedule | Scope pressure | Priority order in `01-coordination-and-schedule.md` §4; cut line defined |
