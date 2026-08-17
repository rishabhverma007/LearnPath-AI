"""Personalization: proficiency estimation and preference adaptation.

These rules turn raw signals (onboarding mentions, assessments,
completions, feedback) into the learner's evolving skill confidence and
content preferences. No LLM is used for these deterministic updates.
"""
from __future__ import annotations

from app import config
from app.data.loader import DataCatalog
from app.database.models import Learner
from app.utils import clamp

# How much an assessment score moves skill confidence (rest is prior)
ASSESSMENT_BLEND = 0.7
# Proficiency gained from completing a course / project / micro-resource
COURSE_BOOST = 0.22
PROJECT_BOOST = 0.30
RESOURCE_BOOST = 0.10
MICROLEARN_BOOST = 0.12

EXPERIENCE_BASE = {
    "beginner": 0.15,
    "intermediate": 0.40,
    "advanced": 0.65,
}


def estimate_experience_level(text: str, known_skills: dict[str, float]) -> str:
    """Infer experience level from goal text keywords and skill confidence."""
    t = text.lower()
    if any(k in t for k in ["senior", "experienced", "advanced", "have been working", "years of"]):
        return "advanced"
    if any(k in t for k in ["third-year", "junior", "student", "beginner", "learning basics", "some basics"]):
        return "intermediate" if known_skills else "beginner"
    avg = sum(known_skills.values()) / len(known_skills) if known_skills else 0.0
    if avg >= 0.6:
        return "advanced"
    if avg >= 0.35:
        return "intermediate"
    return "beginner"


def onboarding_proficiencies(
    mentioned: list[str],
    experience_level: str,
    strengths: list[str] | None = None,
) -> dict[str, float]:
    """Convert mentioned skills into starting proficiencies.

    - Skills listed as strengths get a higher base.
    - Skills mentioned plainly get the experience-level base.
    """
    base = EXPERIENCE_BASE.get(experience_level, 0.3)
    strengths = strengths or []
    prof: dict[str, float] = {}
    for skill_id in mentioned:
        if skill_id in strengths:
            prof[skill_id] = clamp(base + 0.25, 0.0, 1.0)
        else:
            prof[skill_id] = clamp(base, 0.0, 1.0)
    return prof


def apply_assessment_result(
    learner: Learner, skill_id: str, score: float, catalog: DataCatalog
) -> Learner:
    """Blend an assessment score into skill confidence and update history."""
    old = learner.proficiency(skill_id)
    new = ASSESSMENT_BLEND * score + (1 - ASSESSMENT_BLEND) * old
    learner.set_proficiency(skill_id, round(new, 3))
    learner.assessment_scores[skill_id] = round(score, 3)
    return learner


def apply_completion(learner: Learner, item_type: str, skill_ids: list[str]) -> Learner:
    """Boost proficiencies after completing a course/project/resource."""
    boost = {
        "course": COURSE_BOOST,
        "project": PROJECT_BOOST,
        "resource": RESOURCE_BOOST,
        "micro_lesson": MICROLEARN_BOOST,
    }.get(item_type, RESOURCE_BOOST)
    for sid in skill_ids:
        learner.set_proficiency(sid, learner.proficiency(sid) + boost)
    return learner


def preference_weights(learner: Learner) -> dict[str, float]:
    """Derive preference weights (0..1) from the learner's stated preferences
    and observed feedback signals.

    Feedback signals:
      - like/complete on a format  -> reinforces the mapped preference
      - skip on a format           -> weakens it
    """
    base: dict[str, float] = {}
    prefs = learner.learning_preferences or ["hands-on"]
    for pref in prefs:
        base[pref] = 1.0
    # weigh observed behavior more than stated preference
    signal_impact: dict[str, float] = {"like": 0.15, "complete": 0.15, "skip": -0.2,
                                       "too_easy": 0.05, "too_hard": -0.05}
    for fb in learner.feedback:
        impact = signal_impact.get(fb.get("signal", ""), 0.0)
        if not impact:
            continue
        item_type = fb.get("item_type", "")
        for pref, formats in config.PREFERENCE_ALIASES.items():
            if item_type in formats:
                base[pref] = base.get(pref, 0.5) + impact
    for k in base:
        base[k] = clamp(base[k], 0.0, 1.0)
    if not base:
        return {"hands-on": 0.7, "video": 0.5, "reading": 0.5}
    return base


def learner_level_estimate(learner: Learner) -> float:
    """Map the learner's average proficiency to the 1..5 difficulty scale."""
    if not learner.known_skills:
        return 1.5
    avg = sum(learner.known_skills.values()) / len(learner.known_skills)
    return 1.0 + 4.0 * avg


def pace_from_activity(learner: Learner) -> str:
    """Infer learning pace from weekly hours and consistency."""
    hours = learner.weekly_hours
    if hours >= 12:
        return "fast"
    if hours <= 6:
        return "relaxed"
    return "steady"


def consistency_from_activity(learner: Learner) -> float:
    """A proxy consistency score (0..1) from recent activity recency."""
    if not learner.recent_activity:
        return learner.consistency
    # simple heuristic: presence of activity in the last 7 days keeps it high
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    recent = 0
    for act in learner.recent_activity[-20:]:
        try:
            ts = datetime.fromisoformat(act.get("timestamp", ""))
            if (now - ts).days <= 7:
                recent += 1
        except ValueError:
            continue
    return clamp(recent / 20.0, 0.0, 1.0)


def feedback_signal_for_item(learner: Learner, item_id: str, default: float = 0.5) -> float:
    """Historical signal (0..1) for a specific item from prior feedback."""
    for fb in reversed(learner.feedback):
        if fb.get("item_id") == item_id:
            signal = fb.get("signal", "")
            if signal in ("like", "complete"):
                return 0.9
            if signal == "skip":
                return 0.25
            if signal == "too_hard":
                return 0.4
            if signal == "too_easy":
                return 0.6
    return default
