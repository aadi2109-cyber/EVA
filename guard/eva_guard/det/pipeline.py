"""
DET Pipeline Orchestrator.
Coordinates Provenance validation, T1 fast rules, Sentence splitting, T2 sentence classification,
T3 LAYA gray-band routing, surgical Sanitization, failure mode handling, and audit telemetry.
"""
import time
import uuid
import hashlib
import asyncio
from typing import Any, Protocol, runtime_checkable
from eva_guard.det.config import DetConfig
from eva_guard.det.health import DetHealth
from eva_guard.det.provenance import validate_and_normalize_provenance, is_high_risk_field
from eva_guard.det.splitter import split_sentences, SentenceSpan
from eva_guard.det.t1 import scan_t1
from eva_guard.det.t2 import Tier2Scorer, create_t2_scorer, Score
from eva_guard.det.t3 import Tier3Provider, T3Result
from eva_guard.det.sanitizer import sanitize_text, SANITIZED_MARKER

try:
    from contracts.models import (
        ScanRequest, ScanResponse, ScanField, SanitizedField,
        DetSummary, Provenance, Trust, SourceType
    )
except ImportError:
    from eva_guard.det.contracts_stub import (
        ScanRequest, ScanResponse, ScanField, SanitizedField,
        DetSummary, Provenance, Trust, SourceType
    )

class AwaitableScanResponse(ScanResponse):
    """
    Subclass of ScanResponse that implements __await__.
    Allows DetPipeline.scan() to be called synchronously (e.g. guard.scan_tool_result)
    or awaited directly (e.g. await det_pipeline.scan(req)) without error.
    """
    def __await__(self):
        async def _identity():
            return self
        return _identity().__await__()

@runtime_checkable
class AuditSink(Protocol):
    """Protocol for logging audit events to SEC-2's hash-chained log."""
    def emit(self, event_type: str, payload: dict[str, Any]) -> str | None:
        ...

