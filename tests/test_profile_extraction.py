"""Profile extraction tests."""
from __future__ import annotations

from app.ai.extraction import (
    extract_profile,
    merge_llm_extraction,
    _extract_deadline_weeks,
    _extract_weekly_hours,
    _detect_role,
    _detect_skills,
    _detect_preferences,
)


def test_weekly_hours_extraction():
    assert _extract_weekly_hours("can spend 8 hours per week") == 8.0
    assert _extract_weekly_hours("about 10 hours a week") == 10.0
    assert _extract_weekly_hours("12h/week") == 12.0
    assert _extract_weekly_hours("I have no time constraints") == 0.0
    assert _extract_weekly_hours("50 hours per week") <= 40.0  # capped


def test_deadline_extraction():
    assert _extract_deadline_weeks("within six months") == 26
    assert _extract_deadline_weeks("in 3 months") == 12
    assert _extract_deadline_weeks("one year") == 52
    assert _extract_deadline_weeks("in 2 years") == 104
    assert _extract_deadline_weeks("in 8 weeks") == 8
    assert _extract_deadline_weeks("no deadline") == 0


def test_role_detection():
    assert _detect_role("I want to be an ML Engineer", None) == "ml_engineer"
    assert _detect_role("become a data scientist", None) == "data_scientist"
    assert _detect_role("aiming for cybersecurity analyst", None) == "cybersecurity_analyst"
    assert _detect_role("I like cooking", None) == ""


def test_skill_detection(engine):
    skills = _detect_skills("I know Python and basic machine learning", engine.catalog)
    ids = {s for s, _ in skills}
    assert "python" in ids
    assert "ml_fundamentals" in ids


def test_preference_detection():
    assert "hands-on" in _detect_preferences("I prefer practical projects")
    assert "video" in _detect_preferences("I like watching video courses")
    assert "reading" in _detect_preferences("I prefer reading books and documentation")


def test_full_profile_extraction(engine):
    prof = extract_profile(
        "I am a third-year CS student. I know Python and basic ML. I want to become an AI engineer "
        "and get an internship within six months. I prefer practical projects and can study "
        "around 10 hours per week.",
        engine.catalog,
    )
    assert prof.target_role == "ai_engineer"
    assert prof.weekly_hours == 10.0
    assert prof.deadline_weeks == 26
    assert any(s == "python" for s, _ in prof.skills)
    assert "hands-on" in prof.preferences


def test_llm_merge_validation(engine):
    base = extract_profile("I want to be an ML engineer. I know python.", engine.catalog)
    # malformed LLM output must not break the merge
    merged = merge_llm_extraction(base, None)
    assert merged.target_role == base.target_role
    # garbage role ids are rejected
    merged = merge_llm_extraction(base, {"target_role": "not_a_role", "experience_level": "expert"})
    assert merged.target_role == base.target_role
    assert merged.experience_level == base.experience_level
    # valid fields are accepted
    merged = merge_llm_extraction(base, {
        "target_role": "data_scientist",
        "experience_level": "intermediate",
        "weekly_hours": 9,
        "deadline_weeks": 40,
    })
    assert merged.target_role == "data_scientist"
    assert merged.experience_level == "intermediate"
    assert merged.weekly_hours == 9
    assert merged.deadline_weeks == 40
