"""Property tests: the gateway never grants what the policy prohibits, and ALIGN can only downgrade."""
import tempfile

from hypothesis import HealthCheck, given, settings, strategies as st

from contracts.models import (AlignVerdict, BuildPolicyRequest, CheckActionRequest, Provenance, SourceType, Trust)
from eva_guard.api import Guard
from eva_guard.align import AlignClient
from eva_guard.gateway.gateway import TOOL_REGISTRY

WRITE_TOOLS = [t for t, m in TOOL_REGISTRY.items() if not m["read_only"]]
text = st.text(max_size=40)
arg_values = st.one_of(text, st.integers(), st.none(), st.lists(text, max_size=3), st.emails(), st.from_regex(r"https?://[a-z0-9.\-]+/[a-z]*", fullmatch=True))
args_st = st.dictionaries(st.sampled_from(["to", "subject", "body", "path", "content", "url", "query", "channel", "text", "message_id", "approval_id"]), arg_values, max_size=6)
prov_st = st.dictionaries(st.sampled_from(["to", "path", "url"]), st.sampled_from(list(Trust)).map(
    lambda t: Provenance(source_id="s", source_type=SourceType.EMAIL, trust=t)), max_size=3)
SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


def _guard(request: str, tools: list[str], align=None) -> Guard:
    g = Guard(db_url=f"sqlite:///{tempfile.mkdtemp()}/p.db")
    if align is not None:
        g._align = align
    g.build_task_policy(BuildPolicyRequest(task_id="t", user_id="u", user_role="user", user_request=request, available_tools=tools))
    return g


# One guard per module: building a Guard per example is slow and the gateway is stateless w.r.t. these checks.
_RO = _guard("Summarize my emails", ["gmail.search", "gmail.read", "gmail.send", "files.write", "messages.send", "gmail.draft"])


@SETTINGS
@given(tool=st.sampled_from(WRITE_TOOLS), args=args_st, prov=prov_st, read_only=st.booleans())
def test_prohibited_write_tools_never_allowed_or_approvable(tool, args, prov, read_only):
    r = _RO.check_action(CheckActionRequest(task_id="t", call_id="c", tool=tool, args=args, arg_provenance=prov, read_only=read_only))
    assert r.decision == "DENY"
    assert r.approval is None


@SETTINGS
@given(tool=st.text(max_size=20), args=args_st)
def test_unknown_tools_always_denied(tool, args):
    if tool in TOOL_REGISTRY:
        return
    r = _RO.check_action(CheckActionRequest(task_id="t", call_id="c", tool=tool, args=args, read_only=True))
    assert r.decision == "DENY"


@SETTINGS
@given(task=st.text(min_size=1, max_size=8).filter(lambda s: s != "t"), tool=st.sampled_from(list(TOOL_REGISTRY)), args=args_st)
def test_no_policy_means_deny(task, tool, args):
    r = _RO.check_action(CheckActionRequest(task_id=task, call_id="c", tool=tool, args=args, read_only=TOOL_REGISTRY[tool]["read_only"]))
    assert r.decision == "DENY"


ORDER = {"DENY": 0, "REQUIRE_APPROVAL": 1, "ALLOW": 2}


@SETTINGS
@given(verdict=st.sampled_from(["aligned", "misaligned", "uncertain", "unavailable"]),
       tool=st.sampled_from(["gmail.search", "gmail.read", "files.write", "gmail.send"]), args=args_st, prov=prov_st)
def test_align_never_upgrades_a_decision(verdict, tool, args, prov):
    base = _guard("Email the report to bob@corp.com", ["gmail.search", "gmail.read", "gmail.send"],
                  AlignClient(enabled=True, backend=lambda *a: AlignVerdict(verdict="aligned", score=1.0)))
    other = _guard("Email the report to bob@corp.com", ["gmail.search", "gmail.read", "gmail.send"],
                   AlignClient(enabled=True, backend=lambda *a, v=verdict: AlignVerdict(verdict=v, score=0.5)))
    ro = TOOL_REGISTRY[tool]["read_only"]
    mk = lambda: CheckActionRequest(task_id="t", call_id="c", tool=tool, args=args, arg_provenance=prov, read_only=ro)
    assert ORDER[other.check_action(mk()).decision] <= ORDER[base.check_action(mk()).decision]


@SETTINGS
@given(args=args_st)
def test_allow_requires_tool_in_policy(args):
    r = _RO.check_action(CheckActionRequest(task_id="t", call_id="c", tool="web.fetch", args=args, read_only=True))
    assert r.decision != "ALLOW"  # web.fetch is not in a mailbox-summary policy


from datetime import datetime, timedelta, timezone

from contracts.models import TaskPolicy
from eva_guard.gateway import PolicyGateway


@SETTINGS
@given(tool=st.sampled_from(WRITE_TOOLS), args=args_st, prov=prov_st)
def test_prohibited_wins_even_if_also_listed_as_allowed(tool, args, prov):
    """Rule 4 in isolation: a tool in both allowed_operations and prohibited_side_effects is DENY."""
    now = datetime.now(timezone.utc)
    pol = TaskPolicy(task_id="t", user_id="u", version=1, created_at=now, expires_at=now + timedelta(hours=1),
                     allowed_operations=list(TOOL_REGISTRY), allowed_data_scope=[], allowed_destinations=["*"],
                     prohibited_side_effects=[tool], approval_required_for=[], minimum_detector_posture="tier1_ok_readonly",
                     failure_mode="fail_closed", max_steps=12, origin="template")
    r = PolicyGateway().check(CheckActionRequest(task_id="t", call_id="c", tool=tool, args=args, arg_provenance=prov, read_only=False), pol)
    assert r.decision == "DENY"
