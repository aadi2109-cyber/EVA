"""T3 (LAYA) hard-timeout and conservative-failure behaviour."""
import time
import pytest
from eva_guard.det.config import DetConfig
from eva_guard.det.t3 import LayaProvider, T3Result
from eva_guard.det.pipeline import DetPipeline
from eva_guard.det.t2 import Score, Tier2Scorer
from contracts.models import Provenance, Trust, SourceType

PROV = Provenance(source_id="x", source_type=SourceType.TOOL_OUTPUT, trust=Trust.UNTRUSTED)
BUDGET_MS = 150


def _slow_provider(sleep_s=2.0, boom=False):
    p = LayaProvider(DetConfig(t3_timeout_ms=BUDGET_MS))
    def fake(text, ctx):
        if boom:
            raise RuntimeError("laya crashed")
        time.sleep(sleep_s)
        return T3Result(verdict="benign", score=0.1)
    p._sync_predict = fake
    p._loaded = True  # skip the 'is laya installed' probe; the model call is faked
    return p


def test_judge_sync_enforces_timeout():
    p = _slow_provider()
    t0 = time.perf_counter()
    res = p.judge_sync("s", "c", PROV)
    elapsed = (time.perf_counter() - t0) * 1000
    assert res.verdict == "uncertain"
    assert elapsed < BUDGET_MS + 150


@pytest.mark.asyncio
async def test_async_judge_enforces_timeout():
    p = _slow_provider()
    t0 = time.perf_counter()
    res = await p.judge("s", "c", PROV)
    assert res.verdict == "uncertain"
    assert (time.perf_counter() - t0) * 1000 < BUDGET_MS + 150


def test_judge_sync_provider_exception_is_uncertain():
    assert _slow_provider(boom=True).judge_sync("s", "c", PROV).verdict == "uncertain"


def test_laya_missing_is_conservative():
    p = LayaProvider(DetConfig(t3_timeout_ms=BUDGET_MS))  # `laya` not installed here
    assert p.judge_sync("s", "c", PROV).verdict in ("uncertain", "unavailable")


class _Gray(Tier2Scorer):
    def score(self, sentences):
        return [Score(main=0.45, aux=0.0) for _ in sentences]


@pytest.mark.asyncio
async def test_pipeline_scan_bounded_and_sanitizes_on_hung_t3():
    from contracts.models import ScanRequest, ScanField
    cfg = DetConfig(t3_timeout_ms=BUDGET_MS, t3_band_low=0.3)
    pl = DetPipeline(config=cfg, t3=_slow_provider(), t2_scorer=_Gray())
    req = ScanRequest(task_id="t", call_id="c", tool="gmail.read", fields=[
        ScanField(name="body", text="Please review the attached note.", provenance=PROV)])
    t0 = time.perf_counter()
    res = await pl.scan(req)
    assert (time.perf_counter() - t0) * 1000 < BUDGET_MS + 300
    assert res.fields[0].sentences_removed == 1
    assert res.det_summary.t3_used is True
