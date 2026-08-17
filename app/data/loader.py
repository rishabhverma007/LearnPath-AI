"""Catalogue loader: reads all CSV/JSON datasets into typed models.

The catalog is loaded once and cached. All downstream engines (skill
graph, recommender, RAG) consume these in-memory objects.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app import config
from app.data.models import (
    Assessment,
    CareerRole,
    Course,
    Project,
    Question,
    Resource,
    Skill,
)
from app.utils import get_logger, split_list

log = get_logger("catalog")

DATA_FILES = {
    "skills": "skills.csv",
    "courses": "courses.csv",
    "projects": "projects.csv",
    "resources": "resources.csv",
    "career_roles": "career_roles.csv",
    "career_role_skills": "career_role_skills.csv",
    "assessments": "assessments.json",
}


def _read_csv(name: str) -> pd.DataFrame:
    path = config.DATA_DIR / DATA_FILES[name]
    return pd.read_csv(path, dtype=str, keep_default_na=False)


class DataCatalog:
    """In-memory catalogue of skills, roles, courses, projects, resources, assessments."""

    def __init__(self) -> None:
        self._load_skills()
        self._load_roles()
        self._load_courses()
        self._load_projects()
        self._load_resources()
        self._load_assessments()
        log.info(
            "catalogue loaded: %d skills, %d roles, %d courses, %d projects, %d resources, %d assessments",
            len(self.skills),
            len(self.roles),
            len(self.courses),
            len(self.projects),
            len(self.resources),
            len(self.assessments),
        )

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------
    def _load_skills(self) -> None:
        df = _read_csv("skills")
        self.skills: dict[str, Skill] = {}
        for row in df.itertuples(index=False):
            s = Skill(
                skill_id=row.skill_id,
                name=row.name,
                category=row.category,
                difficulty=_to_int(row.difficulty, 2),
                description=row.description,
                prerequisites=tuple(split_list(row.prerequisites)),
                related_skills=tuple(split_list(row.related_skills)),
            )
            self.skills[s.skill_id] = s

    def _load_roles(self) -> None:
        df_roles = _read_csv("career_roles")
        df_map = _read_csv("career_role_skills")
        targets: dict[str, dict[str, float]] = {r: {} for r in df_roles["role_id"].tolist()}
        importance: dict[str, dict[str, float]] = {r: {} for r in df_roles["role_id"].tolist()}
        for row in df_map.itertuples(index=False):
            targets.setdefault(row.role_id, {})[row.skill_id] = _to_float(row.target_level, 0.5)
            importance.setdefault(row.role_id, {})[row.skill_id] = _to_float(row.importance, 0.5)
        self.roles: dict[str, CareerRole] = {}
        for row in df_roles.itertuples(index=False):
            self.roles[row.role_id] = CareerRole(
                role_id=row.role_id,
                title=row.title,
                domain=row.domain,
                summary=row.summary,
                skills=targets.get(row.role_id, {}),
                importance=importance.get(row.role_id, {}),
            )

    def _load_courses(self) -> None:
        df = _read_csv("courses")
        self.courses: dict[str, Course] = {}
        for row in df.itertuples(index=False):
            c = Course(
                course_id=row.course_id,
                title=row.title,
                description=row.description,
                provider=row.provider,
                skills=tuple(split_list(row.skills)),
                difficulty=_to_int(row.difficulty, 3),
                duration_hours=_to_float(row.duration_hours, 10),
                format=row.format,
                prerequisites=tuple(split_list(row.prerequisites)),
                career_roles=tuple(split_list(row.career_roles)),
                url=row.url,
                tags=tuple(split_list(row.tags)),
            )
            self.courses[c.course_id] = c

    def _load_projects(self) -> None:
        df = _read_csv("projects")
        self.projects: dict[str, Project] = {}
        for row in df.itertuples(index=False):
            p = Project(
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                skills=tuple(split_list(row.skills)),
                difficulty=_to_int(row.difficulty, 3),
                duration_hours=_to_float(row.duration_hours, 12),
                prerequisites=tuple(split_list(row.prerequisites)),
                career_roles=tuple(split_list(row.career_roles)),
                deliverables=row.deliverables,
                dataset_hint=row.dataset_hint,
            )
            self.projects[p.project_id] = p

    def _load_resources(self) -> None:
        df = _read_csv("resources")
        self.resources: dict[str, Resource] = {}
        for row in df.itertuples(index=False):
            r = Resource(
                resource_id=row.resource_id,
                title=row.title,
                type=row.type,
                skill_id=row.skill_id,
                url=row.url,
                description=row.description,
                duration_min=_to_int(row.duration_min, 15),
                tags=tuple(split_list(row.tags)),
            )
            self.resources[r.resource_id] = r

    def _load_assessments(self) -> None:
        path = config.DATA_DIR / DATA_FILES["assessments"]
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assessments: dict[str, Assessment] = {}
        for item in raw["assessments"]:
            questions = tuple(
                Question(
                    id=q["id"],
                    concept=q["concept"],
                    type=q["type"],
                    question=q["question"],
                    options=tuple(q["options"]),
                    answer=q["answer"],
                    explanation=q["explanation"],
                )
                for q in item["questions"]
            )
            self.assessments[item["assessment_id"]] = Assessment(
                assessment_id=item["assessment_id"],
                skill_id=item["skill_id"],
                title=item["title"],
                description=item["description"],
                difficulty=_to_int(item.get("difficulty"), 2),
                concepts=tuple(item.get("concepts", [])),
                questions=questions,
            )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def skill(self, skill_id: str) -> Skill | None:
        return self.skills.get(skill_id)

    def role(self, role_id: str) -> CareerRole | None:
        return self.roles.get(role_id)

    def course(self, course_id: str) -> Course | None:
        return self.courses.get(course_id)

    def project(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    def resource(self, resource_id: str) -> Resource | None:
        return self.resources.get(resource_id)

    def assessment(self, assessment_id: str) -> Assessment | None:
        return self.assessments.get(assessment_id)

    def assessment_for_skill(self, skill_id: str) -> Assessment | None:
        for a in self.assessments.values():
            if a.skill_id == skill_id:
                return a
        return None

    def skills_for(self, ids: list[str]) -> list[Skill]:
        return [self.skills[i] for i in ids if i in self.skills]

    def courses_for_skill(self, skill_id: str) -> list[Course]:
        return [c for c in self.courses.values() if skill_id in c.skills]

    def projects_for_skill(self, skill_id: str) -> list[Project]:
        return [p for p in self.projects.values() if skill_id in p.skills]

    def resources_for_skill(self, skill_id: str) -> list[Resource]:
        return [r for r in self.resources.values() if r.skill_id == skill_id]

    def all_skills_sorted(self) -> list[Skill]:
        return sorted(self.skills.values(), key=lambda s: (s.category, s.difficulty, s.name))

    def search_skills(self, text: str) -> list[Skill]:
        """Fuzzy-ish text match over skill names/descriptions."""
        text = text.lower()
        scored = []
        for s in self.skills.values():
            score = 0
            if s.name.lower() in text or s.skill_id.lower() in text:
                score += 3
            if text in s.name.lower():
                score += 2
            for word in text.split():
                if word in s.name.lower() or word in s.description.lower():
                    score += 1
            if score:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored]


def _to_int(value, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


_catalog: DataCatalog | None = None


def get_catalog() -> DataCatalog:
    """Singleton catalog (cache across calls within a process)."""
    global _catalog
    if _catalog is None:
        _catalog = DataCatalog()
    return _catalog


def reset_catalog() -> None:  # pragma: no cover - used by tests
    global _catalog
    _catalog = None
