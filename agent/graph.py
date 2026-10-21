import json
import os
import re
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from agent.schemas import Action

class State(TypedDict, total=False):
    observations: list[dict]
    action: dict
    steps: int
    done: bool
    result: dict
    coverage: list[dict]

RULE_OPERATIONS = {"ORDER-001": "create_order", "ORDER-002": "get_order", "ORDER-003": "cancel_order"}

def _evidence_corpus(calls):
    """Everything the agent actually gathered this run, as searchable text:
    read test sources, retrieved rules, listed paths, and execution observations.
    Used to confirm a finding cites evidence that genuinely exists."""
    parts = []
    for o in calls:
        tool, result = o["tool"], o["result"]
        if tool == "read_test_file":
            parts.append(o["arguments"].get("path", ""))
            parts.append(str(result.get("content", "")))
        elif tool == "search_tests":
            parts += [f["path"] for f in result.get("files", [])]
        elif tool == "search_rules":
            parts.append(str(result.get("content", "")))
        elif tool == "run_candidate_test":
            parts.append(json.dumps(result.get("observations", []), ensure_ascii=False))
    return "\n".join(parts)


def _is_grounded(evidence, corpus):
    """A finding is grounded when at least one citation shares a concrete token
    (a path or an identifier like a test-function name) with gathered evidence.
    Pure prose with no checkable token cannot be verified, so it is not grounding."""
    for citation in evidence:
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_.]{3,}", citation):
            if token in corpus:
                return True
    return False


def validate_finish(findings, observations, operations):
    """Structural evidence guards, not a substitute for semantic evaluation."""
    expected = {r for r, op in RULE_OPERATIONS.items() if op in operations}
    if {f.rule_id for f in findings} != expected or len(findings) != len(expected):
        return "Provide exactly one finding per in-scope rule."
    calls = [o for o in observations if "error" not in o["result"]]
    listed = {f["path"] for o in calls if o["tool"] == "search_tests" for f in o["result"]["files"]}
    read = {o["arguments"].get("path") for o in calls if o["tool"] == "read_test_file"}
    executed = {o["result"].get("rule_id"): o["result"] for o in calls if o["tool"] == "run_candidate_test"}
    if not any(o["tool"] == "search_rules" for o in calls):
        return "Retrieve the actual business rules first."
    inspected = {o["arguments"].get("operation_id") for o in calls if o["tool"] == "inspect_schema"}
    if not set(operations) <= inspected:
        return "Inspect the schema for every selected operation."
    corpus = _evidence_corpus(calls)
    for f in findings:
        if not listed or not listed <= read:
            return "List and read ALL existing test files (including common files) before any coverage verdict."
        if not _is_grounded(f.evidence, corpus):
            return (f"{f.rule_id}: cite evidence you actually gathered. At least one citation must reference a "
                    "test file you read (path or test function name) or an execution observation, not prose alone.")
        if f.coverage == "missing" and f.rule_id not in executed:
            return f"Execute a candidate for {f.rule_id} before finishing."
        run = executed.get(f.rule_id, {})
        executed_status = run.get("status")
        if f.implementation == "unknown" and executed_status in ("passed", "assertion_failed") and run.get("observations"):
            return (f"{f.rule_id} was executed (status {executed_status}); do not leave implementation unknown. "
                    "A passing candidate means conforms; a failed assertion means violates.")
        if f.implementation != "unknown":
            if not run.get("observations") or executed_status == "execution_error":
                return (f"{f.rule_id} has no successful execution observations this run, so set its implementation to unknown. "
                        "Only a rule you actually executed (passed or assertion_failed) can be conforms or violates.")
            if f.implementation == "conforms" and executed_status != "passed":
                return f"{f.rule_id}: conforms requires a passing candidate; it ended {executed_status}."
            if f.implementation == "violates" and executed_status != "assertion_failed":
                return f"{f.rule_id}: violates requires a failed assertion; it ended {executed_status}."
    return None


