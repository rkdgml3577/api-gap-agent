import json
import os
import httpx
from agent.prompts import SYSTEM
from agent.schemas import Action

def inline_schema(value, root=None):
    root = root or value
    if isinstance(value, list):
        return [inline_schema(v, root) for v in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        target = root
        for part in value["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return inline_schema(target, root)
    return {key: inline_schema(item, root) for key, item in value.items() if key != "$defs"}


def action_schema(context):
    common = inline_schema(Action.model_json_schema())["properties"]
    catalog = {tool["name"]: tool for tool in context["tools"]}
    branches = []
    for name in context["available_tools"]:
        args = inline_schema(catalog[name]["parameters"]) if name in catalog else {"type": "object", "properties": {}}
        args.setdefault("properties", {})
        for injected in ("variant", "run_id"):
            args["properties"].pop(injected, None)
        args["required"] = [key for key in args.get("required", []) if key not in ("variant", "run_id")]
        args["additionalProperties"] = False
        if name == "read_test_file":
            args["properties"]["path"] = {"type": "string", "enum": context["progress"]["unread_test_files"]}
        if name == "inspect_schema":
            args["properties"]["operation_id"] = {"type": "string", "enum": context["progress"]["uninspected_operations"]}
        if name == "run_candidate_test" and context["progress"].get("existing_coverage_assessment"):
            args["properties"]["candidate"]["properties"]["rule_id"] = {"type": "string", "enum": [
                f["rule_id"] for f in context["progress"]["existing_coverage_assessment"] if f["coverage"] == "missing"]}
        finding_schema = common["findings"]
        if name == "finish" and context["progress"].get("existing_coverage_assessment"):
            import copy
            variants = []
            for finding in context["progress"]["existing_coverage_assessment"]:
                item = copy.deepcopy(common["findings"]["items"])
                item["properties"]["rule_id"] = {"const": finding["rule_id"]}
                item["properties"]["coverage"] = {"const": finding["coverage"]}
                variants.append(item)
            finding_schema = {"type": "array", "items": {"oneOf": variants}, "minItems": len(variants), "maxItems": len(variants)}
        branches.append({"type": "object", "properties": {
            "tool": {"const": name}, "arguments": args, "reason": common["reason"], "findings": finding_schema},
            "required": ["tool", "arguments", "reason"] + (["findings"] if name in ("finish", "assess_coverage") else []),
            "additionalProperties": False})
    return {"type": "object", "oneOf": branches}


class OllamaLLM:
    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "qwen3:8b")
        self.url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self.tokens = 0

    async def choose(self, context):
        schema = action_schema(context)
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(self.url + "/api/chat", json={
                "model": self.model, "stream": False, "think": False,
                "format": schema,
                "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 1500},
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]})
            response.raise_for_status()
            data = response.json()
        self.tokens += data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
        return Action.model_validate_json(data["message"]["content"])
