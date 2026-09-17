"""Assemble the final report payload (PRD section 14)."""

from .models import CategoryResult, Recommendation, SummaryResult
from .recommend import headline


def build_report(
    categories: list[CategoryResult],
    recommendations: list[Recommendation],
    summary: SummaryResult,
    games_analyzed: int,
    time_control: str,
    username: str,
) -> dict:
    return {
        "username": username,
        "headline": headline(categories),
        "categories": [c.to_payload() for c in categories],
        "recommendations": [r.to_payload() for r in recommendations],
        "summary": summary.text,
        # Surfaced so a fallback paragraph is never mistaken for coach-written
        # prose, and so guardrail catches are visible in testing (PRD section 11).
        "summary_source": summary.source,
        "games_analyzed": games_analyzed,
        "time_control": time_control,
    }
