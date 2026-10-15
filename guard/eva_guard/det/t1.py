"""
T1 — Fast Rules Detector (~1 ms target).
Inspects text for known injection indicators, role-marker spoofing, overrides,
exfiltration patterns, tool mimicry, URL leaks, and hidden text.
Performs analysis-only normalization (base64, rot13, url, leet, homoglyphs)
without modifying output text.
"""
import re
import base64
import urllib.parse
from typing import NamedTuple

# Signal constants
SIGNAL_ROLE_MARKER_SPOOFING = "ROLE_MARKER_SPOOFING"
SIGNAL_OVERRIDE_PHRASES = "OVERRIDE_PHRASES"
SIGNAL_EXFILTRATION_PATTERNS = "EXFILTRATION_PATTERNS"
SIGNAL_TOOL_INVOCATION_MIMICRY = "TOOL_INVOCATION_MIMICRY"
SIGNAL_URL_QUERY_EXFIL = "URL_QUERY_EXFIL"
SIGNAL_HIDDEN_TEXT_INDICATORS = "HIDDEN_TEXT_INDICATORS"

class T1Result(NamedTuple):
    signals: list[str]
    score: float
    is_flagged: bool

# Compiled regex patterns for fast evaluation
_ROLE_PATTERNS = [
    re.compile(r"(?i)(?:^|\n)\s*(?:system\s*:|<\|im_start\|>system|\[system\]|###\s*system|developer\s+message\s*:|<\|developer\|>|\[inst\]\s*system)", re.MULTILINE),
    re.compile(r"(?i)(?:^|\n)\s*(?:assistant\s*:|<\|im_start\|>assistant|\[assistant\]|###\s*assistant)", re.MULTILINE),
    re.compile(r"(?i)\b(?:you\s+are\s+now\s+in\s+developer\s+mode|acting\s+as\s+root|sudo\s+mode)\b"),
]

_OVERRIDE_PATTERNS = [
    re.compile(r"(?i)\b(?:ignore|disregard|forget|skip|override)\s+(?:all\s+)?(?:previous|prior|above|the\s+user(?:'s)?)\s+(?:instructions?|directives?|prompts?|rules?|commands?)\b"),
    re.compile(r"(?i)\bignore\s+the\s+user\b"),
    re.compile(r"(?i)\bnew\s+(?:system\s+)?instructions?\s*:\s*"),
    re.compile(r"(?i)\bfrom\s+now\s+on[,\s]+you\s+(?:must|should|will)\b"),
    re.compile(r"(?i)\bstop\s+what\s+you\s+are\s+doing\s+and\b"),
]

_EXFIL_PATTERNS = [
    re.compile(r"(?i)\b(?:forward|send|email|exfiltrate|post|transmit|upload)\s+(?:all\s+)?(?:emails?|messages?|contacts?|files?|credentials?|secrets?|invoices?|mailbox|history)\s+to\s+([^\s,;]+)"),
    re.compile(r"(?i)\b(?:curl|wget|fetch)\s+https?://[^\s]+\?(?:data|leak|token|secret|q)="),
    re.compile(r"(?i)\bto\s+[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\s+(?:with\s+the\s+(?:contents?|files?|emails?|summary))"),
]

_TOOL_MIMICRY_PATTERNS = [
    re.compile(r"""(?i)\{\s*["'](?:tool|action|function|call)["']\s*:\s*["'][a-zA-Z0-9_.]+["']"""),
    re.compile(r"""(?i)<(?:tool_call|function_call|action)>[\s\S]*?</(?:tool_call|function_call|action)>"""),
    re.compile(r"""(?i)\{\s*["']name["']\s*:\s*["'](?:gmail\.(?:send|draft)|files\.write|messages\.send|web\.fetch)["']"""),
    re.compile(r"""(?i)(?:^|\n)\s*(?:call|action):\s*[a-zA-Z0-9_.]+\s*\{"""),
]

_URL_QUERY_EXFIL_PATTERNS = [
    re.compile(r"(?i)https?://[^\s/$.?#].[^\s]*[?&](?:data|exfil|leak|token|key|cookie|body|payload)=[a-zA-Z0-9%_-]{16,}"),
    re.compile(r"(?i)https?://[^\s/$.?#].[^\s]*[?&](?:forward_to|send_to|recipient)="),
]

