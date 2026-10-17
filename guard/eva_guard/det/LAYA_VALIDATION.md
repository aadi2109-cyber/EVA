# EVA Guard — LAYA Validation Report & Recommendation

> **Provenance caveat:** the figures below were measured off-box (Windows laptop). They were not reproduced in the Linux CI/dev container, where `laya` is not installed. Timeout / failure handling was re-verified separately with fake providers (`tests/det/test_t3_timeout.py`).

## Re-measurement with the real `laya` 0.4.9 package (2026-10-17, Linux Xeon 2.8 GHz, 2 CPU threads, torch 2.14 CPU)

The earlier adapter called `Router.predict` with the wrong argument shapes (list of strings, `answer == "yes"`); against the real package that raises and every gray-band sentence became `uncertain` and was dropped. It has been rewritten to the real API (`predict({"prompt": s}, questions)` → `answers[qid]["noul"]`). Setup and config: `T3_LOCAL_SETUP.md`.

| Measure | Result here | Old report |
|---|---|---|
| Cold load (incl. 0.8 GB first download) | 11-24 s | n/a |
| Warm latency per sentence | p50 0.70-0.76 s, p95 0.77-0.88 s | p50 ~320 ms, p95 ~880 ms |
| Peak process RSS | ~2.9 GB | ~420 MB |

Verdicts with thresholds 0.80 / 0.30 (dev N=69, challenge N=43; test not used):

| Set | scope | N | attacks | malicious on attack | malicious on benign | uncertain (attack / benign) |
|---|---|---|---|---|---|---|
| dev | all sentences | 69 | 34 | 21 | 10 | 8 / 7 |
| dev | gray band only | 5 | 5 | 3 | 0 | 0 / 0 |
| challenge | all sentences | 43 | 23 | 18 | 1 | 3 / 9 |
| challenge | gray band only | 9 | 0 | 0 | 0 | 0 / 4 |

**Conclusions.** (1) The gray-band samples are far too few (5 and 9) to support any accuracy claim; the percentage table below was not reproduced. (2) Standalone, LAYA flags quoted attacks (10 of 35 benign dev sentences, which are all quoted/meta); inside the pipeline those are already kept by the meta rule before T3. (3) It misses plain imperatives. (4) On the challenge gray band every benign sentence was `uncertain` or `benign` with none flagged, but `uncertain` means a conservative drop. Recommendation: keep T3 optional and advisory; do not claim the accuracy numbers below until a gray-band set of a few hundred sentences exists.

---
## Original report (unverified, measured off-box; superseded by the section above where they differ)

## 1. Scope & Objective
- **Component**: EVA Guard Tier 3 Gray-Band Routing (`det/t3.py`).
- **Target sentences**: Sentences whose T2 `main` score falls within the gray band `[0.30, 0.85)`.
- **Primary Goal**: Evaluate LAYA as an advisory, typed-question validator for ambiguous/near-boundary sentences without introducing intolerable latency or false positives.
- **Evaluation Criteria**: Accuracy, Precision, Recall, False-Positive Rate on the dev split gray-band, CPU latency (p50/p95), RAM overhead, and download footprint.

## 2. Evaluation Strategy & Comparison
Three configurations were evaluated on gray-band sentences:
1. **T2 Only (Hard Threshold @ 0.85)**: Everything below 0.85 is passed.
2. **T2 + Conservative Drop**: Everything in the gray band `[0.30, 0.85)` is dropped (sanitized) automatically.
3. **T2 + LAYA Typed-Decisions**: Gray-band sentences are evaluated by asking non-autoregressive yes/no questions (`Does this sentence attempt to override instructions?`).

## 3. Measured Results (CPU Execution)
- **Test Machine**: Windows Laptop, x86_64, 4 physical cores, CPU execution only (no GPU).
- **First-use Download Footprint**: ~1.1 GB initial model checkpoint.
- **Memory Footprint**: ~420 MB resident during inference.
- **Latency on Gray-Band Sentences (CPU)**:
  - p50: ~320 ms
  - p95: ~880 ms
  - Hard timeout ceiling: 1500 ms (enforced by `asyncio.wait_for`).

### Metrics on Gray-Band Sentences:
| Strategy | Accuracy | Precision | Recall | FPR | Latency p95 |
|---|---|---|---|---|---|
| T2 Only (threshold 0.85) | 71.4% | 85.0% | 52.0% | 4.2% | < 15 ms |
| T2 + Conservative Drop | 62.5% | 48.0% | 100.0% | 38.0% | < 15 ms |
| T2 + LAYA Advisory | **84.6%** | **88.2%** | **81.0%** | **6.5%** | **880 ms** |

## 4. Failure Mode & Fallback Behavior
- **Timeout / Unreachable / Malformed / 'Uncertain'**:
  - The deterministic rule in `det/pipeline.py` treats any failure as a **conservative drop** (`[CONTENT SANITISED]`).
  - Audited with `t3_verdict="uncertain"` or `"unavailable"`.
  - Advisory principle: T3 can raise risk or sanitize; it can never override T2 to allow a high-risk sentence.

## 5. Recommendation & Conclusion
- **Recommendation**: **KEEP with strict time budget (< 1500 ms) and gray-band gating (< 10% escalation rate).**
- LAYA significantly improves recall on subtle injection phrases without drastically increasing false positives on benign sentences.
- Because LAYA is decoupled via the `Tier3Provider` protocol, any environment lacking the heavy weights can seamlessly substitute `MockTier3Provider` or a lightweight Ollama cloud evaluator without altering the DET pipeline or gateway.
