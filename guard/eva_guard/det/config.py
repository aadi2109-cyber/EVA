"""
Configuration for DET pipeline components.
"""
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def _read_pin() -> str | None:
    """Pinned SHA-256 of the main T2 model: env T2_MODEL_SHA256, else models/t2.sha256."""
    env = os.environ.get("T2_MODEL_SHA256")
    if env:
        return env.strip()
    f = _MODELS_DIR / "t2.sha256"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


class DetConfig(BaseModel):
    t2_model_path: str = str(_MODELS_DIR / "t2_main.onnx")
    t2_aux_model_path: str = str(_MODELS_DIR / "t2_aux.onnx")
    t2_model_sha256: str | None = Field(default_factory=lambda: _read_pin())  # T2_MODEL_SHA256; mismatch => tier2 unavailable
    t2_high_risk_threshold: float = 0.85
    t2_meta_min_main: float = 0.50      # main>=this and aux>=min_aux => quoted/meta, keep
    t2_meta_min_aux: float = 0.65
    t3_band_low: float = 0.30
    t3_band_high: float = 0.85
    block_threshold: float = 0.85       # T1 rules / low-risk fields
    t2_block_threshold: float = 0.60    # ONNX model score; calibrated on dev (0 FP), never on test
    t3_enabled: bool = True
    t3_timeout_ms: int = 1500
    t3_max_text_chars: int = 2000
    default_failure_mode: Literal["fail_closed", "tier1_only_warning"] = "fail_closed"
    max_field_chars: int = 1_000_000  # Cap and chunk large inputs up to 1 MB
    sentence_max_chars: int = 500     # Chunk excessively long sentences
    intra_op_threads: int = 2         # CPU constraint
