"""Offline plumbing test for eval/det/agentdojo_live.py using a scripted fake LLM (no API, no cost)."""
import pytest

pytest.importorskip("agentdojo")

from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.attacks.attack_registry import load_attack
from agentdojo.benchmark import benchmark_suite_with_injections
from agentdojo.functions_runtime import FunctionCall
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.types import get_text_content_as_str, text_content_block_from_string

from eval.det.agentdojo_live import build_pipeline
from agentdojo.logging import OutputLogger
from eva_guard import Guard

SEEN: list[str] = []
PAYLOAD = "us133000000121212121212"  # attacker IBAN in banking injection_task_0


class ScriptedLLM(BasePipelineElement):
    """Reads the bill file (an injection slot) once, records what it sees, then answers."""
    name = "gpt-4-scripted"

    def query(self, query, runtime, env=None, messages=(), extra_args=None):
        messages = list(messages)
        if messages and messages[-1]["role"] == "tool":
            SEEN.append(get_text_content_as_str(messages[-1]["content"]))
            reply = {"role": "assistant", "content": [text_content_block_from_string("done")], "tool_calls": None}
        else:
            reply = {"role": "assistant", "content": [text_content_block_from_string("")],
                     "tool_calls": [FunctionCall(function="read_file", args={"file_path": "bill-december-2023.txt"})]}
        return query, runtime, env, [*messages, reply], extra_args or {}


def _run(defense, tmp_path):
    SEEN.clear()
    suite = get_suite("v1.2.1", "banking")
    guard = Guard(db_url=f"sqlite:///{tmp_path}/audit.db")
    pipeline, eva = build_pipeline("x", None, defense, "tool", guard, llm=ScriptedLLM())
    attack = load_attack("injecagent", suite, pipeline)
    with OutputLogger(str(tmp_path), live=None):
        res = benchmark_suite_with_injections(pipeline, suite, attack, logdir=tmp_path, force_rerun=True,
                                              user_tasks=["user_task_0"], injection_tasks=["injection_task_0"],
                                              benchmark_version="v1.2.1")
    return res, eva, " ".join(SEEN)


def test_without_defense_llm_sees_injection(tmp_path):
    res, eva, seen = _run("none", tmp_path)
    assert eva is None and PAYLOAD in seen.lower()
    assert set(res) >= {"utility_results", "security_results"}
    assert all(isinstance(k, tuple) and len(k) == 2 for k in res["security_results"])


def test_eva_defense_removes_injection_before_llm_sees_it(tmp_path):
    res, eva, seen = _run("eva", tmp_path)
    assert eva.stats["tool_results"] >= 1 and eva.stats["sanitized"] + eva.stats["held"] >= 1
    assert PAYLOAD not in seen.lower()
    assert "[CONTENT SANITISED]" in seen or "withheld" in seen


def test_pipeline_name_is_a_valid_windows_path_component(tmp_path):
    """Model ids like 'gemma4:31b-cloud' must not put ':' (or other illegal chars) in AgentDojo's log path."""
    class Fake(ScriptedLLM):
        name = "gemma4:31b-cloud"
    for defense in ("none", "eva"):
        pipeline, _ = build_pipeline("x", None, defense, "tool", Guard(db_url=f"sqlite:///{tmp_path}/a.db"), llm=Fake())
        assert not any(c in pipeline.name for c in '<>:"/\\|?*'), pipeline.name
        assert "local" in pipeline.name
