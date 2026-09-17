import pytest
from fastapi.testclient import TestClient

from app import main
from app.models import MoveRow, SummaryResult

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_jobs():
    main.JOBS.clear()
    main._job_started.clear()
    yield
    main.JOBS.clear()
    main._job_started.clear()


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
    body = client.post("/eligibility", json={"username": "x", "time_control": "blitz"}).json()

    assert body["eligible"] is False
    assert body["game_count"] == 8
    assert {a["time_control"] for a in body["alternatives"]} == {"bullet", "rapid"}


def test_ineligible_player_with_no_alternatives(monkeypatch):
    stub_counts({"bullet": 2, "blitz": 8, "rapid": 0}, monkeypatch)
    body = client.post("/eligibility", json={"username": "x", "time_control": "blitz"}).json()
    assert body["alternatives"] == []


def test_unknown_username(monkeypatch):
    stub_counts(None, monkeypatch)
    resp = client.post("/eligibility", json={"username": "nope", "time_control": "blitz"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == {"error": "user_not_found"}


def test_invalid_time_control_is_rejected_before_any_fetch():
    resp = client.post("/eligibility", json={"username": "x", "time_control": "daily"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == {"error": "invalid_time_control"}


def test_analyze_refuses_an_ineligible_player(monkeypatch):
    stub_counts({"bullet": 0, "blitz": 4, "rapid": 0}, monkeypatch)
    resp = client.post("/analyze", json={"username": "x", "time_control": "blitz"})
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
    job_id = client.post("/analyze", json={"username": "x", "time_control": "blitz"}).json()["job_id"]
    body = client.get(f"/analyze/{job_id}").json()

    assert body["status"] == "done"
    report = body["report"]
    assert report["games_analyzed"] == 20
    assert report["time_control"] == "blitz"
    assert report["username"] == "x"
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
    job_id = client.post("/analyze", json={"username": "x", "time_control": "blitz"}).json()["job_id"]
    body = client.get(f"/analyze/{job_id}").json()

    assert body == {"status": "failed", "error": "engine_unavailable"}


def test_insufficient_categories_still_appear_in_the_report(monkeypatch):
    _stub_pipeline(monkeypatch)
    job_id = client.post("/analyze", json={"username": "x", "time_control": "blitz"}).json()["job_id"]
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

    client.post("/analyze", json={"username": "x", "time_control": "blitz"})

    assert "stale" not in main.JOBS
    assert "stale" not in main._job_started


def test_recent_jobs_survive_pruning(monkeypatch):
    _stub_pipeline(monkeypatch)
    main.JOBS["fresh"] = {"status": "done"}
    main._job_started["fresh"] = main.time.monotonic()

    client.post("/analyze", json={"username": "x", "time_control": "blitz"})

    assert "fresh" in main.JOBS
