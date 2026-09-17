import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import CategoryResult, MoveRow  # noqa: E402


def make_row(**overrides) -> MoveRow:
    """A player move with no problems, overridden per test."""
    defaults = dict(
        game_index=0,
        game_id="g0",
        player_color="white",
        result="win",
        ply=1,
        move_number=1,
        is_player_move=True,
        san="e4",
        piece_count=32,
        eval_before_cp=20,
        eval_after_cp=20,
        cpl=0,
        best_move_san="e4",
        best_is_forcing=False,
        clock_remaining_s=None,
        clock_pct=None,
    )
    defaults.update(overrides)
    return MoveRow(**defaults)


def make_category(name, **overrides) -> CategoryResult:
    defaults = dict(name=name, score=0.5, confidence="ok", instances=6, details={})
    defaults.update(overrides)
    return CategoryResult(**defaults)


@pytest.fixture
def row_factory():
    return make_row
