"""
EVA Guard — DET (Content-side Detection & Sanitization).
Owner: SEC-1.
"""
from eva_guard.det.config import DetConfig
from eva_guard.det.health import DetHealth
from eva_guard.det.pipeline import DetPipeline, AuditSink
from eva_guard.det.provenance import validate_and_normalize_provenance, is_high_risk_field
from eva_guard.det.splitter import split_sentences, SentenceSpan
from eva_guard.det.t1 import scan_t1, T1Result
from eva_guard.det.t2 import Tier2Scorer, Score, InterimTier2Scorer, OnnxTier2Scorer, create_t2_scorer
from eva_guard.det.t3 import Tier3Provider, T3Result, LayaProvider, MockTier3Provider
from eva_guard.det.sanitizer import sanitize_text, SANITIZED_MARKER

__all__ = [
    "DetConfig",
    "DetHealth",
    "DetPipeline",
    "AuditSink",
    "validate_and_normalize_provenance",
    "is_high_risk_field",
    "split_sentences",
    "SentenceSpan",
    "scan_t1",
    "T1Result",
    "Tier2Scorer",
    "Score",
    "InterimTier2Scorer",
    "OnnxTier2Scorer",
    "create_t2_scorer",
    "Tier3Provider",
    "T3Result",
    "LayaProvider",
    "MockTier3Provider",
    "sanitize_text",
    "SANITIZED_MARKER",
]
