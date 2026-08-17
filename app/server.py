"""LearnPath AI — FastAPI backend.

Serves the JSON API and the cinematic SPA frontend from one process.

Run:  python -m uvicorn app.server:app --port 8765
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.services.engine import get_engine
from app.services.learner_service import LearnerService
from app.services.recommendation_service import RecommendationService
from app.services.roadmap_service import RoadmapService
from app.services.assessment_service import AssessmentService
from app.utils import get_logger

log = get_logger("server")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="LearnPath AI", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Composition
# ----------------------------------------------------------------------
def _engine():
    return get_engine()


def _learner_service():
    eng = _engine()
    return LearnerService(eng.catalog, eng.repo)


def _roadmap_service():
    eng = _engine()
    return RoadmapService(eng.optimizer, eng.repo)


def _load_learner_or_404(learner_id: str):
    eng = _engine()
    learner = eng.repo.get_learner(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail=f"Learner {learner_id} not found")
    return learner


# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------
@app.post("/api/auth/signup")
def signup(payload: dict = Body(...)):
    from app.services.auth_service import AuthError, AuthService

    try:
        return AuthService(_engine().repo).signup(
            str(payload.get("name", "")),
            str(payload.get("email", "")),
            str(payload.get("password", "")),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/signin")
def signin(payload: dict = Body(...)):
    from app.services.auth_service import AuthError, AuthService

    try:
        return AuthService(_engine().repo).signin(
            str(payload.get("email", "")),
            str(payload.get("password", "")),
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/auth/guest")
def guest():
    from app.services.auth_service import AuthService

    return AuthService(_engine().repo).guest()


@app.get("/api/auth/me")
def me(authorization: str = Header(default="")):
    from app.services.auth_service import AuthService

    token = authorization.removeprefix("Bearer ").strip()
    user = AuthService(_engine().repo).me(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return {"user": user}


@app.post("/api/auth/signout")
def signout(authorization: str = Header(default="")):
    from app.services.auth_service import AuthService

    token = authorization.removeprefix("Bearer ").strip()
    AuthService(_engine().repo).signout(token)
    return {"ok": True}


# ----------------------------------------------------------------------
# Meta / catalogue
# ----------------------------------------------------------------------
@app.get("/api/meta")
def meta():
    eng = _engine()
    return {
        "roles": {rid: {"role_id": r.role_id, "title": r.title, "domain": r.domain,
                        "summary": r.summary} for rid, r in eng.catalog.roles.items()},
        "skills": [
            {"skill_id": s.skill_id, "name": s.name, "category": s.category,
             "difficulty": s.difficulty, "prerequisites": list(s.prerequisites)}
            for s in eng.catalog.all_skills_sorted()
        ],
        "assessments": [
            {"assessment_id": a.assessment_id, "skill_id": a.skill_id, "title": a.title,
             "description": a.description, "difficulty": a.difficulty,
             "concepts": list(a.concepts), "num_questions": len(a.questions)}
            for a in sorted(eng.catalog.assessments.values(), key=lambda a: a.title)
        ],
        "personas": config.DEMO_PERSONAS,
        "weights": config.RECOMMENDATION_WEIGHTS.as_dict(),
        "llm_mode": "openai" if config.OPENAI_API_KEY else "local",
    }


# ----------------------------------------------------------------------
# Profile analysis / learner lifecycle
# ----------------------------------------------------------------------
@app.post("/api/profile/analyze")
def analyze_profile(payload: dict = Body(...)):
    text = str(payload.get("text", "")).strip()
    if len(text) < 3:
        raise HTTPException(status_code=422, detail="Please describe your goal.")
    eng = _engine()
    from app.ai.extraction import extract_profile_hybrid

    extracted = extract_profile_hybrid(text, eng.catalog)
    return extracted.as_dict()


@app.post("/api/learners")
def create_learner(payload: dict = Body(...)):
    eng = _engine()
    service = LearnerService(eng.catalog, eng.repo)
    if payload.get("persona_id"):
        persona = next((p for p in config.DEMO_PERSONAS if p["id"] == payload["persona_id"]), None)
        if persona is None:
            raise HTTPException(status_code=404, detail="Unknown persona")
        learner = service.create_from_persona(persona)
    else:
        text = str(payload.get("text", "")).strip()
        if len(text) < 3:
            raise HTTPException(status_code=422, detail="Describe your goal first.")
        learner, _ = service.create_from_conversation(text)
        # apply client-side corrections if provided
        corrections = payload.get("profile")
        if corrections:
            service.update_profile(
                learner,
                target_role=corrections.get("target_role"),
                experience_level=corrections.get("experience_level"),
                weekly_hours=corrections.get("weekly_hours"),
                deadline_weeks=corrections.get("deadline_weeks"),
                preferences=corrections.get("preferences"),
                skills=corrections.get("skills"),
                remove_skills=corrections.get("remove_skills"),
            )
    return learner.to_dict()


@app.get("/api/learners")
def list_learners():
    eng = _engine()
    return [l.to_dict() for l in eng.repo.list_learners()]


@app.get("/api/learners/{learner_id}")
def get_learner(learner_id: str):
    return _load_learner_or_404(learner_id).to_dict()


@app.put("/api/learners/{learner_id}")
def update_learner(learner_id: str, payload: dict = Body(...)):
    learner = _load_learner_or_404(learner_id)
    service = _learner_service()
    learner = service.update_profile(
        learner,
        goal_text=payload.get("goal_text"),
        target_role=payload.get("target_role"),
        experience_level=payload.get("experience_level"),
        weekly_hours=payload.get("weekly_hours"),
        deadline_weeks=payload.get("deadline_weeks"),
        preferences=payload.get("preferences"),
        skills=payload.get("skills"),
    )
    return learner.to_dict()


@app.delete("/api/learners/{learner_id}")
def delete_learner(learner_id: str):
    _engine().repo.delete_learner(learner_id)
    return {"ok": True}


# ----------------------------------------------------------------------
# Roadmap
# ----------------------------------------------------------------------
@app.post("/api/learners/{learner_id}/roadmap")
def generate_roadmap(learner_id: str, payload: dict = Body(default={})):
    learner = _load_learner_or_404(learner_id)
    roadmap = _roadmap_service().generate(learner, mode=payload.get("mode", "balanced"))
    return roadmap.as_dict()


@app.get("/api/learners/{learner_id}/roadmap")
def get_roadmap(learner_id: str):
    learner = _load_learner_or_404(learner_id)
    roadmap = _roadmap_service().load(learner)
    if roadmap is None:
        return {"phases": [], "generated": False}
    return roadmap.as_dict() | {"generated": True}


# ----------------------------------------------------------------------
# Recommendations
# ----------------------------------------------------------------------
@app.post("/api/learners/{learner_id}/recommendations")
def recommend(learner_id: str, payload: dict = Body(default={})):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    results = RecommendationService(eng.recommender, eng.repo).recommend(
        learner, k=payload.get("k", 10)
    )
    return [r.as_dict() for r in results]


# ----------------------------------------------------------------------
# Items / feedback
# ----------------------------------------------------------------------
@app.post("/api/learners/{learner_id}/items/complete")
def complete_item(learner_id: str, payload: dict = Body(...)):
    learner = _load_learner_or_404(learner_id)
    service = _learner_service()
    learner = service.mark_item_complete(
        learner, str(payload.get("item_type", "")), str(payload.get("item_id", ""))
    )
    _roadmap_service().refresh_statuses(learner)
    return learner.to_dict()


@app.post("/api/learners/{learner_id}/feedback")
def add_feedback(learner_id: str, payload: dict = Body(...)):
    learner = _load_learner_or_404(learner_id)
    service = _learner_service()
    learner = service.record_feedback(
        learner,
        str(payload.get("item_id", "")),
        str(payload.get("item_type", "")),
        str(payload.get("signal", "")),
        str(payload.get("comment", "")),
    )
    if payload.get("signal") in ("like", "complete", "skip"):
        eng = _engine()
        RecommendationService(eng.recommender, eng.repo).record_feedback(
            learner, str(payload.get("item_id", "")), str(payload.get("item_type", "")),
            str(payload.get("signal", "")),
        )
    if payload.get("signal") == "complete":
        service.mark_item_complete(
            learner, str(payload.get("item_type", "")), str(payload.get("item_id", ""))
        )
    return learner.to_dict()


@app.post("/api/learners/{learner_id}/session-missed")
def session_missed(learner_id: str):
    learner = _load_learner_or_404(learner_id)
    learner = _learner_service().record_session_missed(learner)
    return learner.to_dict()


# ----------------------------------------------------------------------
# Skill intelligence
# ----------------------------------------------------------------------
@app.get("/api/learners/{learner_id}/skills")
def skill_intelligence(learner_id: str):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    role = eng.catalog.role(learner.target_role)
    if role is None:
        raise HTTPException(status_code=404, detail="No target role set")
    gaps = eng.graph.analyze_gaps(learner.known_skills, role.skills)
    return {
        "role": {"role_id": role.role_id, "title": role.title, "domain": role.domain},
        "gaps": [g.__dict__ for g in gaps],
        "severity_summary": {
            sev: len(items) for sev, items in eng.graph.gap_summary(gaps).items()
        },
        "radar": {
            "skills": [g.name for g in sorted(gaps, key=lambda g: -g.gap)[:8]],
            "current": [g.current for g in sorted(gaps, key=lambda g: -g.gap)[:8]],
            "required": [g.required for g in sorted(gaps, key=lambda g: -g.gap)[:8]],
        },
        "baseline": (learner.current_learning_state or {}).get("baseline", {}),
        "known_skills": learner.known_skills,
        "learning_velocity": learner.learning_velocity(),
    }


# ----------------------------------------------------------------------
# Assessments
# ----------------------------------------------------------------------
@app.get("/api/assessments/{assessment_id}")
def get_assessment(assessment_id: str):
    """Full assessment for the client — questions and options, answers stripped."""
    eng = _engine()
    assessment = eng.catalog.assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Unknown assessment")
    return {
        "assessment_id": assessment.assessment_id,
        "skill_id": assessment.skill_id,
        "title": assessment.title,
        "description": assessment.description,
        "difficulty": assessment.difficulty,
        "concepts": list(assessment.concepts),
        "questions": [
            {
                "id": q.id,
                "concept": q.concept,
                "type": q.type,
                "question": q.question,
                "options": list(q.options),
            }
            for q in assessment.questions
        ],
    }


@app.post("/api/learners/{learner_id}/assessments/{assessment_id}/submit")
def submit_assessment(learner_id: str, assessment_id: str, payload: dict = Body(...)):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    assessment = eng.catalog.assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Unknown assessment")
    service = AssessmentService(eng.catalog, eng.repo, _roadmap_service())
    result = service.submit(learner, assessment, payload.get("answers", {}))
    return result


@app.post("/api/learners/{learner_id}/micro-lesson")
def micro_lesson(learner_id: str, payload: dict = Body(...)):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    service = AssessmentService(eng.catalog, eng.repo)
    return service.generate_micro_lesson(
        learner, str(payload.get("skill_id", "")), payload.get("weak_concepts")
    )


@app.post("/api/learners/{learner_id}/project")
def generate_project(learner_id: str, payload: dict = Body(...)):
    learner = _load_learner_or_404(learner_id)
    service = AssessmentService(_engine().catalog, _engine().repo)
    return service.generate_project(learner, str(payload.get("skill_id", "")))


# ----------------------------------------------------------------------
# Coach
# ----------------------------------------------------------------------
@app.post("/api/learners/{learner_id}/coach")
def coach_chat(learner_id: str, payload: dict = Body(...)):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    roadmap = _roadmap_service().load(learner)
    reply = eng.coach.chat(learner, roadmap, str(payload.get("message", "")))
    return reply.as_dict()


# ----------------------------------------------------------------------
# Mission / career / what-if
# ----------------------------------------------------------------------
@app.get("/api/learners/{learner_id}/mission")
def mission(learner_id: str):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    roadmap = _roadmap_service().load(learner)
    if roadmap is None or not roadmap.phases:
        return {"mission": None, "schedule": None}
    from app.ml.daily_mission import build_daily_mission, weekly_schedule

    return {
        "mission": build_daily_mission(learner, roadmap, eng.catalog).as_dict(),
        "schedule": weekly_schedule(learner, roadmap),
    }


@app.get("/api/learners/{learner_id}/career")
def career(learner_id: str):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    from app.ml.career_readiness import compute_readiness

    readiness = compute_readiness(learner, eng.catalog)
    if readiness is None:
        raise HTTPException(status_code=404, detail="No target role set")
    return readiness.as_dict()


@app.post("/api/learners/{learner_id}/whatif")
def what_if(learner_id: str, payload: dict = Body(...)):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    from app.ml.what_if import simulate_role_switch

    result = simulate_role_switch(learner, str(payload.get("new_role", "")), eng.catalog, eng.graph)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown role")
    return result.as_dict()


@app.get("/api/learners/{learner_id}/insights")
def insights(learner_id: str):
    learner = _load_learner_or_404(learner_id)
    eng = _engine()
    role = eng.catalog.role(learner.target_role)
    if role is None:
        raise HTTPException(status_code=404, detail="No target role set")
    from app.ml.evaluation import evaluate_recommendations

    recs = eng.recommender.recommend(learner, k=8)
    gaps = [g for g in eng.graph.analyze_gaps(learner.known_skills, role.skills) if g.gap > 0.15]
    raw = evaluate_recommendations(
        learner, recs, set(role.required_skills), {g.skill_id for g in gaps},
        total_skills=len(eng.catalog.skills), k=5,
    )
    metrics = {
        "precision_at_5": raw["precision_at_k"],
        "recall_at_5": raw["recall_at_k"],
        "ndcg_at_5": raw["ndcg_at_k"],
        "coverage": raw["catalogue_coverage"],
        "diversity": raw["type_diversity"],
    }
    return {
        "metrics": metrics,
        "acceptance_rate": eng.repo.rec_acceptance_rate(learner.learner_id),
        "top_skills": sorted(
            {s for r in recs for s in r.skills},
            key=lambda sid: sum(1 for r in recs if sid in r.skills), reverse=True,
        )[:5],
    }


# ----------------------------------------------------------------------
# Static frontend
# ----------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.middleware("http")
async def no_cache(request, call_next):
    """Never cache the SPA shell or frontend assets during development (see index.html ?v= cache busting)."""
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# ----------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765)
