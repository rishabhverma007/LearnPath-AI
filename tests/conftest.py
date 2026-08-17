"""Shared fixtures for the test suite."""
from __future__ import annotations

import pytest

from app import config
from app.services.engine import Engine, reset_engine

# Use a scratch database so tests never touch demo data
config.DATABASE_PATH = config.DATA_DIR / "test_learnpath.db"


@pytest.fixture(scope="session")
def engine() -> Engine:
    reset_engine()
    eng = Engine()
    yield eng
    reset_engine()


@pytest.fixture()
def ml_learner(engine):
    """A standard ML-engineer learner with a generated roadmap."""
    from app.services.learner_service import LearnerService
    from app.services.roadmap_service import RoadmapService

    learner, _ = LearnerService(engine.catalog, engine.repo).create_from_conversation(
        "I want to become an ML Engineer in six months. I know Python and basic statistics. "
        "I prefer practical projects and can spend 8 hours per week."
    )
    roadmap = RoadmapService(engine.optimizer, engine.repo).generate(learner, mode="balanced")
    return learner, roadmap
