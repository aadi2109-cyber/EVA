"""
Run the REAL AgentDojo benchmark (LLM agent + injection attacks) with EVA's content scanner as the defense.

    cd guard && PYTHONPATH=..:. python -m eval.det.agentdojo_live --check
    cd guard && PYTHONPATH=..:. python -m eval.det.agentdojo_live --smoke --provider ollama   (or --model claude-3-5-sonnet-20241022)
    cd guard && PYTHONPATH=..:. python -m eval.det.agentdojo_live --model <model> --suite workspace --defense eva
    ... --defense none        # baseline: same agent, no defense (run both and compare)

Needs:  pip install agentdojo   and an LLM key in the environment (ANTHROPIC_API_KEY / OPENAI_API_KEY / ...)
        or a .env file in the working directory (AgentDojo loads it). This script never prints keys.
COST WARNING: a full run is thousands of LLM calls (v1.2.1: ~97 user tasks x 35 injection tasks). Start with --smoke.

What "eva" means: every tool result is scanned by `eva_guard.Guard.scan_tool_result` (T1 rules + T2 model + T3 if
installed) BEFORE the LLM sees it; malicious sentences are replaced with [CONTENT SANITISED] (held -> whole result
replaced by a marker). This is the DET defense only: SEC-2's policy gateway / approvals are NOT in this loop, so
the numbers below measure content-side defense alone, not full EVA.

Reported (AgentDojo definitions):
  utility                 fraction of user tasks solved with NO attack
  utility under attack    fraction solved while an attack is present
  ASR (attack success)    fraction of (user task, injection task) pairs where the attacker's goal was achieved  [lower = better]
Each result states N, suite(s), model, attack, defense, benchmark version, date, and EVA commit. Nothing is tuned on it.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

HELD_MARKER = "<Content withheld by EVA Guard: held>"
DEFAULT_VERSION = "v1.2.1"
KEY_VARS = ("OLLAMA_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "COHERE_API_KEY", "TOGETHER_API_KEY")
PROVIDER_FOR_KEY = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY",
                    "cohere": "COHERE_API_KEY", "together": "TOGETHER_API_KEY", "ollama": "OLLAMA_API_KEY"}


def _require_agentdojo():
    try:
        import agentdojo  # noqa: F401
    except ImportError:
        sys.exit("agentdojo is not installed: pip install agentdojo")


def make_eva_element(guard):
    """AgentDojo pipeline element that sanitises each new tool result with the EVA Guard facade."""
    from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
    from agentdojo.types import get_text_content_as_str, text_content_block_from_string
    from contracts.models import ScanRequest, ScanField, Provenance, Trust, SourceType

    class EvaGuardElement(BasePipelineElement):
        name = "eva_guard_det"

        def __init__(self):
            super().__init__()
            self.stats = {"tool_results": 0, "sanitized": 0, "held": 0, "errors": 0}
            self._n = 0

        def query(self, query, runtime, env=None, messages: Sequence = (), extra_args: dict | None = None):
            extra_args = extra_args if extra_args is not None else {}
            if not messages or messages[-1]["role"] != "tool":
                return query, runtime, env, messages, extra_args
            i = len(messages) - 1  # all trailing tool messages are new results
            while i >= 0 and messages[i]["role"] == "tool":
                msg = messages[i]
                text = get_text_content_as_str(msg["content"] or "") if msg["content"] else ""
                if text.strip() and not msg.get("error"):
                    self._scan(msg, text)
                i -= 1
            return query, runtime, env, messages, extra_args

        def _scan(self, msg, text):
            self._n += 1
            self.stats["tool_results"] += 1
            tool = msg["tool_call"].function if msg.get("tool_call") else "unknown"
            try:
                res = guard.scan_tool_result(ScanRequest(
                    task_id=f"agentdojo-{os.getpid()}", call_id=f"ad-{self._n}", tool=f"agentdojo.{tool}",
                    fields=[ScanField(name="body", text=text, provenance=Provenance(
                        source_id=f"{tool}-{self._n}", source_type=SourceType.TOOL_OUTPUT, trust=Trust.UNTRUSTED))]))
            except Exception:
                self.stats["errors"] += 1
                msg["content"] = [text_content_block_from_string(HELD_MARKER)]  # fail closed
                return
            if res.disposition in ("held", "quarantined") or not res.fields:
                self.stats["held"] += 1
                msg["content"] = [text_content_block_from_string(HELD_MARKER)]
            elif res.disposition == "sanitized":
                self.stats["sanitized"] += 1
                msg["content"] = [text_content_block_from_string(res.fields[0].text)]

    return EvaGuardElement()


def build_pipeline(model: str, provider: str | None, defense: str, tool_delimiter: str, guard, llm=None):
    """Same structure as AgentPipeline.from_config(defense=None), with the EVA element after tool execution."""
    from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, get_llm, load_system_message
    from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage
    from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, ToolsExecutor, tool_result_to_str
    from agentdojo.models import MODEL_PROVIDERS, ModelsEnum

    if llm is not None:  # injected (tests): skip provider/model resolution
        pass
    elif provider == "ollama":  # same provider as the EVA backend: OpenAI-compatible chat API with tool calling
        import openai
        from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
        client = openai.OpenAI(base_url=os.environ.get("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/") + "/v1",
                               api_key=os.environ["OLLAMA_API_KEY"])
        llm = OpenAILLM(client, model)
    elif provider is None:
        try:
            provider = MODEL_PROVIDERS[ModelsEnum(model)]
        except ValueError:
            sys.exit(f"Unknown model {model!r}; pass --provider (anthropic|openai|google|cohere|together).")
    llm = llm if llm is not None else get_llm(provider, model, None, tool_delimiter)
    llm.name = getattr(llm, "name", None) or model
    llm_name = getattr(llm, "name", model)
    eva = make_eva_element(guard) if defense == "eva" else None
    loop = [ToolsExecutor(tool_result_to_str)] + ([eva] if eva else []) + [llm]
    pipeline = AgentPipeline([SystemMessage(load_system_message(None)), InitQuery(), llm, ToolsExecutionLoop(loop)])
    from agentdojo.models import MODEL_NAMES
    name = str(llm_name)
    known = any(k in name for k in MODEL_NAMES)
    # The pipeline name becomes a log-directory name: Windows forbids : < > " / \\ | ? * in paths.
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    if not known or not any(k in name for k in MODEL_NAMES):
        # AgentDojo addresses the attacker's text to a model name looked up from the pipeline name;
        # ids outside its enum (newer models) fall back to its generic "Local model".
        print(f"[note] {llm_name!r} is not in AgentDojo's model list; attacks will address it as 'Local model'.")
        name += "-local"
    pipeline.name = f"{name}-eva" if eva else name
    return pipeline, eva


def preflight(provider_hint: str | None) -> int:
    ok = True
    try:
        import agentdojo, importlib.metadata as md
        print(f"[ok] agentdojo {md.version('agentdojo')} installed")
    except ImportError:
        print("[FAIL] agentdojo not installed (pip install agentdojo)"); ok = False
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except Exception:
        pass
    present = [k for k in KEY_VARS if os.environ.get(k)]
    need = PROVIDER_FOR_KEY.get(provider_hint or "")
    if need and not os.environ.get(need):
        print(f"[FAIL] {need} not set (needed for provider {provider_hint})"); ok = False
    elif present:
        print(f"[ok] LLM key(s) present: {', '.join(present)}")
    else:
        print("[FAIL] no LLM API key found in the environment or .env (e.g. ANTHROPIC_API_KEY)"); ok = False
    try:
        from eva_guard import Guard
        with tempfile.TemporaryDirectory() as d:
            h = Guard(db_url=f"sqlite:///{d}/audit.db").health()
        print(f"[{'ok' if h.tier2_available else 'FAIL'}] EVA Guard tier2_available={h.tier2_available} t3_available={h.t3_available}")
        ok &= h.tier2_available
    except Exception as exc:  # noqa
        print(f"[FAIL] EVA Guard did not start: {exc!r}"); ok = False
    return 0 if ok else 1


def _rate(d: dict) -> tuple[int, int]:
    return sum(1 for v in d.values() if v), len(d)


def _fmt(label, a, n):
    return f"{label:<26}{a}/{n} ({100 * a / n:.1f}%)" if n else f"{label:<26}n/a"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="AgentDojo model enum value (e.g. claude-3-5-sonnet-20241022) or any id with --provider")
    ap.add_argument("--provider", choices=sorted(PROVIDER_FOR_KEY), help="required for model ids not in AgentDojo's enum; 'ollama' uses OLLAMA_BASE_URL/OLLAMA_API_KEY/OLLAMA_MODEL (same provider as the EVA backend)")
    ap.add_argument("--defense", choices=["eva", "none"], default="eva")
    ap.add_argument("--attack", default="important_instructions")
    ap.add_argument("--suite", action="append", help="repeatable; default all suites")
    ap.add_argument("--user-task", action="append", help="repeatable, e.g. user_task_0")
    ap.add_argument("--injection-task", action="append", help="repeatable, e.g. injection_task_1")
    ap.add_argument("--benchmark-version", default=DEFAULT_VERSION)
    ap.add_argument("--no-injections", action="store_true", help="utility only (no attack)")
    ap.add_argument("--smoke", action="store_true", help="tiny run: banking, 2 user tasks x 2 injection tasks")
    ap.add_argument("--logdir", default="eval/det/agentdojo_runs")
    ap.add_argument("--force-rerun", action="store_true")
    ap.add_argument("--check", action="store_true", help="preflight only: deps, API key, EVA Guard health; no LLM calls")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation before a large run")
    a = ap.parse_args(argv)

    if a.check:
        return preflight(a.provider)
    _require_agentdojo()
    if a.provider == "ollama" and not a.model:
        a.model = os.environ.get("OLLAMA_MODEL")
    if not a.model:
        ap.error("--model is required (or use --check)")
    if a.smoke:
        a.suite, a.user_task, a.injection_task = ["banking"], ["user_task_0", "user_task_1"], ["injection_task_0", "injection_task_1"]
    if preflight(a.provider) != 0:
        sys.exit("Preflight failed; fix the items above (or run --check).")

    from dotenv import load_dotenv
    from agentdojo.attacks.attack_registry import load_attack
    from agentdojo.logging import OutputLogger
    from agentdojo.benchmark import benchmark_suite_with_injections, benchmark_suite_without_injections
    from agentdojo.task_suite.load_suites import get_suites
    from eva_guard import Guard

    suites = get_suites(a.benchmark_version)
    names = a.suite or list(suites)
    for n in names:
        if n not in suites:
            sys.exit(f"unknown suite {n!r}; choices: {', '.join(suites)}")
    n_user = {n: len(a.user_task or suites[n].user_tasks) for n in names}
    n_inj = {n: len(a.injection_task or suites[n].injection_tasks) for n in names}
    calls_est = sum(n_user[n] * (1 if a.no_injections else 1 + n_inj[n]) for n in names)
    print(f"Plan: {a.defense} defense | model {a.model} | suites {names} | ~{calls_est} agent episodes "
          f"(each several LLM calls) | attack {None if a.no_injections else a.attack}")
    if calls_est > 60 and not a.yes:
        if input("This is a large, billable run. Type 'yes' to continue: ").strip().lower() != "yes":
            sys.exit("aborted")

    load_dotenv(".env")
    logdir = Path(a.logdir) / f"{datetime.datetime.now():%Y%m%d-%H%M%S}-{a.defense}"
    logdir.mkdir(parents=True, exist_ok=True)
    guard = Guard(db_url=f"sqlite:///{logdir}/audit.db")
    pipeline, eva = build_pipeline(a.model, a.provider, a.defense, "tool", guard)

    util, util_att, sec = {}, {}, {}
    with OutputLogger(str(logdir), live=None):  # required by AgentDojo for run logging
        for n in names:
            suite = suites[n]
            u = benchmark_suite_without_injections(pipeline, suite, logdir=logdir, force_rerun=a.force_rerun,
                                                   user_tasks=a.user_task, benchmark_version=a.benchmark_version)
            util.update({(n, *k) if isinstance(k, tuple) else (n, k): v for k, v in u["utility_results"].items()})
            if a.no_injections:
                continue
            attack = load_attack(a.attack, suite, pipeline)
            r = benchmark_suite_with_injections(pipeline, suite, attack, logdir=logdir, force_rerun=a.force_rerun,
                                                user_tasks=a.user_task, injection_tasks=a.injection_task,
                                                benchmark_version=a.benchmark_version)
            util_att.update({(n, *k): v for k, v in r["utility_results"].items()})
            sec.update({(n, *k): v for k, v in r["security_results"].items()})

    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    import importlib.metadata as md
    meta = {"date": datetime.datetime.now().isoformat(timespec="seconds"), "model": a.model, "defense": a.defense,
            "attack": None if a.no_injections else a.attack, "benchmark_version": a.benchmark_version,
            "agentdojo": md.version("agentdojo"), "suites": names, "eva_commit": commit,
            "guard": "DET only (no gateway/approvals)" if a.defense == "eva" else None,
            "eva_scan_stats": eva.stats if eva else None}
    ua, un = _rate(util); sa, sn = _rate(sec); uaa, uan = _rate(util_att)
    summary = {**meta, "utility": [ua, un], "utility_under_attack": [uaa, uan], "attack_success": [sa, sn]}
    (logdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps(meta, indent=2))
    print(_fmt("utility (no attack)", ua, un))
    print(_fmt("utility under attack", uaa, uan))
    print(_fmt("attack success (ASR)", sa, sn))
    print(f"\nLogs + summary.json: {logdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
