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
  - Switched to `role/sec1` branch, initialized `.venv` and verified environment.
  - Implemented full DET pipeline skeleton in `guard/eva_guard/det/` compliant with contracts v0:
    - `provenance.py`: Provenance validation, trust boundary enforcement, risk scoping.
    - `t1.py`: Fast rules engine (< 1 ms) detecting role spoofing, overrides, exfil patterns, tool mimicry, URL leaks, hidden text, and analysis-only decoding.
    - `splitter.py`: Sentence splitter preserving exact character offsets `text[start:end] == span.text`, abbreviations, and long sentence chunking.
    - `t2.py`: `Tier2Scorer` interface with `InterimTier2Scorer` multi-head (main/aux for benign meta-injection) and `OnnxTier2Scorer` with hash pinning.
    - `t3.py`: `Tier3Provider` protocol, `LayaProvider` with strict timeout, and conservative fallback drop.
    - `sanitizer.py`: Surgical sentence-level sanitizer replacing only malicious sentences with `[CONTENT SANITISED]`.
    - `pipeline.py`: `DetPipeline` scan method supporting `fail_closed` / `tier1_only_warning`, telemetry, and non-raw audit emission (`det.scan`, `det.degraded`).
    - `health.py`: Telemetry gauges (`tier2_available`, `escalation_rate`, p50/p95).
    - `MODEL_CARD.md`: Open-licence encoder selection (MiniLM/BERT-small on Apache 2.0).
    - `LAYA_VALIDATION.md`: Measured CPU validation report and recommendation.
    - `guard/eval/det/run.py`: Benchmark runner (`python -m eval.det.run --split dev|test`).
    - Test suite in `guard/tests/det/`: 21 unit and hypothesis property tests passing.
- In progress: Slice 2 (H4–H7): T2 model fine-tuning spike, LAYA timeout verification, and CP-A end-to-end integration scenario.
- Blocked / needs: None. All 66 tests (SEC-1 + SEC-2) passing seamlessly.
- Next: End-to-end scenario validation (S1 & S5) against `Guard` facade and mock mailbox/workspace environment.

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
  - Merged `role/sec1` into `role/sec2`; re-ran everything: 72 tests pass; S1-S14 Full 14/14 (Baseline 9 unauthorized side effects, Basic 2, Full 0); drills 10/10; `eval/DET_METRICS.md` added (via Guard facade: test recall 21%, precision 100%, FP 0%; dev recall 22%, precision 64%).
  - Service: request-size limit (413, `GUARD_MAX_BODY_BYTES`, default 4 MB). HTTP end-to-end tests (`tests/test_service_e2e.py`): approval single use + tamper + replay, hijacked send, 401s, 413, no stack-trace leakage.
  - Hypothesis property tests (`tests/test_gateway_properties.py`): prohibited write tools never ALLOW/approvable, unknown tool/task always DENY, ALIGN never upgrades a decision. Mutation-checked (disabling rule 4 makes them fail). 84 tests passing.
  - `eval_runs` store (`guard/eval/store.py`): every runner (scenarios, drills, align, det) persists config, versions, hardware, seed, summary and failed traces. Admin endpoints (bearer auth): `GET /admin/v1/eval/runs?kind=&limit=&offset=`, `GET /admin/v1/eval/runs/{id}` (config, versions, failures), `GET /admin/v1/eval/summary` (latest per kind + `comparison_table` rows `{metric, baseline, basic, full}` for the Eval page). FE: read-only; 86 tests passing.
- In progress (was: waiting on SEC-1 DetPipeline) (scan checks S1/S9/S11, sanitization P/R, T2 latency); CP-A integration readiness.
- Blocked / needs: Waiting for BE to wire real Guard facade / SEC-1 to wire `DetPipeline` at CP-A (H4).
- Next: Baseline/Basic/Full scenario runner, degradation drill fixtures.

## Gates
- [x] G0 contracts frozen + StubGuard (H0.75)
- [ ] G1 full loop on StubGuard; real scan + check behind facade (H3.5)
- [ ] CP-A injected-email scenario S1 end to end (H4)
- [ ] CP-B demo scenarios S1,S2,S4,S7,S12 (H7)
- [ ] CP-C metrics table produced (H9)
