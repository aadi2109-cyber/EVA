"""
Configuration for DET pipeline components.
"""
from typing import Literal
from pydantic import BaseModel, Field

class DetConfig(BaseModel):
    t2_model_path: str = "./guard/models/t2.onnx"
    t2_model_sha256: str | None = None
    t2_high_risk_threshold: float = 0.85
    t3_band_low: float = 0.30
    t3_band_high: float = 0.85
    block_threshold: float = 0.85
    t3_enabled: bool = True
    t3_timeout_ms: int = 1500
    t3_max_text_chars: int = 2000
    default_failure_mode: Literal["fail_closed", "tier1_only_warning"] = "fail_closed"
    max_field_chars: int = 1_000_000  # Cap and chunk large inputs up to 1 MB
    sentence_max_chars: int = 500     # Chunk excessively long sentences
    intra_op_threads: int = 2         # CPU constraint
