"""Repeat evaluation across variants and aggregate — the reliability harness.

A single run of a local sLLM is noisy, so this runs each variant N times and
reports mean/std per metric, completion rate, and per-rule verdict consistency.
It also computes "separation accuracy": healthy and buggy share identical tests,
so their COVERAGE verdicts should match; only the IMPLEMENTATION verdict should
differ (buggy has the ORDER-003 defect). Divergent coverage means the agent is
conflating "test missing" with "implementation buggy".

    python evaluation/run_matrix.py --n 5
    python evaluation/run_matrix.py --n 5 --variants healthy,buggy
    CORPUS=expanded python evaluation/run_matrix.py --n 3   # full-context on big corpus
"""
import argparse
import asyncio
import json
import os
import statistics
from collections import Counter
from datetime import datetime
from uuid import uuid4

from tools.repository import ROOT
from server import AnalysisRequest, analyze, runs
from evaluation.evaluate import score

NUMERIC = ["precision", "recall", "f1", "false_positive_rate",
           "defect_precision", "defect_recall", "defect_f1",
           "abstention_rate",
           "candidate_execution_rate", "steps", "tokens", "seconds"]


def agg(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return {"mean": None, "std": None, "n": 0}
    return {"mean": round(statistics.mean(vals), 3),
            "std": round(statistics.stdev(vals), 3) if len(vals) > 1 else 0.0,
            "n": len(vals)}


def consistency(per_run_verdicts):
    """Per rule: majority-verdict share across runs, averaged over rules."""
    rules = {r for run in per_run_verdicts for r in run}
    shares = []
    majority = {}
    for rule in rules:
        votes = Counter(run[rule] for run in per_run_verdicts if rule in run)
        top, count = votes.most_common(1)[0]
        majority[rule] = top
        shares.append(count / sum(votes.values()))
    return (round(statistics.mean(shares), 3) if shares else None), majority


async def run_variant(variant, n):
    truth = json.loads((ROOT / "evaluation/ground_truth.json").read_text())[variant]
    scores = []
    for i in range(n):
        req = AnalysisRequest(variant=variant).model_dump()
        run_id = uuid4().hex
        runs[run_id] = {"run_id": run_id, "request": req, "events": [], "done": False, "result": None}
        await analyze(run_id, req)
        s = score(runs[run_id]["result"], truth)
        s["run_id"] = run_id
        scores.append(s)
        print(f"  [{variant} {i+1}/{n}] status={s['status']} cov={s['coverage_verdicts']} "
              f"f1={s['f1']} fp_rate={s['false_positive_rate']} defect_f1={s['defect_f1']} "
              f"steps={s['steps']} sec={s['seconds']}")
    cov_cons, cov_majority = consistency([s["coverage_verdicts"] for s in scores])
    impl_cons, impl_majority = consistency([s["implementation_verdicts"] for s in scores])
    return {"variant": variant, "n": n,
            "completion_rate": round(sum(s["status"] == "completed" for s in scores) / n, 3),
            "metrics": {m: agg([s[m] for s in scores]) for m in NUMERIC},
            "coverage_consistency": cov_cons, "coverage_majority": cov_majority,
            "implementation_consistency": impl_cons, "implementation_majority": impl_majority,
            "runs": [{"run_id": s["run_id"], "status": s["status"],
                      "coverage": s["coverage_verdicts"], "implementation": s["implementation_verdicts"]}
                     for s in scores]}


def separation_accuracy(summaries):
    """Coverage verdicts should agree between healthy and buggy (identical tests)."""
    by = {s["variant"]: s for s in summaries}
    if "healthy" not in by or "buggy" not in by:
        return None
    h, b = by["healthy"]["coverage_majority"], by["buggy"]["coverage_majority"]
    rules = set(h) & set(b)
    if not rules:
        return None
    agree = sum(h[r] == b[r] for r in rules)
    return {"coverage_agreement": round(agree / len(rules), 3),
            "rules": sorted(rules),
            "healthy_coverage": h, "buggy_coverage": b}


async def main(n, variants):
    summaries = [await run_variant(v, n) for v in variants]
    out = {"timestamp": datetime.now().isoformat(timespec="seconds"),
           "n": n, "variants": variants, "corpus": os.getenv("CORPUS", "default"),
           "model": os.getenv("OLLAMA_MODEL", "qwen3:8b"),
           "separation_accuracy": separation_accuracy(summaries),
           "summaries": summaries}
    folder = ROOT / "outputs" / f"eval_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("\n" + "=" * 70)
    print(f"집계 (N={n}, corpus={out['corpus']}, model={out['model']})")
    print("=" * 70)
    for s in summaries:
        m = s["metrics"]
        print(f"\n[{s['variant']}] 완료율={s['completion_rate']} "
              f"coverage일관성={s['coverage_consistency']} 구현일관성={s['implementation_consistency']}")
        print(f"  누락: F1={m['f1']['mean']}±{m['f1']['std']}  "
              f"precision={m['precision']['mean']}  recall={m['recall']['mean']}  "
              f"오탐률={m['false_positive_rate']['mean']}")
        print(f"  결함: F1={m['defect_f1']['mean']}  recall={m['defect_recall']['mean']}")
        if m['abstention_rate']['n']:
            print(f"  기권: 기권율={m['abstention_rate']['mean']} (애매 규칙을 uncertain으로 올바르게 보류한 비율)")
        print(f"  비용: steps={m['steps']['mean']}±{m['steps']['std']}  "
              f"tokens={m['tokens']['mean']}  sec={m['seconds']['mean']}±{m['seconds']['std']}")
    sep = out["separation_accuracy"]
    if sep:
        print(f"\n분리 정확도(healthy↔buggy coverage 일치): {sep['coverage_agreement']}")
    print(f"\n저장: {folder / 'summary.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--variants", default="healthy,buggy,covered")
    args = parser.parse_args()
    asyncio.run(main(args.n, [v.strip() for v in args.variants.split(",") if v.strip()]))
