"""Deterministic weakness classifiers (PRD section 15).

Nothing here is a model — each category is a threshold rule over the flat
MoveRow dataset, so every number in a report can be traced back to specific
moves in specific games.
"""

from statistics import mean

from . import config
from .models import CategoryResult, MoveRow

CATEGORIES = ("tactical", "endgame", "time_management", "conversion")


def _confidence(instances: int) -> str:
    if instances < config.MIN_INSTANCES:
        return "insufficient"
    if instances <= config.LOW_CONFIDENCE_MAX:
        return "low"
    return "ok"


def _score(instances: int, opportunities: int, category: str) -> float:
    """How often the category fires, against how often it could have.

    Severity is what qualifies a move as an instance in the first place (the
    centipawn thresholds); the score is then about frequency. Scoring on
    average severity instead makes every category saturate, because a move only
    qualifies once it's already a big mistake.
    """
    if not instances or not opportunities:
        return 0.0
    return min(1.0, (instances / opportunities) / config.SEVERE_RATE[category])


def _example(row: MoveRow) -> dict:
    return {
        "game_index": row.game_index,
        "game_id": row.game_id,
        "move_number": row.move_number,
        "played": row.san,
        "best": row.best_move_san,
        "cpl": row.cpl,
    }


def _worst_examples(rows: list[MoveRow], limit: int = 3) -> list[dict]:
    return [_example(r) for r in sorted(rows, key=lambda r: -(r.cpl or 0))[:limit]]


# A flagged move's eval has to be clearly on the player's side before "you were
# already better" means anything; inside this band the game was level.
PATTERN_AHEAD_CP = 100
PATTERN_LATE_MOVE = 30


def _pattern(rows: list[MoveRow]) -> dict:
    """The shape of a set of flagged moves — when they happen, not what they were.

    The scores say how often a weakness fires; this says whether the misses
    share a situation, which is the part a player can actually act on. Counts
    only, no judgement: `recommend` decides what's lopsided enough to mention.
    """
    if not rows:
        return {}
    return {
        "count": len(rows),
        "while_winning": sum(1 for r in rows if r.eval_before_cp > PATTERN_AHEAD_CP),
        "after_move_30": sum(1 for r in rows if r.move_number > PATTERN_LATE_MOVE),
        "in_games_lost": sum(1 for r in rows if r.result == "loss"),
    }


def is_meaningful(row: MoveRow) -> bool:
    """Was there anything real to lose on this move?

    Two cases where there wasn't: the player was already winning decisively and
    still is, or the game was already lost before the move. Counting either
    scores a super-GM's cleanly won games as full of blunders.
    """
    if (
        row.eval_before_cp >= config.DECISIVE_CP
        and row.eval_after_cp >= config.CONVERSION_WINNING_CP
    ):
        return False
    return row.eval_before_cp > -config.DECISIVE_CP


def _player_moves(rows: list[MoveRow]) -> list[MoveRow]:
    """Every move-based classifier reads through here, so the decided-position
    filter applies to the time-management buckets too."""
    return [
        r for r in rows if r.is_player_move and r.cpl is not None and is_meaningful(r)
    ]


def classify_tactical(rows: list[MoveRow]) -> CategoryResult:
    qualifying = [
        r
        for r in _player_moves(rows)
        if r.cpl >= config.TACTICAL_CPL_THRESHOLD and r.best_is_forcing
    ]
    opportunities = len(_player_moves(rows))
    return CategoryResult(
        name="tactical",
        score=_score(len(qualifying), opportunities, "tactical"),
        confidence=_confidence(len(qualifying)),
        instances=len(qualifying),
        details={
            "avg_cpl": round(mean([r.cpl for r in qualifying])) if qualifying else 0,
            "opportunities": opportunities,
            "pattern": _pattern(qualifying),
            "examples": _worst_examples(qualifying),
        },
    )


