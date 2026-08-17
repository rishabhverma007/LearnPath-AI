"""Recommendation service: wraps the hybrid recommender and persists history."""
from __future__ import annotations

from app import config
from app.database.models import Learner
from app.database.repository import LearnerRepository
from app.ml.recommender import HybridRecommender, RecommendationResult


class RecommendationService:
    def __init__(self, recommender: HybridRecommender, repo: LearnerRepository | None = None) -> None:
        self.recommender = recommender
        self.repo = repo or LearnerRepository()

    def recommend(self, learner: Learner, k: int | None = None, persist: bool = True) -> list[RecommendationResult]:
        results = self.recommender.recommend(learner, k=k)
        if persist and results:
            for r in results[: config.RECOMMENDATION_K]:
                self.repo.add_recommendation(
                    learner.learner_id,
                    {
                        "item_id": r.item_id,
                        "item_type": r.item_type,
                        "score": r.score,
                        "reason_scores": r.reasons,
                        "status": "recommended",
                    },
                )
        return results

    def record_feedback(self, learner: Learner, item_id: str, item_type: str, signal: str) -> None:
        status = {
            "like": "accepted",
            "complete": "complete",
            "skip": "skipped",
        }.get(signal, "recommended")
        self.repo.update_recommendation_status(learner.learner_id, item_id, status)
