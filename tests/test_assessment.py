"""Assessment engine tests."""
from __future__ import annotations


def test_mcq_grading(engine):
    a = engine.catalog.assessment("a_ml_fundamentals")
    # q1=test-set, q2=overfitting, q3=high-bias, q4=imbalance (all correct)
    result = a.grade({"q1": 1, "q2": 1, "q3": 0, "q4": 1})
    assert result["correct"] == 4
    assert result["score"] == 1.0
    assert result["concept_scores"]["train_test_split"] == 1.0
    # wrong answers drop the score and expose weak concepts
    result2 = a.grade({"q1": 0, "q2": 1, "q3": 0, "q4": 1})
    assert result2["correct"] == 3
    assert result2["score"] == 0.75


def test_multi_select_grading(engine):
    a = engine.catalog.assessment("a_classification")
    q3 = next(q for q in a.questions if q.type == "multi")
    assert a._check(q3, [0, 1, 3]) is True
    assert a._check(q3, [0, 1]) is False
    assert a._check(q3, [0, 1, 3, 2]) is False
    assert a._check(q3, None) is False


def test_missing_answers_score_zero(engine):
    a = engine.catalog.assessment("a_python")
    result = a.grade({})
    assert result["score"] == 0.0
    assert result["correct"] == 0


def test_invalid_answers_tolerated(engine):
    a = engine.catalog.assessment("a_sql")
    result = a.grade({"q1": "banana", "q2": None, "q3": 99, "q4": [0, 2]})
    assert result["total"] == 4
    assert 0 <= result["score"] <= 1


def test_assessment_for_every_roadmap_skill_exists(engine, ml_learner):
    """Every skill in the roadmap with a knowledge check has a valid assessment."""
    _, roadmap = ml_learner
    for phase in roadmap.phases:
        for item in phase.items:
            if item.item_type == "assessment":
                assert engine.catalog.assessment(item.item_id) is not None
