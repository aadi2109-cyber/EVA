"""
Contracts v0 definitions for DET pipeline (frozen at 0.1.0).
Provides seamless fallback when the external contracts/ package is not yet materialized.
"""
from enum import Enum
from typing import Literal, Any
from pydantic import BaseModel, Field

class Trust(str, Enum):
    USER = "user"            # typed by the authenticated user in this task
    SYSTEM = "system"        # app-generated constants
    UNTRUSTED = "untrusted"  # anything retrieved: email, file, web, message, tool output

class SourceType(str, Enum):
    USER_REQUEST = "user_request"
    EMAIL = "email"
    FILE = "file"
    WEB = "web"
    MESSAGE = "message"
    TOOL_OUTPUT = "tool_output"

class Provenance(BaseModel):
    source_id: str
    source_type: SourceType
    field: str | None = None
    retrieval_path: list[str] = Field(default_factory=list)
    trust: Trust = Trust.UNTRUSTED

class ScanField(BaseModel):
    name: str
    text: str
    provenance: Provenance

class ScanRequest(BaseModel):
    task_id: str
    call_id: str
    tool: str
    fields: list[ScanField]

class SanitizedField(BaseModel):
    name: str
    text: str
    sentences_total: int
    sentences_removed: int
    quarantined: bool = False

class DetSummary(BaseModel):
    t1_signals: list[str] = Field(default_factory=list)
    t2_max_score: float | None = None
    t3_used: bool = False
    t3_verdict: Literal["malicious", "benign", "uncertain", "unavailable"] | None = None
    latency_ms: dict[str, float] = Field(default_factory=dict)

class ScanResponse(BaseModel):
    disposition: Literal["pass", "sanitized", "quarantined", "held"]
    fields: list[SanitizedField] = Field(default_factory=list)
    det_summary: DetSummary
    tier2_available: bool
    warnings: list[str] = Field(default_factory=list)
    contract_version: str = "0.1.0"
    event_id: str
