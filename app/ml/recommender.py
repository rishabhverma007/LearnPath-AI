"""Hybrid recommendation engine.

Combines, for every candidate item (course / project / resource /
assessment):
  semantic relevance   (TF-IDF cosine vs learner goal + role)
  skill-gap coverage   (how many missing/weak skills it addresses)
  goal alignment       (contribution to the target role's competency map)
  prerequisite fit     (is the learner ready?)
  difficulty fit       (distance from the learner's estimated level)
  preference fit       (content format vs learning preference)
  time fit             (duration vs weekly availability)
  feedback signal      (history: likes/skips)

Weights live in config.RECOMMENDATION_WEIGHTS. A Maximal Marginal
Relevance pass diversifies the final list so the top-K mixes courses,
projects, resources and assessments rather than five similar courses.
Every result carries machine-readable reason scores that the UI turns
into a "Why this?" explanation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app import config
from app.ai.embeddings import SemanticIndex
from app.data.loader import DataCatalog
from app.database.models import Learner
from app.ml import personalization
from app.utils import clamp, get_logger

log = get_logger("recommender")

ITEM_TYPES = ("course", "project", "resource", "assessment")


@dataclass
class RecommendationResult:
    item_type: str
    item_id: str
    title: str
    score: float
    reasons: dict[str, float] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    difficulty: int = 3
    duration_hours: float = 5.0
    format: str = "course"
    url: str = ""
    description: str = ""
    provider: str = ""
    explanation_lines: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_type": self.item_type,
            "item_id": self.item_id,
            "title": self.title,
            "score": round(self.score, 3),
            "reasons": self.reasons,
            "skills": self.skills,
            "difficulty": self.difficulty,
            "duration_hours": self.duration_hours,
            "format": self.format,
            "url": self.url,
            "description": self.description,
            "provider": self.provider,
            "explanation_lines": self.explanation_lines,
        }


class HybridRecommender:
    def __init__(
        self,
        catalog: DataCatalog,
        semantic_index: SemanticIndex,
        weights: config.RecommendationWeights | None = None,
    ) -> None:
        self.catalog = catalog
        self.index = semantic_index
        self.weights = weights or config.RECOMMENDATION_WEIGHTS

    # ------------------------------------------------------------------
    # Candidate builders
    # ------------------------------------------------------------------
    def _candidates(self, learner: Learner, role_skills: set[str]) -> list[dict[str, Any]]:
        cands: list[dict[str, Any]] = []
        for course in self.catalog.courses.values():
            if course.course_id in learner.completed_courses:
                continue
            cands.append({
                "item_type": "course", "item_id": course.course_id, "title": course.title,
                "skills": list(course.skills), "difficulty": course.difficulty,
                "duration_hours": course.duration_hours, "format": course.format,
                "url": course.url, "description": course.description, "provider": course.provider,
                "prerequisites": list(course.prerequisites),
                "career_roles": list(course.career_roles),
            })
        for project in self.catalog.projects.values():
            if project.project_id in learner.completed_projects:
                continue
            cands.append({
                "item_type": "project", "item_id": project.project_id, "title": project.title,
                "skills": list(project.skills), "difficulty": project.difficulty,
                "duration_hours": project.duration_hours, "format": "project",
                "url": "", "description": project.description, "provider": "Hands-on",
                "prerequisites": list(project.prerequisites),
                "career_roles": list(project.career_roles),
            })
        for res in self.catalog.resources.values():
            if res.resource_id in learner.completed_resources:
                continue
            cands.append({
                "item_type": "resource", "item_id": res.resource_id, "title": res.title,
                "skills": [res.skill_id], "difficulty": 2,
                "duration_hours": res.duration_min / 60.0, "format": res.type,
                "url": res.url, "description": res.description, "provider": "Reference",
                "prerequisites": [], "career_roles": [],
            })
        for ass in self.catalog.assessments.values():
            cands.append({
                "item_type": "assessment", "item_id": ass.assessment_id, "title": ass.title,
                "skills": [ass.skill_id], "difficulty": ass.difficulty,
                "duration_hours": 0.5, "format": "assessment",
                "url": "", "description": ass.description, "provider": "Knowledge check",
                "prerequisites": [], "career_roles": [],
            })
        return cands

    # ------------------------------------------------------------------
    # Component scoring
    # ------------------------------------------------------------------
    @staticmethod
    def _doc_id(cand: dict[str, Any]) -> str:
        item_type = cand.get("item_type") or (
            "project" if "project_id" in cand else "course"
        )
        item_id = (
            cand.get("item_id")
            or cand.get("course_id")
            or cand.get("project_id")
            or ""
        )
        return f"{item_type}:{item_id}"

    def _semantic_relevance(self, learner: Learner, cand: dict[str, Any]) -> float:
        role = self.catalog.role(learner.target_role)
        query = learner.goal_text
        if role:
            query += f" {role.title} {role.summary}"
        return float(clamp(self.index.similarity_to(query, self._doc_id(cand)), 0.0, 1.0))

    def _skill_gap_coverage(self, learner: Learner, cand: dict[str, Any], role) -> float:
        if not cand["skills"]:
            return 0.5
        scores = []
        for sid in cand["skills"]:
            skill = self.catalog.skill(sid)
            if skill is None:
                continue
            required = role.target_for(sid) if role else 0.6
            current = learner.proficiency(sid)
            gap = clamp(required - current, 0.0, 1.0)
            scores.append(gap)
        return float(np.mean(scores)) if scores else 0.0

    def _goal_alignment(self, cand: dict[str, Any], role_skills: set[str], target_role_id: str) -> float:
        if not cand["skills"]:
            return 0.0
        aligned = sum(1 for s in cand["skills"] if s in role_skills)
        role_match = 1.0 if target_role_id in cand["career_roles"] else 0.0
        return float(0.7 * aligned / len(cand["skills"]) + 0.3 * role_match)

    def _prerequisite_fit(self, learner: Learner, cand: dict[str, Any]) -> float:
        prereqs = cand.get("prerequisites") or []
        if not prereqs:
            return 1.0
        fits = []
        for p in prereqs:
            prof = learner.proficiency(p)
            if prof >= config.PREREQ_READY_THRESHOLD:
                fits.append(1.0)
            else:
                fits.append(0.4 * prof / config.PREREQ_READY_THRESHOLD)
        return float(np.mean(fits)) if fits else 1.0

    def _difficulty_fit(self, learner: Learner, cand: dict[str, Any]) -> float:
        level = personalization.learner_level_estimate(learner)
        diff = cand.get("difficulty", 3)
        return float(clamp(1.0 - abs(level - diff) / 4.0, 0.0, 1.0))

    def _preference_fit(self, learner: Learner, cand: dict[str, Any]) -> float:
        fmt = cand.get("format", "course")
        prefs = personalization.preference_weights(learner)
        best = 0.0
        for pref, weight in prefs.items():
            match = config.PREFERENCE_FORMAT_MATCH.get(pref, {}).get(fmt, 0.5)
            best = max(best, match * weight)
        return float(best)

    def _time_fit(self, learner: Learner, cand: dict[str, Any]) -> float:
        hours = float(cand.get("duration_hours", 2))
        budget = max(1.0, learner.weekly_hours)
        if hours <= 0.25:
            return 1.0
        if hours <= 0.6 * budget:
            return 1.0
        if hours <= 1.5 * budget:
            return 0.5
        return 0.15

    # ------------------------------------------------------------------
    # Single-item scoring (used by ranking and the path optimizer)
    # ------------------------------------------------------------------
    def score_item(self, learner: Learner, cand: dict[str, Any]) -> tuple[dict[str, float], float]:
        role = self.catalog.role(learner.target_role)
        role_skills = set(role.required_skills) if role else set()
        item_id = (
            cand.get("item_id")
            or cand.get("course_id")
            or cand.get("project_id")
            or cand.get("resource_id")
            or ""
        )
        reasons = {
            "semantic_relevance": self._semantic_relevance(learner, cand),
            "skill_gap_coverage": self._skill_gap_coverage(learner, cand, role),
            "goal_alignment": self._goal_alignment(cand, role_skills, learner.target_role),
            "prerequisite_fit": self._prerequisite_fit(learner, cand),
            "difficulty_fit": self._difficulty_fit(learner, cand),
            "preference_fit": self._preference_fit(learner, cand),
            "time_fit": self._time_fit(learner, cand),
            "feedback_signal": personalization.feedback_signal_for_item(learner, item_id),
        }
        score = sum(self.weights.__dict__[name] * reasons[name] for name in reasons)
        return reasons, float(score)

    # ------------------------------------------------------------------
    # Main ranking
    # ------------------------------------------------------------------
    def recommend(
        self, learner: Learner, k: int | None = None, diversify: bool = True
    ) -> list[RecommendationResult]:
        role = self.catalog.role(learner.target_role)
        role_skills = set(role.required_skills) if role else set()
        candidates = self._candidates(learner, role_skills)
        if not candidates:
            return []

        k = k or config.RECOMMENDATION_K
        results: list[RecommendationResult] = []
        for cand in candidates:
            reasons, score = self.score_item(learner, cand)
            result = RecommendationResult(
                item_type=cand["item_type"],
                item_id=cand["item_id"],
                title=cand["title"],
                score=round(score, 4),
                reasons=reasons,
                skills=cand["skills"],
                difficulty=cand.get("difficulty", 3),
                duration_hours=float(cand.get("duration_hours", 1)),
                format=cand.get("format", "course"),
                url=cand.get("url", ""),
                description=cand.get("description", ""),
                provider=cand.get("provider", ""),
            )
            result.explanation_lines = self.build_explanation(result, learner)
            results.append(result)

        results.sort(key=lambda r: -r.score)
        if diversify:
            results = self._mmr_diversify(results, k)
            results.sort(key=lambda r: -r.score)
        else:
            results = results[:k]
        return results

    # ------------------------------------------------------------------
    # Diversity: Maximal Marginal Relevance
    # ------------------------------------------------------------------
    def _item_similarity(self, a: RecommendationResult, b: RecommendationResult) -> float:
        a_skills = set(a.skills)
        b_skills = set(b.skills)
        if not a_skills or not b_skills:
            type_sim = 1.0 if a.item_type == b.item_type else 0.2
            return type_sim * 0.4
        jaccard = len(a_skills & b_skills) / len(a_skills | b_skills)
        type_sim = 1.0 if a.item_type == b.item_type else 0.35
        return float(0.6 * jaccard + 0.4 * type_sim)

    def _mmr_diversify(self, ranked: list[RecommendationResult], k: int) -> list[RecommendationResult]:
        if not ranked:
            return []
        selected: list[RecommendationResult] = [ranked[0]]
        pool = ranked[1:]
        while len(selected) < k and pool:
            best_idx, best_val = -1, -1.0
            for i, cand in enumerate(pool):
                rel = cand.score
                max_sim = max(
                    (self._item_similarity(cand, s) for s in selected),
                    default=0.0,
                )
                mmr = config.MMR_LAMBDA * rel - (1 - config.MMR_LAMBDA) * max_sim
                if mmr > best_val:
                    best_val, best_idx = mmr, i
            if best_idx == -1:
                break
            selected.append(pool.pop(best_idx))
        return selected

    # ------------------------------------------------------------------
    # Explainability
    # ------------------------------------------------------------------
    def build_explanation(self, result: RecommendationResult, learner: Learner) -> list[str]:
        lines: list[str] = []
        r = result.reasons

        def name(sid: str) -> str:
            s = self.catalog.skill(sid)
            return s.name if s else sid

        if r["semantic_relevance"] >= 0.55:
            lines.append(f"Strong semantic match with your goal ({r['semantic_relevance']:.0%} similarity to your goal text).")
        elif r["semantic_relevance"] >= 0.35:
            lines.append(f"Relevant to your goal (semantic match {r['semantic_relevance']:.0%}).")

        gap_skills = [s for s in result.skills if learner.proficiency(s) < config.PROFICIENCY_STRONG]
        if gap_skills:
            lines.append(f"Covers {len(gap_skills)} skill(s) you need to grow: {', '.join(name(s) for s in gap_skills[:4])}.")
        else:
            lines.append("Reinforces skills that support your target role.")

        role = self.catalog.role(learner.target_role)
        aligned = [s for s in result.skills if role and s in role.required_skills]
        if aligned:
            lines.append(f"Directly contributes to the {role.title if role else 'target'} competency map ({len(aligned)} aligned skill(s)).")

        prereqs = self._missing_prereqs(result.skills, learner)
        if prereqs:
            lines.append(f"Prerequisites you still need: {', '.join(name(p) for p in prereqs[:3])}.")
        else:
            lines.append("Prerequisites: you're ready to start this now.")

        if r["difficulty_fit"] >= 0.75:
            lines.append("Difficulty is well matched to your current level.")
        if r["preference_fit"] >= 0.7:
            pref = ", ".join(learner.learning_preferences or ["hands-on"])
            lines.append(f"Matches your {pref} learning preference.")
        if r["time_fit"] >= 0.9:
            lines.append(f"Fits comfortably in your {learner.weekly_hours:g} hrs/week budget.")

        if not lines:
            lines.append("Recommended based on your profile, skill gaps, and target role.")
        return lines

    def _missing_prereqs(self, skill_ids: list[str], learner: Learner) -> list[str]:
        missing: list[str] = []
        for sid in skill_ids:
            skill = self.catalog.skill(sid)
            if skill is None:
                continue
            for p in skill.prerequisites:
                if learner.proficiency(p) < config.PREREQ_READY_THRESHOLD and p not in missing:
                    missing.append(p)
        return missing
