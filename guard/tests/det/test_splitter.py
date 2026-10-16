import pytest
from hypothesis import given, strategies as st
from eva_guard.det.splitter import split_sentences

def test_split_simple_sentences():
    text = "First sentence. Second sentence! Third sentence? Fourth sentence."
    spans = split_sentences(text)
    assert len(spans) == 4
    for span in spans:
        # Invariant check
        assert text[span.start:span.end] == span.text

def test_split_with_abbreviations():
    text = "Dr. Smith met with Mr. Jones at 10.30 a.m. to discuss Invoice #1234. Payment is due Friday."
    spans = split_sentences(text)
    # The first sentence should not be split at Dr. or Mr.
    assert len(spans) == 2
    assert "Dr. Smith" in spans[0].text
    assert "Payment is due Friday." in spans[1].text
    for span in spans:
        assert text[span.start:span.end] == span.text

def test_split_with_newlines_and_bullets():
    text = "Task list:\n- Check emails\n- Review invoices\nAll done."
    spans = split_sentences(text)
    assert len(spans) >= 3
    for span in spans:
        assert text[span.start:span.end] == span.text

def test_split_long_sentence_chunking():
    # Long text without punctuation
    text = "word " * 200  # 1000 characters
    spans = split_sentences(text, max_sentence_len=200)
    assert len(spans) > 1
    for span in spans:
        assert len(span.text) <= 250
        assert text[span.start:span.end] == span.text

@given(st.text(max_size=500))
def test_split_hypothesis_invariants(text):
    spans = split_sentences(text)
    prev_end = 0
    for span in spans:
        assert span.start >= prev_end
        assert span.end <= len(text)
        assert span.start < span.end
        assert text[span.start:span.end] == span.text
        prev_end = span.end
