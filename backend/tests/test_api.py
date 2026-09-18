import asyncio

import pytest
from fastapi.testclient import TestClient

from app import main
from app.models import MoveRow, SummaryResult

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_jobs():
    _reset_state()
    yield
    _reset_state()


def _reset_state():
    main.JOBS.clear()
    main._job_started.clear()
    main._rate_hits.clear()
    main._queue.clear()


def stub_counts(counts, monkeypatch):
    async def fake(username):
        return counts

    monkeypatch.setattr(main, "fetch_game_counts", fake)


def test_eligible_player(monkeypatch):
    stub_counts({"bullet": 3, "blitz": 47, "rapid": 1}, monkeypatch)
    resp = client.post("/eligibility", json={"username": "hikaru", "time_control": "blitz"})
    assert resp.json() == {"eligible": True, "game_count": 47}


def test_ineligible_player_gets_qualifying_alternatives(monkeypatch):
    stub_counts({"bullet": 61, "blitz": 8, "rapid": 23}, monkeypatch)
    body = client.post("/eligibility", json={"username": "player", "time_control": "blitz"}).json()

    assert body["eligible"] is False
    assert body["game_count"] == 8
    assert {a["time_control"] for a in body["alternatives"]} == {"bullet", "rapid"}


def test_ineligible_player_with_no_alternatives(monkeypatch):
    stub_counts({"bullet": 2, "blitz": 8, "rapid": 0}, monkeypatch)
    body = client.post("/eligibility", json={"username": "player", "time_control": "blitz"}).json()
    assert body["alternatives"] == []


