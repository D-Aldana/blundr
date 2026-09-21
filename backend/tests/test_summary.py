import sys
from types import SimpleNamespace

import pytest

from app import config, providers, summary as summary_module
from app.models import Recommendation
from app.summary import (
    build_facts,
    fallback_summary,
    generate_llm_summary,
    validate_summary,
)
from app.recommend import map_recommendations, rank_categories
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


def test_fallback_is_grounded_and_leads_with_the_worst_category():
    text = fallback_summary(CATEGORIES, RECS)
    # Asserted through the reader, not a substring, so rewording the prose
    # doesn't fail the test while actually staying correct.
    assert summary_module._leading_category(text) == "tactical"
    assert validate_summary(text, FACTS, leads_with="tactical") == []


def test_fallback_when_nothing_qualifies():
    text = fallback_summary([make_category("tactical", confidence="insufficient")], [])
    assert text == summary_module.NO_LEAK_SUMMARY
    assert "stands out" in text


async def test_llm_output_is_used_when_it_validates(monkeypatch):
    async def fake_call(facts, correction=None):
        return "You missed 7 tactical shots across 20 games. Slow down on forcing moves."

    monkeypatch.setattr(summary_module, "_call_llm", fake_call)
    result = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")

    assert result.source == "llm"
    assert result.violations == []


async def test_hallucinated_summary_is_retried_then_falls_back(monkeypatch):
    attempts = []

    async def fake_call(facts, correction=None):
        attempts.append(correction)
        return "You lost 14 games in the Caro-Kann."

    monkeypatch.setattr(summary_module, "_call_llm", fake_call)
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

    monkeypatch.setattr(summary_module, "_call_llm", fake_call)
    result = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")

    assert result.source == "llm"
    assert result.violations == ["unsupported number: 12"]


async def test_llm_failure_falls_back_without_breaking_the_report(monkeypatch):
    async def boom(facts, correction=None):
        raise RuntimeError("no api key")

    monkeypatch.setattr(summary_module, "_call_llm", boom)
    result = await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")

    assert result.source == "fallback"
    assert result.violations == ["llm_error: no api key"]
    assert result.text


def test_spelled_out_number_from_the_facts_is_allowed():
    assert validate_summary("In seven positions you missed the shot.", FACTS) == []


def test_spelled_out_number_that_was_never_provided_is_caught():
    violations = validate_summary("You blundered in twelve games.", FACTS)
    assert violations == ["unsupported number: twelve"]


@pytest.mark.parametrize(
    "text",
    [
        "Develop the habit of scanning for checks first.",  # elo
        "Keeping that momentum will pay off.",  # pin
        "That habit is helping you already.",  # pin
        "Your score is below where it could be.",  # elo
    ],
)
def test_banned_terms_do_not_fire_inside_ordinary_words(text):
    assert validate_summary(text, FACTS) == []


def test_banned_term_as_a_whole_word_is_still_caught():
    assert validate_summary("You keep missing the pin.", FACTS) == [
        "unsupported specificity: pin"
    ]


def test_generic_opponent_is_allowed():
    """The noun is unavoidable in coaching prose and names no one."""
    text = "Scan for what your opponent is forced to answer before you move."
    assert validate_summary(text, FACTS) == []


def test_compound_number_from_the_facts_is_allowed():
    facts = build_facts(
        [make_category("tactical", score=0.63, instances=37)], [], 20, "blitz"
    )
    assert validate_summary("You missed the shot in thirty-seven spots.", facts) == []
    assert validate_summary("You missed it in thirty seven spots.", facts) == []


def test_invented_compound_number_is_caught_as_one_violation():
    violations = validate_summary("You blundered in forty-two games.", FACTS)
    assert violations == ["unsupported number: forty-two"]


def test_compound_ending_in_a_small_word_is_read_as_one_number():
    facts = build_facts(
        [make_category("tactical", score=0.5, instances=21)], [], 20, "blitz"
    )
    assert validate_summary("Twenty-one positions went that way.", facts) == []


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

    monkeypatch.setattr(summary_module, "_call_llm", fake_call)
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
    """Stub the Anthropic SDK and hand back the kwargs the provider sent."""
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
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    return captured


async def test_request_uses_the_configured_model_and_system_prompt(captured_request):
    text = await summary_module._call_llm(FACTS)

    assert text == "Grounded prose."
    assert captured_request["model"] == providers.model_for("anthropic")
    assert captured_request["system"] == summary_module.SYSTEM_PROMPT
    assert captured_request["messages"] == [
        {"role": "user", "content": f"Facts:\n\n{FACTS}"}
    ]


async def test_summary_model_overrides_the_provider_default(captured_request, monkeypatch):
    monkeypatch.setattr(config, "SUMMARY_MODEL", "claude-opus-5")

    await summary_module._call_llm(FACTS)

    assert captured_request["model"] == "claude-opus-5"


async def test_request_sends_no_effort_setting(captured_request):
    """Haiku 4.5 rejects output_config.effort — it must stay off the request."""
    await summary_module._call_llm(FACTS)

    assert "output_config" not in captured_request


def test_anthropic_defaults_to_haiku():
    assert "haiku" in providers.anthropic.DEFAULT_MODEL


async def test_correction_is_appended_to_the_facts(captured_request):
    await summary_module._call_llm(FACTS, correction="unsupported number: 14")

    content = captured_request["messages"][0]["content"]
    assert content.startswith(f"Facts:\n\n{FACTS}")
    assert "unsupported number: 14" in content


async def test_retries_are_charged_against_the_budget(monkeypatch):
    async def hallucinate(facts, correction=None):
        return "You lost 14 games in the Caro-Kann."

    monkeypatch.setattr(summary_module, "_call_llm", hallucinate)
    monkeypatch.setattr(summary_module.config, "SUMMARY_DAILY_BUDGET", 10)

    await generate_llm_summary(CATEGORIES, RECS, 20, "blitz")
    assert len(summary_module._llm_calls) == 2


