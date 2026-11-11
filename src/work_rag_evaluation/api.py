"""HTTP API — sole evaluation backend for the Work Credit RAG stack.

KB Manager UI and CLIs should call this service instead of kb_manager.evaluation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .multiturn.runner import run_suite, write_report
from .retrieval.hitk import evaluate_hitk, write_hitk_report
from .retrieval.remap import remap_dataset

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(os.environ.get("EVAL_ARTIFACTS_DIR", str(ROOT / "artifacts")))
DATASETS = Path(os.environ.get("EVAL_DATASETS_DIR", str(ROOT / "datasets")))
ARTIFACTS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Work RAG Evaluation Suite", version="0.1.0")

_JOBS: dict[str, dict[str, Any]] = {}


class HitkRequest(BaseModel):
    dataset: str = Field(
        default="retrieval/eval_clean_remapped.json",
        description="Path relative to datasets/",
    )
    top_k: int = 5
    limit: int | None = None
    remap_from: str | None = Field(
        default=None,
        description="Optional legacy dataset to remap first (relative to datasets/)",
    )
    min_overlap: float = 0.30


class MultiturnRequest(BaseModel):
    conversations: str = "multiturn/conversations_v1.yaml"
    only: str | None = None
    orch_url: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "evaluation-suite"}


@app.get("/v1/datasets")
async def list_datasets() -> dict[str, Any]:
    items = []
    for p in sorted(DATASETS.rglob("*")):
        if p.is_file() and p.suffix in {".json", ".yaml", ".yml"}:
            items.append(str(p.relative_to(DATASETS)))
    return {"datasets": items}


@app.get("/v1/results/{suite}")
async def latest_results(suite: str) -> Any:
    mapping = {
        "hitk": ARTIFACTS / "hitk_latest.json",
        "multiturn": ARTIFACTS / "multiturn_latest.json",
    }
    path = mapping.get(suite)
    if not path or not path.exists():
        raise HTTPException(404, f"No results for suite={suite}")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/v1/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    return {k: v for k, v in job.items() if not k.startswith("_")}


async def _run_hitk_job(job_id: str, req: HitkRequest) -> None:
    job = _JOBS[job_id]
    try:
        if req.remap_from:
            src = DATASETS / req.remap_from
            dst = DATASETS / "retrieval/eval_clean_remapped.json"
            if not src.exists():
                raise FileNotFoundError(f"remap source missing: {src}")
            job["status"] = "remapping"
            stats = await remap_dataset(
                src, dst, limit=req.limit, min_overlap=req.min_overlap
            )
            job["remap"] = stats
            dataset_path = dst
        else:
            dataset_path = DATASETS / req.dataset
        if not dataset_path.exists():
            raise FileNotFoundError(f"dataset missing: {dataset_path}")
        job["status"] = "running"
        result = await evaluate_hitk(dataset_path, top_k=req.top_k, limit=req.limit)
        out = ARTIFACTS / "hitk_latest.json"
        write_hitk_report(result, out)
        job["status"] = "done"
        job["result_path"] = str(out)
        job["summary"] = {
            "n": result["n"],
            "hit1_rate": result["hit1_rate"],
            "hitk_rate": result["hitk_rate"],
            "top_k": result["top_k"],
        }
    except Exception as exc:
        log.exception("hitk job %s failed", job_id)
        job["status"] = "error"
        job["error"] = str(exc)[:500]
    job["finished_at"] = datetime.now(UTC).isoformat()


async def _run_multiturn_job(job_id: str, req: MultiturnRequest) -> None:
    job = _JOBS[job_id]
    try:
        path = DATASETS / req.conversations
        if not path.exists():
            raise FileNotFoundError(path)
        job["status"] = "running"
        result = await run_suite(path, only=req.only, orch_url=req.orch_url)
        out = ARTIFACTS / "multiturn_latest.json"
        write_report(result, out)
        job["status"] = "done"
        job["result_path"] = str(out)
        job["summary"] = {
            "passed": result["passed"],
            "failed": result["failed"],
            "total": result["total"],
        }
    except Exception as exc:
        log.exception("multiturn job %s failed", job_id)
        job["status"] = "error"
        job["error"] = str(exc)[:500]
    job["finished_at"] = datetime.now(UTC).isoformat()


@app.post("/v1/hitk/run")
async def run_hitk(req: HitkRequest) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {
        "id": job_id,
        "suite": "hitk",
        "status": "queued",
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "error": "",
    }
    _JOBS[job_id]["_task"] = asyncio.create_task(_run_hitk_job(job_id, req))
    return {"job_id": job_id, "status": "queued"}


@app.post("/v1/multiturn/run")
async def run_multiturn(req: MultiturnRequest) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {
        "id": job_id,
        "suite": "multiturn",
        "status": "queued",
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "error": "",
    }
    _JOBS[job_id]["_task"] = asyncio.create_task(_run_multiturn_job(job_id, req))
    return {"job_id": job_id, "status": "queued"}


def create_app() -> FastAPI:
    return app
