# EVA — STATUS (each agent edits only its own section)

Contract version: 0.1.0 · Last human merge: <time>

## FE
- Done:
- In progress:
- Blocked / needs:
- Next:

## BE
- Done:
  - Role started on branch `role/backend`.
  - Verified Python environment, installed dependencies (`pydantic-settings`, `structlog`, `argon2-cffi`, `pytest`, `pytest-asyncio`, `pyyaml`, `prometheus-client`, `greenlet`, `fastapi`, `uvicorn`, `sqlalchemy`, `aiosqlite`).
  - Verified Gate G0 `contracts/` and `StubGuard` integration.
  - Delivered `env/` (docker-compose, .env.example, mock fixtures: mailbox.json, workspace, web, state.py, reset.py).
  - Delivered `agent/backend` app skeleton, configuration, auth, DB models (SQLite WAL).
  - Delivered tool registry (Gmail real/mock, sandboxed files, web, messages).
  - Delivered model providers (ScriptedProvider + OllamaProvider) and GuardClient (InProcess + HTTP).
  - Delivered Orchestrator loop with strict provenance, guard checks, state observation, and SSE replay.
  - Achieved Gate G1: full loop on StubGuard + ScriptedProvider + SSE.
  - Achieved Checkpoint CP-A: injected-email scenario S1 passes end to end with real guard facade; S2, S4, S4 approval flow, S7, and S12 scenarios verified and passing.
  - Full test suite passing: 22/22 tests passing in `agent/backend/tests/`.
  - CP-B work: HttpGuardClient parity tests vs guard service, approvals e2e (S4) incl. edited-args re-approval, admin proxy, SSE Last-Event-ID replay (auth added), web tool hardening, Gmail mock/real backend parity + OAuth hardening, failure-injection hooks (EVA_FAIL_*), eval CLI + reset, Dockerfile/.env.example/compose, docs/RUNBOOK-backend.md.
  - Backend suite: 119/119 passing.
  - Prompt A: per-process test DB (parallel pytest safe); connector `status` column + migration 002 (replaces expires_hint prefix); plain `sqlite:///` DATABASE_URL accepted; edited-args re-approval e2e test; scenarios S3, S8, S10, S11 added to runner; S13/S14 tested through the admin proxy; admin proxy now takes admin identity from the JWT (X-Admin-User-Id, proposed_by), so four-eyes can't be spoofed.
  - Backend suite: 128/128 passing.
- In progress: CP-C robustness (ops/tools work split to other BE teammates).
- Blocked / needs: None. Real Gmail/OAuth and Docker build not verified (mocked-HTTP tests only). S9 (LAYA timeout on a gray-band sentence) is detector-side: needs SEC-1's DetPipeline. S11 "quoted text not stripped" is only as strong as the detector wired in.
- Next / known issues: web.search simulated; SSRF check is hostname-only; in-process mode admin changes don't reach the in-process Guard instance.

## SEC-1
- Done:
- In progress:
- Blocked / needs:
- Next:

## SEC-2
- Done:
  - Gate G0: `contracts/` v0.1.0 (`contracts/models.py`), `CHANGES.md`, exported `openapi.json`, TypeScript definitions (`contracts/ts/`).
  - `StubGuard` test-only implementation (`guard/eva_guard/stub.py`), refuses `APP_ENV=prod`.
  - `Guard` single public facade (`guard/eva_guard/api.py`).
  - Task Policy Builder (`guard/eva_guard/policy/`) with 8 YAML templates, deterministic intent classification, destination extraction, least-privilege enforcement.
  - Deterministic Policy Gateway (`guard/eva_guard/gateway/`) with 100% rule coverage across all 11 evaluation rules in doc 02 §3.
  - Approvals Engine (`guard/eva_guard/approvals/`) with exact cryptographic action hash binding (`sha256`), single-use enforcement, 10-min expiration, and edited-args re-approval.
  - Tamper-evident Audit Logger (`guard/eva_guard/audit/`) with SQLite append-only table, sha256 hash chaining, secret redaction, and `verify_chain()` integrity check.
  - State Verifier (`guard/eva_guard/verify/`) with post-execution assertions on observed environment state.
  - Advisory ALIGN client (`guard/eva_guard/align/`) with downgrade-only rule 10 check.
  - HTTP Service (`guard/service/main.py`) with bearer token auth, prometheus metrics (`/metrics`), structured error responses.
  - Admin API (`guard/admin_api/`) with Four-Eyes config change enforcement, instantaneous kill switches, review queue, and audit verify.
  - Evaluation Corpus v1 (`guard/eval/corpus/`) with 170 attacks across 12 families, 178 benign (including 140 quoted/meta hard negatives), fixed train/dev/test splits ready for SEC-1.
  - Full test suite passing: 45/45 tests passing (`guard/tests/`).
- In progress: Evaluation scenario runner (`guard/eval/runner.py`) for S1-S14 and CP-A integration readiness.
- Blocked / needs: Waiting for BE to wire real Guard facade / SEC-1 to wire `DetPipeline` at CP-A (H4).
- Next: Baseline/Basic/Full scenario runner, degradation drill fixtures.


## Gates
- [x] G0 contracts frozen + StubGuard (H0.75)
- [ ] G1 full loop on StubGuard; real scan + check behind facade (H3.5)
- [ ] CP-A injected-email scenario S1 end to end (H4)
- [ ] CP-B demo scenarios S1,S2,S4,S7,S12 (H7)
- [ ] CP-C metrics table produced (H9)
