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
- In progress: LAYA T3 timeout verification, harder held-out attacks (invoice_fraud/authority_claims are the weakest families), int8 quantization.
- Blocked / needs: None. Note T2 model is a TF-IDF baseline, not a fine-tuned encoder (MODEL_CARD target); no int8 yet.
- Next: Expand corpus with paraphrased attacks, then re-calibrate on dev; BE wires `Guard` facade at CP-A.

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
