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
  - Slice 2: real T2 (ONNX, TF-IDF+LR multi-head, hash-pinned) now actually scores in `OnnxTier2Scorer` (was delegating to interim); main floored by T1, aux floored by rule meta-patterns. `create_t2_scorer` uses it by default.
  - Fixed: committed ONNX models failed to load without an `en_US.UTF-8` locale (StringNormalizer) -> retrained with lowercasing outside the graph; `eval/train_t2.py` now path-independent.
  - Fixed: `eval.det.run` read the wrong corpus path and silently used a 12-item fallback; it now runs the real dev/test splits.
  - Calibration (dev only): `t2_block_threshold=0.60` (separate from T1 `block_threshold`). Dev: P 100% / R 82% / FPR 0%. Test (run once, not tuned): P 100% / R 100% / FPR 0%, p95 < 1 ms. Caveat: test attacks are near-variants of train items, so treat test recall as optimistic.
  - 71 tests passing.
  - T3/LAYA timeout verified and fixed: `LayaProvider.judge_sync` (the path the pipeline uses) had no timeout, so a hung LAYA call would stall a scan; the pipeline's async fallback also waited on pool shutdown. Both now bounded by `t3_timeout_ms` via a shared executor; timeout/exception -> `uncertain` -> conservative drop. Tests in `test_t3_timeout.py`.
  - Paraphrase challenge set `eval/det/challenge.jsonl` (43 items, SEC-1 owned; `--split challenge`). First run, untouched: R 65% / FPR 15%. Added generalizable T1 rules (authority/credential requests, gift-card & "no need to verify" invoice fraud, task-cancel overrides) and meta-discussion patterns -> R 100% / FPR 10% (2 benign at model score ~0.63). The set is now rule-tuned, so it is a regression floor (`test_challenge_set.py`), not an independent measure.
  - Spec audit (role doc `eva-dev-docs/roles/security-1-content.md`) closed the remaining items: T2 hash now pinned by default (`models/t2.sha256` / `T2_MODEL_SHA256`); T2 scoring batched (64) which cut peak RSS 1.6 GB -> ~96 MB on a 1 MB body and 1 MB scan 5.3 s -> 3.1 s; `eval/det/perf.py` perf report (Xeon 2.8 GHz, 2 threads: ~3-4 ms/KB p50, < 6 ms/KB p95 warm, vs < 15 ms/KB target; cold start ~0.1 s); scenarios S6/S9/S10 (detector side) + hostile-input/1 MB robustness tests; `MODEL_CARD.md` rewritten to describe the actual model (it previously claimed a MiniLM int8 model and third-party datasets); new `KNOWN_LIMITS.md`; LAYA report annotated as off-box/unreproduced.
  - T3 wired into the `Guard` facade: `Guard(db_url=None, t3_provider=None)`; default `create_t3_provider()` -> `LayaProvider` (off via `EVA_T3_ENABLED=0`). `LayaProvider.is_available` now probes for the `laya` package (was always True), `Guard.health()` reports real `t3_available` and DET p50/p95/escalation metrics (were hardcoded). S9 verified through the facade (`tests/det/test_facade_t3.py`).
  - 95 tests passing.
- In progress: none.
- Blocked / needs (from others): (1) Real LAYA weights are not installed here, so T3 against the real model is untested; install `laya` where S9 is demoed. (2) SEC-2: S6 full path (gateway denies the fetch) and CP-C metrics table use SEC-2's runner; SEC-1 can supply det-only numbers on request. (3) Decision for the human: invest in a fine-tuned int8 encoder (needs model download) or accept TF-IDF baseline + rules; see KNOWN_LIMITS.md.
- Next: CP-C one-shot `test` report is already recorded in MODEL_CARD.md; re-run only if the model changes.

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
  - Merged SEC-1 through 3d36b28 (T3 wired into Guard, ONNX T2): 113 tests pass, S1-S14 Full 14/14, drills 10/10. Detection via facade: dev recall 91% / test 97% (precision 100%, FP 0) but **blind probe (48 fresh records) recall 58%, precision 78%, FP 17%** - see `eval/DET_METRICS.md`, follow-up in `requests/sec2-to-sec1-01.md`.
- In progress (was: waiting on SEC-1 DetPipeline) (scan checks S1/S9/S11, sanitization P/R, T2 latency); CP-A integration readiness.
- Blocked / needs: Waiting for BE to wire real Guard facade / SEC-1 to wire `DetPipeline` at CP-A (H4).
- Next: Baseline/Basic/Full scenario runner, degradation drill fixtures.

## Gates
- [x] G0 contracts frozen + StubGuard (H0.75)
- [ ] G1 full loop on StubGuard; real scan + check behind facade (H3.5)
- [ ] CP-A injected-email scenario S1 end to end (H4)
- [ ] CP-B demo scenarios S1,S2,S4,S7,S12 (H7)
- [ ] CP-C metrics table produced (H9)
