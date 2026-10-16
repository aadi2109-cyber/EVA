"""DET performance report: python -m eval.det.perf  (CPU only; prints hardware, N, config)."""
import asyncio, platform, resource, statistics, time
from eva_guard.det.config import DetConfig
from eva_guard.det.pipeline import DetPipeline
from contracts.models import ScanRequest, ScanField, Provenance, Trust, SourceType

SENT = "The quarterly report is attached and the figures were reviewed by the finance team on Tuesday. "


def _req(text):
    return ScanRequest(task_id="p", call_id="p", tool="gmail.read", fields=[ScanField(name="body", text=text,
        provenance=Provenance(source_id="p", source_type=SourceType.EMAIL, trust=Trust.UNTRUSTED))])


def _cpu():
    try:
        return next(l.split(":")[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except Exception:
        return platform.processor() or "unknown"


def _pct(xs, q):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(len(xs) * q))]


async def main():
    cfg = DetConfig()
    t0 = time.perf_counter(); pl = DetPipeline(config=cfg); await pl.scan(_req("warm up."))
    cold = (time.perf_counter() - t0) * 1000
    print(f"CPU: {_cpu()} | threads(intra_op)={cfg.intra_op_threads} | python {platform.python_version()}")
    print(f"Cold start (construct + first scan): {cold:.0f} ms | T2 hash pinned: {bool(cfg.t2_model_sha256)} | T2 available: {pl.is_tier2_available()}")
    for kb in (1, 4, 16, 64, 256, 1000):
        text = (SENT * (kb * 1024 // len(SENT) + 1))[: kb * 1024]
        runs = 30 if kb <= 16 else 5 if kb <= 256 else 2
        ms = []
        for _ in range(runs):
            t = time.perf_counter(); await pl.scan(_req(text)); ms.append((time.perf_counter() - t) * 1000)
        print(f"{kb:>5} KB  N={runs:<3} total p50={statistics.median(ms):9.1f} ms p95={_pct(ms,.95):9.1f} ms | per-KB p50={statistics.median(ms)/kb:7.2f} p95={_pct(ms,.95)/kb:7.2f} ms/KB")
    print(f"Peak RSS: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")

if __name__ == "__main__":
    asyncio.run(main())
