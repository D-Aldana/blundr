"""
Chess Weakness Analyzer — backend skeleton (v1)

Three endpoints per the PRD API contract:
  POST /eligibility        -> fast game-count check, no engine analysis
  POST /analyze             -> kicks off a background analysis job
  GET  /analyze/{job_id}    -> poll job status / retrieve report

No database, no Redis/Celery — an in-memory job store is enough for v1
(single instance, no persistence requirement). See PRD Section 13.
"""

import uuid
import asyncio
from enum import Enum
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Chess Weakness Analyzer")

# ---------------------------------------------------------------------------
# In-memory job store (v1 only — swap for Redis/db if this ever needs to
# survive a restart or run across multiple instances)
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

JOBS: dict[str, dict] = {}

MIN_GAMES_REQUIRED = 20
TIME_CONTROLS = ["bullet", "blitz", "rapid"]


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class EligibilityRequest(BaseModel):
    username: str
    time_control: str


class AnalyzeRequest(BaseModel):
    username: str
    time_control: str


# ---------------------------------------------------------------------------
# POST /eligibility
# ---------------------------------------------------------------------------

@app.post("/eligibility")
async def check_eligibility(req: EligibilityRequest):
    counts = await fetch_game_counts(req.username)  # {"bullet": N, "blitz": N, "rapid": N}

    if counts is None:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})

    game_count = counts.get(req.time_control, 0)

    if game_count >= MIN_GAMES_REQUIRED:
        return {"eligible": True, "game_count": game_count}

    alternatives = [
        {"time_control": tc, "game_count": c}
        for tc, c in counts.items()
        if tc != req.time_control and c >= MIN_GAMES_REQUIRED
    ]
    return {
        "eligible": False,
        "game_count": game_count,
        "alternatives": alternatives,
    }


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------

@app.post("/analyze")
async def start_analysis(req: AnalyzeRequest):
    counts = await fetch_game_counts(req.username)
    if counts is None:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})
    if counts.get(req.time_control, 0) < MIN_GAMES_REQUIRED:
        raise HTTPException(status_code=400, detail={"error": "not_eligible"})

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": JobStatus.RUNNING, "step": "fetching_games", "progress": 0.0}

    asyncio.create_task(run_analysis_job(job_id, req.username, req.time_control))

    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# GET /analyze/{job_id}
# ---------------------------------------------------------------------------

