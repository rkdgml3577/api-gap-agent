import argparse
import asyncio
import json
from uuid import uuid4
from tools.repository import ROOT
from server import AnalysisRequest, analyze, runs

def _f1(precision, recall):
    if precision is None or recall is None or (precision + recall) == 0:
        return None
    return 2 * precision * recall / (precision + recall)


def _rate(numerator, denominator):
    return numerator / denominator if denominator else None


def score(result, truth):
    findings = result.get("findings", [])
    # In-scope rules = exactly the ones the agent reported (one finding per rule).
    in_scope = {f["rule_id"] for f in findings}

    # ---- Abstention axis: rules whose correct answer is "cannot decide" ----
    expected_uncertain = set(truth.get("uncertain", [])) & in_scope
    pred_uncertain = {f["rule_id"] for f in findings if f["coverage"] == "uncertain"}
    abstained = expected_uncertain & pred_uncertain          # correctly refused to conclude
    over_concluded = expected_uncertain - pred_uncertain      # forced a verdict despite ambiguity

    # ---- Coverage axis (positive class = "missing"); exclude abstention rules ----
    pred_missing = {f["rule_id"] for f in findings if f["coverage"] == "missing"}
    missing_truth = (set(truth["missing"]) & in_scope if in_scope else set(truth["missing"])) - expected_uncertain
    covered_truth = in_scope - missing_truth - expected_uncertain
    tp = len(pred_missing & missing_truth)          # correctly flagged gap
    fp = len(pred_missing & covered_truth)          # 오탐: 정상 검증을 누락으로
    fn = len(missing_truth - pred_missing)          # missed gap
    tn = len(covered_truth - pred_missing)          # correctly left alone
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)

    # ---- Implementation axis (positive class = "violates") ----
    pred_defect = {f["rule_id"] for f in findings if f["implementation"] == "violates"}
    actual_defects = set(truth["defects"]) & in_scope if in_scope else set(truth["defects"])
    non_defects = in_scope - actual_defects
    dtp = len(pred_defect & actual_defects)
    dfp = len(pred_defect & non_defects)
    dfn = len(actual_defects - pred_defect)
    defect_precision = _rate(dtp, dtp + dfp)
    defect_recall = _rate(dtp, dtp + dfn)

    attempts = [o["result"] for o in result.get("observations", []) if o["tool"] == "run_candidate_test"]
    executable = [o for o in attempts if o.get("status") in ("passed", "assertion_failed")]
    return {"status": result["status"],
            "coverage_verdicts": {f["rule_id"]: f["coverage"] for f in findings},
            "implementation_verdicts": {f["rule_id"]: f["implementation"] for f in findings},
            # coverage axis
            "precision": precision, "recall": recall, "f1": _f1(precision, recall),
            "false_positive_rate": _rate(fp, fp + tn),   # 정상을 누락으로 오판한 비율
            "false_positives": sorted(pred_missing & covered_truth), "missed": sorted(missing_truth - pred_missing),
            # implementation axis
            "defect_precision": defect_precision, "defect_recall": defect_recall,
            "defect_f1": _f1(defect_precision, defect_recall),
            "false_defects": sorted(pred_defect & non_defects),
            # abstention (over-conclusion prevention)
            "uncertain_rules": sorted(pred_uncertain),
            "abstention_rate": _rate(len(abstained), len(expected_uncertain)),
            "over_concluded": sorted(over_concluded),
            # pipeline health
            "candidate_attempts": len(attempts),
            "candidate_execution_rate": _rate(len(executable), len(attempts)),
            "passed_candidates": sum(o.get("status") == "passed" for o in executable),
            "failed_assertion_candidates": sum(o.get("status") == "assertion_failed" for o in executable),
            # cost
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
