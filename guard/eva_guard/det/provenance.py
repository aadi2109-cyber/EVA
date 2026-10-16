"""
Provenance validation, normalization, and risk scoping.
Ensures external content cannot elevate trust, and categorizes fields for tier allocation.
"""
from typing import Any
try:
    from contracts.models import Provenance, Trust, SourceType
except ImportError:
    from eva_guard.det.contracts_stub import Provenance, Trust, SourceType

LOW_RISK_FIELD_PATTERNS = {
    "id", "message_id", "thread_id", "call_id", "task_id", "approval_id",
    "date", "created_at", "updated_at", "expires_at", "timestamp",
    "count", "size", "bytes", "length", "total", "index", "status",
    "seq", "version"
}

HIGH_RISK_FIELD_PATTERNS = {
    "body", "snippet", "content", "text", "subject", "output", "result",
    "message", "raw", "summary", "description", "query", "url"
}

def validate_and_normalize_provenance(
    prov: Provenance | dict[str, Any] | None,
    field_name: str,
    default_source_type: SourceType = SourceType.TOOL_OUTPUT,
    default_source_id: str = "unknown"
) -> Provenance:
    """
    Validates and normalizes field provenance.
    Rule: Never promote trust from content text. Missing provenance defaults to UNTRUSTED.
    """
    if prov is None:
        return Provenance(
            source_id=default_source_id,
            source_type=default_source_type,
            field=field_name,
            retrieval_path=[],
            trust=Trust.UNTRUSTED
        )
    
    if isinstance(prov, dict):
        prov = Provenance.model_validate(prov)
    
    updates = {}
    if prov.source_type in (
        SourceType.EMAIL, SourceType.FILE, SourceType.WEB,
        SourceType.MESSAGE, SourceType.TOOL_OUTPUT
    ):
        if prov.trust != Trust.UNTRUSTED:
            updates["trust"] = Trust.UNTRUSTED

    if not prov.field:
        updates["field"] = field_name

    if updates:
        prov = prov.model_copy(update=updates)

    return prov

def is_high_risk_field(field_name: str, provenance: Provenance) -> bool:
    """
    Computes per-field risk scoping:
    - High-risk fields (body, snippet, file text, web text, tool output free text) get full T2.
    - Low-risk structured fields (ids, dates, numeric) get T1 only.
    """
    f_lower = field_name.lower().strip()
    
    # Check known low risk names first
    if f_lower in LOW_RISK_FIELD_PATTERNS:
        return False
        
    # Check if field name indicates an ID or numeric/date
    for pat in ("_id", "id_", "date_", "_date", "_at", "num_", "_count"):
        if f_lower.endswith(pat) or f_lower.startswith(pat):
            return False

    # Check known high risk names
    if f_lower in HIGH_RISK_FIELD_PATTERNS:
        return True
        
    # Default: if field is free text from an untrusted source, treat as high-risk
    return provenance.trust == Trust.UNTRUSTED
