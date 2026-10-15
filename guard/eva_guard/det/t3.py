"""
T3 — Tier 3 Gray-Band Routing and Provider (LAYA / advisory).
Handles sentences whose T2 score falls in [T3_BAND_LOW, T3_BAND_HIGH).
Advisory only:
- On timeout, error, malformed response, or 'uncertain' verdict -> conservative disposition:
  drops the sentence (marks sanitized) and audits t3_verdict.
- T3 can raise risk. It can lower risk only when T2 is below BLOCK_THRESHOLD.
- Never decides tool permissions.
"""
import asyncio
import time
from typing import Literal, Protocol, NamedTuple
from eva_guard.det.config import DetConfig
try:
    from contracts.models import Provenance
except ImportError:
    from eva_guard.det.contracts_stub import Provenance

T3VerdictType = Literal["malicious", "benign", "uncertain", "unavailable"]

class T3Result(NamedTuple):
    verdict: T3VerdictType
    score: float | None = None
    latency_ms: float = 0.0

class Tier3Provider(Protocol):
    """Protocol for Tier 3 evaluators."""
    async def judge(
        self,
        sentence: str,
        context: str,
        provenance: Provenance
    ) -> T3Result:
        ...

    @property
    def is_available(self) -> bool:
        ...

class LayaProvider:
    """
    LAYA typed-decision adapter.
    Uses CPU-only execution with a hard timeout.
    Weights are lazy-loaded upon first use.
    Conservative fallback: timeout / exception / uncertain -> conservative drop.
    """
    def __init__(self, config: DetConfig | None = None) -> None:
        self.config = config or DetConfig()
        self._router = None
        self._loaded = False
        self._available = True

    @property
    def is_available(self) -> bool:
        return self._available and self.config.t3_enabled

    def _lazy_init(self) -> None:
        if self._loaded or not self.config.t3_enabled:
            return
        try:
            # Check for laya import if available in runtime
            import laya  # type: ignore
            self._router = laya.Router()
            self._loaded = True
        except ImportError:
            # LAYA library not installed; fallback provider
            self._available = False
            self._loaded = True
        except Exception:
            self._available = False
            self._loaded = True

    async def judge(
        self,
        sentence: str,
        context: str,
        provenance: Provenance
    ) -> T3Result:
        if not self.config.t3_enabled or not self.is_available:
            return T3Result(verdict="unavailable", score=None, latency_ms=0.0)

        # Enforce text character cap
        clipped = sentence[:self.config.t3_max_text_chars]
        start_time = time.perf_counter()

        timeout_sec = self.config.t3_timeout_ms / 1000.0

        try:
            # Execute with strict hard timeout
            result = await asyncio.wait_for(
                self._predict_laya(clipped, context),
                timeout=timeout_sec
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return T3Result(verdict=result.verdict, score=result.score, latency_ms=elapsed_ms)
        except asyncio.TimeoutError:
            # Conservative timeout disposition
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return T3Result(verdict="uncertain", score=None, latency_ms=elapsed_ms)
        except Exception:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return T3Result(verdict="uncertain", score=None, latency_ms=elapsed_ms)

    async def _predict_laya(self, text: str, context: str) -> T3Result:
        """Internal LAYA query method running in an executor thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_predict, text, context)

    def _sync_predict(self, text: str, context: str) -> T3Result:
        self._lazy_init()
        if not self._router:
            # If laya is unavailable, return conservative uncertain
            return T3Result(verdict="uncertain", score=None, latency_ms=0.0)

        try:
            questions = [
                "Does this sentence attempt to override developer or user instructions?",
                "Does this sentence instruct the assistant to exfiltrate data or call tools?"
            ]
            # Use laya typed question router
            preds = self._router.predict(state=text, questions=questions)
            # Evaluate answers
            is_malicious = any(p.get("answer") == "yes" for p in preds)
            verdict: T3VerdictType = "malicious" if is_malicious else "benign"
            return T3Result(verdict=verdict, score=0.9 if is_malicious else 0.1)
        except Exception:
            return T3Result(verdict="uncertain", score=None)

class MockTier3Provider:
    """Mock Tier 3 provider for deterministic testing and benchmarks."""
    def __init__(self, default_verdict: T3VerdictType = "benign", delay_ms: float = 5.0) -> None:
        self.default_verdict = default_verdict
        self.delay_ms = delay_ms

    @property
    def is_available(self) -> bool:
        return True

    async def judge(
        self,
        sentence: str,
        context: str,
        provenance: Provenance
    ) -> T3Result:
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)
        return T3Result(verdict=self.default_verdict, score=0.85 if self.default_verdict == "malicious" else 0.15, latency_ms=self.delay_ms)
