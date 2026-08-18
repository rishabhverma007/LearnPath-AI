"""LearnPath XP — deterministic gamification engine.

Rewards learning progress, mastery and consistency — never meaningless
activity. All XP math lives here (server-side); the frontend only submits
*what happened* and the engine decides how many XP it was worth.

Core pipeline (see README):

    Learning Event
        -> XP Engine (anti-farm, difficulty multiplier, bonuses)
        -> XP Transaction (immutable ledger)
        -> Level Calculator
        -> Badge Engine
        -> Streak updater
        -> Leaderboard / challenge progress
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app import config
from app.database.models import Learner
from app.database.repository import LearnerRepository

# ----------------------------------------------------------------------
# Activity types (the only things the frontend can signal)
# ----------------------------------------------------------------------
EVENT_TYPES = {
    "micro_lesson_completed",
    "resource_completed",
    "course_completed",
    "project_completed",
    "assessment_completed",
    "daily_mission_completed",
    "remediation_completed",
    "challenge_completed",
    "phase_completed",
    "capstone_completed",
    "weekly_milestone_completed",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def week_start_iso() -> str:
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


# ----------------------------------------------------------------------
# Levels
# ----------------------------------------------------------------------
def level_for_xp(xp: int) -> tuple[int, str, int, int]:
    """Return (level, title, xp_floor, xp_needed_for_next).

    xp_needed_for_next is 0 at max level.
    """
    matched = config.LEVEL_THRESHOLDS[0]
    for entry in config.LEVEL_THRESHOLDS:
        if xp >= entry[2]:
            matched = entry
    level, title, floor = matched
    # find next threshold above the current floor
    next_floor = None
    for _lvl, _t, f in config.LEVEL_THRESHOLDS:
        if f > floor:
            next_floor = f
            break
    needed = (next_floor - xp) if next_floor is not None else 0
    return level, title, floor, needed


def level_progress(xp: int) -> tuple[float, int, int]:
    """(fraction 0..1 into current level, xp into level, xp needed within level)."""
    level, _, floor, needed = level_for_xp(xp)
    if needed == 0:
        return 1.0, 0, 0
    span = 0
    for lvl, t, f in config.LEVEL_THRESHOLDS:
        if f <= floor:
            continue
        nxt = f
        span = nxt - floor
        break
    if span <= 0:
        return 1.0, 0, 0
    into = xp - floor
    return min(1.0, into / span), into, span - into


# ----------------------------------------------------------------------
# Ranks (competitive standing by XP percentile of cohort)
# ----------------------------------------------------------------------
def rank_for_xp(xp: int, cohort_xp: list[int]) -> str:
    """Map XP to a rank based on percentile within the cohort.

    Falls back gracefully when there is little data.
    """
    if not cohort_xp:
        return config.RANKS[0]
    better = sum(1 for x in cohort_xp if x > xp)
    pct = (better / len(cohort_xp)) if cohort_xp else 0.0
    # top 5% -> Grandmaster ... bottom -> Novice
    idx = min(len(config.RANKS) - 1, int(pct * 10))
    return config.RANKS[9 - idx]


# ----------------------------------------------------------------------
# Streaks
# ----------------------------------------------------------------------
def update_streak(current_streak: int, longest: int, last_learning: str | None,
                  today: datetime | None = None) -> tuple[int, int, str, bool]:
    """Return (new_streak, new_longest, last_learning_date, milestone_hit).

    A streak continues when the learner completes a meaningful activity
    today or yesterday (grace for timezone), and resets after a gap.
    """
    today = today or datetime.now(timezone.utc)
    today_str = today.date().isoformat()
    if last_learning is None:
        return 1, max(longest, 1), today_str, False
    try:
        last = datetime.fromisoformat(last_learning).date()
    except ValueError:
        return 1, max(longest, 1), today_str, False
    delta = (today.date() - last).days
    if delta <= 0:
        # already learned today
        return current_streak, longest, today_str, False
    if delta == 1:
        new = current_streak + 1
        milestone_hit = new in config.STREAK_MILESTONES
        return new, max(longest, new), today_str, milestone_hit
    # gap > 1 day: streak resets
    return 1, longest, today_str, False


# ----------------------------------------------------------------------
# XP calculation
# ----------------------------------------------------------------------
def calculate_xp(
    event_type: str,
    activity_id: str,
    *,
    difficulty: int = 3,
    assessment_score: float | None = None,
    prev_best_score: float | None = None,
    catalog=None,
    repo: LearnerRepository | None = None,
    learner: Learner | None = None,
    is_capstone: bool = False,
    is_remediation: bool = False,
    completed_early: bool = False,
) -> dict[str, Any]:
    """Compute XP for a learning event with full breakdown.

    Returns {\"base_xp\", \"bonus_xp\", \"multiplier\", \"final_xp\", \"reason\", \"is_duplicate\"}
    """
    base = config.XP_RULES.get(event_type, 0)

    # difficulty multiplier (from resource metadata, not learner preference);
    # difficulty <= 0 means "flat event" (mission/streak/challenge) -> 1.0x
    multiplier = config.DIFFICULTY_MULTIPLIERS.get(
        int(difficulty) if difficulty else 3, 1.0
    ) if difficulty else 1.0

    # type-level adjustments
    if event_type == "course_completed" and difficulty >= 4:
        base = config.XP_RULES["difficult_course_completed"]
    elif event_type == "project_completed" and difficulty >= 4:
        base = config.XP_RULES["advanced_project_completed"]
    if is_capstone and event_type in ("project_completed", "course_completed"):
        base = config.XP_RULES["capstone_completed"]
        if activity_id:
            event_type = "capstone_completed"

    bonus = 0
    bonus_parts: list[str] = []

    # performance bonus for assessments
    if assessment_score is not None:
        for lo, hi, xp in config.ASSESSMENT_BONUS:
            if lo <= assessment_score < hi:
                bonus += xp
                bonus_parts.append(f"score {assessment_score:.0%} bonus +{xp}")
                break

    # improvement (comeback) bonus: re-assessment beats previous best
    if assessment_score is not None and prev_best_score is not None:
        if assessment_score > prev_best_score and (
            assessment_score - prev_best_score
        ) >= config.IMPROVEMENT_BONUS_MIN_GAIN:
            bonus += config.IMPROVEMENT_BONUS_XP
            bonus_parts.append(f"improvement +{config.IMPROVEMENT_BONUS_XP}")

    if completed_early:
        bonus += 25
        bonus_parts.append("completed early +25")

    final = int((base + bonus) * multiplier)
    reason = f"{event_type.replace('_', ' ')}"
    if bonus_parts:
        reason += " · " + ", ".join(bonus_parts)
    return {
        "event_type": event_type,
        "activity_id": activity_id or "",
        "base_xp": base,
        "bonus_xp": bonus,
        "multiplier": multiplier,
        "final_xp": final,
        "reason": reason,
        "is_duplicate": False,
    }


# ----------------------------------------------------------------------
# Badge engine (deterministic conditions)
# ----------------------------------------------------------------------
BADGE_BY_ID = {b[0]: b for b in config.BADGE_DEFINITIONS}


def evaluate_badges(
    learner: Learner,
    repo: LearnerRepository,
    *,
    learned_today: bool = False,
    earned_ids: set[str] | None = None,
    phase_completed: bool = False,
    capstone_completed: bool = False,
    early_milestone: bool = False,
    remediation_pass: bool = False,
    streak: int = 0,
) -> list[str]:
    """Return badge ids whose conditions are met but not yet earned.

    All conditions are deterministic — computed from the learner twin
    and the gamification ledger. No randomness, no client input.
    """
    earned = earned_ids if earned_ids is not None else {
        b["badge_id"] for b in repo.learner_badges(learner.learner_id)
    }
    new: list[str] = []

    def award(badge_id: str, cond: bool) -> None:
        if cond and badge_id not in earned and badge_id not in new:
            new.append(badge_id)

    n_completed = (
        len(learner.completed_courses)
        + len(learner.completed_projects)
        + len(learner.completed_resources)
    )
    mastered = [s for s, v in learner.known_skills.items() if v >= 0.90]
    n_projects = len(learner.completed_projects)
    high_scores = sum(
        1 for h in learner.assessment_history if h.get("score", 0) >= 0.90
    )

    award("first_step", n_completed >= 1)
    award("knowledge_seeker", n_completed >= 5)
    award("skill_builder", len(mastered) >= 3)
    award("on_fire", streak >= 7)
    award("consistent_learner", streak >= 30)
    award("builder", n_projects >= 3)
    award("assessment_ace", high_scores >= 5)
    award("path_explorer", phase_completed)
    award("mastery", len(mastered) >= 1)
    award("capstone_champion", capstone_completed)
    award("fast_learner", early_milestone)
    award("problem_solver", remediation_pass)
    for days, (_, badge_id) in config.STREAK_MILESTONES.items():
        award(badge_id, streak >= days)
    return new


def reward_badges(learner: Learner, repo: LearnerRepository, badge_ids: list[str]) -> list[dict]:
    """Persist earned badges, returning [{badge_id, name, icon, description, xp_reward}]."""
    out: list[dict] = []
    for bid in badge_ids:
        info = BADGE_BY_ID.get(bid)
        if info is None:
            continue
        earned = repo.earn_badge(learner.learner_id, bid)
        if earned:
            out.append({
                "badge_id": bid, "name": info[1], "icon": info[2],
                "description": info[3], "xp_reward": info[6],
            })
    return out


def all_badge_definitions() -> list[dict]:
    return [
        {"badge_id": b[0], "name": b[1], "icon": b[2], "description": b[3],
         "condition_type": b[4], "condition_value": b[5], "xp_reward": b[6]}
        for b in config.BADGE_DEFINITIONS
    ]


# ----------------------------------------------------------------------
# Weekly challenges
# ----------------------------------------------------------------------
def seed_weekly_challenges(repo: LearnerRepository) -> None:
    """Ensure this week's challenges exist (idempotent)."""
    start = week_start_iso()
    end = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    for cid, title, desc, ctype, target, xp in config.CHALLENGE_TEMPLATES:
        repo.upsert_weekly_challenge({
            "id": f"{cid}_{start[:10]}", "title": title, "description": desc,
            "challenge_type": ctype, "target": target, "xp_reward": xp,
            "start_date": start, "end_date": end,
        })


def current_challenges(repo: LearnerRepository) -> list[dict]:
    start = week_start_iso()
    return [
        c for c in repo.list_weekly_challenges()
        if (c.get("start_date") or "")[:10] == start[:10]
    ] or repo.list_weekly_challenges()[: len(config.CHALLENGE_TEMPLATES)]


def challenge_progress_value(learner: Learner, challenge_type: str, repo: LearnerRepository,
                             since_iso: str | None = None) -> float:
    """Compute a learner's progress toward a challenge type this week."""
    since = since_iso or week_start_iso()
    if challenge_type == "assessment_count":
        return float(len(repo.attempts_for(learner.learner_id)))
    if challenge_type == "project_count":
        return float(len(learner.completed_projects))
    if challenge_type == "learning_hours":
        # derive from completed item durations (courses + projects + resources)
        hours = 0.0
        for cid in learner.completed_courses:
            c = learner_completed_duration(learner, "course", cid)
            hours += c
        return round(hours, 1)
    if challenge_type == "skill_85_count":
        return float(sum(1 for v in learner.known_skills.values() if v >= 0.85))
    return 0.0


def learner_completed_duration(learner: Learner, item_type: str, item_id: str) -> float:
    """Look up a completed item's duration from the learner's roadmap snapshot."""
    for p in (learner.roadmap or {}).get("phases", []):
        for item in p.get("items", []):
            if item.get("item_id") == item_id:
                return float(item.get("duration_hours", 0))
    return 0.0
