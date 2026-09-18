"""
Chess Weakness Analyzer — backend API (v1)

Three endpoints per the PRD API contract:
  POST /eligibility        -> fast game-count check, no engine analysis
  POST /analyze            -> kicks off a background analysis job
  GET  /analyze/{job_id}   -> poll job status / retrieve report

No database, no Redis/Celery — an in-memory job store is enough for v1
(single instance, no persistence requirement). See PRD Section 13.
"""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config
from .chesscom import fetch_game_counts, fetch_last_n_games
from .classify import classify_weaknesses
from .engine import evaluate_games_with_stockfish
from .recommend import map_recommendations
from .report import build_report
from .summary import generate_llm_summary

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

app = FastAPI(title="Chess Weakness Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


JOBS: dict[str, dict] = {}
JOB_TTL_S = 3600.0
_job_started: dict[str, float] = {}
# asyncio only holds weak references to tasks, so a job that nothing keeps a
# reference to can be garbage-collected mid-run.
_running: set[asyncio.Task] = set()


# Only MAX_CONCURRENT_ANALYSES engine stages run at once; the rest wait here in
# arrival order so a caller can be told where they are in line.
_engine_slots = asyncio.Semaphore(config.MAX_CONCURRENT_ANALYSES)
_queue: list[str] = []

# Per-IP sliding windows, keyed (bucket, ip) -> hit timestamps.
_rate_hits: dict[tuple[str, str], list[float]] = {}


def _client_ip(request: Request) -> str:
    # X-Forwarded-For is forgeable unless a proxy in front overwrites it, so
    # it is consulted only when the deployment says one is there.
    if config.TRUST_PROXY_HEADER:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune_rate_hits(now: float) -> None:
    if len(_rate_hits) < 1024:
        return
    longest = max(config.RATE_LIMIT_ANALYZE[1], config.RATE_LIMIT_ELIGIBILITY[1])
    for key in [k for k, ts in _rate_hits.items() if not ts or now - ts[-1] >= longest]:
        del _rate_hits[key]


def _rate_limit(request: Request, bucket: str, rule: tuple[int, float]) -> None:
    limit, window = rule
    now = time.monotonic()
    key = (bucket, _client_ip(request))
    hits = [t for t in _rate_hits.get(key, []) if now - t < window]

    if len(hits) >= limit:
        _rate_hits[key] = hits
        retry_after = int(window - (now - hits[0])) + 1
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after_s": retry_after},
            headers={"Retry-After": str(retry_after)},
        )

    hits.append(now)
    _rate_hits[key] = hits
    _prune_rate_hits(now)


@asynccontextmanager
async def _engine_slot(job_id: str):
    """Hold one of the engine's concurrency slots for the duration of the
    engine stage, queueing until one frees up."""
    _queue.append(job_id)
    _update(job_id, step="queued", progress=0.1)
    try:
        await _engine_slots.acquire()
    finally:
        if job_id in _queue:
            _queue.remove(job_id)
    try:
        yield
    finally:
        _engine_slots.release()


def _prune_jobs():
    cutoff = time.monotonic() - JOB_TTL_S
    for job_id in [j for j, started in _job_started.items() if started < cutoff]:
        JOBS.pop(job_id, None)
        _job_started.pop(job_id, None)


class EligibilityRequest(BaseModel):
    username: str
    time_control: str


class AnalyzeRequest(BaseModel):
    username: str
    time_control: str


def _validate_username(username: str):
    if not config.USERNAME_PATTERN.match(username):
        raise HTTPException(status_code=400, detail={"error": "invalid_username"})


def _validate_time_control(time_control: str):
    if time_control not in config.VALID_TIME_CLASSES:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_time_control"}
        )


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.post("/eligibility")
async def check_eligibility(req: EligibilityRequest, request: Request):
    _rate_limit(request, "eligibility", config.RATE_LIMIT_ELIGIBILITY)
    _validate_username(req.username)
    _validate_time_control(req.time_control)
    counts = await fetch_game_counts(req.username)

    if counts is None:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})

    game_count = counts.get(req.time_control, 0)
    if game_count >= config.MIN_GAMES_REQUIRED:
        return {"eligible": True, "game_count": game_count}

    alternatives = [
        {"time_control": tc, "game_count": c}
        for tc, c in counts.items()
        if tc != req.time_control and c >= config.MIN_GAMES_REQUIRED
    ]
    return {
        "eligible": False,
        "game_count": game_count,
        "alternatives": alternatives,
    }


