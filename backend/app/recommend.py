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


# A pattern is worth naming only when it's lopsided enough not to be chance.
# Below this it's just where the moves happened to fall.
PATTERN_SHARE = 0.6

# Strongest first: only one is ever said, so a report never turns into a list of
# near-coincidences. "Already better" leads because it names a habit; the others
# name a moment and a consequence.
PATTERN_NOTES = [
    ("while_winning", "{n} of those {total} came in positions you were already better in"),
    ("in_games_lost", "{n} of those {total} came in games you went on to lose"),
    ("after_move_30", "{n} of those {total} came after move 30"),
]

# Axes a category's own trigger already implies, where "they all came in X" is
# arithmetic rather than a finding. Endgame moves are late by construction — 12
# pieces or fewer — the way a conversion instance is by definition a position
# the player was winning, which is why `classify` never counts that one.
PATTERN_IMPLIED = {"endgame": {"after_move_30"}}


def _pattern_note(category: CategoryResult) -> str:
    """One sentence on where a weakness concentrates, or nothing."""
    pattern = category.details.get("pattern") or {}
    total = pattern.get("count", 0)
    if total < config.MIN_INSTANCES:
        return ""  # too few to have a shape

    implied = PATTERN_IMPLIED.get(category.name, frozenset())
    for key, template in PATTERN_NOTES:
        if key in implied:
            continue
        n = pattern.get(key)
        if n and n / total >= PATTERN_SHARE:
            return template.format(n=n, total=total) + "."
    return ""


def _pawns(centipawns: float) -> str:
    return f"{centipawns / 100:.1f}"


def _games(n: int) -> str:
    return f"{n} game" if n == 1 else f"{n} games"


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
        # No centipawn figure here on purpose. A lost position bottoms out at the
        # eval clamp, so "peak minus trough" measures the clamp, not the game —
        # it read as "the advantage fell by 15.2 pawns", which means nothing.
        parts = [
            f"You reached a winning position in "
            f"{_games(d['games_reached_winning'])} and won "
            f"{d['games_converted']} of them cleanly."
        ]
        rest = []
        if d["games_thrown_away"]:
            rest.append(f"{d['games_thrown_away']} slipped into a draw or a loss")
        if d["games_recovered"]:
            rest.append(
                f"{d['games_recovered']} you let go completely before taking "
                f"the win back anyway"
            )
        if rest:
            parts.append("Of the rest, " + " and ".join(rest) + ".")
        return " ".join(parts)
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
            category=c.name,
            text=PRACTICE_TEXT[c.name],
            evidence=_evidence(c),
            pattern=_pattern_note(c),
        )
        for c in rank_categories(categories)[:MAX_RECOMMENDATIONS]
    ]
