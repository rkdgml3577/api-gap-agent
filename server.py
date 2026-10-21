import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)
from agent.graph import build_graph
from agent.approval import build_approver
from agent.llm import OllamaLLM
from agent.mcp_client import ToolClient
from tools.repository import list_endpoints

class AnalysisRequest(BaseModel):
    goal: str = Field(default="업무 규칙에 대한 검증 누락을 조사하고 테스트 실행 결과를 보고해 주세요.", max_length=2000)
    operations: list[Literal["create_order", "get_order", "cancel_order"]] = Field(default=["create_order", "get_order", "cancel_order"], min_length=1)
    variant: Literal["healthy", "buggy", "covered"] = "healthy"

@asynccontextmanager
async def lifespan(app):
    app.state.tasks = set()
    yield
    for task in list(app.state.tasks):
        task.cancel()
    await asyncio.gather(*app.state.tasks, return_exceptions=True)

app = FastAPI(title="API 검증 누락 탐지 Agent", lifespan=lifespan)
runs = {}
approvals = {}  # run_id -> asyncio.Future awaiting a human decision (kept out of the serializable run)

async def analyze(run_id, request):
    run = runs[run_id]
    folder = ROOT / "outputs" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    async def emit(event):
        entry = {"index": len(run["events"]), **event}
        run["events"].append(entry)
        with (folder / "events.jsonl").open("a") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
    llm = OllamaLLM()
    started = time.monotonic()
    try:
        async with ToolClient() as tools:
            catalog = await tools.catalog()
            approver = build_approver(run_id, emit, approvals)
            graph = build_graph(llm, tools, catalog, request, run_id, emit, approver)
            state = await graph.ainvoke({"observations": [], "steps": 0}, config={"recursion_limit": 100})
            run["result"] = {**state["result"], "observations": state.get("observations", []),
                             "steps": state.get("steps", 0), "tokens": llm.tokens,
                             "elapsed_seconds": round(time.monotonic() - started, 2), "model": llm.model}
    except asyncio.CancelledError:
        run["result"] = {"status": "incomplete", "message": "Analysis interrupted", "findings": []}
        raise
    except Exception as exc:
        run["result"] = {"status": "error", "message": str(exc)[:1500], "findings": []}
    finally:
        run["done"] = True
        await emit({"type": "final", "result": run["result"]})
        folder = ROOT / "outputs" / run_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "report.json").write_text(json.dumps(run, ensure_ascii=False, indent=2))

@app.get("/")
def index():
    return FileResponse(ROOT / "web_chat.html")

@app.get("/health")
async def health():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(os.getenv("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json()["models"]]
        return {"status": "ok", "model": os.getenv("OLLAMA_MODEL", "qwen3:8b"), "installed_models": models}
    except Exception as exc:
        return {"status": "ollama_unavailable", "message": str(exc)}

@app.get("/endpoints")
def endpoints():
    return list_endpoints()

@app.post("/analyses", status_code=202)
async def start(req: AnalysisRequest):
    if sum(not r["done"] for r in runs.values()) >= 1:
        raise HTTPException(409, "로컬 모델 분석이 진행 중입니다. 완료 후 다시 실행해 주세요.")
    run_id = uuid4().hex
    runs[run_id] = {"run_id": run_id, "request": req.model_dump(), "events": [], "done": False, "result": None}
    task = asyncio.create_task(analyze(run_id, req.model_dump()))
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)
    return {"run_id": run_id}

class ApprovalDecision(BaseModel):
    approved: bool
    feedback: str = Field(default="", max_length=1000)

@app.post("/analyses/{run_id}/approve")
async def approve(run_id: str, decision: ApprovalDecision):
    future = approvals.get(run_id)
    if future is None or future.done():
        raise HTTPException(409, "승인 대기 중인 분석이 없습니다.")
    future.set_result({"approved": decision.approved, "feedback": decision.feedback, "by": "human"})
    return {"ok": True}

@app.get("/analyses/{run_id}")
def report(run_id: str):
    if run_id in runs:
        return runs[run_id]
    if len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id):
        path = ROOT / "outputs" / run_id / "report.json"
        if path.is_file():
            return json.loads(path.read_text())
    raise HTTPException(404)

@app.get("/analyses/{run_id}/events")
async def events(run_id: str):
    run = report(run_id)
    async def stream():
        cursor = 0
        while True:
            for event in run["events"][cursor:]:
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                cursor += 1
            if run["done"]:
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
