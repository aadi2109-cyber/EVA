"""Live smoke check for the Ollama integration (never prints the key).

    python -m app.eval.check_live

Checks, in order: key/model/base loaded by the app settings; chat is AUTHORISED (a 200 from /api/tags
proves nothing: that listing is public); the model can emit a tool call; the web-search endpoint answers.
Exit code 0 only if every check passes.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import settings
from app.model import ModelEventType, ModelProviderError, OllamaProvider
from app.tools.web_search import OllamaSearchProvider, SearchError

TOOLS = [{"type": "function", "function": {
    "name": "web.search", "description": "Search the web for current information.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}]


def _line(ok: bool, name: str, detail: str) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


async def main() -> int:
    key = settings.OLLAMA_API_KEY
    print(f"settings: base={settings.OLLAMA_BASE_URL} model={settings.OLLAMA_MODEL} key_length={len(key)} "
          f"(a cloud key is 57 chars: 32 + '.' + 24)")
    results = [_line(bool(key), "key loaded", "set" if key else "EMPTY: put OLLAMA_API_KEY in env/.env and restart")]
    p = OllamaProvider()

    try:
        evs = [e async for e in p.step([{"role": "user", "content": "Reply with exactly one word: ok"}])]
        results.append(_line(True, "chat authorised", f"reply={''.join(e.text for e in evs)[:40]!r}"))
    except ModelProviderError as e:
        hint = {"401": "key rejected: create a NEW key at ollama.com and replace it",
                "404": "model name not found: use e.g. gpt-oss:20b (no 'openai/' prefix, no '-cloud' suffix)"}
        h = next((v for k, v in hint.items() if f"status {k}" in str(e)), "")
        results.append(_line(False, "chat authorised", f"{e} {('-> ' + h) if h else ''}"))
        print("  (skipping the tool-call check: chat does not work)")
    else:
        try:
            evs = [e async for e in p.step(
                [{"role": "user", "content": "Use the web.search tool to find the latest stable Python release."}], TOOLS)]
            calls = [e for e in evs if e.type == ModelEventType.TOOL_CALL]
            results.append(_line(bool(calls), "model calls a tool on its own",
                                 f"{calls[0].tool_name}({calls[0].tool_args})" if calls else "answered in text without calling the tool"))
        except ModelProviderError as e:
            results.append(_line(False, "model calls a tool on its own", str(e)))

    try:
        r = await OllamaSearchProvider().search("Ollama web search API", 2)
        results.append(_line(bool(r), "web search endpoint", f"{len(r)} results, first: {r[0].url if r else '-'}"))
    except SearchError as e:
        results.append(_line(False, "web search endpoint", str(e)))

    print("RESULT:", "ALL PASS" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
