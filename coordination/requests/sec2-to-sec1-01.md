# Request sec2-to-sec1-01
Status: OPEN
From: SEC-2 · To: SEC-1 · Date: 2026-10-16

## Need
1. **Corpus re-split (action required if you tuned on the old splits).** `guard/eval/corpus/{train,dev,test}.jsonl` were rebuilt: the old split was ordered, so `test` held only `instruction_override` and `train` had no `invoice_fraud`/`url_query_exfiltration`. New split is stratified by (label, family), grouped by base text (prefixed near-duplicates stay together), deterministic. Now: train 217 / dev 67 / test 64; every attack family appears in every split. Please re-run `eval.det.run` on dev/test and do not tune on test.
2. **T3 never active through `Guard`.** `Guard._init_det_pipeline` calls `DetPipeline()` with no `t3`, so gray-band sentences (0.30–0.85) are never escalated or conservatively dropped in the real facade. Please expose a default factory (e.g. `DetPipeline.default()` building `LayaProvider`) that I can call from `Guard`; I will not edit `det/`. Note `LayaProvider.is_available` is False without the `laya` package, which makes the pipeline skip T3 entirely (gray band passes). Consider making "T3 configured but unavailable" drop/hold per failure mode instead.
3. **Interim T2 recall is low on our labels** (sentence-level, `main>=0.85`, interim rule scorer): test recall 6/29, precision 1.0, FP 0/35; dev recall 7/32, precision 0.64 (4 FP on benign "security alert" meta text). Misses are spread over all families, mostly instruction_override paraphrases ("Disregard all prior guidance…", "Forget the above command…"). Numbers are from SEC-2's quick check, not your benchmark; please confirm with your runner and the ONNX scorer.

## Why / what breaks without it
Without 2, scenario S9 can only be exercised with an injected pipeline fixture; with 3, CP-C sanitization recall will not meet a credible bar.

## Proposed change
None to contracts.

## Answer (recipient fills in)
