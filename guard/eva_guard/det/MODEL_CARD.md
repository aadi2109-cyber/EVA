# EVA Guard — T2 Model Card

## What ships (as of this commit)
- **Model:** two small linear classifiers, each `TF-IDF (word 1–3-grams, lowercased outside the graph) → LogisticRegression`, exported to ONNX (`guard/models/t2_main.onnx`, `t2_aux.onnx`) and run with `onnxruntime` on CPU (2 intra-op threads, 64-sentence batches).
  - `main`: injection probability. `aux`: quoted / meta-discussion of attacks.
- **Not** a fine-tuned transformer and **not** int8-quantized. The earlier MiniLM/BERT-small plan was not executed (no GPU-free download/training budget in this environment); quantization does not apply to this model class.
- **Licence / provenance:** scikit-learn + skl2onnx (BSD-3), trained only on EVA's own authored corpus (`guard/eval/corpus/train.jsonl`, SEC-2). No third-party datasets or pretrained weights are used. Nothing in this card claims third-party dataset use.
- **Training:** `python -m eval.train_t2` (run from `guard/` with `PYTHONPATH=..:.`). Train 208 sentences; threshold chosen on `dev` only; `test` was never used for tuning but was scored several times (see table).
- **Integrity:** SHA-256 of `t2_main.onnx` is pinned in `guard/models/t2.sha256` (override with env `T2_MODEL_SHA256`). Mismatch or load failure ⇒ `tier2_available=false` ⇒ failure-mode policy (fail-closed ⇒ `held`).

## How the score is used
`main` is floored by the T1 rule score; `aux` is floored by regex meta-discussion patterns. A sentence is kept (and audited) when `main ≥ 0.50` and `aux ≥ 0.65` (quoted/meta). Otherwise it is removed when `main ≥ t2_block_threshold = 0.60`. Scores in `[t3_band_low, threshold)` go to T3 when a provider is configured.

## Measured results (Xeon 2.8 GHz, CPU only, 2 threads)
| Split | N | Precision | Recall | FPR | Note |
|---|---|---|---|---|---|
| dev | 69 | 100% | 82% | 0% | threshold chosen here |
| test | 71 | 100% | 100% | 0% | scored 3 times while developing (no decision was based on it); one attack family only and 10/71 items repeat a train sentence after prefix-stripping, so optimistic |
| challenge (paraphrases) | 43 | 92% | 100% | 10% | rule-tuned after first run (was R 65% / FPR 15%); regression floor only |

Latency: see `python -m eval.det.perf` (≈3–4 ms/KB p50, < 6 ms/KB p95 warm; cold start ≈ 0.1 s; peak RSS ≈ 100 MB incl. 1 MB bodies).

## Upgrade path
Replace with a fine-tuned small encoder (MiniLM-class, Apache-2.0) exported to int8 ONNX behind the unchanged `Tier2Scorer` interface; verify each model and dataset licence on its card first.

## Training data and statistics (reproducible: `PYTHONPATH=..:. python -m eval.train_t2`)
**Corpus** (`eval/corpus/*.jsonl`, SEC-2 "corpus v1", 348 sentences, 100% authored/synthetic, 100% English, avg 85–101 chars; no public datasets, no real-world emails):

| split | N | attack | benign | families |
|---|---|---|---|---|
| train | 208 | 102 | 106 (68 quoted/meta) | instruction_override 14, role_marker_spoofing 12, exfiltration 12, tool_misuse 12, encoded 12, homoglyph_leet 12, indirect_web 12, hidden_html 12, authority_claims 4 / benign: quoted_meta 68, business_email 16, technical_work 12, benign_invoice 10 |
| dev | 69 | 34 | 35 (all quoted/meta) | authority_claims 8, invoice_fraud 12, url_query_exfiltration 12, instruction_override 2 / quoted_meta 35 |
| test | 71 | 34 | 37 (all quoted/meta) | instruction_override 34 / quoted_meta 37 |
| challenge (SEC-1, `eval/det/challenge.jsonl`) | 43 | 23 | 20 | hand-written paraphrases; never trained on |

Splits are **not** stratified by family: dev contains families unseen in train (invoice_fraud, url_query_exfiltration), test contains only instruction_override. Exact train/dev/test text overlap: 0.

**Model:** per head `TfidfVectorizer(ngram 1–3, sublinear_tf, lowercase done outside the graph)` = 4,405 n-gram features, then `LogisticRegression(C=5, max_iter=1000, random_state=42)`; 8,810 coefficients; 184 KiB per ONNX file; ops Tokenizer/TfIdfVectorizer/Normalizer/LinearClassifier. `main` label = attack; `aux` label = family name contains "quoted"/"meta" (68/208 train).

**Raw head scores, model alone (no T1/meta rules):**

| split | AUC (main) | recall / precision / FPR @0.50 | @0.60 (shipped) | @0.65 |
|---|---|---|---|---|
| train | 1.000 | 1.00 / 1.00 / 0.00 | 0.98 / 1.00 / 0.00 | 0.98 / 1.00 / 0.00 |
| dev | 1.000 | 0.79 / 1.00 / 0.00 | 0.76 / 1.00 / 0.00 | 0.65 / 1.00 / 0.00 |
| test | 1.000 | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.00 |
| challenge | 0.907 | 0.83 / 0.90 / 0.10 | 0.52 / 0.86 / 0.10 | 0.30 / 1.00 / 0.00 |

Aux head: AUC 1.000 on train/dev/test (label is the family name, so this is easy), but only 0.739 on challenge, where it finds 1 of 6 meta sentences at 0.5; the pipeline therefore also uses regex meta-patterns as a floor.

**Reading these numbers honestly**
- Train accuracy is 100% (4,405 features, 208 samples): the model memorises. Dev/test AUC of 1.000 with recall far below 1 means it ranks well but is under-confident; the threshold, not the ranking, is the weak point on dev. On new phrasing (challenge, AgentDojo) it degrades sharply.
- Highest-weight attack n-grams are surface tokens (`com`, `org`, `net`, `https`, `send`, `system`, `the user`); benign: `the`, `morning`, `good morning`, `report`. It learns shortcuts, which explains false positives on short unfamiliar benign sentences.
- No cross-validation, no confidence intervals on the small splits (dev N=69, test N=71, challenge N=43).
- The shipped pipeline result (see above) also uses T1 rules, which carry much of the recall.