def test_unknown_username(monkeypatch):
    stub_counts(None, monkeypatch)
    resp = client.post("/eligibility", json={"username": "nope", "time_control": "blitz"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == {"error": "user_not_found"}


def test_invalid_time_control_is_rejected_before_any_fetch():
    resp = client.post("/eligibility", json={"username": "player", "time_control": "daily"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == {"error": "invalid_time_control"}


def test_analyze_refuses_an_ineligible_player(monkeypatch):
    stub_counts({"bullet": 0, "blitz": 4, "rapid": 0}, monkeypatch)
    resp = client.post("/analyze", json={"username": "player", "time_control": "blitz"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == {"error": "not_eligible"}


def test_unknown_job_id():
    assert client.get("/analyze/nope").status_code == 404


def _stub_pipeline(monkeypatch, rows=None):
    stub_counts({"bullet": 0, "blitz": 30, "rapid": 0}, monkeypatch)

    async def fake_fetch(username, time_control, n):
        return [{"pgn": f"pgn{i}", "url": f"url{i}"} for i in range(n)]

    async def fake_eval(games, username, progress_cb=None):
        if progress_cb:
            progress_cb(len(games), len(games))
        return rows if rows is not None else [
            MoveRow(
                game_index=i,
                game_id=f"url{i}",
                player_color="white",
                result="loss",
                ply=1,
                move_number=10,
                is_player_move=True,
                san="Qh5",
                piece_count=20,
                eval_before_cp=100,
                eval_after_cp=-200,
                cpl=300,
                best_move_san="Nxe5",
                best_is_forcing=True,
            )
            for i in range(20)
        ]

    async def fake_summary(categories, recommendations, games_analyzed, time_control):
        return SummaryResult(text="A grounded paragraph.", source="llm")

    monkeypatch.setattr(main, "fetch_last_n_games", fake_fetch)
    monkeypatch.setattr(main, "evaluate_games_with_stockfish", fake_eval)
    monkeypatch.setattr(main, "generate_llm_summary", fake_summary)


def test_analysis_job_runs_through_to_a_report(monkeypatch):
    _stub_pipeline(monkeypatch)
    job_id = client.post("/analyze", json={"username": "player", "time_control": "blitz"}).json()["job_id"]
    body = client.get(f"/analyze/{job_id}").json()

    assert body["status"] == "done"
    report = body["report"]
    assert report["games_analyzed"] == 20
    assert report["time_control"] == "blitz"
    assert report["username"] == "player"
    assert [c["name"] for c in report["categories"]] == [
        "tactical",
        "endgame",
        "time_management",
        "conversion",
    ]
    assert report["recommendations"][0]["category"] == "tactical"
    assert "tactic" in report["headline"].lower()
    assert report["summary_source"] == "llm"


def test_job_failure_is_reported_not_raised(monkeypatch):
    _stub_pipeline(monkeypatch)

    async def boom(games, username, progress_cb=None):
        raise FileNotFoundError("stockfish")

    monkeypatch.setattr(main, "evaluate_games_with_stockfish", boom)
    job_id = client.post("/analyze", json={"username": "player", "time_control": "blitz"}).json()["job_id"]
    body = client.get(f"/analyze/{job_id}").json()

    assert body == {"status": "failed", "error": "engine_unavailable"}


def test_insufficient_categories_still_appear_in_the_report(monkeypatch):
    _stub_pipeline(monkeypatch)
    job_id = client.post("/analyze", json={"username": "player", "time_control": "blitz"}).json()["job_id"]
    categories = client.get(f"/analyze/{job_id}").json()["report"]["categories"]

    endgame = next(c for c in categories if c["name"] == "endgame")
    assert endgame["confidence"] == "insufficient"
    assert endgame["instances"] == 0


def test_healthz():
    assert client.get("/healthz").json() == {"ok": True}


def test_old_jobs_are_pruned_when_a_new_one_starts(monkeypatch):
    _stub_pipeline(monkeypatch)
    main.JOBS["stale"] = {"status": "done"}
    main._job_started["stale"] = main.time.monotonic() - main.JOB_TTL_S - 1

    client.post("/analyze", json={"username": "player", "time_control": "blitz"})

    assert "stale" not in main.JOBS
    assert "stale" not in main._job_started


def test_recent_jobs_survive_pruning(monkeypatch):
    _stub_pipeline(monkeypatch)
    main.JOBS["fresh"] = {"status": "done"}
    main._job_started["fresh"] = main.time.monotonic()

    client.post("/analyze", json={"username": "player", "time_control": "blitz"})

    assert "fresh" in main.JOBS


# --- abuse limits ------------------------------------------------------------


@pytest.mark.parametrize(
    "username",
    ["../../../foo", "a?x=1", "a#frag", "ab", "x" * 26, "has space", "semi;colon"],
)
@pytest.mark.parametrize("endpoint", ["/eligibility", "/analyze"])
def test_malformed_usernames_are_rejected(endpoint, username, monkeypatch):
    def explode(_username):
        raise AssertionError("no fetch should happen for a malformed username")

    monkeypatch.setattr(main, "fetch_game_counts", explode)
    resp = client.post(endpoint, json={"username": username, "time_control": "blitz"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == {"error": "invalid_username"}


def test_analyze_is_rate_limited_per_ip(monkeypatch):
    _stub_pipeline(monkeypatch)
    monkeypatch.setattr(main.config, "RATE_LIMIT_ANALYZE", (2, 3600.0))

    for _ in range(2):
        assert client.post("/analyze", json={"username": "player", "time_control": "blitz"}).status_code == 200

    resp = client.post("/analyze", json={"username": "player", "time_control": "blitz"})
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "rate_limited"
    assert int(resp.headers["retry-after"]) > 0


def test_eligibility_and_analyze_have_separate_quotas(monkeypatch):
    _stub_pipeline(monkeypatch)
    stub_counts({"bullet": 0, "blitz": 47, "rapid": 0}, monkeypatch)
    monkeypatch.setattr(main.config, "RATE_LIMIT_ANALYZE", (1, 3600.0))

    client.post("/analyze", json={"username": "player", "time_control": "blitz"})
    assert client.post("/analyze", json={"username": "player", "time_control": "blitz"}).status_code == 429

    # Exhausting the analysis quota must not lock someone out of the cheap check.
    assert client.post("/eligibility", json={"username": "player", "time_control": "blitz"}).status_code == 200


def test_analyze_refuses_work_when_the_queue_is_full(monkeypatch):
    _stub_pipeline(monkeypatch)
    monkeypatch.setattr(main.config, "MAX_CONCURRENT_ANALYSES", 0)
    monkeypatch.setattr(main.config, "MAX_QUEUED_ANALYSES", 0)

    resp = client.post("/analyze", json={"username": "player", "time_control": "blitz"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == {"error": "busy"}
    assert resp.headers["retry-after"] == "60"


def test_a_queued_job_reports_its_position():
    main.JOBS["waiting"] = {"status": "running", "step": "queued", "progress": 0.1}
    main._queue.extend(["ahead", "waiting"])

    body = client.get("/analyze/waiting").json()
    assert body["queue_position"] == 2


async def test_engine_slots_serialise_the_engine_stage(monkeypatch):
    """The whole point of the cap: two jobs never run Stockfish at once."""
    monkeypatch.setattr(main, "_engine_slots", asyncio.Semaphore(1))
    holding: list[str] = []
    peak = 0

    async def job(job_id):
        nonlocal peak
        async with main._engine_slot(job_id):
            holding.append(job_id)
            peak = max(peak, len(holding))
            await asyncio.sleep(0.01)
            holding.remove(job_id)

    await asyncio.gather(job("a"), job("b"), job("c"))
    assert peak == 1
    assert main._queue == []


async def test_a_job_waiting_for_a_slot_is_marked_queued(monkeypatch):
    monkeypatch.setattr(main, "_engine_slots", asyncio.Semaphore(1))
    main.JOBS["second"] = {"status": "running"}

    async with main._engine_slot("first"):
        waiter = asyncio.create_task(_hold("second"))
        await asyncio.sleep(0)  # let it reach the queue
        assert main.JOBS["second"]["step"] == "queued"
        assert main._queue == ["second"]

    await waiter


async def _hold(job_id):
    async with main._engine_slot(job_id):
        pass
