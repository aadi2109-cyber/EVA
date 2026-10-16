# EVA Guard — T2 Model Card

## What ships (as of this commit)
- **Model:** two small linear classifiers, each `TF-IDF (word 1–3-grams, lowercased outside the graph) → LogisticRegression`, exported to ONNX (`guard/models/t2_main.onnx`, `t2_aux.onnx`) and run with `onnxruntime` on CPU (2 intra-op threads, 64-sentence batches).
  - `main`: injection probability. `aux`: quoted / meta-discussion of attacks.
- **Not** a fine-tuned transformer and **not** int8-quantized. The earlier MiniLM/BERT-small plan was not executed (no GPU-free download/training budget in this environment); quantization does not apply to this model class.
- **Licence / provenance:** scikit-learn + skl2onnx (BSD-3), trained only on EVA's own authored corpus (`guard/eval/corpus/train.jsonl`, SEC-2). No third-party datasets or pretrained weights are used. Nothing in this card claims third-party dataset use.
- **Training:** `python -m eval.train_t2` (run from `guard/` with `PYTHONPATH=..:.`). Train 208 sentences; tuned on `dev` only; `test` was never used for tuning.
- **Integrity:** SHA-256 of `t2_main.onnx` is pinned in `guard/models/t2.sha256` (override with env `T2_MODEL_SHA256`). Mismatch or load failure ⇒ `tier2_available=false` ⇒ failure-mode policy (fail-closed ⇒ `held`).

## How the score is used
`main` is floored by the T1 rule score; `aux` is floored by regex meta-discussion patterns. A sentence is kept (and audited) when `main ≥ 0.50` and `aux ≥ 0.65` (quoted/meta). Otherwise it is removed when `main ≥ t2_block_threshold = 0.60`. Scores in `[t3_band_low, threshold)` go to T3 when a provider is configured.

## Measured results (Xeon 2.8 GHz, CPU only, 2 threads)
| Split | N | Precision | Recall | FPR | Note |
|---|---|---|---|---|---|
| dev | 69 | 100% | 82% | 0% | threshold chosen here |
| test | 71 | 100% | 100% | 0% | run once; attacks are near-variants of train items, so optimistic |
| challenge (paraphrases) | 43 | 92% | 100% | 10% | rule-tuned after first run (was R 65% / FPR 15%); regression floor only |

Latency: see `python -m eval.det.perf` (≈3–4 ms/KB p50, < 6 ms/KB p95 warm; cold start ≈ 0.1 s; peak RSS ≈ 100 MB incl. 1 MB bodies).

## Upgrade path
Replace with a fine-tuned small encoder (MiniLM-class, Apache-2.0) exported to int8 ONNX behind the unchanged `Tier2Scorer` interface; verify each model and dataset licence on its card first.
