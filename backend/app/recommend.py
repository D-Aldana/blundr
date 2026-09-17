"""Deterministic mapping from the worst categories to practice recommendations.

Every recommendation carries an evidence line built from the player's own
numbers — no recommendation can be produced without the stats behind it.
"""

from . import config
from .models import CategoryResult, Recommendation

MAX_RECOMMENDATIONS = 2

PRACTICE_TEXT = {
    "tactical": (
        "Before every move, list the checks and captures available to you and "
        "solve puzzles that start from quiet-looking positions — your misses are "
        "forcing shots that were on the board, not deep sacrifices."
    ),
    "endgame": (
        "Drill the basic technical endgames — king and pawn, rook and pawn, and "
        "opposite-colour bishops — until the winning method is automatic rather "
        "than something you calculate over the board."
    ),
    "time_management": (
        "Play the opening and simple recaptures faster to bank time for the "
        "critical moments, and practice playing training games where you must "
        "keep at least a third of your clock past move 30."
    ),
    "conversion": (
        "Practice technique from winning positions: set up your own clearly "
        "winning positions against an engine and convert them, trading pieces "
        "rather than hunting for a knockout."
    ),
}

HEADLINES = {
    "tactical": "Your biggest leak: missing tactics that were already on the board",
    "endgame": "Your biggest leak: endgame technique",
    "time_management": "Your biggest leak: your moves fall apart under time pressure",
    "conversion": "Your biggest leak: converting winning positions",
}

NO_LEAK_HEADLINE = (
    "No single dominant leak — your last 20 games are more balanced than most"
)


def _pawns(centipawns: float) -> str:
    return f"{centipawns / 100:.1f}"


def _evidence(category: CategoryResult) -> str:
    d = category.details
    n = category.instances

    if category.name == "tactical":
        return (
            f"In {n} positions the engine's best move was a capture, check or "
            f"immediate threat and you played something else — "
            f"{_pawns(d['avg_cpl'])} pawns given up on average."
        )
    if category.name == "endgame":
        return (
            f"{n} mistakes of a pawn or more came in positions with 12 or fewer "
            f"pieces on the board, spread across {d['games_affected']} games."
        )
    if category.name == "time_management":
        return (
            f"With under a quarter of your clock left you lost an average of "
            f"{d['low_bucket_avg_cpl']} centipawns per move, versus "
            f"{d['high_bucket_avg_cpl']} when you had time — {d['ratio']}x worse, "
            f"across {d['low_bucket_moves']} rushed moves."
        )
    if category.name == "conversion":
        return (
            f"You reached a winning position in {d['games_reached_winning']} games "
            f"and converted {d['games_converted']} of them; in the {n} you didn't, "
            f"the advantage fell by {_pawns(d['avg_drop_cp'])} pawns on average."
        )
    return ""


def rank_categories(categories: list[CategoryResult]) -> list[CategoryResult]:
    """Worst first. The score is already a rate — how often the category fires
    against how often it could — so frequency is in it; multiplying by the
    instance count again would just favour whichever category had the most
    opportunities. Ties break toward the better-evidenced category.

    Categories without enough data to report (PRD section 15 sample-size
    guard) never rank."""
    reportable = [
        c for c in categories if c.confidence != "insufficient" and c.score > 0
    ]
    return sorted(reportable, key=lambda c: (-c.score, -c.instances))


def headline(categories: list[CategoryResult]) -> str:
    ranked = rank_categories(categories)
    return HEADLINES[ranked[0].name] if ranked else NO_LEAK_HEADLINE


def map_recommendations(categories: list[CategoryResult]) -> list[Recommendation]:
    return [
        Recommendation(
            category=c.name, text=PRACTICE_TEXT[c.name], evidence=_evidence(c)
        )
        for c in rank_categories(categories)[:MAX_RECOMMENDATIONS]
    ]
