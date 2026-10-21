import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from tools.repository import ROOT

class RequestStep(BaseModel):
    method: Literal["GET", "POST"]
    path: str = Field(pattern=r"^/orders(?:/[12](?:/cancel)?)?$")
    user: Literal["alice", "bob"] = "alice"
    body: dict[str, int] | None = None
    expected_status: int = Field(ge=100, le=599)
    expected_json: dict[str, str | int] = Field(default_factory=dict)

class Candidate(BaseModel):
    rule_id: Literal["ORDER-001", "ORDER-002", "ORDER-003"]
    description: str = Field(min_length=3, max_length=500)
    steps: list[RequestStep] = Field(min_length=1, max_length=8)


def run_candidate(variant, run_dir, payload):
    candidate = Candidate.model_validate(payload)
    steps = candidate.steps
    if candidate.rule_id == "ORDER-001":
        if len(steps) != 4 or any(s.method != "POST" or s.path != "/orders" or s.user != "alice"
                or not s.body or set(s.body) != {"quantity"}
                or s.expected_json not in ({}, {"quantity": s.body["quantity"]}) for s in steps):
            raise ValueError("Use exactly four quantity requests; do not invent error response fields")
        checked = {(s.body or {}).get("quantity"): s.expected_status for s in steps
                   if s.method == "POST" and s.path == "/orders" and s.user == "alice"}
        if any(checked.get(q) != status for q, status in ((0,400),(1,201),(100,201),(101,400))):
            raise ValueError("ORDER-001 needs 0/1/100/101 with expected 400/201/201/400")
    elif candidate.rule_id == "ORDER-002":
        for step in steps:
            if not (step.method == "GET" and step.path in ("/orders/1", "/orders/2") and
                    ((step.user == "bob" and step.expected_status == 403 and not step.expected_json) or
                     (step.user == "alice" and step.expected_status == 200 and step.expected_json in ({}, {"owner": "alice"})))):
                raise ValueError("For order 1 or 2: bob GET expects 403 and empty expected_json; alice GET expects 200 with optional owner alice")
        if not any(s.method == "GET" and s.path in ("/orders/1", "/orders/2") and s.user == "bob" and s.expected_status == 403 for s in steps):
            raise ValueError("ORDER-002 needs bob accessing alice's order with expected 403")
    elif candidate.rule_id == "ORDER-003":
        if len(steps) != 2 or steps[0].expected_json or steps[1].expected_json != {"status": "shipping"}:
            raise ValueError("ORDER-003 requires exactly: POST /orders/2/cancel user alice expected_status 409 expected_json {}; then GET /orders/2 user alice expected_status 200 expected_json status=shipping. No error-body assertions.")
        cancel = next((i for i,s in enumerate(steps) if s.method == "POST" and s.path == "/orders/2/cancel"
                       and s.user == "alice" and s.expected_status == 409), None)
        if cancel is None or not any(s.method == "GET" and s.path == "/orders/2" and s.user == "alice"
                                    and s.expected_status == 200 and s.expected_json.get("status") == "shipping" for s in steps[cancel+1:]):
            raise ValueError("ORDER-003 needs rejection (409), followed by GET checking shipping state")
    # Generate source only from validated JSON data, never execute model-produced Python.
    encoded = json.dumps([s.model_dump() for s in candidate.steps], ensure_ascii=False)
    source = f'''import json
from fastapi.testclient import TestClient
from sample_service.app import create_app

def test_candidate():
    observations = []
    with TestClient(create_app({variant!r})) as client:
        for step in json.loads({encoded!r}):
            response = client.request(step["method"], step["path"], headers={{"X-User": step["user"]}}, json=step["body"])
            try:
                body = response.json()
            except ValueError:
                body = {{"raw": response.text}}
            observations.append({{"step": step, "actual_status": response.status_code, "actual_json": body}})
            with open(__file__ + ".observations.json", "w") as output:
                json.dump(observations, output)
            assert response.status_code == step["expected_status"], observations
            for key, value in step["expected_json"].items():
                assert body.get(key) == value, observations
'''
    folder = Path(run_dir)
    folder.mkdir(parents=True, exist_ok=True)
    index = len(list(folder.glob("test_candidate_*.py"))) + 1
    path = folder / f"test_candidate_{index}.py"
    path.write_text(source)
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    try:
        proc = subprocess.run([sys.executable, "-m", "pytest", str(path), "-q", "--tb=short", "-c", str(ROOT / "pytest.ini")],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
        status = "passed" if proc.returncode == 0 else "assertion_failed" if proc.returncode == 1 else "execution_error"
        logs = (proc.stdout + proc.stderr)[-8000:]
    except subprocess.TimeoutExpired:
        status, logs = "execution_error", "Test exceeded 20 seconds"
    observation_path = Path(str(path) + ".observations.json")
    return {"rule_id": candidate.rule_id, "candidate": candidate.model_dump(), "status": status,
            "artifact": str(path.relative_to(ROOT)), "log": logs,
            "observations": json.loads(observation_path.read_text()) if observation_path.exists() else []}
