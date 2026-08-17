"""Composition root: lazily builds and caches the app's core engines.

All engines are cheap except the semantic index, which is disk-cached.
The module singleton covers plain-Python usage (server, tests, scripts).
"""
from __future__ import annotations

from app.ai.embeddings import cached_semantic_index
from app.ai.rag import CoachService
from app.data.loader import DataCatalog, get_catalog
from app.database.repository import LearnerRepository
from app.graph.skill_graph import SkillGraph
from app.ml.path_optimizer import PathOptimizer
from app.ml.recommender import HybridRecommender

_engine: "Engine | None" = None


class Engine:
    def __init__(self) -> None:
        self.catalog: DataCatalog = get_catalog()
        self.repo: LearnerRepository = LearnerRepository()
        self.graph: SkillGraph = SkillGraph(self.catalog)
        self.semantic_index = self._build_index()
        self.recommender: HybridRecommender = HybridRecommender(self.catalog, self.semantic_index)
        self.optimizer: PathOptimizer = PathOptimizer(self.catalog, self.graph, self.recommender)
        self.coach: CoachService = CoachService(self.catalog, self.graph)

    def _build_index(self):
        catalog = self.catalog
        items: list[tuple[str, str]] = []
        for c in catalog.courses.values():
            skills = " ".join(catalog.skill(s).name if catalog.skill(s) else s for s in c.skills)
            items.append((
                f"course:{c.course_id}",
                f"{c.title} {c.description} skills: {skills} format: {c.format} provider: {c.provider}",
            ))
        for p in catalog.projects.values():
            skills = " ".join(catalog.skill(s).name if catalog.skill(s) else s for s in p.skills)
            items.append((
                f"project:{p.project_id}",
                f"{p.title} {p.description} skills: {skills} deliverables: {p.deliverables}",
            ))
        for r in catalog.resources.values():
            skill = catalog.skill(r.skill_id)
            items.append((
                f"resource:{r.resource_id}",
                f"{r.title} {r.description} type: {r.type} about: {skill.name if skill else r.skill_id}",
            ))
        for a in catalog.assessments.values():
            skill = catalog.skill(a.skill_id)
            items.append((
                f"assessment:{a.assessment_id}",
                f"{a.title} {a.description} skill: {skill.name if skill else a.skill_id} concepts: {' '.join(a.concepts)}",
            ))
        return cached_semantic_index(items)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


def reset_engine() -> None:  # pragma: no cover - tests
    global _engine
    _engine = None
