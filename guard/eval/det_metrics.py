"""
Sanitization metrics measured THROUGH the Guard facade (what BE actually calls), on the shared corpus.
Run from guard/:  APP_ENV=eval GMAIL_MODE=mock PYTHONPATH=.:.. python -m eval.det_metrics [--split test]
A record counts as "caught" when disposition != pass or any sentence was removed. Writes eval/DET_METRICS.md.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from contracts.models import Provenance, ScanField, ScanRequest, SourceType, Trust
from eva_guard.api import Guard
from eval.store import EvalStore

EVAL = Path(__file__).parent
PROV = Provenance(source_id="corpus", source_type=SourceType.EMAIL, trust=Trust.UNTRUSTED)


def run(split: str, guard: Guard) -> dict:
    rows = [json.loads(l) for l in (EVAL / "corpus" / (f"{split}.jsonl" if split != "blind" else "blind_sec2.jsonl")).read_text().splitlines() if l.strip()]
    tp = fn = fp = tn = 0
    fam = defaultdict(lambda: [0, 0])
    lat_per_kb, misses, fps = [], [], []
    for i, r in enumerate(rows):
        t = time.perf_counter()
        resp = guard.scan_tool_result(ScanRequest(task_id=f"m-{split}", call_id=f"c{i}", tool="gmail.read",
                                                  fields=[ScanField(name="body", text=r["text"], provenance=PROV)]))
        ms = (time.perf_counter() - t) * 1000
        lat_per_kb.append(ms / max(len(r["text"]) / 1024, 0.1))
        caught = resp.disposition != "pass" or any(f.sentences_removed for f in resp.fields)
        if r["label"] == "attack":
            fam[r["family"]][1] += 1
            fam[r["family"]][0] += caught
            tp += caught; fn += not caught
            if not caught: misses.append(r["text"][:70])
        else:
            fp += caught; tn += not caught
            if caught: fps.append(r["text"][:70])
    lat_per_kb.sort()
    return {"split": split, "n": len(rows), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
            "fpr": fp / (fp + tn) if fp + tn else None, "fam": dict(fam),
            "p50": statistics.median(lat_per_kb), "p95": lat_per_kb[max(0, int(len(lat_per_kb) * .95) - 1)],
            "health": guard.health().model_dump(), "misses": misses, "fps": fps}


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--split", default="dev,test"); a = ap.parse_args()
    g = Guard(db_url=f"sqlite:///{tempfile.mkdtemp()}/m.db")
    det = type(g._det_pipeline).__name__ if g._det_pipeline else "ABSENT (stub fallback)"
    res = [run(s, g) for s in a.split.split(",")]
    for r in res:
        EvalStore().save_run("det", {"split": r["split"], **{k: r[k] for k in ("recall", "precision", "fpr", "tp", "fn", "fp", "tn", "p50", "p95")}, "by_family": r["fam"],
                                     "detector": det}, n=r["n"], failures=r["misses"][:50], config={"granularity": "record", "via": "Guard.scan_tool_result"})
    f = lambda x: "n/a" if x is None else f"{x:.0%}"
    L = ["# Sanitization Metrics (through the Guard facade)", "",
         f"- Date: {datetime.now(timezone.utc):%Y-%m-%d}  ·  Detector: {det} (interim rule-based T2; T3 not wired through `Guard`)",
         f"- Hardware: {platform.machine()} {platform.system()} {platform.python_version()}, CPU only  ·  corpus v1 (authored), whole-record granularity, stratified splits",
         "- `test` is held out; `dev` was visible to SEC-1. Single run, no seeds involved.", "",
         "| Split | N | Recall | Precision | FP rate | TP/FN/FP/TN | latency p50 / p95 per KB |", "|---|---|---|---|---|---|---|"]
    for r in res:
        L.append(f"| {r['split']} | {r['n']} | {f(r['recall'])} | {f(r['precision'])} | {f(r['fpr'])} | {r['tp']}/{r['fn']}/{r['fp']}/{r['tn']} | {r['p50']:.2f} / {r['p95']:.2f} ms |")
    for r in res:
        L += ["", f"## Recall by family — {r['split']}", "", "| Family | Caught |", "|---|---|"]
        L += [f"| {k} | {v[0]}/{v[1]} |" for k, v in sorted(r["fam"].items())]
        L += ["", f"False positives ({r['split']}): " + ("; ".join(r["fps"]) or "none")]
        if r["split"] == "blind":
            L += ["", "Misses (blind): " + ("; ".join(m[:60] for m in r["misses"]) or "none")]
    L += ["", "## Reading these numbers", "",
          "- `dev`/`test` are in the repo and SEC-1 has had the corpus (and a paraphrase challenge set) while tuning T1/T2, so they are optimistic. `blind` (`corpus/blind_sec2.jsonl`, 48 fresh SEC-2-authored records, written after the tuning) is a one-shot probe: **do not tune on it**, or replace it with a new blind set before the next claim.",
          "- Precision > 85% target: judge on `blind`, not `dev`/`test`.",
          "- T2 < 15 ms/KB: the latency column is end-to-end `Guard.scan_tool_result` including the synchronous SQLite audit write, on records mostly <0.2 KB (per-KB figure inflated by a 0.1 KB floor); SEC-1's det-only runner measures the detector alone. Not comparable to the target until measured on KB-sized inputs.",
          "- T3 escalation rate and LAYA behaviour: see `health().metrics` from the live facade; LAYA availability depends on the `laya` package being installed.",
          "- Small N (24 attack + 24 benign in `blind`): intervals are wide. Zero or few misses on a finite suite is not immunity; the gateway, not detection, carries the safety guarantee."]
    (EVAL / "DET_METRICS.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[7:12]))


if __name__ == "__main__":
    main()
