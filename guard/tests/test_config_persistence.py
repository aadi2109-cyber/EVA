import pytest
from fastapi import HTTPException

import admin_api.routes as routes
from contracts.models import BuildPolicyRequest, ConfigProposalRequest
from eva_guard.api import Guard


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/c.db"


def _use(g):
    routes._guard_singleton = g


def _propose(changes, by="alice"):
    return routes.propose_config_change(ConfigProposalRequest(proposed_by=by, changes=changes, justification="t"))


def _send_policy(g, tid):
    return g.build_task_policy(BuildPolicyRequest(task_id=tid, user_id="u", user_role="user",
                                                  user_request="Email the report to bob@corp.com", available_tools=["gmail.send"]))


def test_pending_proposal_and_approved_config_survive_restart(url):
    g = Guard(db_url=url); _use(g)
    pid = _propose({"minimum_detector_posture": "tier1_ok_readonly"}).proposal_id
    g2 = Guard(db_url=url); _use(g2)  # restart while pending
    assert g2.get_config()["minimum_detector_posture"] == "tier2_required"
    with pytest.raises(HTTPException):
        routes.approve_config_proposal(pid, approver_id="alice")  # still four-eyes
    routes.approve_config_proposal(pid, approver_id="bob")
    g3 = Guard(db_url=url)  # restart after approval
    assert g3.get_config()["minimum_detector_posture"] == "tier1_ok_readonly" and g3.get_config()["version"] == 2
    hist = g3._store.config_history()
    assert [h["version"] for h in hist] == [2, 1] and hist[0]["approved_by"] == "bob" and hist[0]["changed_by"] == "alice"


def test_posture_floor_change_only_affects_new_policies_and_needs_second_admin(url):
    g = Guard(db_url=url); _use(g)
    before = _send_policy(g, "old")
    assert before.minimum_detector_posture == "tier2_required"
    pid = _propose({"minimum_detector_posture": "tier1_ok_readonly"}).proposal_id
    assert _send_policy(g, "mid").minimum_detector_posture == "tier2_required"  # proposal alone changes nothing
    routes.approve_config_proposal(pid, approver_id="bob")
    assert _send_policy(g, "new").minimum_detector_posture == "tier1_ok_readonly"
    assert Guard(db_url=url).build_task_policy(BuildPolicyRequest(task_id="old", user_id="u", user_role="user", user_request="x", available_tools=[])).minimum_detector_posture == "tier2_required"


def test_invalid_config_rejected(url):
    _use(Guard(db_url=url))
    for bad in ({"nope": 1}, {"minimum_detector_posture": "none"}, {"block_threshold": 5}, {"align_enabled": "yes"}):
        with pytest.raises(HTTPException) as e:
            _propose(bad)
        assert e.value.status_code == 422


def test_align_disabled_via_config_takes_effect_after_restart(url):
    g = Guard(db_url=url); _use(g)
    routes.approve_config_proposal(_propose({"align_enabled": False}).proposal_id, approver_id="bob")
    assert g._align.enabled is False and Guard(db_url=url)._align.enabled is False


def test_double_approval_rejected_and_review_queue_persists(url):
    g = Guard(db_url=url); _use(g)
    pid = _propose({"t3_enabled": False}).proposal_id
    routes.approve_config_proposal(pid, approver_id="bob")
    with pytest.raises(HTTPException):
        routes.approve_config_proposal(pid, approver_id="carol")
    from contracts.models import ReviewDecisionRequest
    routes.submit_review_decision("item-1", ReviewDecisionRequest(reviewer_id="r", decision="rejected", notes="n"))
    _use(Guard(db_url=url))
    assert [i["id"] for i in routes.list_review_queue()] == ["item-1"]


def test_reset_config_for_tests_restores_defaults_and_is_env_guarded(url, monkeypatch):
    g = Guard(db_url=url); _use(g)
    routes.approve_config_proposal(_propose({"align_enabled": False}).proposal_id, approver_id="bob")
    g.reset_config_for_tests()
    assert g.get_config() == Guard.DEFAULT_CONFIG and g._align.enabled is True
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(RuntimeError):
        g.reset_config_for_tests()
