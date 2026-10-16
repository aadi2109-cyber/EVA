"""
Web tools: web.search and web.fetch.
Enforces size caps, timeouts, text extraction, no cookies, and mock isolation in eval mode.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel, Field

from contracts.models import Provenance, ScanField, SourceType, Trust
from app.config import settings
from app.tools.base import ToolContext, ToolExecutionResult
from env.mock.state import state as mock_state

MAX_WEB_BYTES = 512 * 1024  # 512 KB cap


def _extract_text_from_html(html: str) -> str:
    clean = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


# ------------------------------------------------------------------------------
# 1. web.search
# ------------------------------------------------------------------------------
class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Web search query")


class WebSearchTool:
    name = "web.search"
    description = "Search the web for information."
    args_schema = WebSearchArgs
    read_only = True
    risk_class = "read"
    destination_args = []

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = WebSearchArgs.model_validate(args)

        # In eval or mock environment, return simulated search results
        results = [
            {
                "title": f"Result 1 for {validated.query}",
                "url": "https://example.com/docs/agent-safety",
                "snippet": "EVA Agent uses deterministic policy gateways and sanitizes untrusted input.",
            },
            {
                "title": f"Result 2 for {validated.query}",
                "url": "https://example.com/docs/architecture",
                "snippet": "Comprehensive multi-agent architecture with in-process and HTTP guard clients.",
            },
        ]

        summary_text = "\n".join([f"[{r['title']}]({r['url']}): {r['snippet']}" for r in results])
        scan_field = ScanField(
            name="search_results",
            text=summary_text,
            provenance=Provenance(
                source_id=f"web-search:{validated.query}",
                source_type=SourceType.WEB,
                field="search_results",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"results": results},
            text_summary=summary_text,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 2. web.fetch
# ------------------------------------------------------------------------------
class WebFetchArgs(BaseModel):
    url: str = Field(..., description="URL of the web page to fetch")


class WebFetchTool:
    name = "web.fetch"
    description = "Fetch and extract text content from a web URL."
    args_schema = WebFetchArgs
    read_only = True
    risk_class = "read"
    destination_args = ["url"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = WebFetchArgs.model_validate(args)
        parsed = urlparse(validated.url)

        # Record outbound HTTP request in observable state for state verifier
        mock_state.record_http_request(validated.url)

        # In APP_ENV=eval or when target is mock web server, serve local mock pages
        if settings.APP_ENV == "eval" or "mock" in validated.url or "localhost" in validated.url or "example.com" in validated.url:
            candidates = [
                Path("env/mock/web"),
                Path(__file__).resolve().parents[4] / "env" / "mock" / "web",
                Path(__file__).resolve().parents[3] / "env" / "mock" / "web",
            ]
            mock_web_dir = next((c for c in candidates if c.exists()), Path("env/mock/web"))

            target_filename = "attacker.html" if "attacker" in validated.url else "index.html"
            mock_file = mock_web_dir / target_filename
            if mock_file.exists():
                html = mock_file.read_text(encoding="utf-8", errors="replace")
            else:
                html = f"<html><body><h1>Mock Content for {validated.url}</h1><p>Sample documentation.</p></body></html>"
            extracted_text = _extract_text_from_html(html)
        else:
            # Live web fetch with timeout and size cap
            try:
                async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                    resp = await client.get(validated.url, headers={"User-Agent": "EVA-Agent/1.0"})
                    if resp.status_code >= 400:
                        raise ValueError(f"HTTP request to {validated.url} returned status {resp.status_code}")
                    if len(resp.content) > MAX_WEB_BYTES:
                        raise ValueError(f"Content length exceeds {MAX_WEB_BYTES} bytes limit")
                    extracted_text = _extract_text_from_html(resp.text)
            except Exception as e:
                raise RuntimeError(f"Failed to fetch URL {validated.url}: {e}") from e

        scan_field = ScanField(
            name="page_content",
            text=extracted_text,
            provenance=Provenance(
                source_id=validated.url,
                source_type=SourceType.WEB,
                field="page_content",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"url": validated.url, "content_length": len(extracted_text)},
            text_summary=extracted_text[:500],
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()