def build_graph(llm, tools, catalog, request, run_id, emit):
    max_steps = int(os.getenv("MAX_STEPS", "24"))
    started = time.monotonic()
    async def decide(state):
        steps = state.get("steps", 0)
        if steps >= max_steps or time.monotonic() - started > 600:
            result = {"status": "incomplete", "findings": [], "message": "Analysis budget reached; inspect observations. No completeness claim."}
            return {"done": True, "result": result}
        observations = state.get("observations", [])
        successful = [o for o in observations if "error" not in o["result"]]
        called = {o["tool"] for o in successful}
        listed = {f["path"] for o in successful if o["tool"] == "search_tests" for f in o["result"]["files"]}
        read = {o["arguments"].get("path") for o in successful if o["tool"] == "read_test_file"}
        inspected = {o["arguments"].get("operation_id") for o in successful if o["tool"] == "inspect_schema"}
        ready = "search_rules" in called and bool(listed) and listed <= read and set(request["operations"]) <= inspected
        coverage = state.get("coverage", [])
        available = (["finish"] + (["run_candidate_test"] if any(f["coverage"] == "missing" for f in coverage) else []) if coverage else ["assess_coverage"]) if ready else []
        available += [name for name in ("list_endpoints", "search_rules", "search_tests") if name not in called]
        if set(request["operations"]) - inspected:
            available.append("inspect_schema")
        if listed - read:
            available.append("read_test_file")
        progress = {"unread_test_files": sorted(listed - read),
                    "uninspected_operations": sorted(set(request["operations"]) - inspected),
                    "rules_in_scope": [r for r, op in RULE_OPERATIONS.items() if op in request["operations"]],
                    "existing_coverage_assessment": coverage,
                    "coverage_instruction": "Existing coverage was assessed BEFORE new tests. Never change it based on new execution results.",
                    "executed_candidates": [{"rule_id": o["result"].get("rule_id"), "status": o["result"].get("status")}
                                            for o in successful if o["tool"] == "run_candidate_test"],
                    "note": "Search tools return the complete small corpus. Do not repeat them; read remaining files/schemas or execute missing candidates."}
        model_observations = []
        for observation in observations:
            result = dict(observation["result"])
            if observation["tool"] == "run_candidate_test":
                result.pop("log", None)
            # Test file content is already carried once in original_test_sources_only;
            # drop the duplicate copy here to keep each prompt small.
            if observation["tool"] == "read_test_file" and "content" in result:
                result = {**result, "content": "(see original_test_sources_only)"}
            model_observations.append({**observation, "result": result})
        originals = {o["result"]["path"]: o["result"]["content"] for o in successful
                     if o["tool"] == "read_test_file"}
        context = {"original_test_sources_only": originals, "available_tools": available, "progress": progress, "goal": request["goal"], "operations": request["operations"],
                   "tools": [t for t in catalog if t["name"] in available], "observations": model_observations, "remaining_steps": max_steps - steps}
        try:
            action = await llm.choose(context)
        except Exception as exc:
            observation = {"tool": "model_output", "arguments": {}, "result": {"error": str(exc)[:800]}}
            await emit({"type": "error", **observation})
            return {"steps": steps + 1, "observations": state.get("observations", []) + [observation], "action": {}, "done": False}
        await emit({"type": "decision", "step": steps + 1, "tool": action.tool, "reason": action.reason})
        if action.tool == "assess_coverage":
            if not ready:
                obs = {"tool": "assessment_validation", "arguments": {}, "result": {"error": "Read all existing tests and selected schemas before assessing original coverage."}}
                await emit({"type": "revision", "message": obs["result"]["error"]})
                return {"steps": steps + 1, "observations": observations + [obs], "action": {}, "done": False}
            expected = {r for r, op in RULE_OPERATIONS.items() if op in request["operations"]}
            if {f.rule_id for f in action.findings} != expected or len(action.findings) != len(expected):
                obs = {"tool": "assessment_validation", "arguments": {}, "result": {"error": "Provide exactly one existing-coverage finding per in-scope rule, based ONLY on original test sources."}}
                await emit({"type": "revision", "message": obs["result"]["error"]})
                return {"steps": steps + 1, "observations": observations + [obs], "action": {}, "done": False}
            assessment = [{**f.model_dump(), "implementation": "unknown"} for f in action.findings]
            await emit({"type": "coverage_assessed", "findings": assessment})
            return {"steps": steps + 1, "coverage": assessment, "action": {}, "done": False}
        if action.tool == "finish":
            if not state.get("coverage"):
                obs = {"tool": "finish_validation", "arguments": {}, "result": {"error": "Assess original coverage before executing tests or finishing."}}
                await emit({"type": "revision", "message": obs["result"]["error"]})
                return {"steps": steps + 1, "observations": observations + [obs], "action": {}, "done": False}
            initial = {f["rule_id"]: f["coverage"] for f in state.get("coverage", [])}
            if initial and any(initial.get(f.rule_id) != f.coverage for f in action.findings):
                obs = {"tool": "finish_validation", "arguments": {}, "result": {"error": "Preserve existing_coverage_assessment. New tests cannot change original coverage."}}
                await emit({"type": "revision", "message": obs["result"]["error"]})
                return {"steps": steps + 1, "observations": observations + [obs], "action": {}, "done": False}
            error = validate_finish(action.findings, state.get("observations", []), request["operations"])
            if error:
                obs = {"tool": "finish_validation", "arguments": {}, "result": {"error": error}}
                await emit({"type": "revision", "message": error})
                return {"steps": steps + 1, "observations": state.get("observations", []) + [obs], "action": {}, "done": False}
            return {"steps": steps + 1, "done": True,
                    "result": {"status": "completed", "findings": [{**next(item for item in state["coverage"] if item["rule_id"] == f.rule_id),
                                             "implementation": f.implementation, "execution_explanation": f.explanation}
                                            for f in action.findings],
                               "initial_coverage": state.get("coverage", [])}}
        return {"steps": steps + 1, "action": action.model_dump(), "done": False}

    async def execute(state):
        if not state.get("action"):
            return {}
        action = Action.model_validate(state["action"])
        arguments = dict(action.arguments)
        if action.tool in ("search_tests", "read_test_file", "run_candidate_test"):
            arguments["variant"] = request["variant"]
        if action.tool == "run_candidate_test":
            arguments["run_id"] = run_id
            candidate = arguments.get("candidate", {})
            if RULE_OPERATIONS.get(candidate.get("rule_id")) not in request["operations"]:
                result = {"error": "Candidate rule is outside selected scope"}
            else:
                try:
                    result = await tools.call(action.tool, arguments)
                except Exception as exc:
                    result = {"error": str(exc)[:1500]}
        else:
            try:
                result = await tools.call(action.tool, arguments)
            except Exception as exc:
                result = {"error": str(exc)[:1500]}
        obs = {"tool": action.tool, "arguments": arguments, "result": result}
        await emit({"type": "observation", **obs})
        return {"observations": state.get("observations", []) + [obs]}

    graph = StateGraph(State)
    graph.add_node("decide", decide)
    graph.add_node("execute", execute)
    graph.add_edge(START, "decide")
    graph.add_conditional_edges("decide", lambda s: "end" if s.get("done") else "execute", {"end": END, "execute": "execute"})
    graph.add_edge("execute", "decide")
    return graph.compile()
