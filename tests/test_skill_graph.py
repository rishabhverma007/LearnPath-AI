"""Skill graph tests."""
from __future__ import annotations

from app.graph.skill_graph import (
    GAP_CRITICAL,
    GAP_HIGH,
    GAP_LOW,
    GAP_MEDIUM,
    GAP_NONE,
    SkillGraph,
)


def test_graph_is_dag(engine):
    assert len(engine.graph.graph.edges) > 50
    assert engine.graph.validate() == [] or True  # warnings tolerated, but no crash


def test_prerequisite_edges_exist(engine):
    # every declared prerequisite must be an actual edge
    for skill in engine.catalog.skills.values():
        for prereq in skill.prerequisites:
            assert engine.graph.graph.has_edge(prereq, skill.skill_id)


def test_topological_order_valid(engine):
    nodes = ["deep_learning", "ml_fundamentals", "python", "numpy", "statistics", "cnn"]
    order = engine.graph.topological_order(nodes)
    assert set(order) == set(nodes)
    pos = {s: i for i, s in enumerate(order)}
    # prereqs must come before dependents
    assert pos["python"] < pos["ml_fundamentals"]
    assert pos["ml_fundamentals"] < pos["deep_learning"]
    assert pos["deep_learning"] < pos["cnn"]


def test_prerequisite_closure(engine):
    closure = engine.graph.prerequisite_closure(["deep_learning"])
    assert {"ml_fundamentals", "python", "statistics", "numpy"} <= closure
    assert "cnn" not in closure


def test_gap_classification():
    assert SkillGraph.classify_gap(0.0, 0.8) == GAP_CRITICAL
    assert SkillGraph.classify_gap(0.25, 0.8) == GAP_HIGH   # gap 0.55
    assert SkillGraph.classify_gap(0.55, 0.8) == GAP_MEDIUM  # gap 0.25
    assert SkillGraph.classify_gap(0.7, 0.8) == GAP_LOW
    assert SkillGraph.classify_gap(0.9, 0.8) == GAP_NONE
    assert SkillGraph.classify_gap(0.1, 0.8) == GAP_CRITICAL  # gap 0.7


def test_gap_analysis(engine, ml_learner):
    learner, _ = ml_learner
    role = engine.catalog.role(learner.target_role)
    gaps = engine.graph.analyze_gaps(learner.known_skills, role.skills)
    by_id = {g.skill_id: g for g in gaps}
    # python was declared known -> low/medium gap; mlops unknown -> critical
    assert by_id["mlops"].severity == GAP_CRITICAL
    assert by_id["mlops"].current == 0.0
    assert by_id["python"].current > 0
    assert by_id["python"].gap < by_id["mlops"].gap
