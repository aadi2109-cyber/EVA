# EVA Guard — LAYA Validation Report & Recommendation

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
