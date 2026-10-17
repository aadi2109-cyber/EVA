"""The project supports Python >= 3.11. Newer interpreters (PEP 701, 3.12+) accept f-strings that
reuse the enclosing quote character; 3.11 raises SyntaxError. Catch that wherever the suite runs."""

from __future__ import annotations

import io
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git"}


def _quote_of(token_text: str) -> str:
    body = token_text.lstrip("rRbBfFuU")
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


def pep701_only_fstrings(source: str) -> list[int]:
    """Line numbers where a string literal inside an f-string reuses the f-string's own quote."""
    if sys.version_info < (3, 12):  # older tokenizers can't parse such code at all
        return []
    hits, stack = [], []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        name = tokenize.tok_name.get(tok.type, "")
        if name == "FSTRING_START":
            q = _quote_of(tok.string)
            if stack and stack[-1] == q:
                hits.append(tok.start[0])
            stack.append(q)
        elif name == "FSTRING_END":
            stack.pop()
        elif name == "STRING" and stack and _quote_of(tok.string) == stack[-1]:
            hits.append(tok.start[0])
    return hits


@pytest.mark.skipif(sys.version_info < (3, 12), reason="running on 3.11: the interpreter itself rejects it")
def test_detector_catches_the_original_bug():
    bad = '''x = f"{e['name']} ({'dir' if e['d'] else f'{e['size']} B'})"\n'''
    assert pep701_only_fstrings(bad) == [1]
    assert pep701_only_fstrings('''x = f"{e['name']} {a}"\n''') == []


@pytest.mark.skipif(sys.version_info < (3, 12), reason="running on 3.11: the interpreter itself rejects it")
def test_no_python_312_only_fstrings_in_repo():
    offenders = []
    for p in ROOT.rglob("*.py"):
        if SKIP_DIRS & set(p.parts):
            continue
        for line in pep701_only_fstrings(p.read_text(encoding="utf-8")):
            offenders.append(f"{p.relative_to(ROOT)}:{line}")
    assert not offenders, "f-string reuses its own quote (SyntaxError on Python 3.11): " + ", ".join(offenders)
