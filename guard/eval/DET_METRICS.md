# Sanitization Metrics (through the Guard facade)

- Date: 2026-10-16  ·  Detector: DetPipeline (interim rule-based T2; T3 not wired through `Guard`)
- Hardware: x86_64 Linux 3.13.16, CPU only  ·  corpus v1 (authored), whole-record granularity, stratified splits
- `test` is held out; `dev` was visible to SEC-1. Single run, no seeds involved.

| Split | N | Recall | Precision | FP rate | TP/FN/FP/TN | latency p50 / p95 per KB |
|---|---|---|---|---|---|---|
| dev | 67 | 22% | 64% | 11% | 7/25/4/31 | 24.79 / 43.51 ms |
| test | 64 | 21% | 100% | 0% | 6/23/0/35 | 26.62 / 37.10 ms |

## Recall by family — dev

| Family | Caught |
|---|---|
| authority_claims | 1/2 |
| encoded | 0/2 |
| exfiltration | 0/2 |
| hidden_html | 0/2 |
| homoglyph_leet | 0/2 |
| indirect_web | 0/2 |
| instruction_override | 4/12 |
| invoice_fraud | 0/2 |
| role_marker_spoofing | 1/2 |
| tool_misuse | 0/2 |
| url_query_exfiltration | 1/2 |

False positives (dev): Security alert: be vigilant against emails claiming 'Our banking detai; Good morning! Security alert: be vigilant against emails claiming 'Our; Please note: Security alert: be vigilant against emails claiming 'Our ; FYI from team: Security alert: be vigilant against emails claiming 'Ou

## Recall by family — test

| Family | Caught |
|---|---|
| authority_claims | 0/2 |
| encoded | 1/2 |
| exfiltration | 0/2 |
| hidden_html | 1/2 |
| homoglyph_leet | 0/2 |
| indirect_web | 0/2 |
| instruction_override | 0/9 |
| invoice_fraud | 1/2 |
| role_marker_spoofing | 2/2 |
| tool_misuse | 0/2 |
| url_query_exfiltration | 1/2 |

False positives (test): none

## Targets (doc 04 §2)

- Precision > 85%: met on the sets above only if the table says so; recall is far below any useful bar and is reported, not claimed.
- T2 < 15 ms/KB p95: the table is end-to-end `Guard.scan_tool_result` including the synchronous SQLite audit write, with records mostly <0.2 KB (per-KB figure is inflated by the 0.1 KB floor). SEC-1's own det-only runner reports <1 ms per record. Not comparable to the target until measured on KB-sized inputs without the audit write.
- T3 escalation rate < 10%: 0% trivially, because `Guard` builds `DetPipeline` without a T3 provider (request sec2-to-sec1-01).
- Zero misses on a finite suite would not mean immunity; here recall is low and the gateway, not detection, carries the safety guarantee.
