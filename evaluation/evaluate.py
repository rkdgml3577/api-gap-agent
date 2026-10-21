import argparse
import asyncio
import json
from uuid import uuid4
from tools.repository import ROOT
from server import AnalysisRequest, analyze, runs

def score(result, truth):
    findings = result.get("findings", [])
    predicted = {f["rule_id"] for f in findings if f["coverage"] == "missing"}
    expected = set(truth["missing"])
    tp = len(predicted & expected)
    defects = {f["rule_id"] for f in findings if f["implementation"] == "violates"}
    actual_defects = set(truth["defects"])
    attempts = [o["result"] for o in result.get("observations", []) if o["tool"] == "run_candidate_test"]
    executable = [o for o in attempts if o.get("status") in ("passed", "assertion_failed")]
    return {"candidate_attempts": len(attempts),
            "candidate_execution_rate": len(executable) / len(attempts) if attempts else None,
            "passed_candidates": sum(o.get("status") == "passed" for o in executable),
            "failed_assertion_candidates": sum(o.get("status") == "assertion_failed" for o in executable),
            "status": result["status"], "precision": tp / len(predicted) if predicted else None,
            "recall": tp / len(expected) if expected else None,
            "false_positives": sorted(predicted - expected), "missed": sorted(expected - predicted),
            "defect_recall": len(defects & actual_defects) / len(actual_defects) if actual_defects else None,
            "false_defects": sorted(defects - actual_defects),
            "steps": result.get("steps"), "tokens": result.get("tokens"), "seconds": result.get("elapsed_seconds")}

async def main(variant):
    truth = json.loads((ROOT / "evaluation/ground_truth.json").read_text())[variant]
    req = AnalysisRequest(variant=variant).model_dump()
    run_id = uuid4().hex
    runs[run_id] = {"run_id": run_id, "request": req, "events": [], "done": False, "result": None}
    await analyze(run_id, req)
    metrics = score(runs[run_id]["result"], truth)
    (ROOT / "outputs" / run_id / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps({"run_id": run_id, **metrics}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["healthy", "buggy", "covered"], default="healthy")
    asyncio.run(main(parser.parse_args().variant))
