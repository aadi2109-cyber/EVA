"""
HTML -> text extraction shared by gmail.read and web.fetch.

Visible text is returned first. Text that a human would not see (display:none,
visibility:hidden, zero font-size, opacity:0, `hidden` attribute, aria-hidden,
off-screen positioning, HTML comments) is NOT dropped: it is appended in labelled
sections so the security scanner sees everything the model could be exposed to.
<script>/<style> bodies are never rendered text and are omitted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_SKIP = {"script", "style", "template"}
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none"
    r"|visibility\s*:\s*hidden"
    r"|font-size\s*:\s*0(?:\.0+)?\s*(?:px|pt|em|rem|%)?\s*(?:;|$|!)"
    r"|opacity\s*:\s*0(?:\.0+)?\s*(?:;|$|!)"
    r"|(?:left|top|text-indent)\s*:\s*-\d{3,}"
    r"|(?:^|;)\s*(?:width|height|max-height|max-width)\s*:\s*0(?:px)?\s*(?:;|$)",
    re.IGNORECASE,
)


@dataclass
class ExtractedHtml:
    visible: str = ""
    hidden: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = [self.visible]
        if self.comments:
            parts.append("[HTML_COMMENT: " + " | ".join(self.comments) + "]")
        if self.hidden:
            parts.append("[HIDDEN_TEXT: " + " | ".join(self.hidden) + "]")
        return "\n\n".join(p for p in parts if p)

    def hidden_only(self) -> str:
        parts = []
        if self.comments:
            parts.append("[HTML_COMMENT: " + " | ".join(self.comments) + "]")
        if self.hidden:
            parts.append("[HIDDEN_TEXT: " + " | ".join(self.hidden) + "]")
        return "\n\n".join(parts)


def _is_hidden(attrs: list[tuple[str, str | None]]) -> bool:
    d = {k.lower(): (v or "") for k, v in attrs}
    if "hidden" in d:
        return True
    if d.get("aria-hidden", "").lower() == "true":
        return True
    style = d.get("style", "")
    return bool(style and _HIDDEN_STYLE.search(style))


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []  # (tag, opened_hidden_or_skip)
        self.hidden_depth = 0
        self.skip_depth = 0
        self.visible: list[str] = []
        self.hidden: list[str] = []
        self.comments: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _VOID:
            if tag == "br":
                (self.hidden if self.hidden_depth else self.visible).append("\n")
            return
        hid = tag not in _SKIP and _is_hidden(attrs)
        skip = tag in _SKIP
        self.stack.append((tag, hid or skip))
        if hid:
            self.hidden_depth += 1
        if skip:
            self.skip_depth += 1
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            (self.hidden if self.hidden_depth else self.visible).append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                while len(self.stack) > i:
                    t, flagged = self.stack.pop()
                    if flagged:
                        if t in _SKIP:
                            self.skip_depth -= 1
                        else:
                            self.hidden_depth -= 1
                break

    def handle_data(self, data):
        if self.skip_depth:
            return
        (self.hidden if self.hidden_depth else self.visible).append(data)

    def handle_comment(self, data):
        text = data.strip()
        if text:
            self.comments.append(re.sub(r"\s+", " ", text))


def _clean(chunks: list[str]) -> str:
    text = "".join(chunks)
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_html(html: str) -> ExtractedHtml:
    if not html:
        return ExtractedHtml()
    p = _Extractor()
    try:
        p.feed(html)
        p.close()
    except Exception:  # malformed markup must never crash a tool; fall back to tag stripping
        stripped = re.sub(r"<[^>]*>", " ", html)
        return ExtractedHtml(visible=re.sub(r"\s+", " ", stripped).strip())
    hidden = [h for h in (re.sub(r"\s+", " ", _clean([c])) for c in _split_hidden(p.hidden)) if h]
    return ExtractedHtml(visible=_clean(p.visible), hidden=hidden, comments=p.comments)


def _split_hidden(chunks: list[str]) -> list[str]:
    joined = _clean(chunks)
    return [b for b in re.split(r"\n{2,}", joined)] if joined else []


def extract_html_text_with_hidden(html: str) -> str:
    """Visible text plus labelled hidden/comment sections (nothing silently dropped)."""
    return extract_html(html).render()


def looks_like_html(text: str) -> bool:
    return bool(re.search(r"<\s*(!--|/?[a-zA-Z][a-zA-Z0-9]*[\s>/])", text or ""))