@app.get("/analyze/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    return job


# ---------------------------------------------------------------------------
# Background job pipeline
# ---------------------------------------------------------------------------

async def run_analysis_job(job_id: str, username: str, time_control: str):
    try:
        _update(job_id, step="fetching_games", progress=0.1)
        games = await fetch_last_n_games(username, time_control, n=MIN_GAMES_REQUIRED)

        _update(job_id, step="evaluating_games", progress=0.3)
        move_rows = await evaluate_games_with_stockfish(games)  # flat per-move dataset

        _update(job_id, step="classifying_weaknesses", progress=0.7)
        categories = classify_weaknesses(move_rows)  # rule-based, see thresholds doc

        _update(job_id, step="generating_recommendations", progress=0.85)
        recommendations = map_recommendations(categories)

        _update(job_id, step="writing_summary", progress=0.95)
        summary = await generate_llm_summary(categories, recommendations)  # guardrail-validated

        report = build_report(games, categories, recommendations, summary)

        JOBS[job_id] = {"status": JobStatus.DONE, "report": report}

    except Exception as exc:  # noqa: BLE001 — replace with narrower handling as pipeline solidifies
        JOBS[job_id] = {"status": JobStatus.FAILED, "error": str(exc)}


def _update(job_id: str, step: str, progress: float):
    JOBS[job_id] = {"status": JobStatus.RUNNING, "step": step, "progress": progress}


# ---------------------------------------------------------------------------
# Pipeline stubs — each of these gets filled in as its own focused piece
# ---------------------------------------------------------------------------

CHESS_COM_BASE = "https://api.chess.com/pub"

# Chess.com requires a descriptive User-Agent (app + contact) or returns 403.
# Replace the contact email before deploying.
CHESS_COM_HEADERS = {"User-Agent": "chess-weakness-analyzer/0.1 (you@example.com)"}

# Chess.com's `time_class` values we care about (bullet/blitz/rapid — daily excluded).
VALID_TIME_CLASSES = {"bullet", "blitz", "rapid"}


async def _fetch_archive_urls(client: "httpx.AsyncClient", username: str) -> list[str]:
    """GET /pub/player/{username}/games/archives -> list of monthly archive URLs,
    oldest first. Chess.com has no per-username "not found" body distinct from a
    plain 404, so a 404 here is how we detect an unknown username."""
    resp = await client.get(
        f"{CHESS_COM_BASE}/player/{username.lower()}/games/archives",
        headers=CHESS_COM_HEADERS,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["archives"]


async def _iter_recent_games(client: "httpx.AsyncClient", username: str):
    """Yield games newest-first by walking monthly archives backward.
    Chess.com has no "give me the last N games" endpoint — archives are
    monthly, so we pull whole months and filter/sort in-process."""
    archive_urls = await _fetch_archive_urls(client, username)
    if archive_urls is None:
        return  # unknown username — caller distinguishes via fetch_game_counts

    for url in reversed(archive_urls):  # most recent month first
        resp = await client.get(url, headers=CHESS_COM_HEADERS)
        resp.raise_for_status()
        games = resp.json().get("games", [])
        # Within a month, Chess.com returns games oldest-first; reverse for newest-first.
        for game in reversed(games):
            yield game


async def fetch_game_counts(username: str) -> Optional[dict]:
    """Return per-time-control counts, capped at MIN_GAMES_REQUIRED per bucket
    once we have enough to know eligibility — no need to walk a user's entire
    history just to confirm they clear the bar. Returns None if the username
    doesn't exist on Chess.com.

    Caps at 3x MIN_GAMES_REQUIRED per bucket purely to bound how many months
    we walk for very active players; good enough for an eligibility check,
    not meant to be an exact lifetime count.
    """
    counts = {tc: 0 for tc in VALID_TIME_CLASSES}
    cap = MIN_GAMES_REQUIRED * 3

    async with httpx.AsyncClient(timeout=10.0) as client:
        found_any = False
        async for game in _iter_recent_games(client, username):
            found_any = True
            tc = game.get("time_class")
            if tc in counts and counts[tc] < cap:
                counts[tc] += 1
            if all(c >= MIN_GAMES_REQUIRED or c >= cap for c in counts.values()):
                break
        else:
            if not found_any:
                # Distinguish "user exists, zero games" from "user not found":
                # _iter_recent_games already returns early (no yields) for both,
                # so re-check archive existence explicitly here.
                archives = await _fetch_archive_urls(client, username)
                if archives is None:
                    return None

    return counts


async def fetch_last_n_games(username: str, time_control: str, n: int) -> list:
    """Return the most recent n games (as PGN strings) for the given time
    control, newest first. Assumes eligibility was already checked — does
    not itself distinguish "not enough games" from "user not found"."""
    if time_control not in VALID_TIME_CLASSES:
        raise ValueError(f"unsupported time_control: {time_control}")

    matched: list[str] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        async for game in _iter_recent_games(client, username):
            if game.get("time_class") == time_control and "pgn" in game:
                matched.append(game["pgn"])
                if len(matched) >= n:
                    break

    return matched


async def evaluate_games_with_stockfish(games: list) -> list:
    """python-chess + Stockfish: return one row per move with eval/clock/phase data."""
    raise NotImplementedError


def classify_weaknesses(move_rows: list) -> list:
    """Apply the deterministic thresholds (tactical/endgame/time/conversion) to move_rows."""
    raise NotImplementedError


def map_recommendations(categories: list) -> list:
    """Deterministic lookup: worst categories -> specific, evidence-backed suggestions."""
    raise NotImplementedError


async def generate_llm_summary(categories: list, recommendations: list) -> str:
    """Call the LLM with only computed scores/counts, then validate output against them."""
    raise NotImplementedError


def build_report(games: list, categories: list, recommendations: list, summary: str) -> dict:
    """Assemble the final report payload matching the PRD's report shape."""
    raise NotImplementedError
