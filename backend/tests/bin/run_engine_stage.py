#!/usr/bin/env python3
"""Runs the engine stage under asyncio.run — the same shape uvicorn gives it —
and prints the outcome as JSON. Driven by test_engine_process.py, which can't
host engine subprocesses inside pytest-asyncio's loop.

Usage: run_engine_stage.py <ok|unparseable|missing_binary>
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import config, engine  # noqa: E402

PGN = """[White "TestPlayer"]
[Black "Rival"]
[Result "1-0"]
[TimeControl "180+2"]

1. e4 e5 2. Nf3 Nc6 1-0
"""


async def main(case: str) -> dict:
    # A list command works the same as a path; this one runs the stub under the
    # interpreter that has python-chess installed.
    config.STOCKFISH_PATH = [sys.executable, str(Path(__file__).parent / "fake_uci_engine.py")]
    games = [{"pgn": PGN, "url": "url0"}, {"pgn": PGN, "url": "url1"}]

    if case == "unparseable":
        games = [{"pgn": "not a pgn", "url": "u"}]
    elif case == "missing_binary":
        config.STOCKFISH_PATH = "/nonexistent/stockfish"
    elif case == "timeout":
        os.environ["FAKE_ENGINE_STALL"] = "1"
        config.ENGINE_TIMEOUT_S = 1.0

    progress = []
    try:
        rows = await engine.evaluate_games_with_stockfish(
            games, "TestPlayer", progress_cb=lambda d, t: progress.append([d, t])
        )
    except Exception as exc:
        return {"error": type(exc).__name__}

    return {
        "rows": len(rows),
        "progress": progress,
        "game_ids": sorted({r.game_id for r in rows}),
        "evals": sorted({r.eval_before_cp for r in rows}),
        "first_best_move": rows[0].best_move_san,
        "player_moves": sum(1 for r in rows if r.is_player_move),
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main(sys.argv[1]))))