class DetPipeline:
    """
    Main detection pipeline implementing the scan_tool_result interface.
    Follows frozen contract 02 §2.2 and behavior rules in 02 §3.
    """
    def __init__(
        self,
        config: DetConfig | None = None,
        audit: AuditSink | None = None,
        t3: Tier3Provider | None = None,
        t2_scorer: Tier2Scorer | None = None,
    ) -> None:
        self.config = config or DetConfig()
        self.audit = audit
        self.t3 = t3
        self.t2 = t2_scorer or create_t2_scorer(self.config)

        # Telemetry metrics
        self._latencies: list[float] = []
        self._total_sentences: int = 0
        self._t3_escalated_sentences: int = 0

    def is_tier2_available(self) -> bool:
        """Check if Tier 2 is available (read by Guard facade & health checks)."""
        return self.t2.is_available

    def is_t3_available(self) -> bool:
        """Check if Tier 3 is available."""
        return (self.t3 is not None and self.t3.is_available) if self.config.t3_enabled else False

    def health(self) -> DetHealth:
        """Reports DET health and telemetry gauges."""
        p50 = 0.0
        p95 = 0.0
        if self._latencies:
            sorted_lat = sorted(self._latencies)
            p50 = sorted_lat[len(sorted_lat) // 2]
            p95 = sorted_lat[int(len(sorted_lat) * 0.95)]

        escalation_rate = 0.0
        if self._total_sentences > 0:
            escalation_rate = round(self._t3_escalated_sentences / self._total_sentences, 4)

        return DetHealth(
            tier2_available=self.is_tier2_available(),
            t3_available=self.is_t3_available(),
            t2_model_hash=self.t2.model_hash,
            failure_mode=self.config.default_failure_mode,
            metrics={
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "escalation_rate": escalation_rate,
            }
        )

    def _judge_t3_safe(self, text: str, context: str, prov: Provenance) -> T3Result:
        """Executes Tier 3 judgment safely in sync/async contexts."""
        if hasattr(self.t3, "judge_sync"):
            return self.t3.judge_sync(text, context, prov)
        try:
            from eva_guard.det.t3 import _T3_POOL
            fut = _T3_POOL.submit(asyncio.run, self.t3.judge(text, context, prov))
            try:
                return fut.result(timeout=self.config.t3_timeout_ms / 1000.0)
            except Exception:
                fut.cancel()
                raise
        except Exception:
            return T3Result(verdict="uncertain", score=None, latency_ms=0.0)

    def scan(self, req: ScanRequest) -> AwaitableScanResponse:
        """
        Scans all fields in a ScanRequest.
        Applies T1 -> T2 -> T3, sanitizes malicious content, handles failure modes, and emits audit.
        Returns an AwaitableScanResponse that can be consumed synchronously or awaited.
        """
        start_total = time.perf_counter()
        warnings: list[str] = []
        t1_signals_all: set[str] = set()
        t2_scores_all: list[float] = []
        t3_used = False
        t3_last_verdict = None
        latencies = {"t1": 0.0, "t2": 0.0, "t3": 0.0, "total": 0.0}

        event_id = str(uuid.uuid4())
        tier2_available = self.is_tier2_available()

        # 1. Failure Mode Check
        if not tier2_available:
            warnings.append("TIER2_UNAVAILABLE")
            if self.config.default_failure_mode == "fail_closed":
                # Fail closed: hold everything, no field content reaches the model
                elapsed_total = (time.perf_counter() - start_total) * 1000.0
                latencies["total"] = round(elapsed_total, 2)

                if self.audit:
                    self.audit.emit("det.degraded", {
                        "task_id": req.task_id,
                        "call_id": req.call_id,
                        "tier2_available": False,
                        "action": "held",
                        "reason": "Tier 2 unavailable under fail_closed policy"
                    })

                return AwaitableScanResponse(
                    disposition="held",
                    fields=[],
                    det_summary=DetSummary(
                        t1_signals=[],
                        t2_max_score=None,
                        t3_used=False,
                        t3_verdict=None,
                        latency_ms=latencies
                    ),
                    tier2_available=False,
                    warnings=warnings,
                    contract_version="0.1.0",
                    event_id=event_id
                )

        sanitized_fields: list[SanitizedField] = []
        any_sanitized = False
        any_quarantined = False

        # 2. Process each field
        for field in req.fields:
            # Validate provenance
            norm_prov = validate_and_normalize_provenance(
                field.provenance,
                field_name=field.name,
                default_source_id=req.call_id
            )

            raw_text = field.text or ""

            # Check for excessive input (cap and chunk at 1 MB)
            if len(raw_text) > self.config.max_field_chars:
                warnings.append(f"FIELD_TRUNCATED_{field.name}")
                raw_text = raw_text[:self.config.max_field_chars]

            # Fast T1 scan on field text
            t1_start = time.perf_counter()
            field_t1 = scan_t1(raw_text)
            latencies["t1"] += (time.perf_counter() - t1_start) * 1000.0

            for sig in field_t1.signals:
                t1_signals_all.add(sig)

            # Risk scoping
            is_high_risk = is_high_risk_field(field.name, norm_prov)

            if not is_high_risk or not raw_text.strip():
                # Low risk structured field: sanitize if strong T1 override
                malicious_spans: list[SentenceSpan] = []
                spans: list[SentenceSpan] = []
                if field_t1.score >= self.config.block_threshold:
                    spans = [SentenceSpan(text=raw_text, start=0, end=len(raw_text))]
                    malicious_spans = spans

                san_res = sanitize_text(raw_text, spans, malicious_spans)
                if san_res.sentences_removed > 0:
                    any_sanitized = True

                sanitized_fields.append(SanitizedField(
                    name=field.name,
                    text=san_res.text,
                    sentences_total=san_res.sentences_total,
                    sentences_removed=san_res.sentences_removed,
                    quarantined=san_res.quarantined
                ))
                continue

            # High-risk field: split sentences with stable offsets
            sentence_spans = split_sentences(raw_text, max_sentence_len=self.config.sentence_max_chars)
            self._total_sentences += len(sentence_spans)

            malicious_spans: list[SentenceSpan] = []

            if sentence_spans:
                span_texts = [s.text for s in sentence_spans]

                # T2 sentence classification
                t2_start = time.perf_counter()
                scores = self.t2.score(span_texts) if tier2_available else [Score(main=field_t1.score, aux=0.0) for _ in span_texts]
                latencies["t2"] += (time.perf_counter() - t2_start) * 1000.0

                for span, score in zip(sentence_spans, scores):
                    t2_scores_all.append(score.main)

                    # Rule: Quoted/meta discussion of attacks stays benign
                    if score.meta_injection_discussed:
                        continue

                    # Direct T2 block threshold check
                    if score.main >= self.config.t2_block_threshold:
                        malicious_spans.append(span)
                        continue

                    # T3 gray-band check
                    if (
                        self.config.t3_band_low <= score.main < self.config.t3_band_high
                        and self.t3 is not None
                        and self.t3.is_available
                    ):
                        self._t3_escalated_sentences += 1
                        t3_used = True
                        t3_start = time.perf_counter()
                        t3_res: T3Result = self._judge_t3_safe(
                            text=span.text,
                            context=raw_text[:500],
                            prov=norm_prov
                        )
                        latencies["t3"] += (time.perf_counter() - t3_start) * 1000.0
                        t3_last_verdict = t3_res.verdict

                        if t3_res.verdict == "malicious":
                            malicious_spans.append(span)
                        elif t3_res.verdict in ("uncertain", "unavailable"):
                            # Conservative drop: drop the sentence, mark [CONTENT SANITISED]
                            malicious_spans.append(span)

            # Surgical sanitization
            san_res = sanitize_text(raw_text, sentence_spans, malicious_spans)
            if san_res.sentences_removed > 0:
                any_sanitized = True
            if san_res.quarantined:
                any_quarantined = True

            sanitized_fields.append(SanitizedField(
                name=field.name,
                text=san_res.text,
                sentences_total=san_res.sentences_total,
                sentences_removed=san_res.sentences_removed,
                quarantined=san_res.quarantined
            ))

            # Audit logging: emit det.scan event without logging raw text
            if self.audit:
                text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
                redacted_snippet = (
                    san_res.text[:120].replace("\n", " ") if san_res.text else ""
                )
                self.audit.emit("det.scan", {
                    "task_id": req.task_id,
                    "call_id": req.call_id,
                    "field": field.name,
                    "provenance": norm_prov.model_dump(),
                    "content_hash": text_hash,
                    "redacted_snippet": redacted_snippet,
                    "t1_signals": list(t1_signals_all),
                    "t2_scores_summary": {
                        "min": min(t2_scores_all) if t2_scores_all else 0.0,
                        "max": max(t2_scores_all) if t2_scores_all else 0.0,
                        "mean": (sum(t2_scores_all) / len(t2_scores_all)) if t2_scores_all else 0.0
                    },
                    "t3_verdict": t3_last_verdict,
                    "sentences_removed": san_res.sentences_removed,
                    "tier2_available": tier2_available
                })

        # Disposition determination
        if any_quarantined:
            disposition = "quarantined"
        elif any_sanitized:
            disposition = "sanitized"
        else:
            disposition = "pass"

        elapsed_total = (time.perf_counter() - start_total) * 1000.0
        latencies["total"] = round(elapsed_total, 2)
        latencies["t1"] = round(latencies["t1"], 2)
        latencies["t2"] = round(latencies["t2"], 2)
        latencies["t3"] = round(latencies["t3"], 2)
        self._latencies.append(elapsed_total)

        t2_max = max(t2_scores_all) if t2_scores_all else None

        return AwaitableScanResponse(
            disposition=disposition,
            fields=sanitized_fields,
            det_summary=DetSummary(
                t1_signals=sorted(list(t1_signals_all)),
                t2_max_score=round(t2_max, 3) if t2_max is not None else None,
                t3_used=t3_used,
                t3_verdict=t3_last_verdict,
                latency_ms=latencies
            ),
            tier2_available=tier2_available,
            warnings=warnings,
            contract_version="0.1.0",
            event_id=event_id
        )
