"""
DET Health and Metrics tracking.
Exposes tier availability, model hashes, and latency/escalation gauges for SEC-2's /metrics.
"""
from pydantic import BaseModel, Field

class DetHealth(BaseModel):
    tier2_available: bool
    t3_available: bool
    t2_model_hash: str | None = None
    failure_mode: str = "fail_closed"
    metrics: dict[str, float] = Field(default_factory=dict)
