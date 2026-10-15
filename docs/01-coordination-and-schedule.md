# 01 — Coordination and One-Day Schedule

Four agents work in parallel in separate chats. They coordinate through **files in the repo**, not through each other's chats. The human relays and merges at checkpoints.

## 1. Repository layout

```
eva/
├─ contracts/              # SHARED. Pydantic models + OpenAPI + JSON Schema. Owner: SEC-2. Change process in §3
├─ agent/
│  ├─ frontend/            # Owner: FE
│  └─ backend/             # Owner: BE
├─ guard/                  # Own pyproject + CI. Never imports from agent/
│  ├─ eva_guard/           # core library. SEC-1: det/ ; SEC-2: everything else
│  │  ├─ det/              # SEC-1: provenance, t1, t2, t3, sanitizer, pipeline, failure modes
│  │  ├─ policy/           # SEC-2: task policy builder, templates
│  │  ├─ gateway/          # SEC-2: deterministic gateway
│  │  ├─ align/            # SEC-2: ALIGN client
│  │  ├─ approvals/        # SEC-2
│  │  ├─ audit/            # SEC-2: hash-chained log
│  │  ├─ verify/           # SEC-2: state verifier
│  │  ├─ stub.py           # SEC-2: StubGuard for others, delivered in first 45 min
│  │  └─ api.py            # SEC-2: the single public facade implementing contracts v0
│  ├─ service/             # SEC-2: FastAPI wrapper over eva_guard.api
│  ├─ admin_api/           # SEC-2
│  └─ eval/                # SEC-2 owns harness+corpus; SEC-1 owns det-only benchmarks in eval/det/
├─ env/                    # Owner: BE. docker-compose, seeds, mock mailbox/files/web fixtures
├─ coordination/           # STATUS.md, requests/, decisions/
└─ docs/                   # this pack
```

Ownership rule: **an agent edits only its own directories.** Need a change elsewhere → write a request file (§3). The one exception is `STATUS.md`, where each agent edits only its own section.

## 2. Branches

- One branch/worktree per agent: `role/frontend`, `role/backend`, `role/sec1`, `role/sec2`; `main` is merged by the human at checkpoints.
- Directory ownership keeps merges conflict-free. Shared files (`contracts/`, `env/docker-compose.yml`, `.gitignore`, root `README.md`) have a single owner and are changed only by that owner.
- Commit small and often; each commit message starts with the role: `[BE] add gmail read tool`.

## 3. Communication protocol

- `coordination/STATUS.md` — each agent keeps its section current: done / in progress / blocked / next. Update at every milestone and whenever blocked.
- `coordination/requests/<from>-to-<to>-<nn>.md` — cross-role requests (e.g. "BE → SEC-2: need reason code X"). Recipient answers in the same file and marks it `RESOLVED`.
- **Contract changes** (`contracts/`): requester writes a request to SEC-2 with the exact schema diff. Rules: additive changes only after the contract freeze (§4, H0.75); breaking changes need both BE and SEC-2 agreement recorded in `coordination/decisions/`. Bump `CONTRACT_VERSION` on every change and list it in `contracts/CHANGES.md`.
- `coordination/decisions/NNN-title.md` — short decision records (what, why, who). Anything that deviates from this pack goes here.

## 4. One-day schedule (relative hours, all agents in parallel)

| Window | FE | BE | SEC-1 | SEC-2 | Gate |
|---|---|---|---|---|---|
| **H0 – H0.75** Setup + contract freeze | Ask human for UI ref link; scaffold Vite/TS/Tailwind/shadcn; typed API client from `02-contracts-v0.md` §6 | Repo skeleton, `env/` compose, FastAPI app, DB models, mock env fixtures | Package skeleton `guard/eva_guard/det`; start T2 model/licence spike | Materialise `contracts/` from doc 02; ship `StubGuard`; `eva_guard.api` facade skeleton | **G0 (H0.75):** contracts v0 frozen; StubGuard importable |
| **H0.75 – H3.5** Slice 1 | Shell, auth, chat + live trace on mocked SSE | Orchestrator loop, Ollama provider, scripted provider, tool registry, files + mock Gmail tools, GuardClient wired to StubGuard, SSE | T1, provenance, sentence splitter, sanitizer, pipeline with interim T2 scorer, failure modes, DET events | Task policy builder + templates, gateway rules, audit hash chain, approvals engine, verify | **G1 (H3.5):** BE runs full loop with StubGuard; SEC-1 `scan` and SEC-2 `check_action` real behind facade |
| **H3.5 – H4.0** Integration A | Point FE at real BE | Swap StubGuard → real `eva_guard` (in-process) | Fix integration issues in scan | Fix integration issues in check/policy | **CP-A (H4):** injected-email scenario passes end-to-end on mock |
| **H4 – H7** Slice 2 | Approval modal, connectors page, files view, admin shell, degraded banners | Real Gmail (OAuth, read/draft/send), web tools, messages mock, HTTP guard client + service | Real T2 model (ONNX int8), T3 LAYA adapter + timeouts, perf benchmarks | ALIGN client (LAYA typed questions), approvals + revalidation, admin API, eval harness + corpus | **CP-B (H7):** demo scenarios 1–6 (doc 04) pass |
| **H7 – H9** Evaluate and harden | Polish, empty/error states, a11y pass | Failure injection hooks, robustness, cancellation, logs | LAYA validation report, threshold calibration, T2 metrics | Baseline/Basic/Full eval runs, degradation drills, kill switch, audit verify | **CP-C (H9):** metrics table produced |
| **H9 – H10** Wrap-up | Screens for demo | Runbook | Known limits (DET) | Eval report + known limits | **Done:** definition of done (§5) |

### Priority order and cut line (if time runs short, cut from the bottom)

1. Contract, StubGuard, end-to-end loop on **mock** mailbox with the injection scenario
2. Gateway + task policy + audit
3. DET T1 + sanitizer + T2 (even interim) + failure modes
4. Approvals with exact-action display
5. Real Gmail read/draft/send
6. LAYA T3 + ALIGN
7. Admin console depth (keep Health + Audit; Review queue and Config can be read-only)
8. Eval harness polish, AgentDojo subset (deferred; keep own corpus)

## 5. Definition of done (all roles)

- Code runs from a clean checkout with the commands in your role file; unit tests pass; lint passes.
- Your section of `STATUS.md` is accurate; every deviation has a decision record.
- No secret in the repo; `.env.example` complete.
- Guard-down and Tier-2-down behaviour demonstrated (fail closed).
- Honest claims: any number you report states what was measured, on what data, on what hardware.
