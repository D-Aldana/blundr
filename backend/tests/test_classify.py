from app import config
from app.classify import (
    classify_conversion,
    classify_endgame,
    classify_tactical,
    classify_time_management,
    classify_weaknesses,
)
from conftest import make_row


def test_tactical_counts_only_big_misses_on_forcing_moves():
    rows = [
        make_row(cpl=200, best_is_forcing=True),   # counts
        make_row(cpl=400, best_is_forcing=True),   # counts
        make_row(cpl=140, best_is_forcing=True),   # under threshold
        make_row(cpl=300, best_is_forcing=False),  # quiet best move
        make_row(cpl=None, is_player_move=False, best_is_forcing=True),  # opponent
    ]
    result = classify_tactical(rows)
    assert result.instances == 2
    assert result.details["avg_cpl"] == 300
    # 2 misses in 4 meaningful moves is a 50% rate, far past severe.
    assert result.score == 1.0


def test_endgame_requires_low_piece_count():
    rows = [
        make_row(cpl=120, piece_count=10),
        make_row(cpl=150, piece_count=12),
        make_row(cpl=400, piece_count=13),  # too many pieces
        make_row(cpl=90, piece_count=6),    # under threshold
    ]
    result = classify_endgame(rows)
    assert result.instances == 2
    assert result.confidence == "insufficient"


def test_sample_size_guard_confidence_tiers():
    def tactical_with(n):
        rows = [make_row(cpl=200, best_is_forcing=True) for _ in range(n)]
        return classify_tactical(rows).confidence

    assert tactical_with(2) == "insufficient"
    assert tactical_with(3) == "low"
    assert tactical_with(5) == "low"
    assert tactical_with(6) == "ok"


def test_score_is_a_rate_against_opportunity_not_average_severity():
    # Same four misses, but one player had ten times as many chances to err.
    busy = [make_row(cpl=300, best_is_forcing=True) for _ in range(4)]
    busy += [make_row(cpl=0) for _ in range(396)]
    sloppy = [make_row(cpl=300, best_is_forcing=True) for _ in range(4)]
    sloppy += [make_row(cpl=0) for _ in range(36)]

    assert classify_tactical(busy).score < classify_tactical(sloppy).score
    assert classify_tactical(busy).instances == classify_tactical(sloppy).instances


def test_score_is_capped_at_one():
    rows = [make_row(cpl=1500, best_is_forcing=True) for _ in range(4)]
    assert classify_tactical(rows).score == 1.0


def test_an_elite_error_rate_does_not_read_as_severe():
    # 16 misses across ~870 meaningful moves — a real super-GM sample, well
    # under the calibrated severe rate.
    rows = [make_row(cpl=330, best_is_forcing=True) for _ in range(16)]
    rows += [make_row(cpl=20) for _ in range(853)]
    assert classify_tactical(rows).score < 0.25


def test_a_typical_club_rate_lands_mid_range():
    # The sweep's median club player: ~6 misses per 100 meaningful moves.
    rows = [make_row(cpl=300, best_is_forcing=True) for _ in range(30)]
    rows += [make_row(cpl=20) for _ in range(470)]
    assert 0.4 < classify_tactical(rows).score < 0.7


def test_severe_rates_are_above_every_rate_seen_at_the_median():
    # Guards the failure that started this: a constant set below the typical
    # observed rate pins every player at 1.0.
    assert config.SEVERE_RATE["tactical"] > 0.06
    assert config.SEVERE_RATE["endgame"] > 0.15
    assert config.SEVERE_RATE["time_management"] > 0.22
    assert config.SEVERE_RATE["conversion"] > 0.43


def test_time_management_flags_only_when_pressure_amplifies_errors():
    calm = [make_row(cpl=40, clock_pct=0.8) for _ in range(10)]
    rushed = [make_row(cpl=200, clock_pct=0.1) for _ in range(6)]
    result = classify_time_management(calm + rushed)

    assert result.details["ratio"] == 5.0
    assert result.details["gate_met"] is True
    assert result.instances == 6
    assert result.score > 0


def test_time_management_not_flagged_when_errors_are_uniform():
    calm = [make_row(cpl=150, clock_pct=0.8) for _ in range(10)]
    rushed = [make_row(cpl=150, clock_pct=0.1) for _ in range(6)]
    result = classify_time_management(calm + rushed)

    assert result.details["ratio"] == 1.0
    assert result.details["gate_met"] is False
    assert result.score == 0.0


def test_time_management_needs_enough_low_clock_moves():
    calm = [make_row(cpl=20, clock_pct=0.9) for _ in range(10)]
    rushed = [make_row(cpl=300, clock_pct=0.05) for _ in range(4)]
    result = classify_time_management(calm + rushed)

    assert result.details["low_bucket_moves"] == 4
    assert result.details["gate_met"] is False
    assert result.score == 0.0


