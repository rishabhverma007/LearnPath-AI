"""Career Readiness Index.

Computes a 0-100 readiness score for the learner's target role across
dimensions, plus concrete guidance on what is required to reach 90%.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app import config
from app.data.loader import DataCatalog
from app.database.models import Learner

# Skills counted toward the deployment dimension
DEPLOYMENT_SKILLS = {
    "fastapi", "docker", "cloud", "mlops", "monitoring", "aws",
    "kubernetes", "terraform", "cicd", "site_reliability", "cloud_arch",
}


@dataclass
class ReadinessDimension:
    key: str
    label: str
    score: float          # 0..1
    weight: float
    detail: str = ""


@dataclass
class CareerReadiness:
    role_id: str
    overall: float
    dimensions: list[ReadinessDimension] = field(default_factory=list)
    to_reach_90: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "overall": round(self.overall, 3),
            "dimensions": [
                {"key": d.key, "label": d.label, "score": round(d.score, 3),
                 "weight": d.weight, "detail": d.detail}
                for d in self.dimensions
            ],
            "to_reach_90": self.to_reach_90,
        }


def compute_readiness(learner: Learner, catalog: DataCatalog) -> CareerReadiness | None:
    role = catalog.role(learner.target_role)
    if role is None:
        return None

    # 1. Technical skills: importance-weighted proficiency on required skills
    tech = 0.0
    weight_sum = 0.0
    low_skills: list[str] = []
    for sid, target in role.skills.items():
        w = role.importance.get(sid, 0.5)
        prof = learner.proficiency(sid)
        ratio = min(1.0, prof / max(0.01, target))
        tech += w * ratio
        weight_sum += w
        if prof < target * 0.6:
            skill = catalog.skill(sid)
            low_skills.append(skill.name if skill else sid)
    tech = tech / weight_sum if weight_sum else 0.0

    # 2. Projects: fraction of recommended/milestone projects completed
    recommended_projects = [p for p in catalog.projects.values() if role.role_id in p.career_roles]
    done_projects = [p for p in recommended_projects if p.project_id in learner.completed_projects]
    projects = len(done_projects) / len(recommended_projects) if recommended_projects else 0.0

    # 3. Problem solving: average assessment performance
    scores = list(learner.assessment_scores.values())
    problem_solving = float(np.mean(scores)) if scores else 0.25

    # 4. Deployment skills
    depl_skills = [s for s in role.required_skills if s in DEPLOYMENT_SKILLS]
    deployment = (
        np.mean([learner.proficiency(s) for s in depl_skills]) if depl_skills else 0.0
    )

    # 5. Portfolio: projects + communication skills + git
    portfolio_parts = [projects]
    for sid in ("data_storytelling", "git", "data_viz"):
        if sid in role.required_skills:
            portfolio_parts.append(learner.proficiency(sid))
    portfolio = float(np.mean(portfolio_parts)) if portfolio_parts else projects

    dims = [
        ReadinessDimension("technical", "Technical Skills", tech, 0.35,
                           f"{sum(1 for s in role.required_skills if learner.proficiency(s) >= 0.7)}/{len(role.required_skills)} skills at target"),
        ReadinessDimension("projects", "Projects", projects, 0.20,
                           f"{len(done_projects)}/{len(recommended_projects)} recommended projects done"),
        ReadinessDimension("problem_solving", "Problem Solving", problem_solving, 0.15,
                           f"avg assessment score {np.mean(scores):.0%}" if scores else "no assessments yet"),
        ReadinessDimension("deployment", "Deployment", float(deployment), 0.15,
                           f"{len(depl_skills)} deployment skills in scope"),
        ReadinessDimension("portfolio", "Portfolio & Communication", portfolio, 0.15,
                           "projects + storytelling + git"),
    ]
    overall = sum(d.score * d.weight for d in dims)

    # 3. guidance to reach 90%
    to_90: list[str] = []
    for d in dims:
        if d.score < 0.9:
            gap_pct = int((0.9 - d.score) * 100)
            to_90.append(f"{d.label}: +{gap_pct} pts ({d.detail})")
    if low_skills:
        to_90.append("Prioritize: " + ", ".join(low_skills[:5]))

    return CareerReadiness(
        role_id=learner.target_role,
        overall=float(overall),
        dimensions=dims,
        to_reach_90=to_90[:6],
    )
