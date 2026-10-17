"""Coverage for BE/FE requests: BE-to-SEC2-01/02, backend-to-sec2-01, fe-to-be items 7-10."""
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException

import admin_api.routes as routes
from contracts.models import (BuildPolicyRequest, CheckActionRequest, ConfigProposalRequest, Provenance,
                              ReviewDecisionRequest, ScanField, ScanRequest, SourceType, Trust)
from eva_guard.api import Guard
from eval.store import EvalStore

P = lambda t: Provenance(source_id="s", source_type=SourceType.EMAIL if t == Trust.UNTRUSTED else SourceType.USER_REQUEST, trust=t)


@pytest.fixture
def g(tmp_path):
    g = Guard(db_url=f"sqlite:///{tmp_path}/g.db")
    routes._guard_singleton = g
    return g


def _web_policy(g):
    g.build_task_policy(BuildPolicyRequest(task_id="w", user_id="u", user_role="user",
                                           user_request="Search the web for invoice fraud guidance",
                                           available_tools=["web.search", "web.fetch"]))


def test_web_search_query_provenance(g):
    _web_policy(g)
    chk = lambda prov: g.check_action(CheckActionRequest(task_id="w", call_id="c", tool="web.search", args={"query": "q"}, read_only=True, arg_provenance=prov))
    assert chk({"query": P(Trust.USER)}).decision == "ALLOW"
    assert chk({}).decision == "ALLOW"  # no provenance supplied: same convention as rule 7 (only declared-untrusted args are escalated)
    r = chk({"query": P(Trust.UNTRUSTED)})
    assert r.decision == "REQUIRE_APPROVAL" and "UNTRUSTED_ARG_PROVENANCE" in [x.value for x in r.reasons]


def test_eval_run_shape_for_fe(g):
    st = EvalStore(g._audit.db_path)
    rid = st.save_run("scenarios", {"profiles": {}}, n=42, failures=[{"scenario": "S1"}] * 25, config={"env": "mock"}, seed=3)
    row = routes.list_eval_runs(kind=None, limit=10, offset=0)[0]
    for k in ("id", "created_at", "profile", "config_version", "split", "seed", "metrics", "failed_traces"):
        assert k in row
    assert row["config_version"] == 1 and row["seed"] == 3 and len(row["failed_traces"]) == 20 and row["failed_count"] == 25
    assert len(routes.get_eval_run(rid)["failed_traces"]) == 20 or routes.get_eval_run(rid)["failures"]


def test_proposals_list_and_reject(g):
    p1 = routes.propose_config_change(ConfigProposalRequest(proposed_by="a", changes={"align_enabled": False}, justification="x")).proposal_id
    p2 = routes.propose_config_change(ConfigProposalRequest(proposed_by="a", changes={"t3_enabled": False}, justification="y")).proposal_id
    assert {p["proposal_id"] for p in routes.list_config_proposals(status="pending")} == {p1, p2}
    out = routes.reject_config_proposal(p1, rejecter_id="b")
    assert out.status == "rejected" and g.get_config()["align_enabled"] is True
    with pytest.raises(HTTPException):
        routes.approve_config_proposal(p1, approver_id="c")  # cannot approve a rejected proposal
    with pytest.raises(HTTPException):
        routes.reject_config_proposal(p1, rejecter_id="c")
    routes.approve_config_proposal(p2, approver_id="b")
    assert [p["proposal_id"] for p in routes.list_config_proposals(status="pending")] == []
    assert any(e.type == "config.rejected" for e in g._audit.query(task_id=p1))


def test_quarantined_or_held_scan_enters_review_queue_and_decision_never_grants_authority(g):
    class Det:
        def scan(self, req):
            from contracts.models import DetSummary, ScanResponse
            return ScanResponse(disposition="held", fields=[], det_summary=DetSummary(t1_signals=["override"]), tier2_available=False, event_id="evt-held-1")
        def is_tier2_available(self): return False
    g._det_pipeline = Det()
    g.scan_tool_result(ScanRequest(task_id="t", call_id="c", tool="gmail.read", fields=[ScanField(name="body", text="SECRET RAW TEXT", provenance=P(Trust.UNTRUSTED))]))
    q = routes.list_review_queue(status="pending")
    assert [i["id"] for i in q] == ["evt-held-1"] and "SECRET RAW TEXT" not in str(q)
    out = routes.submit_review_decision("evt-held-1", ReviewDecisionRequest(reviewer_id="spoofed", decision="approved", notes="n"), admin_id="real-admin")
    assert out["item"]["reviewer_id"] == "real-admin" and out["item"]["status"] == "decided"
    assert routes.list_review_queue(status="pending") == []


def test_templates_read_only(g):
    names = [t["template_id"] for t in routes.list_templates()]
    assert "send_email_to_named_recipient" in names and routes.get_template("file_work")["template_id"] == "file_work"
    with pytest.raises(HTTPException) as e:
        routes.get_template("nope")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        routes.templates_not_editable()
    assert e.value.status_code == 405


def test_guard_database_url_env_is_honoured(tmp_path, monkeypatch):
    monkeypatch.delenv("GUARD_DB_PATH", raising=False)
    monkeypatch.setenv("GUARD_DATABASE_URL", f"sqlite:///{tmp_path}/via_url.db")
    g = Guard()
    assert Path(g._audit.db_path) == tmp_path / "via_url.db" and EvalStore().db_path == tmp_path / "via_url.db"


def test_dockerfile_matches_compose_expectations():
    d = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert "--port\", \"8100\"" in d and "service.main:app" in d and "COPY contracts" in d and "USER eva-guard" in d
    assert "agent/backend" not in d.replace("agent/backend sources", "")
