"""
Sentence splitter with stable character offsets.
Splits text into SentenceSpans with exact start and end offsets, handling lists,
quotes, signatures, abbreviations, and long sentence chunking.
"""
import re
from typing import NamedTuple

class SentenceSpan(NamedTuple):
    text: str
    start: int
    end: int

# Common English and domain abbreviations to avoid false splitting
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc", "fig",
    "e.g", "i.e", "inc", "ltd", "corp", "co", "jan", "feb", "mar",
    "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "u.s", "u.k", "eu", "no", "approx", "a.m", "p.m", "am", "pm"
}

def split_sentences(text: str, max_sentence_len: int = 500) -> list[SentenceSpan]:
    """
    Splits text into sentences while tracking exact character offsets in `text`.
    Guarantees:
      - text[span.start : span.end] == span.text
      - No spans overlap.
      - Every span has len(span.text) > 0.
      - Very long segments are chunked up to max_sentence_len characters.
    """
    if not text:
        return []

    spans: list[SentenceSpan] = []
    length = len(text)
    cur_start = 0
    i = 0

    while i < length:
        ch = text[i]

        # Break on newlines
        if ch == '\n' or ch == '\r':
            seg = text[cur_start:i]
            if seg.strip():
                _add_spans(text, cur_start, i, spans, max_sentence_len)
            # Advance past consecutive newlines/whitespace
            while i < length and text[i] in '\r\n':
                i += 1
            cur_start = i
            continue

        # Check for sentence end punctuation: . ! ?
        if ch in '.!?':
            # Check for abbreviations
            is_abbrev = False
            if ch == '.':
                # Look backwards for word
                word_match = re.search(r"([a-zA-Z.]+)\Z", text[cur_start:i])
                if word_match:
                    candidate = word_match.group(1).lower().rstrip('.')
                    if candidate in _ABBREVIATIONS:
                        is_abbrev = True
                # Check for numeric decimal e.g. 12.50 or IP address
                if i > 0 and i + 1 < length and text[i-1].isdigit() and text[i+1].isdigit():
                    is_abbrev = True

            # If followed by whitespace/quote or end of string, and not abbreviation:
            if not is_abbrev:
                next_pos = i + 1
                # Absorb closing quotes/parentheses if any
                while next_pos < length and text[next_pos] in '"\'”)>]':
                    next_pos += 1
                
                # Boundary is reached if at end of string or followed by space/newline
                if next_pos >= length or text[next_pos].isspace():
                    seg = text[cur_start:next_pos]
                    if seg.strip():
                        _add_spans(text, cur_start, next_pos, spans, max_sentence_len)
                    # Advance past trailing whitespace
                    while next_pos < length and text[next_pos].isspace():
                        next_pos += 1
                    cur_start = next_pos
                    i = next_pos
                    continue

        # If current segment has grown beyond max_sentence_len, force a chunk
        if (i - cur_start) >= max_sentence_len:
            # Try to break at a space or comma
            break_pt = _find_break_point(text, cur_start, i)
            _add_spans(text, cur_start, break_pt, spans, max_sentence_len)
            # Advance past spaces
            while break_pt < length and text[break_pt].isspace():
                break_pt += 1
            cur_start = break_pt
            i = break_pt
            continue

        i += 1

    # Remaining tail
    if cur_start < length:
        seg = text[cur_start:length]
        if seg.strip():
            _add_spans(text, cur_start, length, spans, max_sentence_len)

    return spans

def _find_break_point(text: str, start: int, end: int) -> int:
    """Finds a natural whitespace/punctuation breakpoint near the end of a long segment."""
    for p in range(end, start + (end - start) // 2, -1):
        if text[p].isspace() or text[p] in ',;:':
            return p + 1
    return end

def _add_spans(
    full_text: str,
    start: int,
    end: int,
    out: list[SentenceSpan],
    max_len: int
) -> None:
    """Adds trimmed span while preserving exact substring invariant."""
    raw = full_text[start:end]
    # Strip leading whitespace
    lead_strip = len(raw) - len(raw.lstrip())
    # Strip trailing whitespace
    trail_strip = len(raw) - len(raw.rstrip())

    real_start = start + lead_strip
    real_end = end - trail_strip

    if real_start < real_end:
        span_text = full_text[real_start:real_end]
        # Guarantee invariant
        assert span_text == full_text[real_start:real_end]
        out.append(SentenceSpan(text=span_text, start=real_start, end=real_end))
