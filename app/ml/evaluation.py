"""Evaluation framework for the recommendation engine.

NOTE ON METHODOLOGY: there is no human-labeled ground-truth dataset for
"the perfect learning path", so these metrics run against a **synthetic
benchmark** constructed from the catalogue itself:

  - relevant items for a learner = items whose skills overlap the
    learner's role competency map and that cover at least one gap skill.

This is explicitly labeled synthetic; the point is to catch regressions
in ranking quality (are gap-covering items ranked above irrelevant
ones?) rather than to claim real-world performance numbers.
"""
from __future__ import annotations

import numpy as np

from app.database.models import Learner
from app.ml.recommender import RecommendationResult


def precision_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    if k <= 0 or not recommended:
        return 0.0
    top = recommended[:k]
    hits = sum(1 for item in top if item in relevant)
    return hits / len(top)


def recall_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    top = recommended[:k]
    hits = sum(1 for item in top if item in relevant)
    return hits / len(relevant)


def ndcg_at_k(recommended: list[str], relevance: dict[str, float], k: int) -> float:
    """NDCG with graded relevance (0..1)."""
    if k <= 0 or not recommended:
        return 0.0
    top = recommended[:k]
    dcg = sum(
        (2 ** relevance.get(item, 0.0) - 1) / np.log2(i + 2)
        for i, item in enumerate(top)
    )
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum((2 ** r - 1) / np.log2(i + 2) for i, r in enumerate(ideal))
    return float(dcg / idcg) if idcg > 0 else 0.0


def catalogue_coverage(recommended_skills: set[str], total_skills: int) -> float:
    return len(recommended_skills) / total_skills if total_skills else 0.0


def type_diversity(item_types: list[str]) -> float:
    """1.0 if all types are different, lower with repetition."""
    if not item_types:
        return 0.0
    counts = {}
    for t in item_types:
        counts[t] = counts.get(t, 0) + 1
    return len(counts) / len(item_types)


def build_synthetic_relevance(
    learner: Learner, role_skills: set[str], gap_skills: set[str]
) -> tuple[set[str], dict[str, float]]:
    """Synthetic ground truth: items covering gaps/role skills are relevant."""
    relevant: set[str] = set()
    relevance: dict[str, float] = {}
    from app.services.engine import Engine

    engine = Engine()
    for course in engine.catalog.courses.values():
        overlap = set(course.skills) & role_skills
        if overlap:
            score = 0.3 + 0.7 * len(set(course.skills) & gap_skills) / max(1, len(gap_skills))
            relevant.add(course.course_id)
            relevance[course.course_id] = min(1.0, score)
    for project in engine.catalog.projects.values():
        if set(project.skills) & role_skills:
            relevant.add(project.project_id)
            relevance[project.project_id] = 0.7
    return relevant, relevance


def evaluate_recommendations(
    learner: Learner,
    results: list[RecommendationResult],
    role_skills: set[str],
    gap_skills: set[str],
    total_skills: int,
    k: int = 5,
) -> dict[str, float]:
    """Full synthetic-benchmark evaluation of a recommendation list."""
    relevant, relevance = build_synthetic_relevance(learner, role_skills, gap_skills)
    recommended_ids = [r.item_id for r in results]
    covered_skills = {s for r in results for s in r.skills}
    return {
        "precision_at_k": round(precision_at_k(recommended_ids, relevant, k), 3),
        "recall_at_k": round(recall_at_k(recommended_ids, relevant, k), 3),
        "ndcg_at_k": round(ndcg_at_k(recommended_ids, relevance, k), 3),
        "catalogue_coverage": round(catalogue_coverage(covered_skills, total_skills), 3),
        "type_diversity": round(type_diversity([r.item_type for r in results]), 3),
    }
