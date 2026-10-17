from eva_guard.align import AlignClient
from eva_guard.align.laya_backend import LayaAlignBackend


class Fake:
    def __init__(self, answers=None, boom=False):
        self.answers, self.boom, self.seen = answers, boom, None

    def predict(self, state, questions):
        if self.boom:
            raise RuntimeError("no weights")
        self.seen = state
        return {"answers": self.answers}


def _v(answers, **kw):
    b = LayaAlignBackend(runner=Fake(answers, **kw))
    return b("Email the report to bob@corp.com", None, "gmail.send", {"to": "bob@corp.com"}).verdict


def test_verdict_mapping():
    assert _v({"serves_request": "yes", "unnamed_destination": "no", "extra_side_effect": "no"}) == "aligned"
    assert _v({"serves_request": "yes", "unnamed_destination": "yes", "extra_side_effect": "no"}) == "misaligned"
    assert _v({"serves_request": {"answer": "no"}, "unnamed_destination": "no", "extra_side_effect": "no"}) == "misaligned"
    assert _v({"serves_request": "unknown", "unnamed_destination": "no", "extra_side_effect": "no"}) == "uncertain"


def test_bad_shapes_and_errors_are_unavailable_not_aligned():
    assert _v({}) == "unavailable"
    assert _v({"serves_request": 3.7, "unnamed_destination": None, "extra_side_effect": []}) == "unavailable"
    assert _v(None, boom=True) == "unavailable"


def test_missing_laya_package_is_unavailable(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "laya", None)
    assert LayaAlignBackend()("r", None, "gmail.send", {}).verdict == "unavailable"


def test_only_request_and_action_reach_the_model_and_client_timeout_applies():
    f = Fake({"serves_request": "yes", "unnamed_destination": "no", "extra_side_effect": "no"})
    AlignClient(enabled=True, backend=LayaAlignBackend(runner=f)).check("Email bob", None, "gmail.send", {"to": "bob@corp.com"})
    assert isinstance(f.seen, str) and f.seen.startswith("REQUEST: ") and "\nACTION: " in f.seen
    import time
    slow = type("S", (), {"predict": lambda self, s, q: time.sleep(0.5)})()
    assert AlignClient(enabled=True, timeout_ms=50, backend=LayaAlignBackend(runner=slow)).check("r", None, "gmail.send", {}).verdict == "unavailable"


def test_env_selects_laya_backend(monkeypatch):
    monkeypatch.setenv("ALIGN_BACKEND", "laya")
    assert isinstance(AlignClient(enabled=True)._backend, LayaAlignBackend)
