# EVA Guard

Security layer for the EVA agent: content-side detection (`eva_guard/det`) and authority-side policy, gateway, approvals and audit.

Dev setup (from the repo root):

    pip install -e "./guard[dev,bench]"
    cd guard && PYTHONPATH=..:. python -m pytest -q        # PowerShell: $env:PYTHONPATH = "..;."

AgentDojo: see `eval/det/agentdojo_live.py` and `eval/det/AGENTDOJO_RESULTS.md`.

Modular security guardrail system for tool-using AI agent execution.
Provides deterministic policy gates (Sec-1) and content defense pipelines (Sec-2).
