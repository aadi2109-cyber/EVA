"""Eval harness + regression tests for sandbox paths, write intent and draft handling."""
import tempfile
from pathlib import Path

import yaml

from contracts.models import BuildPolicyRequest, CheckActionRequest
from eva_guard.api import Guard
from eva_guard.gateway.gateway import is_sandbox_path
from eval import runner


def _guard():
    return Guard(db_url=f"sqlite:///{tempfile.mkdtemp()}/t.db")


def test_full_profile_meets_all_scenario_expectations():
    scenarios = yaml.safe_load(runner.SCENARIO_FILE.read_text())
    with tempfile.TemporaryDirectory() as d:
        results = [runner.run_scenario(sc, p, Path(d)) for sc in scenarios for p in runner.PROFILES]
    full = [r for r in results if r.profile == "full"]
    assert {r.id for r in full} == {f"S{i}" for i in range(1, 15)}
    assert all(r.expectations_met for r in full), [r.id for r in full if not r.expectations_met]
    assert sum(r.unauthorized_side_effects for r in full) == 0
    assert sum(r.unauthorized_side_effects for r in results if r.profile == "off") > 0


def test_sandbox_path_rejects_traversal_and_absolute():
    assert is_sandbox_path("workspace/a.txt")
    for bad in ["../x", "workspace/../../etc/passwd", "/etc/passwd", "~/.ssh/id_rsa", "C:\\x", "http://x/y"]:
        assert not is_sandbox_path(bad), bad


def test_file_read_traversal_denied_and_write_needs_intent():
    g = _guard()
    g.build_task_policy(BuildPolicyRequest(task_id="t", user_id="u", user_role="user",
                        user_request="Read workspace/notes.txt", available_tools=["files.read", "files.write"]))
    ok = g.check_action(CheckActionRequest(task_id="t", call_id="1", tool="files.read", args={"path": "workspace/notes.txt"}, read_only=True))
    bad = g.check_action(CheckActionRequest(task_id="t", call_id="2", tool="files.read", args={"path": "../../etc/passwd"}, read_only=True))
    wr = g.check_action(CheckActionRequest(task_id="t", call_id="3", tool="files.write", args={"path": "workspace/a", "content": "x"}, read_only=False))
    assert ok.decision == "ALLOW"
    assert bad.decision == "DENY" and "DESTINATION_NOT_ALLOWED" in [r.value for r in bad.reasons]
    assert wr.decision == "DENY" and "TOOL_PROHIBITED" in [r.value for r in wr.reasons]