def test_time_management_ignores_games_without_clock_data():
    rows = [make_row(cpl=300) for _ in range(10)]
    result = classify_time_management(rows)
    assert result.instances == 0
    assert result.confidence == "insufficient"


def _game(index, evals, result):
    return [
        make_row(game_index=index, ply=i + 1, eval_after_cp=cp, result=result)
        for i, cp in enumerate(evals)
    ]


def test_conversion_counts_once_per_blown_game():
    rows = (
        _game(0, [50, 400, 350, -200], "loss")   # blown
        + _game(1, [20, 500, 600, 800], "win")   # converted
        + _game(2, [10, 120, 90, 0], "draw")     # never winning
        + _game(3, [0, 350, 340, 330], "draw")   # winning, drawn anyway
    )
    result = classify_conversion(rows)

    assert result.instances == 2
    assert result.details["games_reached_winning"] == 3
    assert result.details["games_converted"] == 1
    assert {i["game_index"] for i in result.details["examples"]} == {0, 3}


def test_conversion_ignores_peak_on_final_move():
    rows = _game(0, [0, 100, 900], "win")
    assert classify_conversion(rows).instances == 0


def test_classify_returns_all_four_categories():
    names = [c.name for c in classify_weaknesses([make_row()])]
    assert names == ["tactical", "endgame", "time_management", "conversion"]


def test_thresholds_match_the_prd():
    assert config.TACTICAL_CPL_THRESHOLD == 150
    assert config.ENDGAME_CPL_THRESHOLD == 100
    assert config.ENDGAME_MAX_PIECES == 12
    assert config.TIME_RATIO_TRIGGER == 1.5
    assert config.CONVERSION_WINNING_CP == 300


def test_moves_in_already_won_positions_are_not_mistakes():
    rows = [
        # +11 to +8.5 is still completely winning — nothing was lost.
        make_row(cpl=254, best_is_forcing=True, eval_before_cp=1105, eval_after_cp=851),
        # Throwing a winning position away does count.
        make_row(cpl=800, best_is_forcing=True, eval_before_cp=900, eval_after_cp=100),
    ]
    result = classify_tactical(rows)
    assert result.instances == 1
    assert result.details["examples"][0]["cpl"] == 800


def test_moves_in_already_lost_positions_are_not_mistakes():
    rows = [make_row(cpl=400, best_is_forcing=True, eval_before_cp=-700, eval_after_cp=-1100)]
    assert classify_tactical(rows).instances == 0


def test_decided_positions_are_excluded_from_time_buckets():
    won = [
        make_row(cpl=600, clock_pct=0.1, eval_before_cp=1200, eval_after_cp=600)
        for _ in range(10)
    ]
    result = classify_time_management(won)
    assert result.details["low_bucket_moves"] == 0
    assert result.instances == 0


# --- Pattern shape -----------------------------------------------------------

from app.classify import _pattern  # noqa: E402


def _row(**kw):
    base = dict(eval_before_cp=0, move_number=10, result="win")
    base.update(kw)
    return make_row(**base)


def test_pattern_counts_the_situations_a_miss_happened_in():
    rows = [
        _row(eval_before_cp=300, move_number=40, result="loss"),
        _row(eval_before_cp=300, move_number=12, result="win"),
        _row(eval_before_cp=-200, move_number=35, result="loss"),
    ]
    assert _pattern(rows) == {
        "count": 3,
        "while_winning": 2,
        "after_move_30": 2,
        "in_games_lost": 2,
    }


def test_a_level_position_is_not_winning():
    """The 100cp band is noise, not an advantage the player squandered."""
    assert _pattern([_row(eval_before_cp=100)])["while_winning"] == 0
    assert _pattern([_row(eval_before_cp=101)])["while_winning"] == 1


def test_move_30_itself_is_not_late():
    assert _pattern([_row(move_number=30)])["after_move_30"] == 0
    assert _pattern([_row(move_number=31)])["after_move_30"] == 1


def test_no_flagged_moves_means_no_pattern():
    assert _pattern([]) == {}


def test_every_classifier_reports_a_pattern():
    """Including conversion, which counts whole games rather than moves."""
    rows = [
        make_row(cpl=300, best_is_forcing=True, piece_count=8, clock_pct=0.1,
                 eval_after_cp=700, move_number=35, result="loss"),
        make_row(cpl=250, best_is_forcing=True, piece_count=8, clock_pct=0.1,
                 eval_after_cp=50, move_number=36, result="loss"),
    ]
    for category in classify_weaknesses(rows):
        assert "pattern" in category.details, category.name
