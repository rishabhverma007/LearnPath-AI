"""Roadmap generation + adaptive learning tests."""
from __future__ import annotations

from app import config
from app.services.assessment_service import AssessmentService
from app.services.roadmap_service import RoadmapService


def _assert_prereq_valid(engine, roadmap):
    """Every roadmap item's skill must have its prerequisites in an earlier item."""
    placed: set[str] = set()
    for phase in roadmap.phases:
        for item in phase.items:
            for sid in item.skill_ids:
                skill = engine.catalog.skill(sid)
                if skill is None:
                    continue
                for prereq in skill.prerequisites:
                    assert prereq in placed, (
                        f"{sid} in phase {phase.index} requires {prereq} not yet placed"
                    )
                placed.add(sid)


def test_roadmap_prereq_ordering(engine, ml_learner):
    learner, roadmap = ml_learner
    assert len(roadmap.phases) >= 5
    _assert_prereq_valid(engine, roadmap)


def test_roadmap_feasible_for_deadline(engine, ml_learner):
    learner, roadmap = ml_learner
    assert roadmap.feasible is True
    assert roadmap.total_weeks <= learner.deadline_weeks + 1
    assert roadmap.total_hours > 0


def test_roadmap_mixes_formats(engine, ml_learner):
    _, roadmap = ml_learner
    item_types = {i.item_type for p in roadmap.phases for i in p.items}
    assert {"course", "assessment"} <= item_types
    assert "project" in item_types


def test_roadmap_modes_differ(engine, ml_learner):
    learner, _ = ml_learner
    svc = RoadmapService(engine.optimizer, engine.repo)
    balanced = svc.generate(learner, mode="balanced")
    accelerated = svc.generate(learner, mode="accelerated")
    assert accelerated.weekly_hours > balanced.weekly_hours
    assert accelerated.total_weeks < balanced.total_weeks


def test_adaptive_remediation_inserted(engine, ml_learner):
    learner, roadmap = ml_learner
    service = AssessmentService(engine.catalog, engine.repo,
                                RoadmapService(engine.optimizer, engine.repo))
    assessment = engine.catalog.assessment("a_ml_fundamentals")
    # deliberately fail 3 of 4 questions
    result = service.submit(learner, assessment, {"q1": 0, "q2": 0, "q3": 0, "q4": 1})
    assert result["score"] < config.ASSESSMENT_PASS_SCORE
    assert len(result["weak_concepts"]) >= 1
    assert result.get("roadmap_adapted") is True
    assert any("Remediation" in note or "remediation" in note.lower()
               for note in result.get("adaptation_notes", []))

    updated = RoadmapService(engine.optimizer, engine.repo).load(learner)
    assert updated is not None
    remedial = [p for p in updated.phases if p.label == "Remediation"]
    assert len(remedial) == 1
    labels = {i.item_type for i in remedial[0].items}
    assert "micro_lesson" in labels
    assert "assessment" in labels  # re-check


def test_strong_performance_accelerates(engine, ml_learner):
    learner, _ = ml_learner
    service = AssessmentService(engine.catalog, engine.repo,
                                RoadmapService(engine.optimizer, engine.repo))
    assessment = engine.catalog.assessment("a_ml_fundamentals")
    # all four correct (answers: 1, 1, 0, 1)
    result = service.submit(learner, assessment, {"q1": 1, "q2": 1, "q3": 0, "q4": 1})
    assert result["score"] >= config.ASSESSMENT_STRONG_SCORE
    assert any("Strong" in n or "accelerat" in n.lower() for n in result.get("adaptation_notes", []))


def test_learner_state_updated_after_assessment(engine, ml_learner):
    learner, _ = ml_learner
    before = learner.proficiency("ml_fundamentals")
    service = AssessmentService(engine.catalog, engine.repo)
    assessment = engine.catalog.assessment("a_ml_fundamentals")
    # 3 of 4 correct (answers: 1, 1, 0, 1)
    service.submit(learner, assessment, {"q1": 1, "q2": 1, "q3": 0, "q4": 0})
    assert learner.proficiency("ml_fundamentals") > before
    assert learner.assessment_scores.get("ml_fundamentals") == 0.75
