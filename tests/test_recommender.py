"""Recommendation engine tests."""
from __future__ import annotations

from app import config
from app.ml.recommender import HybridRecommender
from app.services.recommendation_service import RecommendationService


def test_weights_sum_to_one():
    assert abs(config.RECOMMENDATION_WEIGHTS.total - 1.0) < 1e-9


def test_recommendations_have_explanations(engine, ml_learner):
    learner, _ = ml_learner
    recs = HybridRecommender(engine.catalog, engine.semantic_index).recommend(learner, k=10)
    assert len(recs) >= 5
    for r in recs[:5]:
        assert set(r.reasons.keys()) == {
            "semantic_relevance", "skill_gap_coverage", "goal_alignment", "prerequisite_fit",
            "difficulty_fit", "preference_fit", "time_fit", "feedback_signal",
        }
        assert len(r.explanation_lines) >= 1
        # every reason score is a valid 0..1 number
        for v in r.reasons.values():
            assert 0.0 <= v <= 1.0


def test_mmr_diversity(engine, ml_learner):
    learner, _ = ml_learner
    recs = HybridRecommender(engine.catalog, engine.semantic_index).recommend(learner, k=10)
    types = {r.item_type for r in recs}
    assert len(types) >= 3  # diverse mix of courses/projects/resources/assessments
    scores = [r.score for r in recs]
    assert scores == sorted(scores, reverse=True)  # sorted by match after MMR


def test_personalization_changes_rankings(engine, ml_learner):
    learner, _ = ml_learner
    rec = HybridRecommender(engine.catalog, engine.semantic_index)
    before = {r.item_id: r.score for r in rec.recommend(learner, k=10)}
    # a learner who prefers video should score video items higher relative to reading
    learner.learning_preferences = ["video"]
    after = {r.item_id: r.score for r in rec.recommend(learner, k=10)}
    shared = set(before) & set(after)
    assert len(shared) > 3
    # the ranking changed for at least some items
    assert any(abs(before[i] - after[i]) > 1e-6 for i in shared)


def test_service_persists_recommendations(engine, ml_learner):
    learner, _ = ml_learner
    svc = RecommendationService(engine.recommender, engine.repo)
    recs = svc.recommend(learner, k=5)
    assert len(recs) >= 3
    svc.record_feedback(learner, recs[0].item_id, recs[0].item_type, "like")
    assert engine.repo.rec_acceptance_rate(learner.learner_id) > 0


def test_completed_items_excluded(engine, ml_learner):
    learner, _ = ml_learner
    rec = HybridRecommender(engine.catalog, engine.semantic_index)
    learner.completed_courses.append("c_kaggle_python")
    ids = {r.item_id for r in rec.recommend(learner, k=20)}
    assert "c_kaggle_python" not in ids
