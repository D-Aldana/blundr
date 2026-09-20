import sys
from types import SimpleNamespace

import pytest

from app import config, summary as summary_module
from app.models import Recommendation
from app.summary import (
    build_facts,
    fallback_summary,
    generate_llm_summary,
    validate_summary,
)
from conftest import make_category

CATEGORIES = [
    make_category("tactical", score=0.65, instances=7, details={"avg_cpl": 240}),
    make_category("endgame", score=0.0, instances=1, confidence="insufficient"),
]
RECS = [
    Recommendation(
        category="tactical",
        text="Before every move, list the checks and captures available to you.",
        evidence="In 7 positions the engine's best move was a capture or check.",
    )
]
FACTS = build_facts(CATEGORIES, RECS, games_analyzed=20, time_control="blitz")


def test_facts_never_include_raw_game_data():
    assert "tactical" in FACTS and "0.65" in FACTS and "7 instances" in FACTS
    assert "not enough data" in FACTS  # the insufficient category is named, not scored
    assert "pgn" not in FACTS.lower() and "1. e4" not in FACTS


def test_clean_summary_passes():
    text = (
        "Across your last 20 blitz games the clearest pattern is tactical: 7 times "
        "the winning capture or check was there and you played something else. "
        "Start listing the forcing moves before you commit."
    )
    assert validate_summary(text, FACTS) == []


def test_invented_number_is_caught():
    text = "You missed 23 tactics in these games."
    assert validate_summary(text, FACTS) == ["unsupported number: 23"]


def test_score_restated_as_a_percentage_is_allowed():
    assert validate_summary("Your tactical score is 65 out of 100.", FACTS) == []


def test_invented_opening_is_caught():
    text = "Your play in the Sicilian is the problem."
    assert validate_summary(text, FACTS) == ["unsupported specificity: sicilian"]


def test_invented_motif_is_caught():
    violations = validate_summary("You keep missing back rank mates.", FACTS)
    assert violations == ["unsupported specificity: back rank"]


def test_term_present_in_the_facts_is_allowed():
    facts = FACTS + "\n- conversion: you hung pieces to a fork 4 times."
    assert validate_summary("That fork pattern keeps costing you.", facts) == []


def test_fallback_is_grounded_and_mentions_the_worst_category():
    text = fallback_summary(CATEGORIES, RECS)
    assert "tactical" in text
    assert validate_summary(text, FACTS) == []


def test_fallback_when_nothing_qualifies():
    text = fallback_summary([make_category("tactical", confidence="insufficient")], [])
    assert "no single fundamental stands out" in text


async def test_llm_output_is_used_when_it_validates(monkeypatch):
    async def fake_call(facts, correction=None):
        return "You missed 7 tactical shots across 20 games. Slow down on forcing moves."

    monkeypatch.setattr(summary_module, "_call_claude", fake_call)
    result = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")

    assert result.source == "llm"
    assert result.violations == []


async def test_hallucinated_summary_is_retried_then_falls_back(monkeypatch):
    attempts = []

    async def fake_call(facts, correction=None):
        attempts.append(correction)
        return "You lost 14 games in the Caro-Kann."

    monkeypatch.setattr(summary_module, "_call_claude", fake_call)
    result = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")

    assert len(attempts) == 2
    assert attempts[0] is None and "caro-kann" in attempts[1]
    assert result.source == "fallback"
    assert "unsupported number: 14" in result.violations


async def test_retry_that_validates_is_accepted(monkeypatch):
    calls = {"n": 0}

    async def fake_call(facts, correction=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "You hung 12 pieces."
        return "You missed 7 forcing shots across 20 games."

    monkeypatch.setattr(summary_module, "_call_claude", fake_call)
    result = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")

    assert result.source == "llm"
    assert result.violations == ["unsupported number: 12"]


async def test_llm_failure_falls_back_without_breaking_the_report(monkeypatch):
    async def boom(facts, correction=None):
        raise RuntimeError("no api key")

    monkeypatch.setattr(summary_module, "_call_claude", boom)
    result = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")

    assert result.source == "fallback"
    assert result.violations == ["llm_error: no api key"]
    assert result.text


def test_spelled_out_number_from_the_facts_is_allowed():
    assert validate_summary("In seven positions you missed the shot.", FACTS) == []


def test_spelled_out_number_that_was_never_provided_is_caught():
    violations = validate_summary("You blundered in twelve games.", FACTS)
    assert violations == ["unsupported number: twelve"]


def test_small_number_words_are_treated_as_prose_not_claims():
    text = "Do those two things and one habit will carry over."
    assert validate_summary(text, FACTS) == []


def test_spelled_number_check_is_case_insensitive():
    assert validate_summary("Twelve games went that way.", FACTS) == [
        "unsupported number: Twelve"
    ]


@pytest.fixture(autouse=True)
def reset_llm_budget():
    summary_module._llm_calls.clear()
    yield
    summary_module._llm_calls.clear()


async def test_summary_falls_back_once_the_daily_budget_is_spent(monkeypatch):
    calls = []

    async def fake_call(facts, correction=None):
        calls.append(1)
        return "You missed 7 tactical shots across 20 games. Slow down on forcing moves."

    monkeypatch.setattr(summary_module, "_call_claude", fake_call)
    monkeypatch.setattr(summary_module.config, "SUMMARY_DAILY_BUDGET", 1)

    first = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")
    second = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")

    assert first.source == "llm"
    # The job still returns a report — it degrades rather than failing.
    assert second.source == "fallback"
    assert "daily_budget_exhausted" in second.violations
    assert len(calls) == 1


@pytest.fixture
def captured_request(monkeypatch):
    """Stub the SDK and hand back the kwargs `_call_claude` sent."""
    captured: dict = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="  Grounded prose.  ")]
            )

    fake_client = SimpleNamespace(messages=FakeMessages())
    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(AsyncAnthropic=lambda: fake_client)
    )
    return captured


async def test_request_uses_the_configured_model_and_system_prompt(captured_request):
    text = await summary_module._call_claude(FACTS)

    assert text == "Grounded prose."
    assert captured_request["model"] == config.SUMMARY_MODEL
    assert captured_request["system"] == summary_module.SYSTEM_PROMPT
    assert captured_request["messages"] == [
        {"role": "user", "content": f"Facts:\n\n{FACTS}"}
    ]


async def test_request_sends_no_effort_setting(captured_request):
    """Haiku 4.5 rejects output_config.effort — it must stay off the request."""
    await summary_module._call_claude(FACTS)

    assert "output_config" not in captured_request


def test_default_model_is_haiku():
    assert "haiku" in config.SUMMARY_MODEL


async def test_correction_is_appended_to_the_facts(captured_request):
    await summary_module._call_claude(FACTS, correction="unsupported number: 14")

    content = captured_request["messages"][0]["content"]
    assert content.startswith(f"Facts:\n\n{FACTS}")
    assert "unsupported number: 14" in content


async def test_retries_are_charged_against_the_budget(monkeypatch):
    async def hallucinate(facts, correction=None):
        return "You lost 14 games in the Caro-Kann."

    monkeypatch.setattr(summary_module, "_call_claude", hallucinate)
    monkeypatch.setattr(summary_module.config, "SUMMARY_DAILY_BUDGET", 10)

    await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")
    assert len(summary_module._llm_calls) == 2
