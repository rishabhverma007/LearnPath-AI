"""Central configuration for LearnPath AI.

All tunable knobs live here: recommendation weights, proficiency
thresholds, path constraints, provider selection. Values can be
overridden with environment variables (see .env.example).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
ASSET_DIR = ROOT_DIR / os.getenv("ASSET_DIR", "assets")
CACHE_DIR = DATA_DIR / "embeddings_cache"

# ------------------------------------------------------------------
# Provider selection
# ------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "tfidf").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "learnpath.db")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ------------------------------------------------------------------
# Recommendation weights (configurable, sum to 1.0)
# ------------------------------------------------------------------
@dataclass(frozen=True)
class RecommendationWeights:
    semantic_relevance: float = 0.30
    skill_gap_coverage: float = 0.20
    goal_alignment: float = 0.15
    prerequisite_fit: float = 0.10
    difficulty_fit: float = 0.10
    preference_fit: float = 0.05
    time_fit: float = 0.05
    feedback_signal: float = 0.05

    @property
    def total(self) -> float:
        return sum(
            [
                self.semantic_relevance,
                self.skill_gap_coverage,
                self.goal_alignment,
                self.prerequisite_fit,
                self.difficulty_fit,
                self.preference_fit,
                self.time_fit,
                self.feedback_signal,
            ]
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "semantic_relevance": self.semantic_relevance,
            "skill_gap_coverage": self.skill_gap_coverage,
            "goal_alignment": self.goal_alignment,
            "prerequisite_fit": self.prerequisite_fit,
            "difficulty_fit": self.difficulty_fit,
            "preference_fit": self.preference_fit,
            "time_fit": self.time_fit,
            "feedback_signal": self.feedback_signal,
        }


RECOMMENDATION_WEIGHTS = RecommendationWeights()

# ------------------------------------------------------------------
# Proficiency / gap thresholds
# ------------------------------------------------------------------
SKILL_PROFICIENCY_START = 0.30       # default when a skill is mentioned but unmeasured
SKILL_PROFICIENCY_UNKNOWN = 0.0      # skill never seen
PROFICIENCY_STRONG = 0.75            # >= this => considered "known / strong"
PROFICIENCY_WEAK = 0.45              # < this and required => weak
PREREQ_READY_THRESHOLD = 0.55        # proficiency needed to be "ready" for a dependent skill
ASSESSMENT_PASS_SCORE = 0.6          # fraction of correct answers to pass a knowledge check
ASSESSMENT_STRONG_SCORE = 0.85       # >= this => accelerate (skip repetition)

# ------------------------------------------------------------------
# Roadmap constraints
# ------------------------------------------------------------------
DEFAULT_WEEKLY_HOURS = 8.0
MAX_WEEKLY_HOURS = 40.0
MIN_SESSION_MINUTES = 15
DEFAULT_DEADLINE_WEEKS = 26          # "six months"
MIN_PHASE_WEEKS = 1
MAX_PHASE_WEEKS = 8

# ------------------------------------------------------------------
# Path modes (what-if / comparison)
# ------------------------------------------------------------------
@dataclass(frozen=True)
class PathMode:
    name: str
    weekly_hours: float
    label: str
    description: str


PATH_MODES = {
    "balanced": PathMode("balanced", 8.0, "Balanced", "8 hrs/week — steady, sustainable pace"),
    "accelerated": PathMode("accelerated", 12.0, "Accelerated", "12 hrs/week — fastest feasible pace"),
    "flexible": PathMode("flexible", 5.0, "Flexible", "5 hrs/week — relaxed pace"),
}

# ------------------------------------------------------------------
# Content types / formats
# ------------------------------------------------------------------
CONTENT_FORMATS = {
    "video": "Video course",
    "interactive": "Interactive tutorial",
    "docs": "Documentation",
    "book": "Book / long-form reading",
    "course": "Structured course",
    "project": "Hands-on project",
    "article": "Article / short reading",
    "cheatsheet": "Cheatsheet / reference",
    "tool": "Tool / practice platform",
}

PREFERENCE_ALIASES = {
    "hands-on": ["project", "interactive", "tool"],
    "project": ["project", "interactive"],
    "video": ["video"],
    "reading": ["docs", "book", "article", "cheatsheet"],
    "interactive": ["interactive", "tool"],
    "theory": ["book", "docs", "course"],
    "practice": ["tool", "interactive", "project"],
}

# How well a learner preference maps to a content format (0..1)
PREFERENCE_FORMAT_MATCH = {
    "hands-on": {"project": 1.0, "interactive": 1.0, "tool": 0.9, "video": 0.5, "docs": 0.4, "book": 0.3, "article": 0.4, "cheatsheet": 0.5, "course": 0.6},
    "project": {"project": 1.0, "interactive": 0.9, "tool": 0.8, "video": 0.5, "docs": 0.4, "book": 0.3, "article": 0.4, "cheatsheet": 0.4, "course": 0.6},
    "video": {"video": 1.0, "interactive": 0.6, "course": 0.8, "docs": 0.3, "book": 0.3, "article": 0.4, "cheatsheet": 0.4, "project": 0.4, "tool": 0.4},
    "reading": {"docs": 1.0, "book": 1.0, "article": 1.0, "cheatsheet": 1.0, "video": 0.4, "interactive": 0.5, "course": 0.6, "project": 0.4, "tool": 0.4},
    "interactive": {"interactive": 1.0, "tool": 1.0, "project": 0.8, "video": 0.4, "docs": 0.4, "book": 0.3, "article": 0.4, "cheatsheet": 0.5, "course": 0.7},
    "theory": {"book": 1.0, "docs": 0.9, "course": 0.8, "video": 0.6, "article": 0.7, "cheatsheet": 0.6, "interactive": 0.4, "project": 0.3, "tool": 0.3},
    "practice": {"tool": 1.0, "interactive": 1.0, "project": 1.0, "video": 0.4, "docs": 0.4, "book": 0.3, "article": 0.4, "cheatsheet": 0.5, "course": 0.6},
}

# ------------------------------------------------------------------
# Misc
# ------------------------------------------------------------------
MAX_LLM_TIMEOUT_SECONDS = 30
COACH_RETRIEVAL_K = 5
RECOMMENDATION_K = 8
MMR_LAMBDA = 0.7        # diversity vs relevance trade-off in MMR

DEMO_PERSONAS = [
    {
        "id": "ml_engineer",
        "name": "Aisha — Aspiring ML Engineer",
        "goal_text": (
            "I am a third-year computer science student. I know Python and basic statistics. "
            "I want to become an ML Engineer and land an internship within six months. "
            "I prefer practical hands-on projects and can study about 8 hours per week."
        ),
        "known_skills": ["python", "git", "statistics", "numpy"],
        "role_id": "ml_engineer",
        "weekly_hours": 8.0,
        "deadline_weeks": 26,
        "preference": "hands-on",
    },
    {
        "id": "data_scientist",
        "name": "Ravi — Data Scientist",
        "goal_text": (
            "I work as a data analyst and know SQL, Excel and basic Python. I want to become a "
            "Data Scientist within one year. I like reading and theory combined with projects, "
            "and can dedicate 10 hours a week."
        ),
        "known_skills": ["sql", "excel", "python", "data_viz"],
        "role_id": "data_scientist",
        "weekly_hours": 10.0,
        "deadline_weeks": 52,
        "preference": "reading",
    },
    {
        "id": "cybersecurity",
        "name": "Priya — Cybersecurity Analyst",
        "goal_text": (
            "I have a background in IT support and know Linux basics and networking. I want to "
            "become a Cybersecurity Analyst in nine months. I prefer short hands-on labs and can "
            "spend 7 hours per week."
        ),
        "known_skills": ["linux", "networking"],
        "role_id": "cybersecurity_analyst",
        "weekly_hours": 7.0,
        "deadline_weeks": 39,
        "preference": "interactive",
    },
    {
        "id": "cloud_engineer",
        "name": "Diego — Cloud Engineer",
        "goal_text": (
            "I am a junior developer who knows Linux, Git and basic scripting. I want to become a "
            "Cloud Engineer within eight months. I prefer video courses and labs, with about "
            "9 hours per week available."
        ),
        "known_skills": ["linux", "git", "python", "networking"],
        "role_id": "cloud_engineer",
        "weekly_hours": 9.0,
        "deadline_weeks": 34,
        "preference": "video",
    },
]


def resolve_provider(provider: str) -> str:
    """Resolve the effective provider, honoring explicit user override."""
    value = provider.strip().lower()
    if value in {"local", "openai"}:
        return value
    # auto-detect
    if provider == "auto":
        if OPENAI_API_KEY:
            return "openai"
        return "local"
    return "local"
