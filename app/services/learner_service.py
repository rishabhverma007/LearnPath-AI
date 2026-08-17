"""Learner service: create, update, and evolve the Learner Digital Twin."""
from __future__ import annotations

import uuid
from typing import Any

from app import config
from app.ai.extraction import ExtractedProfile, extract_profile_hybrid
from app.data.loader import DataCatalog
from app.database.models import Learner
from app.database.repository import LearnerRepository
from app.ml.personalization import (
    apply_completion,
    onboarding_proficiencies,
    pace_from_activity,
)
from app.utils import get_logger

log = get_logger("learner_service")


def new_learner_id() -> str:
    return f"learner_{uuid.uuid4().hex[:10]}"


class LearnerService:
    def __init__(self, catalog: DataCatalog, repo: LearnerRepository | None = None) -> None:
        self.catalog = catalog
        self.repo = repo or LearnerRepository()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    def create_from_conversation(self, text: str) -> tuple[Learner, ExtractedProfile]:
        extracted = extract_profile_hybrid(text, self.catalog)
        return self._build_learner(extracted), extracted

    def create_from_persona(self, persona: dict[str, Any]) -> Learner:
        extracted = ExtractedProfile(
            goal=persona["goal_text"],
            target_role=persona["role_id"],
            experience_level="intermediate",
            skills=[(s, 0.55) for s in persona["known_skills"]],
            strengths=persona["known_skills"],
            preferences=[persona["preference"]],
            weekly_hours=persona["weekly_hours"],
            deadline_weeks=persona["deadline_weeks"],
            raw_text=persona["goal_text"],
            extraction_source="persona",
            confidence=0.95,
        )
        return self._build_learner(extracted, persona_id=persona["id"])

    def _build_learner(self, extracted: ExtractedProfile, persona_id: str | None = None) -> Learner:
        mentioned = [s for s, _ in extracted.skills]
        strengths = extracted.strengths
        profs = onboarding_proficiencies(mentioned, extracted.experience_level, strengths)
        # boost persona skills slightly higher for a better first impression
        if persona_id:
            for s in strengths:
                profs[s] = max(profs.get(s, 0.4), 0.6)

        learner = Learner(
            learner_id=new_learner_id(),
            goal_text=extracted.goal or extracted.raw_text,
            target_role=extracted.target_role,
            target_domain=self._domain_for_role(extracted.target_role),
            experience_level=extracted.experience_level,
            known_skills=profs,
            interests=extracted.interests or [],
            learning_preferences=extracted.preferences or ["hands-on"],
            preferred_content_type=extracted.preferences[0] if extracted.preferences else "mixed",
            weekly_hours=extracted.weekly_hours or config.DEFAULT_WEEKLY_HOURS,
            deadline_weeks=extracted.deadline_weeks or config.DEFAULT_DEADLINE_WEEKS,
            learning_pace="steady",
            profile_source="persona" if persona_id else "conversation",
        )
        learner.learning_pace = self._pace(learner)
        learner.consistency = 0.5
        learner.log_activity("onboarding_complete",
                             f"role={learner.target_role} skills={len(learner.known_skills)}")
        self.repo.save_learner(learner)
        return learner

    def _pace(self, learner: Learner) -> str:
        return pace_from_activity(learner)

    def _domain_for_role(self, role_id: str) -> str:
        role = self.catalog.role(role_id)
        return role.domain if role else ""

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------
    def update_profile(
        self,
        learner: Learner,
        *,
        goal_text: str | None = None,
        target_role: str | None = None,
        experience_level: str | None = None,
        weekly_hours: float | None = None,
        deadline_weeks: int | None = None,
        preferences: list[str] | None = None,
        skills: dict[str, float] | None = None,
        remove_skills: list[str] | None = None,
    ) -> Learner:
        if goal_text is not None:
            learner.goal_text = goal_text
        if target_role is not None and target_role in self.catalog.roles:
            learner.target_role = target_role
            learner.target_domain = self._domain_for_role(target_role)
        if experience_level in ("beginner", "intermediate", "advanced"):
            learner.experience_level = experience_level
        if weekly_hours is not None and 0 < weekly_hours <= config.MAX_WEEKLY_HOURS:
            learner.weekly_hours = weekly_hours
        if deadline_weeks is not None and 0 < deadline_weeks <= 104:
            learner.deadline_weeks = deadline_weeks
        if preferences:
            learner.learning_preferences = preferences
            learner.preferred_content_type = preferences[0]
        if remove_skills:
            for sid in remove_skills:
                learner.known_skills.pop(sid, None)
        if skills is not None:
            for sid, val in skills.items():
                learner.set_proficiency(sid, float(val))
        learner.learning_pace = self._pace(learner)
        learner.touch()
        learner.log_activity("profile_updated")
        self.repo.save_learner(learner)
        return learner

    def mark_item_complete(
        self, learner: Learner, item_type: str, item_id: str
    ) -> Learner:
        """Mark a course/project/resource complete and boost proficiencies."""
        skill_ids: list[str] = []
        if item_type == "course":
            course = self.catalog.course(item_id)
            if course:
                skill_ids = list(course.skills)
                if item_id not in learner.completed_courses:
                    learner.completed_courses.append(item_id)
        elif item_type == "project":
            project = self.catalog.project(item_id)
            if project:
                skill_ids = list(project.skills)
                if item_id not in learner.completed_projects:
                    learner.completed_projects.append(item_id)
        elif item_type == "resource":
            res = self.catalog.resource(item_id)
            if res:
                skill_ids = [res.skill_id]
                if item_id not in learner.completed_resources:
                    learner.completed_resources.append(item_id)
        if skill_ids:
            apply_completion(learner, item_type, skill_ids)
        learner.touch()
        learner.log_activity("item_completed", f"{item_type}:{item_id}")
        self.repo.save_learner(learner)
        return learner

    def record_feedback(
        self, learner: Learner, item_id: str, item_type: str, signal: str, comment: str = ""
    ) -> Learner:
        entry = {
            "item_id": item_id,
            "item_type": item_type,
            "signal": signal,
            "comment": comment,
        }
        learner.feedback.append(entry)
        learner.feedback = learner.feedback[-200:]
        self.repo.add_feedback(learner.learner_id, entry)
        learner.touch()
        learner.log_activity("feedback", f"{item_type}:{item_id} {signal}")
        self.repo.save_learner(learner)
        return learner

    def record_session_missed(self, learner: Learner) -> Learner:
        learner.log_activity("session_missed")
        self.repo.save_learner(learner)
        return learner
