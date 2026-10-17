"""
Tests for T3 — Tier 3 Gray-Band Routing and Provider (LAYA / advisory).
Verifies LayaProvider, MockTier3Provider, create_t3_provider factory,
and DetPipeline integration with Tier 3 routing.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch

from eva_guard.det.config import DetConfig
from eva_guard.det.t3 import (
    LayaProvider,
    MockTier3Provider,
    create_t3_provider,
    T3Result,
)
from eva_guard.det.t2 import Tier2Scorer, Score
from eva_guard.det.pipeline import DetPipeline, SANITIZED_MARKER

try:
    from contracts.models import ScanRequest, ScanField, Provenance, Trust, SourceType
except ImportError:
    from eva_guard.det.contracts_stub import ScanRequest, ScanField, Provenance, Trust, SourceType


def _make_dummy_provenance() -> Provenance:
    return Provenance(
        source_id="test-source-1",
        source_type=SourceType.TOOL_OUTPUT,
        trust=Trust.UNTRUSTED
    )


def test_laya_provider_init_and_availability():
    """Verify LayaProvider initializes with config and availability flags."""
    import importlib.util
    cfg = DetConfig(t3_enabled=True)
    provider = LayaProvider(cfg)
    assert provider.is_available == (importlib.util.find_spec("laya") is not None)

    cfg_disabled = DetConfig(t3_enabled=False)
    provider_disabled = LayaProvider(cfg_disabled)
    assert provider_disabled.is_available is False


def test_laya_provider_fallback_when_laya_uninstalled():
    """When laya package is not installed, probe reports unavailable."""
    provider = LayaProvider(DetConfig(t3_enabled=True))
    prov = _make_dummy_provenance()
    res = provider.judge_sync("Please evaluate this sentence.", "context", prov)
    assert isinstance(res, T3Result)
    assert res.verdict in ("unavailable", "uncertain")
    assert res.score is None


@pytest.mark.asyncio
async def test_laya_provider_async_judge():
    """Async judge call delegates and returns T3Result."""
    provider = LayaProvider(DetConfig(t3_enabled=True))
    prov = _make_dummy_provenance()
    res = await provider.judge("Another suspicious sentence.", "context", prov)
    assert isinstance(res, T3Result)
    assert res.verdict in ("unavailable", "uncertain")


@pytest.mark.asyncio
async def test_laya_provider_timeout_conservative_drop():
    """When LAYA execution exceeds timeout, conservative uncertain verdict is returned."""
    cfg = DetConfig(t3_enabled=True, t3_timeout_ms=50)
    provider = LayaProvider(cfg)
    provider._loaded = True
    prov = _make_dummy_provenance()

    async def _slow_predict(text, context):
        await asyncio.sleep(0.2)
        return T3Result(verdict="benign", score=0.1)

    with patch.object(provider, "_predict_laya", side_effect=_slow_predict):
        res = await provider.judge("Slow sentence evaluation.", "context", prov)
        assert res.verdict == "uncertain"


def _laya_answers(override, exfil):
    """Shape of the real `laya.Router.predict` result: answers[qid]["noul"] = P(yes)."""
    return {"answers": {"override": {"noul": override}, "exfil_or_tool": {"noul": exfil}}, "routing": {}}


def test_laya_provider_with_mocked_router():
    """Real response shape -> verdict by thresholds (malicious >= 0.8, benign <= 0.3, else uncertain)."""
    provider = LayaProvider(DetConfig(t3_enabled=True))
    prov = _make_dummy_provenance()
    mock_router = MagicMock()
    provider._router = mock_router
    provider._loaded = True

    mock_router.predict.return_value = _laya_answers(0.97, 0.10)
    res = provider.judge_sync("Malicious sentence", "context", prov)
    assert res.verdict == "malicious" and res.score == 0.97

    mock_router.predict.return_value = _laya_answers(0.02, 0.05)
    res = provider.judge_sync("Safe invoice info", "context", prov)
    assert res.verdict == "benign" and res.score == 0.05

    mock_router.predict.return_value = _laya_answers(0.40, 0.55)
    assert provider.judge_sync("Ambiguous", "context", prov).verdict == "uncertain"

    # the call must use the real API contract: dict state keyed `prompt`, dict of questions
    args, kwargs = mock_router.predict.call_args
    assert args[0] == {"prompt": "Ambiguous"} and isinstance(args[1], dict) and "override" in args[1]


def test_mock_tier3_provider():
    """MockTier3Provider operates synchronously and asynchronously."""
    mock = MockTier3Provider(default_verdict="benign", delay_ms=1.0)
    assert mock.is_available is True
    prov = _make_dummy_provenance()
    res = mock.judge_sync("test", "ctx", prov)
    assert res.verdict == "benign"
    assert res.score == 0.15


def test_create_t3_provider_factory():
    """create_t3_provider creates LayaProvider by default or MockTier3Provider on request."""
    p1 = create_t3_provider()
    assert isinstance(p1, LayaProvider)

    p2 = create_t3_provider(use_mock=True)
    assert isinstance(p2, MockTier3Provider)


def test_det_pipeline_connects_laya_by_default():
    """DetPipeline connects LAYA Tier 3 provider by default."""
    import importlib.util
    pipeline = DetPipeline()
    assert pipeline.t3 is not None
    assert isinstance(pipeline.t3, LayaProvider)
    assert pipeline.is_t3_available() == (importlib.util.find_spec("laya") is not None)
    health = pipeline.health()
    assert health.t3_available == (importlib.util.find_spec("laya") is not None)


def test_det_pipeline_t3_disabled_config():
    """When t3_enabled is False in DetConfig, Tier 3 is not connected."""
    cfg = DetConfig(t3_enabled=False)
    pipeline = DetPipeline(config=cfg)
    assert pipeline.t3 is None
    assert pipeline.is_t3_available() is False
    health = pipeline.health()
    assert health.t3_available is False


@pytest.mark.asyncio
async def test_det_pipeline_gray_band_routes_to_laya_and_drops():
    """Gray-band sentence automatically routes to LAYA and gets conservatively dropped."""
    config = DetConfig(t3_enabled=True, t3_band_low=0.30, t3_band_high=0.85)

    class FixedGrayBandScorer(Tier2Scorer):
        @property
        def is_available(self) -> bool:
            return True
        def score(self, sentences: list[str]) -> list[Score]:
            return [Score(main=0.55, aux=0.0) for _ in sentences]

    pipeline = DetPipeline(config=config, t2_scorer=FixedGrayBandScorer())
    pipeline.t3._loaded = True  # mark loaded so is_available is True
    pipeline.t3._router = None  # without router -> uncertain verdict -> conservative drop

    req = ScanRequest(
        task_id="task-laya-gray",
        call_id="call-1",
        tool="messages.read",
        fields=[
            ScanField(
                name="body",
                text="Please handle this ambiguous grey band sentence carefully.",
                provenance=_make_dummy_provenance()
            )
        ]
    )

    res = await pipeline.scan(req)
    # Conservative drop occurs: uncertain verdict -> sanitized
    assert res.disposition == "sanitized"
    assert res.det_summary.t3_used is True
    assert res.det_summary.t3_verdict == "uncertain"
    assert SANITIZED_MARKER in res.fields[0].text
    assert res.fields[0].sentences_removed == 1



def test_factory_env_overrides_and_no_preload(monkeypatch):
    monkeypatch.setenv("EVA_T3_MODEL", "multilingual")
    monkeypatch.setenv("EVA_T3_MALICIOUS_P", "0.9")
    monkeypatch.setenv("EVA_T3_BENIGN_P", "0.2")
    monkeypatch.setenv("EVA_T3_TIMEOUT_MS", "2500")
    monkeypatch.setenv("EVA_T3_PRELOAD", "0")
    p = create_t3_provider()
    assert isinstance(p, LayaProvider)
    assert (p.config.t3_model, p.config.t3_malicious_p, p.config.t3_benign_p, p.config.t3_timeout_ms) == ("multilingual", 0.9, 0.2, 2500)
    assert p._loading is False


def test_provider_unavailable_while_warming_up_and_after_failed_load():
    p = LayaProvider(DetConfig(t3_enabled=True))
    p._loading = True
    assert p.is_available is False          # gray band is not escalated mid-load (no 1.5 s timeout drops)
    p._loading = False; p._loaded = True; p._router = None; p._available = False
    assert p.is_available is False          # failed load stays unavailable


def test_laya_questions_use_the_prompt_key():
    from eva_guard.det.t3 import LAYA_QUESTIONS
    assert all(q["type"] == "noul" and "`prompt`" in q["instructions"] for q in LAYA_QUESTIONS.values())
