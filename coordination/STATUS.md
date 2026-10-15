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
- In progress: Awaiting SEC-2 facade integration checkpoint (CP-A) and corpus delivery for full fine-tuning spike.
- Blocked / needs: None. Ready for integration with SEC-2's `api.py` facade and BE's loop.
- Next: Integration checkpoint CP-A (verifying S1 and S5 end-to-end through facade); ONNX model asset packaging.

## SEC-2
- Done:
- In progress:
- Blocked / needs:
- Next:

## Gates
- [ ] G0 contracts frozen + StubGuard (H0.75)
- [ ] G1 full loop on StubGuard; real scan + check behind facade (H3.5)
- [ ] CP-A injected-email scenario S1 end to end (H4)
- [ ] CP-B demo scenarios S1,S2,S4,S7,S12 (H7)
- [ ] CP-C metrics table produced (H9)
