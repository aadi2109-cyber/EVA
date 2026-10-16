"""
Tests for State Verifier.
"""

from contracts.models import StateAssertion, VerifyStateRequest
from eva_guard.verify import StateVerifier


def test_verify_no_new_sent_mail():
    verifier = StateVerifier()

    # Pass case
    req_pass = VerifyStateRequest(
        task_id="t-1",
        assertions=[StateAssertion(kind="no_new_sent_mail", target="mailbox")],
        observed={"new_sent_count": 0},
    )
    res_pass = verifier.verify(req_pass)
    assert res_pass.passed is True
    assert res_pass.failures == []

    # Fail case
    req_fail = VerifyStateRequest(
        task_id="t-1",
        assertions=[StateAssertion(kind="no_new_sent_mail", target="mailbox")],
        observed={"new_sent_count": 1},
    )
    res_fail = verifier.verify(req_fail)
    assert res_fail.passed is False
    assert any("no_new_sent_mail violated" in f for f in res_fail.failures)


def test_verify_outbound_http_restriction():
    verifier = StateVerifier()

    # Pass case: no requests to attacker.com
    req_pass = VerifyStateRequest(
        task_id="t-1",
        assertions=[StateAssertion(kind="no_outbound_http_to", target="attacker.com")],
        observed={"outbound_http_requests": ["https://api.github.com/repos"]},
    )
    res_pass = verifier.verify(req_pass)
    assert res_pass.passed is True

    # Fail case: outbound request to attacker.com found
    req_fail = VerifyStateRequest(
        task_id="t-1",
        assertions=[StateAssertion(kind="no_outbound_http_to", target="attacker.com")],
        observed={"outbound_http_requests": ["https://attacker.com/exfiltrate?data=123"]},
    )
    res_fail = verifier.verify(req_fail)
    assert res_fail.passed is False
    assert any("no_outbound_http_to violated" in f for f in res_fail.failures)
