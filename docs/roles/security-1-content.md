# Role: SEC-1 — Content-side security ("DET") (1 of 2 security agents)

You own `guard/eva_guard/det/` and `guard/eval/det/`. You build everything that inspects **content**: provenance tagging, T1/T2/T3 detection, the sentence-level sanitizer, failure modes, DET telemetry. You detect and neutralize; you never grant authority. Your partner is SEC-2 (policy, gateway, ALIGN, approvals, audit, admin, eval).

Objectives you serve: separate user instructions from instructions in external content (provenance), detect and neutralize malicious instructions in tool outputs, keep legitimate tasks completing (surgical sanitization), log decisions (emit events).

## Read first
`00` · `01` · `02` (§1 types, §2.2 scan, §3 behaviour rules, §8 audit) · `03` (hardware: CPU only) · `04` (corpus, metrics).

## Stack
Python 3.12, Pydantic v2, `onnxruntime` (CPU), `tokenizers`, a sentence splitter (pysbd or a rules-based one — pick one, document it), `numpy`, `pytest`, `hypothesis`. Training spike only: `torch` + `transformers` + `optimum`/onnx export (dev dependency group, not required at runtime).

## Public surface (what SEC-2's facade calls)
```python
# guard/eva_guard/det/pipeline.py
class DetPipeline:
    def __init__(self, config: DetConfig, audit: AuditSink, t3: Tier3Provider | None): ...
    async def scan(self, req: ScanRequest) -> ScanResponse   # contract 02 §2.2
    def health(self) -> DetHealth                            # tier2_available, t3_available, t2_model_hash
```
`AuditSink` is a tiny protocol SEC-2 provides (`emit(type, payload)`); never import SEC-2 modules beyond contracts and that protocol.

## What to build

### 1. Provenance (`det/provenance.py`)
Validate and normalize `Provenance` on every field; any claim of "system"/"developer"/"assistant" inside content stays `UNTRUSTED` (never promote trust from text). Fields missing provenance are treated as `UNTRUSTED`. Compute per-field risk scoping: high-risk fields (body, snippet, file text, web text, tool output free text) get full T2; structured low-risk fields (ids, dates, numeric) get T1 only.

### 2. T1 — fast rules (`det/t1.py`, ~1 ms target)
Signals (each a named, loggable constant): role-marker spoofing (`SYSTEM:`, `<|im_start|>`, "developer message"), override phrases ("ignore previous/above/the user"), exfiltration patterns (forward/send/export + all/mailbox + external address/URL), tool-invocation mimicry (JSON/XML tool-call lookalikes), URL-query data exfil, hidden-text indicators, and **analysis-only** normalization for decoding base64 / URL-encoding / ROT13 / homoglyph / leetspeak candidates — decode to *analyse*, but output text is never rewritten. Output `t1_signals` and a T1 score.

### 3. Sentence splitting
Split into sentences with stable character offsets so the sanitizer can remove exactly a span and keep the rest, including inside lists, quoted replies, signatures, HTML-derived text. Handle very long sentences (chunk) and non-English text without crashing.

