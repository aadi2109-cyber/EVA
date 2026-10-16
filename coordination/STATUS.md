# EVA — STATUS (each agent edits only its own section)

Contract version: 0.1.0 · Last human merge: <time>

## FE
- Done:
- In progress:
- Blocked / needs:
- Next:

## BE
- Done:
- In progress:
- Blocked / needs:
- Next:

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
  - Scenario runner `guard/eval/runner.py` + `eval/scenarios/s1_s14.yaml`: S1-S14 x Baseline/Basic/Full; writes `eval/REPORT.md` + `results.json`; refuses unless `APP_ENV=eval GMAIL_MODE=mock`. Run: `cd guard && APP_ENV=eval GMAIL_MODE=mock PYTHONPATH=.:.. python -m eval.runner`.
  - Fixes found by the runner: file-path destinations (sandbox sentinel + traversal check), files.write only on user write intent, gmail.draft to out-of-policy recipient -> REQUIRE_APPROVAL (see contracts/CHANGES.md).
  - Test suite: 48 passing. Latest run: Full 14/14 expectations, 0 unauthorized side effects (Baseline 9, Basic 3); detector-dependent checks N/A until SEC-1 lands.
  - Degradation drills `eval/drills.py` -> `eval/DRILLS.md`: 10/10 fail closed (tier2 down, audit write failure, ALIGN timeout/crash, kill switch, unknown tool/task, missing DetPipeline warning).
  - ALIGN: hard timeout + swappable `backend` in `AlignClient`; `eval/ALIGN_VALIDATION.md` (N=25 authored, heuristic backend: recall 10/14, FP 0/11, misses all in the `hard` group; LAYA backend not wired, so LAYA is unvalidated).
  - Tests: 49 passing.
  - Corpus re-split (stratified by family, grouped by base text; old test split held one family only). Request `requests/sec2-to-sec1-01.md` sent.
  - S9 now uses a gray-band + timing-out T3 fixture when SEC-1's DetPipeline is present. Verified in a scratch merge of `role/sec1`: 14/14 Full expectations (S1, S9, S11 pass), 72 tests passing.
- In progress: waiting on SEC-1 DetPipeline (scan checks S1/S9/S11, sanitization P/R, T2 latency); CP-A integration readiness.
- Blocked / needs: Waiting for BE to wire real Guard facade / SEC-1 to wire `DetPipeline` at CP-A (H4).
- Next: Baseline/Basic/Full scenario runner, degradation drill fixtures.


## Gates
- [x] G0 contracts frozen + StubGuard (H0.75)
- [ ] G1 full loop on StubGuard; real scan + check behind facade (H3.5)
- [ ] CP-A injected-email scenario S1 end to end (H4)
- [ ] CP-B demo scenarios S1,S2,S4,S7,S12 (H7)
- [ ] CP-C metrics table produced (H9)
