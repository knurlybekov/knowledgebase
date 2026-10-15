"""Runner HTTP service inside the hermes-agent container (PLAN.md "Runner").

POST /runs                 create (idempotent on run_key); does not start the process
POST /runs/{key}/start     start the process (idempotent)
GET  /runs/{key}           state
GET  /runs/{key}/events    JSONL events with seq > after
POST /runs/{key}/cancel    SIGINT the process group, then SIGKILL
DELETE /runs/{key}         acknowledge: erase the terminal record and files (refused while active)
GET  /health               liveness
GET  /health/attestation   last configuration attestation
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
import attestation
from runs import REGISTRY_ROOT, RUNS_ROOT, Run, RunRecord, reconcile_orphans

SHARED_SECRET = os.environ.get("RUNNER_SHARED_SECRET", "")
MAX_CONCURRENT = int(os.environ.get("RUNNER_MAX_CONCURRENT", "4"))

app = FastAPI(title="knowledgebase hermes runner", docs_url=None, redoc_url=None, openapi_url=None)
_runs: dict[str, Run] = {}
_lock = threading.Lock()
_attestation: dict = {"ok": False, "detail": "not run"}


def _auth(authorization: str | None = Header(default=None)) -> None:
    if not SHARED_SECRET:
        raise HTTPException(500, "RUNNER_SHARED_SECRET is not configured")
    if not authorization or not secrets.compare_digest(authorization, f"Bearer {SHARED_SECRET}"):
        raise HTTPException(401, "runner secret required")


class CreateRun(BaseModel):
    run_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9:_-]+$")
    question: str = Field(min_length=1, max_length=4000)
    instructions: str = Field(min_length=1, max_length=20000)
    max_turns: int = Field(ge=1, le=100)
    max_tool_calls: int = Field(ge=1, le=200)
    timeout_s: int = Field(ge=10, le=3600)
    mcp_token: str = Field(min_length=16, max_length=256)
    model: str | None = None


_pending: dict[str, CreateRun] = {}


def _get(run_key: str) -> Run:
    run = _runs.get(run_key)
    if run is None:
        record = RunRecord.load(run_key)
        if record is None:
            raise HTTPException(404, "unknown run")
        run = Run(record)
        _runs[run_key] = run
    return run


def _state(run: Run) -> dict:
    r = run.record
    return {
        "run_key": r.run_key,
        "state": r.state,
        "exit_code": r.exit_code,
        "terminal": r.terminal,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/attestation", dependencies=[Depends(_auth)])
def health_attestation():
    return _attestation


@app.post("/runs", dependencies=[Depends(_auth)])
def create_run(body: CreateRun):
    if not _attestation.get("ok"):
        raise HTTPException(503, f"configuration attestation failed: {_attestation.get('detail')}")
    with _lock:
        existing = _runs.get(body.run_key) or (RunRecord.load(body.run_key) and _get(body.run_key))
        if existing:
            return JSONResponse(_state(existing), status_code=200)
        active = sum(1 for r in _runs.values() if r.active)
        if active >= MAX_CONCURRENT:
            raise HTTPException(429, f"too many concurrent runs (max {MAX_CONCURRENT})")
        safe = body.run_key.replace(":", "_")
        record = RunRecord(
            run_key=body.run_key,
            state="created",
            dir=str(RUNS_ROOT / safe),
            events_path=str(REGISTRY_ROOT / f"{safe}.events.jsonl"),
            timeout_s=body.timeout_s,
        )
        record.save()
        run = Run(record)
        _runs[body.run_key] = run
        _pending[body.run_key] = body
    return JSONResponse(_state(run), status_code=201)


@app.post("/runs/{run_key}/start", dependencies=[Depends(_auth)])
def start_run(run_key: str):
    run = _get(run_key)
    with _lock:
        body = _pending.pop(run_key, None)
        if run.record.state != "created":
            return _state(run)  # idempotent
        if body is None:
            raise HTTPException(
                409, "run was created by a previous runner process; create it again"
            )
        run.start(
            body.question,
            body.instructions,
            max_turns=body.max_turns,
            max_tool_calls=body.max_tool_calls,
            timeout_s=body.timeout_s,
            mcp_token=body.mcp_token,
            model=body.model,
        )
    return _state(run)


@app.get("/runs/{run_key}", dependencies=[Depends(_auth)])
def get_run(run_key: str):
    return _state(_get(run_key))


@app.get("/runs/{run_key}/events", dependencies=[Depends(_auth)])
def get_events(run_key: str, after: int = 0, wait_s: float = 0.0):
    run = _get(run_key)
    deadline = time.time() + min(max(wait_s, 0.0), 25.0)
    while True:
        events = run.events_after(after)
        if events or time.time() >= deadline or not run.active:
            break
        time.sleep(0.25)
    body = "".join(json.dumps(e) + "\n" for e in events)
    return PlainTextResponse(body, media_type="application/x-ndjson")


@app.post("/runs/{run_key}/cancel", dependencies=[Depends(_auth)])
def cancel_run(run_key: str):
    run = _get(run_key)
    cancelled = run.cancel()
    return {"cancelled": cancelled, **_state(run)}


@app.delete("/runs/{run_key}", dependencies=[Depends(_auth)])
def delete_run(run_key: str):
    run = _get(run_key)
    if run.active:
        raise HTTPException(409, "run is active; cancel it first")
    run.record.delete()
    _runs.pop(run_key, None)
    return {"deleted": True}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def main() -> None:
    global _attestation
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    reaped = reconcile_orphans()
    print(json.dumps({"event": "runner.startup", **reaped}), flush=True)
    _attestation = (
        attestation.run()
        if os.environ.get("RUNNER_SKIP_ATTESTATION") != "1"
        else {"ok": True, "detail": "skipped by env"}
    )
    print(json.dumps({"event": "runner.attestation", **_attestation}), flush=True)
    uvicorn.run(
        app, host="0.0.0.0", port=int(os.environ.get("RUNNER_PORT", "8700")), log_level="info"
    )


if __name__ == "__main__":
    main()
