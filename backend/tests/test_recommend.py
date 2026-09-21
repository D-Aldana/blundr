from app.recommend import (
    MAX_RECOMMENDATIONS,
    NO_LEAK_HEADLINE,
    headline,
    map_recommendations,
    rank_categories,
)
from conftest import make_category


def test_insufficient_and_zero_score_categories_never_rank():
    categories = [
        make_category("tactical", score=0.9, instances=2, confidence="insufficient"),
        make_category("endgame", score=0.0, instances=8),
        make_category("conversion", score=0.4, instances=5, confidence="low"),
    ]
    assert [c.name for c in rank_categories(categories)] == ["conversion"]


def test_ranking_is_by_score_since_the_score_is_already_a_rate():
    categories = [
        make_category("tactical", score=0.9, instances=3),
        make_category("endgame", score=0.4, instances=10),
        make_category("conversion", score=0.5, instances=4),
    ]
    assert [c.name for c in rank_categories(categories)] == [
        "tactical",
        "conversion",
        "endgame",
    ]


def test_ranking_ties_break_toward_the_better_evidenced_category():
    categories = [
        make_category("endgame", score=0.6, instances=4),
        make_category("tactical", score=0.6, instances=11),
    ]
    assert [c.name for c in rank_categories(categories)] == ["tactical", "endgame"]


def test_headline_follows_the_worst_category():
    categories = [make_category("conversion", score=0.7, instances=6)]
    assert "converting winning positions" in headline(categories)


def test_headline_when_nothing_qualifies():
    categories = [make_category("tactical", confidence="insufficient", instances=1)]
    assert headline(categories) == NO_LEAK_HEADLINE


def test_recommendations_are_capped_and_carry_evidence():
    categories = [
        make_category(
            "tactical", score=0.8, instances=7, details={"avg_cpl": 240, "examples": []}
        ),
        make_category(
            "endgame",
            score=0.6,
            instances=6,
            details={"avg_cpl": 150, "games_affected": 4, "examples": []},
        ),
        make_category(
            "conversion",
            score=0.5,
            instances=4,
            details={
                "games_reached_winning": 9,
                "games_converted": 5,
                "avg_drop_cp": 520,
                "examples": [],
            },
        ),
    ]
    recs = map_recommendations(categories)

    assert len(recs) == MAX_RECOMMENDATIONS
    assert [r.category for r in recs] == ["tactical", "endgame"]
    assert "7 positions" in recs[0].evidence
    assert "2.4 pawns" in recs[0].evidence
    assert "4 games" in recs[1].evidence


def test_time_management_evidence_quotes_the_ratio():
    categories = [
        make_category(
            "time_management",
            score=0.6,
            instances=9,
            details={
                "ratio": 2.3,
                "low_bucket_moves": 31,
                "low_bucket_avg_cpl": 92,
                "high_bucket_avg_cpl": 40,
                "examples": [],
            },
        )
    ]
    evidence = map_recommendations(categories)[0].evidence
    assert "2.3x worse" in evidence and "31 rushed moves" in evidence


def test_no_recommendations_when_no_category_qualifies():
    assert map_recommendations([make_category("tactical", confidence="insufficient")]) == []


# --- Pattern notes -----------------------------------------------------------

from app.recommend import _pattern_note  # noqa: E402


def _details(count, **counts):
    base = {"count": count, "while_winning": 0, "after_move_30": 0, "in_games_lost": 0}
    base.update(counts)
    return {"pattern": base}


def test_a_lopsided_pattern_is_named():
    note = _pattern_note(_details(9, while_winning=6))
    assert note == " 6 of those 9 came in positions you were already better in."


def test_an_even_spread_says_nothing():
    """Three of nine is where those moves happened to fall, not a habit."""
    assert _pattern_note(_details(9, while_winning=3, after_move_30=3)) == ""


def test_too_few_instances_to_have_a_shape():
    assert _pattern_note(_details(2, while_winning=2)) == ""


def test_only_the_strongest_pattern_is_said():
    """All three qualify; the report must not list every near-coincidence."""
    note = _pattern_note(_details(10, while_winning=8, in_games_lost=9, after_move_30=10))
    assert "already better in" in note
    assert "went on to lose" not in note and "after move 30" not in note


def test_losing_games_is_named_when_winning_positions_are_not():
    note = _pattern_note(_details(5, while_winning=1, in_games_lost=4))
    assert note == " 4 of those 5 came in games you went on to lose."


def test_missing_pattern_data_is_harmless():
    assert _pattern_note({}) == ""
    assert _pattern_note({"pattern": {}}) == ""


def test_the_note_rides_on_the_evidence_line():
    cats = [
        make_category("tactical", score=0.5, instances=9, details={
            "avg_cpl": 230, "opportunities": 300,
            "pattern": {"count": 9, "while_winning": 6,
                        "after_move_30": 0, "in_games_lost": 0},
        })
    ]
    evidence = map_recommendations(cats)[0].evidence
    assert "2.3 pawns given up" in evidence          # the original evidence survives
    assert "already better in" in evidence           # and the pattern is appended
