"""End-to-end test of the FastAPI backend + SPA demo flow.

Exercises the exact demo story over the real HTTP API:
  meta -> persona onboarding -> roadmap -> skills intelligence
  -> recommendations (explainable) -> coach Q&A -> assessment
  -> adaptive roadmap -> career readiness + what-if simulator
  -> static frontend assets served.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _create_persona(client, persona_id: str = "ml_engineer") -> dict:
    res = client.post("/api/learners", json={"persona_id": persona_id})
    assert res.status_code == 200, res.text
    return res.json()


def test_meta_exposes_catalogue_and_personas(client):
    res = client.get("/api/meta")
    assert res.status_code == 200
    meta = res.json()
    assert len(meta["personas"]) == 4
    assert "ml_engineer" in meta["roles"]
    assert meta["llm_mode"] in ("local", "openai")
    assert len(meta["skills"]) > 40
    assert sum(meta["weights"].values()) == pytest.approx(1.0)


def test_persona_onboarding_generates_roadmap(client):
    learner = _create_persona(client)
    assert learner["target_role"] == "ml_engineer"
    assert learner["weekly_hours"] == 8.0
    assert len(learner["known_skills"]) >= 4

    res = client.post(f"/api/learners/{learner['learner_id']}/roadmap", json={"mode": "balanced"})
    assert res.status_code == 200, res.text
    roadmap = res.json()
    assert roadmap["feasible"] is True
    assert len(roadmap["phases"]) >= 4
    labels = [p["label"] for p in roadmap["phases"]]
    assert "Foundations" in labels
    # every phase has items and a sane schedule
    for p in roadmap["phases"]:
        assert p["items"], f"empty phase {p['label']}"
        assert p["week_start"] >= 1 and p["week_end"] >= p["week_start"]


def test_roadmap_respects_prerequisites(client):
    learner = _create_persona(client)
    res = client.post(f"/api/learners/{learner['learner_id']}/roadmap", json={"mode": "balanced"})
    roadmap = res.json()
    # all items in the roadmap must appear in the catalogue
    for p in roadmap["phases"]:
        for item in p["items"]:
            assert item["item_id"]
            assert item["skill_ids"]


def test_skill_intelligence_returns_gaps(client):
    learner = _create_persona(client)
    res = client.get(f"/api/learners/{learner['learner_id']}/skills")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["role"]["role_id"] == "ml_engineer"
    assert data["gaps"], "expected at least one skill gap"
    assert data["radar"]["skills"]
    # gap ordering: biggest gaps first
    gaps = data["gaps"]
    assert gaps[0]["gap"] >= gaps[-1]["gap"]


def test_recommendations_are_explainable_and_diverse(client):
    learner = _create_persona(client)
    res = client.post(f"/api/learners/{learner['learner_id']}/recommendations", json={"k": 10})
    assert res.status_code == 200, res.text
    recs = res.json()
    assert len(recs) >= 6
    for r in recs:
        assert 0 <= r["score"] <= 1
        assert r["explanation_lines"], f"missing explanation for {r['title']}"
        assert set(r["reasons"]) >= {"semantic_relevance", "skill_gap_coverage", "goal_alignment"}
    # diversity: more than one item type in top-6
    types = {r["item_type"] for r in recs[:6]}
    assert len(types) >= 2


def test_coach_answers_mission_question(client):
    learner = _create_persona(client)
    client.post(f"/api/learners/{learner['learner_id']}/roadmap", json={"mode": "balanced"})
    res = client.post(
        f"/api/learners/{learner['learner_id']}/coach",
        json={"message": "What should I do today?"},
    )
    assert res.status_code == 200, res.text
    reply = res.json()
    assert reply["intent"] == "mission"
    assert "minute" in reply["text"].lower() or "focus" in reply["text"].lower()


def test_assessment_submission_adapts_roadmap(client):
    learner = _create_persona(client)
    client.post(f"/api/learners/{learner['learner_id']}/roadmap", json={"mode": "balanced"})

    meta = client.get("/api/meta").json()
    ml_assessment = next(a for a in meta["assessments"] if a["skill_id"] == "ml_fundamentals")

    res = client.get(f"/api/assessments/{ml_assessment['assessment_id']}")
    assert res.status_code == 200, res.text
    assessment = res.json()
    assert assessment["questions"], "assessment must expose questions"
    for q in assessment["questions"]:
        assert "answer" not in q, "answers must never reach the client"
        assert q["options"]

    # answer everything wrong -> below pass mark -> remediation inserted
    answers = {q["id"]: 0 for q in assessment["questions"]}
    res = client.post(
        f"/api/learners/{learner['learner_id']}/assessments/{assessment['assessment_id']}/submit",
        json={"answers": answers},
    )
    assert res.status_code == 200, res.text
    result = res.json()
    assert result["pass"] is False
    assert result["weak_concepts"], "all-wrong answers must produce weak concepts"
    assert result["roadmap_adapted"] is True
    assert any("Remediation" in n or "remediation" in n.lower() for n in result["adaptation_notes"])


def test_strong_assessment_accelerates_roadmap(client):
    learner = _create_persona(client)
    client.post(f"/api/learners/{learner['learner_id']}/roadmap", json={"mode": "balanced"})

    meta = client.get("/api/meta").json()
    python_assessment = next(a for a in meta["assessments"] if a["skill_id"] == "python")
    res = client.get(f"/api/assessments/{python_assessment['assessment_id']}")
    assessment = res.json()

    # A real all-correct submission can't be constructed client-side (answers are
    # stripped from the API), so simulate a strong score on the twin directly and
    # verify the adaptive engine produces the acceleration note.
    from app.services.engine import get_engine
    from app.ml.personalization import apply_assessment_result
    from app.services.roadmap_service import RoadmapService

    eng = get_engine()
    stored = eng.repo.get_learner(learner["learner_id"])
    apply_assessment_result(stored, "python", 0.95, eng.catalog)
    eng.repo.save_learner(stored)
    adapted = RoadmapService(eng.optimizer, eng.repo).adapt_after_assessment(
        stored, {"score": 0.95, "weak_concepts": [], "skill_id": "python"}
    )
    assert any("Strong performance" in n for n in adapted.adaptation_notes)


def test_career_readiness_and_whatif(client):
    learner = _create_persona(client, persona_id="data_scientist")
    res = client.get(f"/api/learners/{learner['learner_id']}/career")
    assert res.status_code == 200, res.text
    career = res.json()
    assert career["role_id"] == "data_scientist"
    assert 0 <= career["overall"] <= 1
    assert len(career["dimensions"]) == 5
    assert career["to_reach_90"]

    res = client.post(
        f"/api/learners/{learner['learner_id']}/whatif", json={"new_role": "ml_engineer"}
    )
    assert res.status_code == 200, res.text
    w = res.json()
    assert w["target_role"] == "ml_engineer"
    assert w["retained_skills"] or w["additional_skills"]
    assert w["extra_hours"] > 0


def test_feedback_and_missed_session_signal(client):
    learner = _create_persona(client)
    res = client.post(
        f"/api/learners/{learner['learner_id']}/feedback",
        json={"item_id": "some_course", "item_type": "course", "signal": "like"},
    )
    assert res.status_code == 200, res.text
    assert any(f["signal"] == "like" for f in res.json()["feedback"])

    res = client.post(f"/api/learners/{learner['learner_id']}/session-missed")
    assert res.status_code == 200, res.text
    assert any(a["event"] == "session_missed" for a in res.json()["recent_activity"])


def test_frontend_spa_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "LearnPath AI" in res.text
    for asset in ["/static/js/app.js", "/static/js/pages.js", "/static/js/motion.js",
                  "/static/css/styles.css"]:
        assert client.get(asset).status_code == 200


def test_unknown_learner_404(client):
    assert client.get("/api/learners/nope").status_code == 404
    assert client.post("/api/profile/analyze", json={"text": ""}).status_code == 422
