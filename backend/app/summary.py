"""LLM summary stage plus the output-validation guardrail (PRD section 10).

The model never sees a PGN, a move, or an opening name — only the computed
scores, counts and recommendation text. Anything it writes is then checked
back against those facts, and a summary that introduces unsupported
specificity is retried once and then replaced by a deterministic paragraph.
"""

import logging
import re
import time
from typing import Optional

from . import config
from .models import CategoryResult, Recommendation, SummaryResult
from .recommend import rank_categories

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a chess coach writing the closing paragraph of an \
automated weakness report for a club-level online player.

You will be given ONLY computed statistics from the player's last 20 games. \
Write 3-4 sentences, second person, warm and direct — encouraging without being \
saccharine, specific without being technical.

Hard rules:
- Use only the facts given. Never mention an opening, a specific game, an \
opponent, a rating, a tactical motif, or any number that is not in the facts.
- Never invent or estimate a statistic.
- Do not use bullet points or headings. Plain prose only.
- Do not restate every category; lead with the biggest leak and what to do about it."""

# Specificity the model has no basis for: it never receives openings, motifs,
# opponents or ratings, so these words in a summary mean it invented something.
BANNED_TERMS = [
    "sicilian", "french defense", "caro-kann", "london system", "italian game",
    "ruy lopez", "queen's gambit", "king's indian", "scandinavian", "vienna",
    "english opening", "najdorf", "gambit", "opening repertoire",
    "fork", "pin", "skewer", "discovered attack", "back rank", "zugzwang",
    "en passant", "windmill", "fianchetto", "opponent", "rating", "elo",
    "grandmaster", "puzzle rush",
]

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# The model does spell counts out ("in seven spots"), which digit matching
# alone would wave through. One/two/three are left out on purpose — they read
# as ordinary prose ("one of those", "do those two things") far more often
# than as claims, and rejecting them would fail good summaries.
NUMBER_WORDS = {
    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


def build_facts(
    categories: list[CategoryResult],
    recommendations: list[Recommendation],
    games_analyzed: int,
    time_control: str,
) -> str:
    lines = [f"Games analyzed: {games_analyzed} {time_control} games.", "", "Category scores (0 = no problem, 1 = severe):"]
    for category in categories:
        if category.confidence == "insufficient":
            lines.append(f"- {category.name}: not enough data in these games to score.")
        else:
            lines.append(
                f"- {category.name}: score {category.score:.2f}, "
                f"{category.instances} instances, confidence {category.confidence}."
            )

    lines += ["", "Recommendations already written for the player:"]
    if recommendations:
        for rec in recommendations:
            lines.append(f"- {rec.category}: {rec.text} Evidence: {rec.evidence}")
    else:
        lines.append("- none: no category scored high enough to recommend a focus.")
    return "\n".join(lines)


def _allowed_numbers(facts: str) -> set[str]:
    """Numbers the summary may use: the ones in the facts, plus the percentage
    form of any 0-1 score, since that's a restatement rather than a new claim."""
    allowed: set[str] = set()
    for raw in NUMBER_RE.findall(facts):
        value = float(raw)
        allowed.add(_norm(value))
        if 0 <= value <= 1:
            allowed.add(_norm(value * 100))
    return allowed


def _norm(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}"


def validate_summary(summary: str, facts: str) -> list[str]:
    """Return the specificity violations in `summary`, empty list if clean."""
    violations = []
    allowed = _allowed_numbers(facts)
    for raw in NUMBER_RE.findall(summary):
        if _norm(float(raw)) not in allowed:
            violations.append(f"unsupported number: {raw}")
    for word in WORD_RE.findall(summary):
        if _norm(NUMBER_WORDS[word.lower()]) not in allowed:
            violations.append(f"unsupported number: {word}")

    lowered = summary.lower()
    facts_lowered = facts.lower()
    for term in BANNED_TERMS:
        if term in lowered and term not in facts_lowered:
            violations.append(f"unsupported specificity: {term}")

    return violations


def fallback_summary(
    categories: list[CategoryResult], recommendations: list[Recommendation]
) -> str:
    """Deterministic paragraph, used when the LLM is unavailable or its output
    fails validation. Says less, but every word is grounded."""
    ranked = rank_categories(categories)
    if not ranked:
        return (
            "Across these games no single fundamental stands out as a clear leak — "
            "nothing here is costing you games often enough to score. Keep playing "
            "and check back in a few weeks, when a pattern has more room to show up."
        )

    worst = ranked[0]
    parts = [
        f"Your clearest leak in these games is {worst.name.replace('_', ' ')}, "
        f"flagged {worst.instances} times."
    ]
    if recommendations:
        parts.append(recommendations[0].evidence)
        parts.append(recommendations[0].text)
    if len(ranked) > 1:
        parts.append(
            f"Once that improves, {ranked[1].name.replace('_', ' ')} is the next "
            f"thing worth your practice time."
        )
    return " ".join(parts)


async def _call_claude(facts: str, correction: Optional[str] = None) -> str:
    import anthropic

    user_content = f"Facts:\n\n{facts}"
    if correction:
        user_content += (
            f"\n\nYour previous attempt was rejected by the report's validator for: "
            f"{correction}. Rewrite it using only the facts above."
        )

    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model=config.SUMMARY_MODEL,
        max_tokens=config.SUMMARY_MAX_TOKENS,
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


# Timestamps of paid LLM calls in the last 24h. A global ceiling, because the
# per-IP limits don't stop many callers each making one expensive request.
_llm_calls: list[float] = []


def _claim_llm_budget() -> bool:
    """Record a call against the rolling daily budget, or report it exhausted."""
    cutoff = time.monotonic() - 86400
    _llm_calls[:] = [t for t in _llm_calls if t > cutoff]
    if len(_llm_calls) >= config.SUMMARY_DAILY_BUDGET:
        return False
    _llm_calls.append(time.monotonic())
    return True


async def generate_llm_summary(
    categories: list[CategoryResult],
    recommendations: list[Recommendation],
    games_analyzed: int,
    time_control: str,
) -> SummaryResult:
    facts = build_facts(categories, recommendations, games_analyzed, time_control)
    all_violations: list[str] = []
    correction = None

    for attempt in range(config.SUMMARY_MAX_ATTEMPTS):
        if not _claim_llm_budget():
            log.warning("daily LLM budget exhausted; using deterministic summary")
            all_violations.append("daily_budget_exhausted")
            break

        try:
            text = await _call_claude(facts, correction)
        except Exception as exc:  # noqa: BLE001 — any LLM failure falls back
            log.warning("LLM summary unavailable: %s", exc)
            all_violations.append(f"llm_error: {exc}")
            break

        violations = validate_summary(text, facts)
        if not violations:
            return SummaryResult(text=text, source="llm", violations=all_violations)

        log.warning("summary attempt %s rejected: %s", attempt + 1, violations)
        all_violations.extend(violations)
        correction = "; ".join(violations)

    return SummaryResult(
        text=fallback_summary(categories, recommendations),
        source="fallback",
        violations=all_violations,
    )
