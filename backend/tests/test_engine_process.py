"""Exercises the real engine subprocess path — popen_uci, configure, analyse,
quit — against a stub UCI engine.

The stage runs in a child process under asyncio.run rather than in pytest's
event loop: pytest-asyncio's loop doesn't reap engine subprocesses, and
asyncio.run is how uvicorn runs this code anyway.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "tests" / "bin" / "run_engine_stage.py"


def run_stage(case: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), case],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=BACKEND,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_engine_is_launched_configured_and_shut_down():
    result = run_stage("ok")

    assert result["rows"] == 8  # 4 plies per game
    assert result["progress"] == [[1, 2], [2, 2]]
    assert result["game_ids"] == ["url0", "url1"]
    assert result["player_moves"] == 4
    assert result["evals"] == [-25, 25]  # the stub's eval, from each side's view
    assert result["first_best_move"] == "Nh3"  # the stub's first legal move


def test_unparseable_games_raise_rather_than_reporting_on_nothing():
    assert run_stage("unparseable") == {"error": "NoAnalyzableGames"}


def test_missing_engine_binary_surfaces_as_file_not_found():
    assert run_stage("missing_binary") == {"error": "FileNotFoundError"}


def test_a_wedged_engine_fails_the_job_instead_of_hanging():
    assert run_stage("timeout") == {"error": "TimeoutError"}
