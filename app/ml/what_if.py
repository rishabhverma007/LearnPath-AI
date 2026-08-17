"""What-If goal simulator.

Answers: "what changes if I switch my target role?" by diffing the two
roles' competency maps against the learner's current proficiencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.data.loader import DataCatalog
from app.database.models import Learner
from app.graph.skill_graph import SkillGraph
from app.ml.path_optimizer import estimate_additional_hours


@dataclass
class WhatIfResult:
    current_role: str
    target_role: str
    retained_skills: list[str] = field(default_factory=list)
    additional_skills: list[str] = field(default_factory=list)
    extra_hours: float = 0.0
    extra_weeks: float = 0.0
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "current_role": self.current_role,
            "target_role": self.target_role,
            "retained_skills": self.retained_skills,
            "additional_skills": self.additional_skills,
            "extra_hours": self.extra_hours,
            "extra_weeks": self.extra_weeks,
            "summary": self.summary,
        }


def simulate_role_switch(
    learner: Learner, new_role_id: str, catalog: DataCatalog, graph: SkillGraph
) -> WhatIfResult | None:
    new_role = catalog.role(new_role_id)
    if new_role is None:
        return None
    current_role = catalog.role(learner.target_role)

    retained: list[str] = []
    additional: list[str] = []
    for sid, target in new_role.skills.items():
        skill = catalog.skill(sid)
        name = skill.name if skill else sid
        current = learner.proficiency(sid)
        if current >= target * 0.7:
            retained.append(name)
        elif current >= 0.3:
            retained.append(f"{name} (partial)")
            additional.append(name)
        else:
            additional.append(name)

    extra_hours, extra_weeks = estimate_additional_hours(
        catalog, [s for s in new_role.skills if learner.proficiency(s) < new_role.skills[s] * 0.7],
        learner.weekly_hours,
    )

    summary = (
        f"Switching from {current_role.title if current_role else 'your current goal'} to "
        f"{new_role.title}: you already have {len(retained)} transferable skill area(s). "
        f"Plan for roughly {extra_hours:g} extra hours (≈{extra_weeks:.0f} weeks at "
        f"{learner.weekly_hours:g} hrs/week) to close the {len(additional)} new requirement(s)."
    )
    return WhatIfResult(
        current_role=learner.target_role,
        target_role=new_role_id,
        retained_skills=retained[:12],
        additional_skills=additional[:12],
        extra_hours=extra_hours,
        extra_weeks=extra_weeks,
        summary=summary,
    )
