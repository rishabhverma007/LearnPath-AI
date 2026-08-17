"""Assessment service: select, grade, update the learner, and adapt the roadmap."""
from __future__ import annotations

import re
from typing import Any

from app import config
from app.ai.llm import get_llm_provider
from app.ai.prompts import MICRO_LESSON_SYSTEM, MICRO_LESSON_USER
from app.data.loader import DataCatalog
from app.data.models import Assessment
from app.database.models import Learner
from app.database.repository import LearnerRepository
from app.ml.personalization import apply_assessment_result
from app.services.roadmap_service import RoadmapService
from app.utils import get_logger, safe_json

log = get_logger("assessment_service")


class AssessmentService:
    def __init__(
        self,
        catalog: DataCatalog,
        repo: LearnerRepository | None = None,
        roadmap_service: RoadmapService | None = None,
    ) -> None:
        self.catalog = catalog
        self.repo = repo or LearnerRepository()
        self.roadmaps = roadmap_service

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def list_assessments(self) -> list[Assessment]:
        return sorted(self.catalog.assessments.values(), key=lambda a: (a.skill_id, a.title))

    def for_skill(self, skill_id: str) -> Assessment | None:
        return self.catalog.assessment_for_skill(skill_id)

    def by_id(self, assessment_id: str) -> Assessment | None:
        return self.catalog.assessment(assessment_id)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    def submit(
        self, learner: Learner, assessment: Assessment, answers: dict[str, Any]
    ) -> dict[str, Any]:
        result = assessment.grade(answers)
        weak = [
            c for c, s in result["concept_scores"].items()
            if s < config.ASSESSMENT_PASS_SCORE
        ]
        result["weak_concepts"] = weak
        result["assessment_title"] = assessment.title
        result["pass"] = result["score"] >= config.ASSESSMENT_PASS_SCORE
        result["strong"] = result["score"] >= config.ASSESSMENT_STRONG_SCORE

        # update the learner digital twin
        apply_assessment_result(learner, assessment.skill_id, result["score"], self.catalog)
        learner.assessment_history.append({
            "assessment_id": assessment.assessment_id,
            "skill_id": assessment.skill_id,
            "score": result["score"],
            "weak_concepts": weak,
        })
        self.repo.add_attempt(learner.learner_id, result)
        learner.touch()
        learner.log_activity("assessment_completed",
                             f"{assessment.skill_id} score={result['score']:.0%}")
        self.repo.save_learner(learner)

        # adapt the roadmap
        if self.roadmaps is not None:
            try:
                roadmap = self.roadmaps.adapt_after_assessment(learner, result)
                result["roadmap_adapted"] = True
                result["adaptation_notes"] = roadmap.adaptation_notes
                result["roadmap_version"] = roadmap.version
            except Exception as exc:  # noqa: BLE001 - adaptation must never break grading
                log.error("roadmap adaptation failed: %s", exc)
                result["roadmap_adapted"] = False
                result["adaptation_notes"] = []
        return result

    # ------------------------------------------------------------------
    # AI micro-learning (10-minute lessons)
    # ------------------------------------------------------------------
    def generate_micro_lesson(self, learner: Learner, skill_id: str, weak_concepts: list[str] | None = None) -> dict[str, Any]:
        skill = self.catalog.skill(skill_id)
        if skill is None:
            return {"title": "Unknown skill", "summary": "I couldn't find that skill."}
        weak = weak_concepts or []
        provider = get_llm_provider()
        if provider.available() and provider.name != "local":
            data = provider.complete_json(
                MICRO_LESSON_SYSTEM,
                MICRO_LESSON_USER.format(
                    skill_name=skill.name,
                    skill_description=skill.description,
                    weak_concepts=", ".join(weak) if weak else "core concepts",
                    experience_level=learner.experience_level,
                ),
            )
            if data and isinstance(data.get("summary"), str):
                return data
        # deterministic fallback from the knowledge base
        kb = self.catalog.resources_for_skill(skill_id)
        return {
            "title": f"{skill.name} in 10 minutes",
            "summary": (
                f"{skill.description} Focus on: {', '.join(weak) if weak else skill.name}."
            ),
            "key_concepts": [c.replace("_", " ") for c in (weak or [skill.skill_id])][:4],
            "example": "Work through one small example of each concept above with real data.",
            "exercise": f"Implement a 15-line practice of {skill.name} using a small dataset, then explain it out loud.",
            "quiz": [],
            "resources": [
                {"title": r.title, "url": r.url, "minutes": r.duration_min}
                for r in kb[:2]
            ],
            "source": "local_knowledge_base",
        }

    # ------------------------------------------------------------------
    # AI project generator
    # ------------------------------------------------------------------
    def generate_project(self, learner: Learner, milestone_skill: str) -> dict[str, Any]:
        skill = self.catalog.skill(milestone_skill)
        skill_name = skill.name if skill else milestone_skill
        provider = get_llm_provider()
        if provider.available() and provider.name != "local":
            from app.ai.prompts import PROJECT_GENERATION_SYSTEM, PROJECT_GENERATION_USER

            data = provider.complete_json(
                PROJECT_GENERATION_SYSTEM,
                PROJECT_GENERATION_USER.format(
                    milestone=skill_name,
                    skills=skill_name,
                    experience_level=learner.experience_level,
                    preferences=", ".join(learner.learning_preferences),
                ),
            )
            if data and isinstance(data.get("title"), str):
                return data
        # deterministic fallback: adapt the best catalogue project for this skill
        project = self.catalog.projects_for_skill(milestone_skill)
        if project:
            p = project[0]
            return {
                "title": p.title,
                "objective": p.description,
                "prerequisites": list(p.prerequisites),
                "duration_hours": p.duration_hours,
                "skills_practiced": list(p.skills),
                "dataset_suggestion": p.dataset_hint,
                "deliverables": p.deliverables.split(", "),
                "evaluation_rubric": [
                    "Functional core implementation",
                    "Clean, documented code",
                    "Evaluation with appropriate metrics",
                    "Short write-up of findings",
                ],
                "difficulty": p.difficulty,
                "source": "catalogue",
            }
        return {
            "title": f"{skill_name} practice project",
            "objective": f"Apply {skill_name} to a small real-world problem end-to-end.",
            "prerequisites": [],
            "duration_hours": 8,
            "skills_practiced": [skill_name],
            "dataset_suggestion": "Any public dataset relevant to the domain",
            "deliverables": ["Code", "Report"],
            "evaluation_rubric": ["Correctness", "Clarity", "Insights"],
            "difficulty": 3,
            "source": "template",
        }


def extract_concept_tags(text: str) -> list[str]:
    """Very light parser for concept tags from user input (used for demo notes)."""
    words = re.findall(r"[a-zA-Z][a-zA-Z \-]{2,30}", text.lower())
    return [w.strip() for w in words[:8]]
