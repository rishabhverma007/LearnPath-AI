"""Evaluation framework tests (synthetic benchmark)."""
from __future__ import annotations

from app.ml.evaluation import (
    build_synthetic_relevance,
    catalogue_coverage,
    evaluate_recommendations,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    type_diversity,
)


def test_precision_recall():
    recommended = ["a", "b", "c", "d"]
    relevant = {"a", "c", "e"}
    assert precision_at_k(recommended, relevant, 2) == 0.5
    assert precision_at_k(recommended, relevant, 4) == 0.5
    assert recall_at_k(recommended, relevant, 4) == 2 / 3
    assert recall_at_k(recommended, relevant, 2) == 1 / 3
    assert precision_at_k([], relevant, 5) == 0.0


def test_ndcg_ranks_relevant_first():
    relevance = {"a": 1.0, "b": 0.0, "c": 1.0, "d": 0.5}
    good = ndcg_at_k(["a", "c", "d", "b"], relevance, 4)
    bad = ndcg_at_k(["b", "d", "a", "c"], relevance, 4)
    assert good > bad
    assert ndcg_at_k([], relevance, 3) == 0.0


def test_diversity():
    assert type_diversity(["course", "project", "resource"]) == 1.0
    assert type_diversity(["course", "course", "course"]) == 1 / 3


def test_coverage():
    assert catalogue_coverage({"a", "b"}, 10) == 0.2
    assert catalogue_coverage(set(), 5) == 0.0


def test_synthetic_relevance_and_full_eval(engine, ml_learner):
    learner, _ = ml_learner
    role = engine.catalog.role(learner.target_role)
    gaps = [g for g in engine.graph.analyze_gaps(learner.known_skills, role.skills) if g.gap > 0.15]
    relevant, relevance = build_synthetic_relevance(
        learner, set(role.required_skills), {g.skill_id for g in gaps}
    )
    assert len(relevant) > 0

    recs = engine.recommender.recommend(learner, k=8)
    metrics = evaluate_recommendations(
        learner, recs, set(role.required_skills), {g.skill_id for g in gaps},
        total_skills=len(engine.catalog.skills), k=5,
    )
    # gap-covering items should dominate the top of the list
    assert metrics["precision_at_k"] >= 0.4
    assert 0 <= metrics["ndcg_at_k"] <= 1
    assert metrics["type_diversity"] >= 0.4