def classify_endgame(rows: list[MoveRow]) -> CategoryResult:
    endgame_moves = [
        r for r in _player_moves(rows) if r.piece_count <= config.ENDGAME_MAX_PIECES
    ]
    qualifying = [r for r in endgame_moves if r.cpl >= config.ENDGAME_CPL_THRESHOLD]
    games = len({r.game_index for r in qualifying})
    return CategoryResult(
        name="endgame",
        score=_score(len(qualifying), len(endgame_moves), "endgame"),
        confidence=_confidence(len(qualifying)),
        instances=len(qualifying),
        details={
            "avg_cpl": round(mean([r.cpl for r in qualifying])) if qualifying else 0,
            "games_affected": games,
            "opportunities": len(endgame_moves),
            "pattern": _pattern(qualifying),
            "examples": _worst_examples(qualifying),
        },
    )


def classify_time_management(rows: list[MoveRow]) -> CategoryResult:
    """Not a per-move threshold — a correlation check between clock pressure and
    move quality, so the flag means time pressure *amplifies* the error rate
    rather than just that mistakes exist."""
    timed = [r for r in _player_moves(rows) if r.clock_pct is not None]
    low = [r for r in timed if r.clock_pct < config.TIME_LOW_BUCKET]
    high = [r for r in timed if r.clock_pct > config.TIME_HIGH_BUCKET]

    low_avg = mean([r.cpl for r in low]) if low else 0.0
    high_avg = mean([r.cpl for r in high]) if high else 0.0
    ratio = low_avg / high_avg if high and high_avg > 0 else None

    gate_met = (
        len(low) >= config.TIME_MIN_LOW_MOVES
        and ratio is not None
        and ratio >= config.TIME_RATIO_TRIGGER
    )
    qualifying = [r for r in low if r.cpl >= config.TIME_CPL_THRESHOLD]

    return CategoryResult(
        name="time_management",
        score=_score(len(qualifying), len(low), "time_management") if gate_met else 0.0,
        confidence=_confidence(len(qualifying)),
        instances=len(qualifying),
        details={
            "ratio": round(ratio, 2) if ratio is not None else None,
            "low_bucket_moves": len(low),
            "low_bucket_avg_cpl": round(low_avg),
            "high_bucket_avg_cpl": round(high_avg),
            "gate_met": gate_met,
            "pattern": _pattern(qualifying),
            "examples": _worst_examples(qualifying),
        },
    )


def classify_conversion(rows: list[MoveRow]) -> CategoryResult:
    """Counted once per game: reached a clearly winning eval, then let it go."""
    by_game: dict[int, list[MoveRow]] = {}
    for row in rows:
        by_game.setdefault(row.game_index, []).append(row)

    instances = []
    games_winning = 0
    for game_index, game_rows in sorted(by_game.items()):
        game_rows = sorted(game_rows, key=lambda r: r.ply)
        evals = [r.eval_after_cp for r in game_rows]
        peak = max(evals)
        if peak < config.CONVERSION_WINNING_CP:
            continue

        games_winning += 1
        peak_at = evals.index(peak)
        after_peak = evals[peak_at + 1 :]
        if not after_peak:
            continue

        low_after = min(after_peak)
        result = game_rows[0].result
        if low_after < config.CONVERSION_LOST_CP or result != "win":
            instances.append(
                {
                    "game_index": game_index,
                    "game_id": game_rows[0].game_id,
                    "peak_cp": peak,
                    "low_after_cp": low_after,
                    "result": result,
                    "drop_cp": peak - low_after,
                }
            )

    # Letting a win go and losing it is a different event from letting it go and
    # scrambling back, and a report that calls the second one "not converted"
    # is telling the player they lost a game they remember winning.
    thrown_away = [i for i in instances if i["result"] != "win"]
    recovered = [i for i in instances if i["result"] == "win"]

    return CategoryResult(
        name="conversion",
        score=_score(len(instances), games_winning, "conversion"),
        confidence=_confidence(len(instances)),
        instances=len(instances),
        details={
            "games_reached_winning": games_winning,
            "games_converted": games_winning - len(instances),
            "games_thrown_away": len(thrown_away),
            "games_recovered": len(recovered),
            "pattern": {
                "count": len(instances),
                "in_games_lost": sum(1 for i in instances if i["result"] == "loss"),
            } if instances else {},
            "examples": sorted(instances, key=lambda i: -i["drop_cp"])[:3],
        },
    )


def classify_weaknesses(rows: list[MoveRow]) -> list[CategoryResult]:
    return [
        classify_tactical(rows),
        classify_endgame(rows),
        classify_time_management(rows),
        classify_conversion(rows),
    ]
