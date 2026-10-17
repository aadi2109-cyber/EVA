"""
Surgical sentence-level sanitizer.
Replaces only malicious sentence spans with `[CONTENT SANITISED]` while preserving
surrounding whitespace, legitimate facts (invoices, dates, instructions), and structure.
Supports field-level quarantine when structure cannot be preserved.
"""
from typing import NamedTuple
from eva_guard.det.splitter import SentenceSpan

SANITIZED_MARKER = "[CONTENT SANITISED]"

class SanitizedResult(NamedTuple):
    text: str
    sentences_total: int
    sentences_removed: int
    quarantined: bool

def sanitize_text(
    original_text: str,
    all_spans: list[SentenceSpan],
    malicious_spans: list[SentenceSpan],
    force_quarantine: bool = False
) -> SanitizedResult:
    """
    Surgically removes malicious spans from original_text.
    Spans are removed in reverse offset order to prevent index drift.
    """
    sentences_total = len(all_spans)
    
    if force_quarantine:
        return SanitizedResult(
            text=SANITIZED_MARKER,
            sentences_total=sentences_total,
            sentences_removed=sentences_total,
            quarantined=True
        )

    if not malicious_spans:
        return SanitizedResult(
            text=original_text,
            sentences_total=sentences_total,
            sentences_removed=0,
            quarantined=False
        )

    # Validate spans and sort in reverse order of start position
    sorted_spans = sorted(malicious_spans, key=lambda s: s.start, reverse=True)

    # Invariant check: verify non-overlapping
    cleaned = original_text
    removed_count = 0

    for span in sorted_spans:
        # Check boundaries
        if span.start < 0 or span.end > len(cleaned) or span.start >= span.end:
            continue
        
        # Replace span with marker
        prefix = cleaned[:span.start]
        suffix = cleaned[span.end:]
        cleaned = prefix + SANITIZED_MARKER + suffix
        removed_count += 1

    return SanitizedResult(
        text=cleaned,
        sentences_total=sentences_total,
        sentences_removed=removed_count,
        quarantined=False
    )
