# DET (content-side) — Known Limits

1. **T2 is a small lexical model** trained on ~200 authored sentences. It learns phrasing, not intent; novel wording, other languages, and obfuscation beyond T1's analysis-only decoders (base64/URL/ROT13/leet) can evade it. Rules supply a large share of recall.
2. **Reported accuracy is optimistic.** `test` attacks are near-variants of `train` items. The paraphrase challenge set (first run R 65% / FPR 15%) is a better indicator of generalization, and has since been used to add rules.
3. **False positives exist** on benign sentences that resemble attack phrasing (e.g. "Our system prompt guidelines say…", 2/20 benign on the challenge set). Cost is a removed sentence, not a blocked document.
4. **Sentence-level only.** Attacks split across sentences or fields, or carried by images/attachments/non-text content, are not seen. Cross-field context is limited.
5. **T3 (LAYA) is advisory and unverified here.** `laya` is not installed in the dev container; the validation numbers in `LAYA_VALIDATION.md` were measured elsewhere. The timeout/conservative-drop logic is tested with fakes. The `Guard` facade constructs `DetPipeline()` without a T3 provider, so gray-band escalation is inactive unless a provider is wired.
6. **Quoted/meta handling is a trade-off.** An attack wrapped in academic-sounding framing can be kept as "meta discussion" (audited, not removed). Authority still comes only from the gateway (SEC-2); DET never grants permissions.
7. **Over-cap bodies** (> `max_field_chars`, 1 MB) are truncated before scanning; content past the cap is not inspected.
8. **No adaptive-attacker evaluation.** Nothing here was tested against an attacker who can query the detector.