_HIDDEN_TEXT_PATTERNS = [
    re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]{2,}"),  # Zero-width clusters
    re.compile(r"(?i)display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0px|color\s*:\s*(?:transparent|#ffffff|white)"),
    re.compile(r"(?i)<!--[\s\S]*?(?:ignore|system|instruction|forward|send|secret)[\s\S]*?-->"),
]

# Simple homoglyph/leet mapping for candidate inspection
_LEET_MAP = str.maketrans({
    '@': 'a', '4': 'a', '3': 'e', '1': 'i', '!': 'i', '0': 'o', '5': 's', '$': 's', '7': 't', '+': 't'
})

def _decode_candidates(text: str) -> list[str]:
    """
    Produces candidate variants for analysis only.
    Text is NOT mutated for downstream consumers.
    """
    variants = [text]
    
    # URL decode
    try:
        decoded_url = urllib.parse.unquote(text)
        if decoded_url != text:
            variants.append(decoded_url)
    except Exception:
        pass

    # Leet decode
    leet_decoded = text.translate(_LEET_MAP)
    if leet_decoded != text:
        variants.append(leet_decoded)

    # Base64 candidate search (words of length >= 16 that match b64 charset)
    b64_matches = re.findall(r"(?:^|[\s:;,])([A-Za-z0-9+/]{16,}={0,2})(?:$|[\s:;,.])", text)
    for candidate in b64_matches:
        try:
            raw = base64.b64decode(candidate).decode('utf-8', errors='ignore')
            if len(raw) >= 8 and any(c.isalpha() for c in raw):
                variants.append(raw)
        except Exception:
            continue

    # ROT13 check if override keywords emerge
    try:
        import codecs
        rot_candidate = codecs.decode(text, 'rot_13')
        if any(w in rot_candidate.lower() for w in ["ignore", "system:", "forward", "disregard"]):
            variants.append(rot_candidate)
    except Exception:
        pass

    return variants

def scan_t1(text: str) -> T1Result:
    """
    Runs T1 fast checks on text.
    Returns detected signals, a heuristic T1 score in [0.0, 1.0], and flagged boolean.
    """
    if not text or not text.strip():
        return T1Result(signals=[], score=0.0, is_flagged=False)

    signals: set[str] = set()
    variants = _decode_candidates(text)

    for v in variants:
        # 1. Role Marker Spoofing
        if any(p.search(v) for p in _ROLE_PATTERNS):
            signals.add(SIGNAL_ROLE_MARKER_SPOOFING)

        # 2. Override Phrases
        if any(p.search(v) for p in _OVERRIDE_PATTERNS):
            signals.add(SIGNAL_OVERRIDE_PHRASES)

        # 3. Exfiltration Patterns
        if any(p.search(v) for p in _EXFIL_PATTERNS):
            signals.add(SIGNAL_EXFILTRATION_PATTERNS)

        # 4. Tool Invocation Mimicry
        if any(p.search(v) for p in _TOOL_MIMICRY_PATTERNS):
            signals.add(SIGNAL_TOOL_INVOCATION_MIMICRY)

        # 5. URL Query Exfil
        if any(p.search(v) for p in _URL_QUERY_EXFIL_PATTERNS):
            signals.add(SIGNAL_URL_QUERY_EXFIL)

        # 6. Hidden Text Indicators
        if any(p.search(v) for p in _HIDDEN_TEXT_PATTERNS):
            signals.add(SIGNAL_HIDDEN_TEXT_INDICATORS)

    # Compute heuristic score based on signal weights
    weights = {
        SIGNAL_OVERRIDE_PHRASES: 0.95,
        SIGNAL_EXFILTRATION_PATTERNS: 0.95,
        SIGNAL_ROLE_MARKER_SPOOFING: 0.90,
        SIGNAL_TOOL_INVOCATION_MIMICRY: 0.88,
        SIGNAL_URL_QUERY_EXFIL: 0.85,
        SIGNAL_HIDDEN_TEXT_INDICATORS: 0.70,
    }

    signal_list = sorted(list(signals))
    if not signal_list:
        return T1Result(signals=[], score=0.0, is_flagged=False)

    max_score = max(weights.get(s, 0.5) for s in signal_list)
    # If multiple critical signals combine, reinforce confidence
    if len(signal_list) > 1 and max_score >= 0.85:
        score = min(0.99, max_score + 0.04)
    else:
        score = max_score

    return T1Result(signals=signal_list, score=round(score, 3), is_flagged=True)