### 4. T2 — local sentence classifier (`det/t2.py`)
- Interface `Tier2Scorer.score(sentences) -> list[Score(main, aux)]`, ONNX int8 on CPU, `max_length=128`, batch sentences, 2 threads. Multi-head: `main` = injection score; `aux` = "quoted / meta discussion of attacks" to cut false positives on documents *about* injection. Decision rule: high `main` with high `aux` → keep (benign meta), but audit it.
- **Hour 0–0.75:** ship an interim scorer behind the same interface (combines T1 signals into a 0–1 score) so SEC-2 and BE get a working pipeline immediately.
- **Hours 1–4 (model spike):** choose an openly licensed small encoder (MiniLM-class). Candidates to evaluate — **verify each licence and dataset licence yourself on the model card; do not assume**: a MiniLM/BERT-small base you fine-tune on our corpus (preferred, you control the licence), or an existing openly licensed prompt-injection classifier as a reference baseline. Avoid models whose licence restricts use or redistribution. Record choice, licence, dataset sources in `guard/eva_guard/det/MODEL_CARD.md`.
- Fine-tune on `train`, tune on `dev`, report once on `test` (SEC-2's corpus, doc 04 §3). Export to ONNX, quantize int8, pin `T2_MODEL_SHA256`. At startup verify the hash; mismatch ⇒ `tier2_available=false`.
- Benchmark on the dev laptop (no GPU): ms per sentence, ms/KB p50/p95, cold start, RSS. Report CPU model.

### 5. Gray-band routing + T3 (LAYA) (`det/t3.py`)
- Sentences with T2 main score in `[T3_BAND_LOW, T3_BAND_HIGH)` (start `[0.30, 0.85)`) go to T3. Target escalation < 10% of sentences. Cap `T3_MAX_TEXT_CHARS`; hard timeout `T3_TIMEOUT_MS`.
- `Tier3Provider` protocol: `async def judge(sentence, context, provenance) -> T3Verdict(malicious|benign|uncertain, score)`.
- `LayaProvider`: LAYA is a non-autoregressive typed-decision encoder (checkpoints `laya`, `laya-multilingual`, `laya-typed-decisions`; Python `laya.Router().predict(state, questions)`; has a guard-question preset for jailbreaks/injections). Ask a small fixed set of typed yes/no (`noul`) questions about the sentence and compose a verdict. Lazy-load weights, keep at most one checkpoint resident, CPU only.
- **Advisory only.** Rules: T3 timeout / error / malformed / `uncertain` ⇒ conservative: drop the sentence, mark `[CONTENT SANITISED]`, audit `det.scan` with `t3_verdict`. T3 can raise a sentence's risk; it can lower it only when T2 is below `BLOCK_THRESHOLD`. It never decides about tool permissions.
- **LAYA validation (required deliverable, `guard/eva_guard/det/LAYA_VALIDATION.md`):** on the dev split report accuracy / precision / recall / false-positive rate for the gray-band sentences only, CPU latency p50/p95, memory, first-use download size/time; compare with "T2 only" and "T2 + conservative drop". Recommendation: keep / refine / replace. If it fails, the `Tier3Provider` interface lets SEC-2/BE swap in another judge (e.g. a small Ollama call) without changes elsewhere.

### 6. Sanitizer (`det/sanitizer.py`)
Remove or quarantine **only** sentences whose final disposition is malicious; replace each with `[CONTENT SANITISED]`; keep surrounding structure/whitespace; keep legitimate facts (invoice numbers, dates). If structure cannot be preserved (e.g. malformed JSON field, code block), quarantine the whole field (`quarantined=true`, text replaced by a marker). Return counts per field.

### 7. Failure modes and telemetry
- `fail_closed` (default for side-effect tasks): T2 unavailable (missing model, hash mismatch, runtime error) ⇒ `disposition="held"`, no fields returned. `tier1_only_warning` (only when the policy says read-only/restricted): continue on T1, `warnings=["TIER2_UNAVAILABLE"]`. The caller's policy sets the floor; you cannot lower it.
- Emit `det.scan` and `det.degraded` audit events: per-field t1 signals, t2 score summary (min/mean/max), t3 verdicts, removed sentence offsets, per-phase timings, `tier2_available`, model hash. Store a content hash and a ≤120-char redacted snippet — **not** the raw text.
- Expose gauges for SEC-2's `/metrics`: `tier2_available`, escalation_rate, p50/p95.

### 8. Performance and robustness
Pipeline must handle: empty fields, 1 MB bodies (cap and chunk; over-cap ⇒ hold or sample-and-quarantine, never crash), binary garbage, huge unicode, deeply nested HTML-text. Time budget: T1 ≈ 1 ms, T2 target < 15 ms/KB p95 warm on CPU. Property tests (hypothesis): sanitizer never expands text; offsets valid; output never contains a removed span; idempotent on already-sanitized text.

## Layout
```
guard/eva_guard/det/
  __init__.py  config.py  provenance.py  t1.py  splitter.py  t2.py  t3.py  sanitizer.py  pipeline.py  health.py
  MODEL_CARD.md  LAYA_VALIDATION.md
guard/eval/det/   # benchmark + metric scripts: python -m eval.det.run --split dev|test
guard/tests/det/
```

## Milestones
- **H0.75:** package skeleton, `DetPipeline` with T1 + interim T2 scorer returning valid `ScanResponse`s.
- **H3.5:** provenance, splitter, sanitizer, failure modes, audit events; unit + property tests.
- **CP-A (H4):** S1 and S5 sanitize correctly through SEC-2's facade.
- **CP-B (H7):** real ONNX T2 + hash pinning; LAYA adapter with timeouts; perf numbers.
- **CP-C (H9):** `LAYA_VALIDATION.md`, calibrated thresholds on `dev`, one `test` report, DET known-limits section.

## Definition of done
`pytest guard/tests/det` passes; S1, S5, S6(sanitization part), S7, S8, S9, S11 pass through the full path; metrics reported per `04` §2 with hardware stated; STATUS section current.

## Do not
Do not decide allow/deny for any tool; do not import agent code; do not log raw content; do not let T3 or any detector output flow into permissions; do not tune on the `test` split; do not claim Defender's published numbers as ours.
