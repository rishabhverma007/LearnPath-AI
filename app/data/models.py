"""Typed data models for the LearnPath AI catalogue."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Skill:
    skill_id: str
    name: str
    category: str
    difficulty: int          # 1..5
    description: str
    prerequisites: tuple[str, ...] = ()
    related_skills: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "difficulty": self.difficulty,
            "description": self.description,
            "prerequisites": list(self.prerequisites),
            "related_skills": list(self.related_skills),
        }


@dataclass(frozen=True)
class CareerRole:
    role_id: str
    title: str
    domain: str
    summary: str
    skills: dict[str, float] = field(default_factory=dict)   # skill_id -> target proficiency
    importance: dict[str, float] = field(default_factory=dict)  # skill_id -> importance 0..1

    @property
    def required_skills(self) -> list[str]:
        return list(self.skills.keys())

    def target_for(self, skill_id: str) -> float:
        return self.skills.get(skill_id, 0.0)


@dataclass(frozen=True)
class Course:
    course_id: str
    title: str
    description: str
    provider: str
    skills: tuple[str, ...]
    difficulty: int
    duration_hours: float
    format: str
    prerequisites: tuple[str, ...]
    career_roles: tuple[str, ...]
    url: str
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "course_id": self.course_id,
            "title": self.title,
            "description": self.description,
            "provider": self.provider,
            "skills": list(self.skills),
            "difficulty": self.difficulty,
            "duration_hours": self.duration_hours,
            "format": self.format,
            "prerequisites": list(self.prerequisites),
            "career_roles": list(self.career_roles),
            "url": self.url,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class Project:
    project_id: str
    title: str
    description: str
    skills: tuple[str, ...]
    difficulty: int
    duration_hours: float
    prerequisites: tuple[str, ...]
    career_roles: tuple[str, ...]
    deliverables: str
    dataset_hint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "skills": list(self.skills),
            "difficulty": self.difficulty,
            "duration_hours": self.duration_hours,
            "prerequisites": list(self.prerequisites),
            "career_roles": list(self.career_roles),
            "deliverables": self.deliverables,
            "dataset_hint": self.dataset_hint,
        }


@dataclass(frozen=True)
class Resource:
    resource_id: str
    title: str
    type: str
    skill_id: str
    url: str
    description: str
    duration_min: int
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Question:
    id: str
    concept: str
    type: str            # mcq | multi | scenario | coding
    question: str
    options: tuple[str, ...]
    answer: Any          # int (mcq) or list[int] (multi)
    explanation: str


@dataclass(frozen=True)
class Assessment:
    assessment_id: str
    skill_id: str
    title: str
    description: str
    difficulty: int
    concepts: tuple[str, ...]
    questions: tuple[Question, ...]

    def concept_for_question(self, question_id: str) -> str:
        for q in self.questions:
            if q.id == question_id:
                return q.concept
        return "general"

    def grade(self, answers: dict[str, Any]) -> dict[str, Any]:
        """Grade a submission. answers maps question_id -> selected index or list of indices."""
        correct = 0
        concept_results: dict[str, list[bool]] = {}
        for q in self.questions:
            user = answers.get(q.id)
            ok = self._check(q, user)
            if ok:
                correct += 1
            concept_results.setdefault(q.concept, []).append(ok)
        total = len(self.questions)
        score = correct / total if total else 0.0
        concept_scores = {
            concept: (sum(results) / len(results)) for concept, results in concept_results.items()
        }
        return {
            "assessment_id": self.assessment_id,
            "skill_id": self.skill_id,
            "score": round(score, 3),
            "correct": correct,
            "total": total,
            "concept_scores": concept_scores,
        }

    @staticmethod
    def _check(q: Question, user: Any) -> bool:
        if user is None:
            return False
        if q.type == "multi":
            try:
                expected = set(q.answer)
                given = {int(i) for i in user} if not isinstance(user, (int, str)) else {int(user)}
                return expected == given
            except (TypeError, ValueError):
                return False
        try:
            return int(user) == int(q.answer)
        except (TypeError, ValueError):
            return False