# --- Leading category --------------------------------------------------------

# The categories behind the real report that surfaced this: endgame ranks top
# on score, but time management has more instances and the model led with it.
CONTRADICTION_CATEGORIES = [
    make_category("endgame", score=0.48, instances=3, confidence="low",
                  details={"games_affected": 3}),
    make_category("time_management", score=0.39, instances=5, confidence="low"),
]

REAL_CONTRADICTING_SUMMARY = (
    "Your biggest leak right now is time pressure: when you're down to your "
    "final seconds, your moves deteriorate sharply. Front-load your thinking "
    "so you preserve clock for the middlegame and endgame."
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Your endgame technique is what's costing you.", "endgame"),
        ("You keep missing tactics that were right there.", "tactical"),
        ("Your moves fall apart under time pressure.", "time_management"),
        ("You reach a winning position and can't convert.", "conversion"),
        ("Keep playing and check back in a few weeks.", None),
    ],
)
def test_leading_category_is_read_from_prose(text, expected):
    assert summary_module._leading_category(text) == expected


def test_first_category_mentioned_wins_not_the_most_mentioned():
    text = "Your endgame is the issue. Clock, clock, and more clock after that."
    assert summary_module._leading_category(text) == "endgame"


def test_summary_leading_with_the_wrong_category_is_caught():
    violations = validate_summary(
        REAL_CONTRADICTING_SUMMARY, FACTS, leads_with="endgame"
    )
    assert len(violations) == 1
    assert "leads with time_management" in violations[0]
    assert "endgame" in violations[0]


def test_summary_leading_with_the_right_category_passes():
    text = "Your endgame technique is the clearest leak; drill basic endings."
    assert validate_summary(text, FACTS, leads_with="endgame") == []


def test_unrecognised_prose_is_not_rejected():
    """Lenient by design — a wrong rejection costs a retry and a worse paragraph."""
    text = "You are closer to your next level than these games suggest."
    assert validate_summary(text, FACTS, leads_with="endgame") == []


def test_leader_check_is_off_unless_a_leader_is_given():
    assert validate_summary(REAL_CONTRADICTING_SUMMARY, FACTS) == []


async def test_contradicting_summary_is_retried_then_falls_back(monkeypatch):
    attempts = []

    async def contradict(facts, correction=None):
        attempts.append(correction)
        return REAL_CONTRADICTING_SUMMARY

    monkeypatch.setattr(summary_module, "_call_llm", contradict)
    result = await generate_llm_summary(CONTRADICTION_CATEGORIES, [], 20, "blitz")

    assert len(attempts) == 2
    assert "lead with that instead" in attempts[1]
    assert result.source == "fallback"


def test_the_fallback_paragraph_never_contradicts_the_headline():
    """It is built from the same ranking, so it must satisfy its own check."""
    ranked = rank_categories(CONTRADICTION_CATEGORIES)
    facts = build_facts(CONTRADICTION_CATEGORIES, [], 20, "blitz")
    text = fallback_summary(CONTRADICTION_CATEGORIES, [])
    assert validate_summary(text, facts, leads_with=ranked[0].name) == []


# --- Fallback prose ----------------------------------------------------------


@pytest.mark.parametrize("category", ["tactical", "endgame", "time_management", "conversion"])
def test_every_category_has_an_opener_the_reader_can_identify(category):
    """An opener the leading-category check can't read would make the fallback
    fail the very agreement rule the LLM path is held to."""
    assert summary_module._leading_category(summary_module.OPENERS[category]) == category


@pytest.mark.parametrize("category", ["tactical", "endgame", "time_management", "conversion"])
def test_every_category_can_be_named_as_the_next_thing(category):
    assert category in summary_module.NEXT_UP
    assert summary_module.NEXT_UP[category].islower()


def test_low_confidence_is_said_out_loud():
    thin = [make_category("endgame", score=0.48, instances=3, confidence="low",
                          details={"games_affected": 3})]
    assert "settled diagnosis" in fallback_summary(thin, map_recommendations(thin))


def test_a_solid_sample_is_not_hedged():
    solid = [make_category("tactical", score=0.62, instances=14, details={"avg_cpl": 240})]
    assert "settled diagnosis" not in fallback_summary(solid, map_recommendations(solid))


def test_fallback_never_leaks_internal_names_or_jargon():
    """'time_management' and 'flagged N times' both reached users before."""
    for worst in ("tactical", "endgame", "time_management", "conversion"):
        cats = [make_category(worst, score=0.5, instances=8, details=_DETAILS[worst])]
        text = fallback_summary(cats, map_recommendations(cats))
        assert "_" not in text
        assert "flagged" not in text
        assert "instances" not in text


_DETAILS = {
    "tactical": {"avg_cpl": 240},
    "endgame": {"games_affected": 4},
    "time_management": {"low_bucket_avg_cpl": 180, "high_bucket_avg_cpl": 90,
                        "ratio": 2.0, "low_bucket_moves": 22},
    "conversion": {"games_reached_winning": 10, "games_converted": 3, "avg_drop_cp": 450},
}


@pytest.mark.parametrize("worst", ["tactical", "endgame", "time_management", "conversion"])
def test_fallback_validates_for_every_worst_category(worst):
    cats = [make_category(worst, score=0.5, instances=8, details=_DETAILS[worst])]
    recs = map_recommendations(cats)
    facts = build_facts(cats, recs, 20, "blitz")
    text = fallback_summary(cats, recs)
    assert validate_summary(text, facts, leads_with=worst) == []
