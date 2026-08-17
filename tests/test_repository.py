"""Repository + learner service tests."""
from __future__ import annotations

from app.database.repository import LearnerRepository
from app.services.learner_service import LearnerService


def test_learner_roundtrip(engine):
    repo = LearnerRepository()
    learner = repo.get_learner("does_not_exist")
    assert learner is None

    service = LearnerService(engine.catalog, repo)
    learner, extracted = service.create_from_conversation(
        "I want to become a Cloud Engineer in 8 months. I know Linux and Git. "
        "I can spend 9 hours per week."
    )
    assert extracted.target_role == "cloud_engineer"
    assert learner.weekly_hours == 9.0
    assert learner.deadline_weeks == 32  # 8 months x 4 weeks

    loaded = repo.get_learner(learner.learner_id)
    assert loaded is not None
    assert loaded.goal_text == learner.goal_text
    assert loaded.known_skills == learner.known_skills
    assert "linux" in loaded.known_skills

    repo.delete_learner(learner.learner_id)
    assert repo.get_learner(learner.learner_id) is None


def test_persona_learner(engine):
    from app import config

    service = LearnerService(engine.catalog, engine.repo)
    persona = config.DEMO_PERSONAS[0]
    learner = service.create_from_persona(persona)
    assert learner.target_role == persona["role_id"]
    assert learner.profile_source == "persona"
    assert learner.weekly_hours == persona["weekly_hours"]
    assert set(persona["known_skills"]) <= set(learner.known_skills)


def test_completion_boosts_skills(engine, ml_learner):
    learner, _ = ml_learner
    before = learner.proficiency("python")
    service = LearnerService(engine.catalog, engine.repo)
    learner = service.mark_item_complete(learner, "course", "c_kaggle_python")
    assert learner.proficiency("python") > before
    assert "c_kaggle_python" in learner.completed_courses


def test_feedback_stored(engine, ml_learner):
    learner, _ = ml_learner
    service = LearnerService(engine.catalog, engine.repo)
    learner = service.record_feedback(learner, "c_kaggle_python", "course", "skip")
    assert any(fb["signal"] == "skip" for fb in learner.feedback)
    rows = engine.repo.feedback_for(learner.learner_id)
    assert any(r["signal"] == "skip" for r in rows)


def test_profile_update(engine, ml_learner):
    learner, _ = ml_learner
    service = LearnerService(engine.catalog, engine.repo)
    learner = service.update_profile(
        learner, weekly_hours=12.0, preferences=["video"], target_role="data_scientist"
    )
    assert learner.weekly_hours == 12.0
    assert learner.learning_preferences == ["video"]
    assert learner.target_role == "data_scientist"
    assert learner.target_domain == "Data Science"
