"""T3 provider wiring through the public Guard facade (incl. S9: LAYA timeout on a gray-band sentence)."""
import time
import pytest
from contracts.models import ScanRequest, ScanField, Provenance, Trust, SourceType
from eva_guard import Guard
from eva_guard.det.config import DetConfig
from eva_guard.det.t2 import Score, Tier2Scorer
from eva_guard.det.t3 import LayaProvider, MockTier3Provider, T3Result, create_t3_provider


class Gray(Tier2Scorer):
    def score(self, sentences):
        return [Score(main=0.45, aux=0.0) for _ in sentences]


def scan_req(text="Quarterly figures are attached. One ambiguous line here."):
    return ScanRequest(task_id="t", call_id="c", tool="files.read", fields=[ScanField(
        name="content", text=text,
        provenance=Provenance(source_id="f", source_type=SourceType.FILE, trust=Trust.UNTRUSTED))])


def guard_with(t3):
    g = Guard(t3_provider=t3)
    g._det_pipeline.t2 = Gray()
    return g


def test_injected_provider_is_used_and_reported_available():
    t3 = MockTier3Provider(default_verdict="benign", delay_ms=0)
    g = guard_with(t3)
    assert g._det_pipeline.t3 is t3
    assert g.health().t3_available is True
    res = g.scan_tool_result(scan_req())
    assert res.det_summary.t3_used is True
    assert res.fields[0].sentences_removed == 0     # benign verdict keeps the sentences


def test_malicious_verdict_removes_gray_band_sentence():
    res = guard_with(MockTier3Provider(default_verdict="malicious", delay_ms=0)).scan_tool_result(scan_req())
    assert res.fields[0].sentences_removed >= 1


def test_s9_laya_timeout_through_facade_is_conservative_audited_and_completes():
    laya = LayaProvider(DetConfig(t3_timeout_ms=100))
    laya.__dict__["_sync_predict"] = lambda t, c: (time.sleep(1.5), T3Result(verdict="benign"))[1]
    laya._loaded = True; laya._router = object()
    g = Guard(t3_provider=laya)
    g._det_pipeline.t2 = Gray()
    g._det_pipeline.config = DetConfig(t3_timeout_ms=100)
    t0 = time.perf_counter()
    res = g.scan_tool_result(scan_req())
    assert time.perf_counter() - t0 < 1.0
    assert res.disposition != "held"
    assert res.fields[0].sentences_removed >= 1
    assert res.det_summary.t3_used is True


def test_default_provider_is_laya_and_health_is_honest_when_not_installed(monkeypatch):
    monkeypatch.delenv("EVA_T3_ENABLED", raising=False)
    g = Guard()
    assert isinstance(g._det_pipeline.t3, LayaProvider)
    import importlib.util
    assert g.health().t3_available == (importlib.util.find_spec("laya") is not None)


def test_env_can_disable_t3(monkeypatch):
    monkeypatch.setenv("EVA_T3_ENABLED", "0")
    assert create_t3_provider() is None
    assert Guard()._det_pipeline.t3 is None and Guard().health().t3_available is False
