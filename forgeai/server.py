"""Web API for the factory UI and the chat runner. `python -m forgeai serve`.

Runs are plain folders under runs/; the API only reads/writes there. With Ollama offline it still serves
committed runs read-only ("replay mode"), which is what a free-tier host can offer."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .llm import OllamaLLM
from .schemas import AgentDefinition, Requirements

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
RUNS.mkdir(exist_ok=True)
INPUT_SETS = [ROOT / "demos", ROOT / "holdout"]
_SAFE = re.compile(r"^[A-Za-z0-9_.\-]+$")
ARTIFACTS = re.compile(r"^(brief\.md|requirements\.(json|md)|agent(_v\d+)?\.json|candidate_\d\.json|tournament\.json|"
                       r"tool_selection\.json|evalset\.json|evalgen_log\.json|scorecards\.json|iteration_log\.json|"
                       r"report\.md|run\.json|baseline_comparison\.(md|json)|judge_agreement\.json|regression\.(md|json))$")

app = FastAPI(title="ForgeAI")
_active: dict[str, dict] = {}  # run id -> {"thread", "error", "checkpoint": Event, "req": Requirements|None}
_runtimes: dict[str, object] = {}


def _run_dir(rid: str) -> Path:
    if not _SAFE.match(rid) or not (RUNS / rid).is_dir():
        raise HTTPException(404, "unknown run")
    return RUNS / rid


def _inside(p: Path, roots: list[Path]) -> bool:
    p = p.resolve()
    return any(p.is_relative_to(r.resolve()) for r in roots)


@app.get("/api/health")
def health():
    return OllamaLLM().health()


@app.get("/api/inputs")
def inputs():
    """Brief + document sets shipped in the repo (demos and held-out)."""
    out = []
    for base in INPUT_SETS:
        for brief in sorted(base.rglob("brief.md")):
            docs = brief.parent / "docs"
            if docs.is_dir():
                out.append({"id": str(brief.parent.relative_to(ROOT)).replace("\\", "/"), "group": base.name,
                            "brief": brief.read_text(encoding="utf-8"),
                            "docs": sorted(p.name for p in docs.iterdir() if p.is_file())})
    return out


@app.get("/api/runs")
def list_runs():
    out = []
    for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        meta = json.loads((d / "run.json").read_text(encoding="utf-8")) if (d / "run.json").exists() else {}
        a = _active.get(d.name)
        ev = d / "events.jsonl"
        # runs started from the CLI aren't in _active: an unfinished run whose log moved recently is still running
        fresh = ev.exists() and time.time() - ev.stat().st_mtime < 300
        status = "running" if (a and a["thread"].is_alive()) or (not a and not meta.get("finished") and fresh) else \
            ("failed" if a and a.get("error") else ("done" if meta.get("finished") else "incomplete"))
        if not meta.get("name") and ev.exists():
            with open(ev, encoding="utf-8") as f:
                meta["name"] = json.loads(f.readline() or "{}").get("name")
        if a and a.get("req") is not None and not a["checkpoint"].is_set():
            status = "awaiting_approval"
        out.append({"id": d.name, "status": status, "error": (a or {}).get("error"), "name": meta.get("name") or d.name,
                    "final": meta.get("final"), "stop_reason": meta.get("stop_reason"), "duration_s": meta.get("duration_s"),
                    "tokens": meta.get("tokens"), "model": meta.get("model"), "updated": d.stat().st_mtime})
    return out


class StartRun(BaseModel):
    name: str
    input_id: str | None = None   # e.g. "demos/hr_policy"
    brief: str | None = None      # overrides the input set's brief
    answers: list[str] | None = None
    candidates: int = 3
    iters: int = 3
    budget_tokens: int | None = None
    budget_seconds: float | None = None
    checkpoint: bool = False


def _start(rid: str, brief: str, docs: Path, req: StartRun):
    from .pipeline import Factory
    out = RUNS / rid
    out.mkdir(parents=True, exist_ok=True)
    state = {"error": None, "checkpoint": threading.Event(), "req": None}

    def checkpoint(r: Requirements) -> Requirements:
        state["req"] = r
        (out / "requirements.pending.json").write_text(r.model_dump_json(indent=2), encoding="utf-8")
        state["checkpoint"].wait()
        return state["req"]

    def work():
        try:
            Factory(OllamaLLM(), out, max_iters=req.iters, candidates=req.candidates, budget_tokens=req.budget_tokens,
                    budget_seconds=req.budget_seconds).run(brief, docs, req.name, answers=req.answers,
                                                            checkpoint=checkpoint if req.checkpoint else None)
        except Exception as e:  # surfaced to the UI; the traceback is in the server log
            state["error"] = f"{type(e).__name__}: {e}"
            with open(out / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.time(), "stage": "error", "status": "failed", "error": state["error"]}) + "\n")
            raise
    state["thread"] = threading.Thread(target=work, daemon=True)
    _active[rid] = state
    state["thread"].start()


def _new_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "run"
    return f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}"


READONLY = os.getenv("FORGE_READONLY") == "1"  # public hosting: show committed runs, accept no work from strangers
MAX_FILE_BYTES, MAX_FILES = 20 * 1024 * 1024, 20


def _preflight():
    """Every endpoint that writes files or spends model time goes through here."""
    if READONLY:
        raise HTTPException(403, "This deployment is read-only. Run ForgeAI locally to start runs or chat.")
    h = OllamaLLM().health()
    if not h.get("ok"):
        raise HTTPException(503, f"Ollama is not ready: {h.get('error') or h.get('missing')}")


@app.post("/api/runs")
def start_run(req: StartRun):
    _preflight()
    if not req.input_id:
        raise HTTPException(400, "input_id required (or use /api/runs/upload)")
    base = (ROOT / req.input_id).resolve()
    if not _inside(base, INPUT_SETS) or not (base / "docs").is_dir():
        raise HTTPException(400, "unknown input set")
    brief = req.brief or (base / "brief.md").read_text(encoding="utf-8")
    rid = _new_id(req.name)
    _start(rid, brief, base / "docs", req)
    return {"id": rid}


@app.post("/api/runs/upload")
async def upload_run(name: str = Form(...), brief: str = Form(...), checkpoint: bool = Form(False),
                     candidates: int = Form(3), files: list[UploadFile] = File(...)):
    _preflight()
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"at most {MAX_FILES} files per run")
    rid = _new_id(name)
    docs = RUNS / rid / "input_docs"
    docs.mkdir(parents=True)
    for f in files:
        fname = Path(f.filename or "").name
        data = await f.read(MAX_FILE_BYTES + 1)
        problem = ("unsupported file name or type" if not _SAFE.match(fname) or
                   Path(fname).suffix.lower() not in {".pdf", ".md", ".txt", ".csv"}
                   else "file larger than 20 MB" if len(data) > MAX_FILE_BYTES else None)
        if problem:
            shutil.rmtree(RUNS / rid)
            raise HTTPException(400, f"{problem}: {f.filename}")
        (docs / fname).write_bytes(data)
    _start(rid, brief, docs, StartRun(name=name, checkpoint=checkpoint, candidates=candidates))
    return {"id": rid}


@app.get("/api/runs/{rid}/events")
async def events(rid: str):
    path = _run_dir(rid) / "events.jsonl"

    async def gen():
        pos = 0
        while True:
            if path.exists():
                with open(path, "rb") as f:
                    f.seek(pos)
                    chunk = f.read()
                complete = chunk[:chunk.rfind(b"\n") + 1]  # never emit a half-written line
                pos += len(complete)
                for line in complete.decode("utf-8").splitlines():
                    if line.strip():
                        yield {"data": line}
            a = _active.get(rid)
            if not a or not a["thread"].is_alive():
                yield {"event": "end", "data": "{}"}
                return
            await asyncio.sleep(0.5)
    return EventSourceResponse(gen())


@app.get("/api/runs/{rid}/artifacts/{name}")
def artifact(rid: str, name: str):
    if not ARTIFACTS.match(name):
        raise HTTPException(404, "not an artifact")
    p = _run_dir(rid) / ("regression" if name.startswith("regression.") else "") / name  # `regress` writes a subfolder
    if not p.exists():
        raise HTTPException(404, "not produced (yet)")
    if name.endswith(".json"):
        return JSONResponse(json.loads(p.read_text(encoding="utf-8")))
    return FileResponse(p, media_type="text/markdown")


@app.get("/api/runs/{rid}/checkpoint")
def get_checkpoint(rid: str):
    a = _active.get(rid)
    if not a or a.get("req") is None or a["checkpoint"].is_set():
        raise HTTPException(404, "nothing awaiting approval")
    return JSONResponse(a["req"].model_dump(mode="json"))


@app.post("/api/runs/{rid}/checkpoint")
def approve(rid: str, body: dict):
    a = _active.get(rid)
    if not a or a.get("req") is None or a["checkpoint"].is_set():
        raise HTTPException(404, "nothing awaiting approval")
    a["req"] = Requirements.model_validate(body)  # human edits are validated like any other artifact
    a["checkpoint"].set()
    return {"ok": True}


class Ask(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/api/chat/{rid}")
def chat(rid: str, body: Ask):
    from .agent_runtime import AgentRuntime
    _preflight()
    d = _run_dir(rid)
    if not (d / "agent.json").exists():
        raise HTTPException(409, "this run has not produced an agent yet")
    key = f"{rid}@{(d / 'agent.json').stat().st_mtime_ns}"  # a re-run into the same folder must load the new agent
    if key not in _runtimes:
        defn = AgentDefinition.model_validate_json((d / "agent.json").read_text(encoding="utf-8"))
        if not Path(defn.docs_path).is_dir():  # committed runs carry absolute paths from another machine
            local = d / "input_docs" if (d / "input_docs").is_dir() else None
            for base in INPUT_SETS:
                for cand in base.rglob("docs"):
                    if cand.is_dir() and cand.parent.name in defn.docs_path:
                        local = cand
            if not local:
                raise HTTPException(409, "the agent's document folder is not available on this machine")
            defn.docs_path = str(local)
        meta = json.loads((d / "run.json").read_text(encoding="utf-8")) if (d / "run.json").exists() else {}
        # chat with the exact models the agent was built and tested with, not the server's defaults
        _runtimes[key] = AgentRuntime(defn, OllamaLLM(**{k: meta[k] for k in ("model", "judge_model", "embed_model") if meta.get(k)}))
    tr = _runtimes[key].ask(body.question[:2000], body.history[-6:])
    return tr.model_dump(mode="json")


# Answers run as server-side jobs so a page refresh never kills one: the browser keeps the job id and re-attaches.
# shortcut: jobs live in this process's memory for an hour; a server restart loses unfinished ones (the UI says so)
_jobs: dict[str, dict] = {}


@app.post("/api/chat/{rid}/jobs")
def start_chat_job(rid: str, body: Ask):
    _run_dir(rid)
    _preflight()
    now = time.time()
    for old in [j for j, v in _jobs.items() if now - v["started"] > 3600]:
        _jobs.pop(old, None)
    jid = os.urandom(8).hex()
    _jobs[jid] = {"status": "running", "rid": rid, "started": now}

    def work():
        try:
            _jobs[jid].update(status="done", trace=chat(rid, body))
        except HTTPException as e:
            _jobs[jid].update(status="error", error=str(e.detail))
        except Exception as e:  # surfaced to the UI; full traceback in the server log
            _jobs[jid].update(status="error", error=f"{type(e).__name__}: {e}")
            raise
    threading.Thread(target=work, daemon=True).start()
    return {"job": jid}


@app.get("/api/chat/jobs/{jid}")
def chat_job(jid: str):
    if jid not in _jobs:
        raise HTTPException(404, "This answer is no longer on the server (it restarted). Ask again.")
    return {k: v for k, v in _jobs[jid].items() if k != "rid"}


_dist = ROOT / "web" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
