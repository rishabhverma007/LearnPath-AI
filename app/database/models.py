"""Domain models: the Learner Digital Twin and related records.

The learner is stored as a JSON blob in SQLite (robust, simple) while
event-like data (assessments, feedback, recommendations) uses explicit
rows so analytics can aggregate them.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FeedbackEntry:
    item_id: str
    item_type: str            # course | project | resource | roadmap_item
    signal: str               # like | dislike | skip | complete | too_easy | too_hard
    comment: str = ""
    timestamp: str = field(default_factory=_now)


@dataclass
class AssessmentAttempt:
    attempt_id: str
    assessment_id: str
    skill_id: str
    score: float              # 0..1
    correct: int
    total: int
    concept_scores: dict[str, float] = field(default_factory=dict)
    weak_concepts: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)


@dataclass
class RecommendationRecord:
    item_id: str
    item_type: str            # course | project | resource
    score: float
    reason_scores: dict[str, float] = field(default_factory=dict)
    status: str = "recommended"   # recommended | accepted | skipped
    timestamp: str = field(default_factory=_now)


@dataclass
class Learner:
    learner_id: str
    goal_text: str = ""
    target_role: str = ""            # role_id
    target_domain: str = ""
    experience_level: str = "beginner"   # beginner | intermediate | advanced
    known_skills: dict[str, float] = field(default_factory=dict)   # skill_id -> proficiency 0..1
    interests: list[str] = field(default_factory=list)
    learning_preferences: list[str] = field(default_factory=list)  # hands-on, video, reading...
    preferred_content_type: str = "mixed"
    weekly_hours: float = 8.0
    deadline_weeks: int = 26
    learning_pace: str = "steady"    # steady | fast | relaxed
    consistency: float = 0.5         # 0..1 derived from activity
    completed_courses: list[str] = field(default_factory=list)
    completed_projects: list[str] = field(default_factory=list)
    completed_resources: list[str] = field(default_factory=list)
    assessment_scores: dict[str, float] = field(default_factory=dict)   # skill_id -> latest score
    assessment_history: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    recommendation_history: list[dict[str, Any]] = field(default_factory=list)
    recent_activity: list[dict[str, Any]] = field(default_factory=list)
    roadmap: dict[str, Any] = field(default_factory=dict)      # serialized roadmap
    roadmap_version: int = 0
    current_learning_state: dict[str, Any] = field(default_factory=dict)
    profile_source: str = "manual"   # manual | persona | llm
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Learner":
        known = {k: v for k, v in cls.__dataclass_fields__.items()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, raw: str) -> "Learner":
        return cls.from_dict(json.loads(raw))

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def proficiency(self, skill_id: str) -> float:
        return float(self.known_skills.get(skill_id, 0.0))

    def set_proficiency(self, skill_id: str, value: float) -> None:
        self.known_skills[skill_id] = max(0.0, min(1.0, value))

    def touch(self) -> None:
        self.updated_at = _now()

    def log_activity(self, event: str, detail: str = "") -> None:
        self.recent_activity.append(
            {"event": event, "detail": detail, "timestamp": _now()}
        )
        self.recent_activity = self.recent_activity[-100:]

    def learning_velocity(self) -> float:
        """Mean proficiency across skills with any signal (0..1)."""
        if not self.known_skills:
            return 0.0
        return sum(self.known_skills.values()) / len(self.known_skills)
