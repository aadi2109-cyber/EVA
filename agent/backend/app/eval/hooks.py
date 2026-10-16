"""
Eval-only failure-injection hooks and GUARD_PROFILE overlay.

Everything here is inert unless ``settings.APP_ENV == "eval"``. In any other
environment the flags are ignored at call time, and config validation refuses
to boot if a flag or a non-``full`` profile is set (see ``app.config``).

Flags (env var -> settings attribute):
  EVA_FAIL_TIER2_DOWN        -> INJECT_TIER2_DOWN
  EVA_FAIL_GUARD_UNREACHABLE -> INJECT_GUARD_UNREACHABLE
  EVA_FAIL_LAYA_TIMEOUT      -> INJECT_LAYA_TIMEOUT
(the legacy ``INJECT_*`` env names are accepted as well)

Injection is applied at the GuardClient boundary, so the real guard facade is
never modified or bypassed in dev/prod.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Iterator

from contracts.models import (
    CheckActionRequest,
    CheckActionResponse,
    Health,
    ReasonCode,
    ScanRequest,
    ScanResponse,
    TaskPolicy,
)
from app.config import settings
from app.guard_client.base import GuardDownError

FLAGS = ("INJECT_TIER2_DOWN", "INJECT_GUARD_UNREACHABLE", "INJECT_LAYA_TIMEOUT")


def eval_active() -> bool:
    return settings.APP_ENV == "eval"


def flag(name: str) -> bool:
    """True only when APP_ENV=eval and the flag is set."""
    return eval_active() and bool(getattr(settings, name, False))


def profile() -> str:
    """Effective guard profile: anything but 'full' is honoured only in eval."""
    return settings.GUARD_PROFILE if eval_active() else "full"


@contextlib.contextmanager
def injected(**flags: bool) -> Iterator[None]:
    """Temporarily set flags (e.g. injected(INJECT_TIER2_DOWN=True)). Eval only."""
    if not eval_active():
        raise RuntimeError("Failure injection is only available when APP_ENV=eval")
    old = {k: getattr(settings, k) for k in flags}
    for k, v in flags.items():
        if k not in FLAGS:
            raise ValueError(f"Unknown injection flag {k}")
        setattr(settings, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(settings, k, v)


def raise_if_unreachable() -> None:
    if flag("INJECT_GUARD_UNREACHABLE"):
        raise GuardDownError("Injected failure: guard service is unreachable")


# ---------------------------------------------------------------- scan / check

def adjust_scan(resp: ScanResponse) -> ScanResponse:
    """Overlay tier2-down / laya-timeout on a scan response (fail-conservative)."""
    if profile() == "off":
        return resp
    update: dict = {}
    warnings = list(resp.warnings)
    if flag("INJECT_TIER2_DOWN"):
        update["tier2_available"] = False
        warnings.append("tier2_unavailable (injected)")
    if flag("INJECT_LAYA_TIMEOUT"):
        summary = resp.det_summary.model_copy(update={"t3_verdict": "unavailable", "t3_used": False})
        update["det_summary"] = summary
        warnings.append("t3_timeout (injected)")
    if update:
        update["warnings"] = warnings
        return resp.model_copy(update=update)
    return resp


def passthrough_scan(req: ScanRequest, template: ScanResponse) -> ScanResponse:
    """GUARD_PROFILE=off: no scanning at all, text unchanged."""
    from contracts.models import DetSummary, SanitizedField

    fields = [
        SanitizedField(name=f.name, text=f.text, sentences_total=0, sentences_removed=0)
        for f in req.fields
    ]
    return ScanResponse(
        disposition="pass",
        fields=fields,
        det_summary=DetSummary(),
        tier2_available=template.tier2_available,
        warnings=["profile_off: scanning disabled"],
        event_id=f"eval-off-{uuid.uuid4().hex[:8]}",
    )


def _resp(decision: str, reasons: list[ReasonCode], text: str, align: dict | None = None) -> CheckActionResponse:
    return CheckActionResponse(
        decision=decision,  # type: ignore[arg-type]
        reasons=reasons,
        reason_text=text,
        align=align or {},
        event_id=f"eval-{uuid.uuid4().hex[:8]}",
    )


def profile_check(req: CheckActionRequest, policy: TaskPolicy | None) -> CheckActionResponse | None:
    """Override gateway decision for off/basic profiles; None = defer to the guard."""
    p = profile()
    if p == "off":
        return _resp("ALLOW", [], "Guard profile 'off': gateway disabled (baseline).")
    if p == "basic":
        allowed = policy.allowed_operations if policy else None
        if allowed is not None and req.tool not in allowed:
            return _resp("DENY", [ReasonCode.TOOL_NOT_IN_POLICY], "Tool is not in the task allowlist.")
        return _resp("ALLOW", [], "Guard profile 'basic': tool allowlist only.")
    return None


def adjust_check(req: CheckActionRequest, resp: CheckActionResponse) -> CheckActionResponse:
    """Overlay posture degradation / ALIGN timeout on a full-profile decision."""
    if resp.decision == "DENY":
        return resp
    if flag("INJECT_TIER2_DOWN") and not req.read_only:
        return _resp(
            "DENY",
            [ReasonCode.POSTURE_DEGRADED],
            "Side effects are blocked while the Tier 2 detector is unavailable.",
        )
    if flag("INJECT_LAYA_TIMEOUT") and not req.read_only:
        # ALIGN (LAYA) timed out: no advisory verdict -> fail closed for side effects.
        return _resp(
            "DENY",
            [ReasonCode.ALIGN_UNCERTAIN],
            "Action intent could not be verified (alignment check timed out).",
            align={"verdict": "unavailable", "score": None},
        )
    return resp


def adjust_health(h: Health) -> Health:
    if flag("INJECT_TIER2_DOWN"):
        return h.model_copy(update={"tier2_available": False, "status": "degraded"})
    if flag("INJECT_LAYA_TIMEOUT"):
        return h.model_copy(update={"t3_available": False, "align_available": False})
    return h
