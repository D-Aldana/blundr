"""End-to-end check of the stages between real PGN text and a report payload,
with the engine faked so it runs without a Stockfish binary."""

import chess
import chess.engine

from app.classify import classify_weaknesses
from app.engine import evaluate_game, parse_pgn
from app.recommend import map_recommendations
from app.report import build_report
from app.summary import fallback_summary, generate_llm_summary

PGN = """[Event "Live Chess"]
[White "TestPlayer"]
[Black "Rival"]
[Result "0-1"]
[TimeControl "300"]

1. e4 {[%clk 0:04:55]} e5 {[%clk 0:04:56]} 2. Nf3 {[%clk 0:04:45]} Nc6 {[%clk 0:04:50]}
3. Bc4 {[%clk 0:04:30]} Nf6 {[%clk 0:04:40]} 4. Ng5 {[%clk 0:04:10]} d5 {[%clk 0:04:20]}
5. exd5 {[%clk 0:00:25]} Nxd5 {[%clk 0:04:00]} 6. Nxf7 {[%clk 0:00:12]} Kxf7 {[%clk 0:03:50]} 0-1
"""


class ScriptedEngine:
    """Eval per ply, from the side-to-move's perspective."""

    def __init__(self, scores):
        self.scores = scores
        self.calls = 0

    async def analyse(self, board, limit):
        score = self.scores[min(self.calls, len(self.scores) - 1)]
        self.calls += 1
        return {
            "score": chess.engine.PovScore(chess.engine.Cp(score), board.turn),
            "pv": [next(iter(board.legal_moves))],
        }


async def _rows_for(game_index, scores):
    game = parse_pgn(PGN)
    return await evaluate_game(
        ScriptedEngine(scores), game, "TestPlayer", game_index, f"url{game_index}"
    )


async def test_pipeline_produces_a_grounded_report(monkeypatch):
    # White builds a +400, then gives it all back — the two worst moves coming
    # with under 10% of the clock left. Scores are side-to-move relative, so
    # they alternate sign around a stable evaluation.
    scores = [30, -30, 30, -30, 400, -400, 400, -100, 100, 200, -200, 300, -300]
    rows = []
    for index in range(20):
        rows.extend(await _rows_for(index, scores))

    categories = classify_weaknesses(rows)
    by_name = {c.name: c for c in categories}

    assert by_name["conversion"].instances == 20
    assert by_name["conversion"].confidence == "ok"

    time_mgmt = by_name["time_management"]
    assert time_mgmt.details["gate_met"] is True
    assert time_mgmt.details["ratio"] > 1.5
    assert time_mgmt.instances == 40  # two rushed blunders per game

    recommendations = map_recommendations(categories)
    assert recommendations, "a report this bad must recommend something"
    assert all(r.evidence for r in recommendations)

    monkeypatch.setattr(
        "app.summary._call_claude",
        _raise,
    )
    summary = await generate_llm_summary(categories, recommendations, 20, "blitz")
    report = build_report(categories, recommendations, summary, 20, "blitz", "TestPlayer")

    assert report["summary_source"] == "fallback"
    assert report["summary"] == fallback_summary(categories, recommendations)
    assert report["games_analyzed"] == 20
    assert len(report["categories"]) == 4
    assert all(0.0 <= c["score"] <= 1.0 for c in report["categories"])
    assert set(report["recommendations"][0]) == {"category", "text", "evidence"}
    # No category detail (examples, raw cpl lists) leaks into the payload.
    assert all(set(c) == {"name", "score", "confidence", "instances"} for c in report["categories"])


async def _raise(facts, correction=None):
    raise RuntimeError("no api key configured")


async def test_clean_games_produce_no_recommendations(monkeypatch):
    rows = []
    for index in range(20):
        rows.extend(await _rows_for(index, [20, -20] * 7))

    categories = classify_weaknesses(rows)
    assert all(c.score == 0.0 for c in categories)

    monkeypatch.setattr("app.summary._call_claude", _raise)
    summary = await generate_llm_summary(categories, [], 20, "blitz")
    report = build_report(categories, [], summary, 20, "blitz", "TestPlayer")

    assert report["recommendations"] == []
    assert "No single dominant leak" in report["headline"]
