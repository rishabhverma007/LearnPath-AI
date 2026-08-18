"""Demo learner seeding for the leaderboard.

Creates clearly-labeled demo learners with realistic XP, levels,
streaks and badges so the leaderboard feels alive — without ever
implying they are real users. Runs once per database (idempotent).

Privacy: demo learners have no email / password; they only exist for
ranking context and are excluded from auth entirely.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import config
from app.database.models import Learner
from app.database.repository import LearnerRepository
from app.ml import gamification as gam

# name, total_xp, streak, badge_ids, days_ago_created
DEMO_LEARNERS = [
    {
        "name": "Alex",
        "total_xp": 8420, "streak": 21, "level": 8, "role": "ml_engineer",
        "skills": {"python": 0.96, "statistics": 0.93, "ml_fundamentals": 0.91,
                    "deep_learning": 0.88, "sql": 0.82, "numpy": 0.95},
        "badges": ["first_step", "knowledge_seeker", "skill_builder", "on_fire",
                   "builder", "assessment_ace", "path_explorer", "mastery",
                   "streak_3", "streak_7", "streak_14"],
    },
    {
        "name": "Priya",
        "total_xp": 7980, "streak": 18, "level": 7, "role": "data_scientist",
        "skills": {"python": 0.94, "statistics": 0.92, "sql": 0.9,
                    "ml_fundamentals": 0.87, "data_viz": 0.91},
        "badges": ["first_step", "knowledge_seeker", "skill_builder", "on_fire",
                   "assessment_ace", "mastery", "streak_3", "streak_7", "streak_14"],
    },
    {
        "name": "Rahul",
        "total_xp": 7650, "streak": 14, "level": 7, "role": "cybersecurity_analyst",
        "skills": {"linux": 0.93, "networking": 0.9, "cybersecurity_fundamentals": 0.88,
                    "python": 0.8, "threat_intelligence": 0.85},
        "badges": ["first_step", "knowledge_seeker", "on_fire", "builder",
                   "streak_3", "streak_7", "streak_14"],
    },
    {
        "name": "Demo Learner",
        "total_xp": 6920, "streak": 12, "level": 6, "role": "cloud_engineer",
        "skills": {"linux": 0.9, "networking": 0.86, "cloud_fundamentals": 0.84,
                    "docker": 0.82, "git": 0.88},
        "badges": ["first_step", "knowledge_seeker", "skill_builder", "on_fire",
                   "streak_3", "streak_7"],
    },
]


def seed_demo_gamification(repo: LearnerRepository) -> int:
    """Seed demo leaderboard rows + twins once. Returns number seeded (0 if done)."""
    existing = repo.get_gamification("demo_alex")

    now = datetime.now(timezone.utc)
    for spec in DEMO_LEARNERS:
        lid = "demo_" + spec["name"].lower().replace(" ", "_")
        # twins are upsert-safe and always refreshed so the mastery/skill
        # leaderboards stay meaningful on pre-existing databases too
        skills = spec.get("skills", {"python": 0.92, "statistics": 0.88,
                                     "ml_fundamentals": 0.84, "sql": 0.8})
        twin = Learner(
            learner_id=lid,
            goal_text="Demo learner profile (not a real user)",
            target_role=spec.get("role", "ml_engineer"),
            target_domain="demo",
            experience_level="intermediate",
            known_skills=skills,
            created_at=(now - timedelta(days=60)).isoformat(),
        )
        repo.save_learner(twin)

    if existing:
        return 0

    for spec in DEMO_LEARNERS:
        lid = "demo_" + spec["name"].lower().replace(" ", "_")
        weekly = int(spec["total_xp"] * 0.08)
        monthly = int(spec["total_xp"] * 0.22)
        repo.upsert_gamification(lid, {
            "total_xp": spec["total_xp"], "weekly_xp": weekly, "monthly_xp": monthly,
            "current_streak": spec["streak"], "longest_streak": spec["streak"],
            "last_learning_date": (now - timedelta(hours=6)).isoformat(),
            "rank": config.RANKS[min(spec["level"] - 1, len(config.RANKS) - 1)],
            "level": spec["level"], "updated_at": now.isoformat(),
        })
        for bid in spec["badges"]:
            repo.earn_badge(lid, bid, (now - timedelta(days=30)).isoformat())
        for i in range(4):
            repo.add_xp_transaction(lid, {
                "activity_id": f"demo_seed_{i}", "activity_type": "course_completed",
                "base_xp": 100, "bonus_xp": 0, "multiplier": 1.0,
                "final_xp": 100, "reason": "Demo data (not a real user)",
                "created_at": (now - timedelta(days=i * 2)).isoformat(),
            })
    gam.seed_weekly_challenges(repo)
    return len(DEMO_LEARNERS)


def seed_weekly_challenges(repo: LearnerRepository) -> None:
    gam.seed_weekly_challenges(repo)
