"""Roadmap service: generate, persist, and adapt learning paths."""
from __future__ import annotations

from app.database.models import Learner
from app.database.repository import LearnerRepository
from app.ml.path_optimizer import PathOptimizer, Roadmap


class RoadmapService:
    def __init__(self, optimizer: PathOptimizer, repo: LearnerRepository | None = None) -> None:
        self.optimizer = optimizer
        self.repo = repo or LearnerRepository()

    def generate(self, learner: Learner, mode: str = "balanced") -> Roadmap:
        roadmap = self.optimizer.generate(learner, mode=mode)
        self._persist(learner, roadmap)
        return roadmap

    def load(self, learner: Learner) -> Roadmap | None:
        if not learner.roadmap:
            return None
        try:
            return Roadmap.from_dict(learner.roadmap)
        except Exception:
            return None

    def adapt_after_assessment(self, learner: Learner, assessment_result: dict) -> Roadmap:
        current = self.load(learner)
        if current is None:
            current = self.generate(learner)
        updated = self.optimizer.adapt_after_assessment(learner, current, assessment_result)
        self._persist(learner, updated)
        return updated

    def refresh_statuses(self, learner: Learner) -> Roadmap | None:
        """Recompute item statuses after completions without changing structure."""
        current = self.load(learner)
        if current is None:
            return None
        self.optimizer._mark_statuses(current, learner)  # noqa: SLF001
        self._persist(learner, current)
        return current

    def _persist(self, learner: Learner, roadmap: Roadmap) -> None:
        learner.roadmap = roadmap.as_dict()
        learner.roadmap_version = roadmap.version
        learner.current_learning_state = {
            "phase_count": len(roadmap.phases),
            "next_action": roadmap.next_action().title if roadmap.next_action() else "",
            "feasible": roadmap.feasible,
            "total_weeks": roadmap.total_weeks,
        }
        learner.touch()
        learner.log_activity("roadmap_generated",
                             f"mode={roadmap.mode} phases={len(roadmap.phases)}")
        self.repo.save_learner(learner)