@app.post("/analyze")
async def start_analysis(req: AnalyzeRequest, request: Request):
    _rate_limit(request, "analyze", config.RATE_LIMIT_ANALYZE)
    _validate_username(req.username)
    _validate_time_control(req.time_control)

    # Admission control: refuse outright rather than accepting work that would
    # sit behind an unbounded queue.
    if len(_running) >= config.MAX_CONCURRENT_ANALYSES + config.MAX_QUEUED_ANALYSES:
        raise HTTPException(
            status_code=503,
            detail={"error": "busy"},
            headers={"Retry-After": "60"},
        )

    counts = await fetch_game_counts(req.username)
    if counts is None:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})
    if counts.get(req.time_control, 0) < config.MIN_GAMES_REQUIRED:
        raise HTTPException(status_code=400, detail={"error": "not_eligible"})

    _prune_jobs()
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": JobStatus.RUNNING,
        "step": "fetching_games",
        "progress": 0.0,
    }
    _job_started[job_id] = time.monotonic()

    task = asyncio.create_task(run_analysis_job(job_id, req.username, req.time_control))
    _running.add(task)
    task.add_done_callback(_running.discard)
    return {"job_id": job_id}


@app.get("/analyze/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    if job.get("step") == "queued" and job_id in _queue:
        return {**job, "queue_position": _queue.index(job_id) + 1}
    return job


# ---------------------------------------------------------------------------
# Background job pipeline
# ---------------------------------------------------------------------------

# The engine stage dominates the wall clock, so it owns most of the progress bar.
EVAL_PROGRESS_START = 0.15
EVAL_PROGRESS_END = 0.75


async def run_analysis_job(job_id: str, username: str, time_control: str):
    try:
        _update(job_id, step="fetching_games", progress=0.05)
        games = await fetch_last_n_games(
            username, time_control, n=config.MIN_GAMES_REQUIRED
        )
        if len(games) < config.MIN_GAMES_REQUIRED:
            raise RuntimeError("not_enough_games")

        def on_game_done(done: int, total: int):
            span = EVAL_PROGRESS_END - EVAL_PROGRESS_START
            _update(
                job_id,
                step="evaluating_games",
                progress=EVAL_PROGRESS_START + span * (done / total),
            )

        async with _engine_slot(job_id):
            _update(job_id, step="evaluating_games", progress=EVAL_PROGRESS_START)
            move_rows = await evaluate_games_with_stockfish(
                games, username, progress_cb=on_game_done
            )

        _update(job_id, step="classifying_weaknesses", progress=0.8)
        categories = classify_weaknesses(move_rows)

        _update(job_id, step="generating_recommendations", progress=0.88)
        recommendations = map_recommendations(categories)

        _update(job_id, step="writing_summary", progress=0.94)
        summary = await generate_llm_summary(
            categories, recommendations, len(games), time_control
        )

        JOBS[job_id] = {
            "status": JobStatus.DONE,
            "report": build_report(
                categories, recommendations, summary, len(games), time_control, username
            ),
        }

    except Exception as exc:  # noqa: BLE001 — every failure becomes a job status
        log.exception("analysis job %s failed", job_id)
        JOBS[job_id] = {"status": JobStatus.FAILED, "error": _error_code(exc)}


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ValueError) and str(exc) == "invalid_username":
        return "invalid_username"
    if isinstance(exc, FileNotFoundError):
        return "engine_unavailable"
    if isinstance(exc, asyncio.TimeoutError):
        return "stockfish_timeout"
    return str(exc) or exc.__class__.__name__


def _update(job_id: str, step: str, progress: float):
    JOBS[job_id] = {
        "status": JobStatus.RUNNING,
        "step": step,
        "progress": round(progress, 2),
    }
