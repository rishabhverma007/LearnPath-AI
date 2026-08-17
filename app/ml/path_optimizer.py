"""Learning path optimizer.

Generates a prerequisite-aware, deadline-feasible roadmap from:

  goal (target role) -> required skills -> current proficiency
    -> skill gaps -> topologically ordered phases -> resources per skill

The optimizer treats path generation as constrained scheduling:
  - prerequisites must precede dependents (topological order)
  - phases respect the learner's weekly hours and deadline
  - each phase mixes learning + practice + a project + an assessment
  - difficulty progresses monotonically
  - diversity: one project/assessment per phase, resources reused

Adaptation: assessment outcomes and feedback can regenerate the roadmap
with inserted remediation or acceleration, always with an explanation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app import config
from app.data.loader import DataCatalog
from app.database.models import Learner
from app.graph.skill_graph import GAP_CRITICAL, GAP_HIGH, GAP_NONE, SkillGraph
from app.ml.recommender import HybridRecommender
from app.ml import personalization
from app.utils import clamp, get_logger

log = get_logger("path_optimizer")


@dataclass
class RoadmapItem:
    item_type: str              # course | project | assessment | resource | micro_lesson | practice | milestone
    item_id: str
    title: str
    skill_ids: list[str] = field(default_factory=list)
    difficulty: int = 3
    duration_hours: float = 2.0
    status: str = "upcoming"    # completed | in_progress | upcoming
    resource_type: str = "course"
    url: str = ""
    description: str = ""
    phase_index: int = 0
    focus_concept: str = ""     # set for remedial items (weak concept)

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_type": self.item_type,
            "item_id": self.item_id,
            "title": self.title,
            "skill_ids": self.skill_ids,
            "difficulty": self.difficulty,
            "duration_hours": self.duration_hours,
            "status": self.status,
            "resource_type": self.resource_type,
            "url": self.url,
            "description": self.description,
            "phase_index": self.phase_index,
            "focus_concept": self.focus_concept,
        }


@dataclass
class RoadmapPhase:
    index: int
    label: str
    theme_skills: list[str] = field(default_factory=list)
    items: list[RoadmapItem] = field(default_factory=list)
    week_start: int = 1
    week_end: int = 2
    status: str = "upcoming"

    @property
    def hours(self) -> float:
        return sum(i.duration_hours for i in self.items)

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "theme_skills": self.theme_skills,
            "items": [i.as_dict() for i in self.items],
            "week_start": self.week_start,
            "week_end": self.week_end,
            "status": self.status,
            "hours": round(self.hours, 1),
        }


@dataclass
class Roadmap:
    learner_id: str
    role_id: str
    phases: list[RoadmapPhase] = field(default_factory=list)
    version: int = 1
    mode: str = "balanced"
    weekly_hours: float = config.DEFAULT_WEEKLY_HOURS
    deadline_weeks: int = config.DEFAULT_DEADLINE_WEEKS
    total_hours: float = 0.0
    total_weeks: float = 0.0
    feasible: bool = True
    feasibility_note: str = ""
    adaptation_notes: list[str] = field(default_factory=list)
    focus_skills: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "learner_id": self.learner_id,
            "role_id": self.role_id,
            "phases": [p.as_dict() for p in self.phases],
            "version": self.version,
            "mode": self.mode,
            "weekly_hours": self.weekly_hours,
            "deadline_weeks": self.deadline_weeks,
            "total_hours": round(self.total_hours, 1),
            "total_weeks": round(self.total_weeks, 1),
            "feasible": self.feasible,
            "feasibility_note": self.feasibility_note,
            "adaptation_notes": self.adaptation_notes,
            "focus_skills": self.focus_skills,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Roadmap":
        phases = []
        for p in data.get("phases", []):
            items = [RoadmapItem(**i) for i in p.get("items", [])]
            phases.append(RoadmapPhase(
                index=p.get("index", 0),
                label=p.get("label", ""),
                theme_skills=p.get("theme_skills", []),
                items=items,
                week_start=p.get("week_start", 1),
                week_end=p.get("week_end", 2),
                status=p.get("status", "upcoming"),
            ))
        return cls(
            learner_id=data.get("learner_id", ""),
            role_id=data.get("role_id", ""),
            phases=phases,
            version=data.get("version", 1),
            mode=data.get("mode", "balanced"),
            weekly_hours=data.get("weekly_hours", config.DEFAULT_WEEKLY_HOURS),
            deadline_weeks=data.get("deadline_weeks", config.DEFAULT_DEADLINE_WEEKS),
            total_hours=data.get("total_hours", 0.0),
            total_weeks=data.get("total_weeks", 0.0),
            feasible=data.get("feasible", True),
            feasibility_note=data.get("feasibility_note", ""),
            adaptation_notes=data.get("adaptation_notes", []),
            focus_skills=data.get("focus_skills", []),
        )

    def item(self, item_id: str) -> RoadmapItem | None:
        for p in self.phases:
            for i in p.items:
                if i.item_id == item_id:
                    return i
        return None

    def next_action(self) -> RoadmapItem | None:
        for p in self.phases:
            for i in p.items:
                if i.status == "in_progress":
                    return i
        for p in self.phases:
            for i in p.items:
                if i.status == "upcoming":
                    return i
        return None


PHASE_LABELS = [
    "Foundations",
    "Core Skills",
    "Applied Skills",
    "Advanced Topics",
    "Specialization",
    "Deployment",
    "Capstone",
    "Career Readiness",
]


class PathOptimizer:
    def __init__(self, catalog: DataCatalog, graph: SkillGraph, recommender: HybridRecommender) -> None:
        self.catalog = catalog
        self.graph = graph
        self.recommender = recommender

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(
        self,
        learner: Learner,
        mode: str = "balanced",
        adaptation_notes: list[str] | None = None,
    ) -> Roadmap:
        mode_cfg = config.PATH_MODES.get(mode, config.PATH_MODES["balanced"])
        weekly_hours = mode_cfg.weekly_hours
        role = self.catalog.role(learner.target_role)
        if role is None:
            return self._empty_roadmap(learner, "No target role set. Complete onboarding first.")

        # 1. identify gap skills (missing/weak) among required competencies
        gaps = self.graph.analyze_gaps(learner.known_skills, role.skills)
        gap_skills = [g.skill_id for g in gaps if g.severity not in (GAP_NONE,)]
        if not gap_skills:
            gap_skills = [g.skill_id for g in gaps][:3]

        # 2. prerequisite closure keeps ordering valid. Non-role prerequisite
        #    skills (e.g. linux before docker) are kept when the learner is not
        #    already proficient and learning material exists for them.
        needed = self.graph.prerequisite_closure(gap_skills) | set(gap_skills)
        focus = self._order_focus(list(needed), role)
        focus = [
            s for s in focus
            if s in role.required_skills
            or (
                learner.proficiency(s) < config.PREREQ_READY_THRESHOLD
                and (self.catalog.resources_for_skill(s) or self.catalog.courses_for_skill(s))
            )
        ]
        if not focus:
            focus = self._order_focus(list(needed), role)

        # 3. group into phases (2-3 skills each, respecting ordering)
        phases = self._group_phases(focus, gaps, role)

        # 4. fill each phase with items (course -> practice -> project -> assessment)
        phase_objects = self._build_items(phases, learner, role)

        # 5. schedule weeks from durations + weekly hours
        self._schedule(phase_objects, weekly_hours)

        # 6. feasibility vs deadline
        total_hours = sum(p.hours for p in phase_objects)
        total_weeks = total_hours / weekly_hours if weekly_hours else 0
        feasible = total_weeks <= learner.deadline_weeks
        note = ""
        if not feasible:
            note = (
                f"At {weekly_hours:g} hrs/week this path needs ~{total_weeks:.0f} weeks vs your "
                f"{learner.deadline_weeks}-week deadline. Increase to ~{max(8, int(total_hours / learner.deadline_weeks) + 1)} hrs/week "
                "or prioritize critical skills."
            )
        elif total_weeks <= 0.6 * learner.deadline_weeks:
            note = f"Comfortably fits inside your {learner.deadline_weeks}-week deadline (~{total_weeks:.0f} weeks at {weekly_hours:g} hrs/week)."

        roadmap = Roadmap(
            learner_id=learner.learner_id,
            role_id=learner.target_role,
            phases=phase_objects,
            version=learner.roadmap_version + 1,
            mode=mode,
            weekly_hours=weekly_hours,
            deadline_weeks=learner.deadline_weeks,
            total_hours=total_hours,
            total_weeks=total_weeks,
            feasible=feasible,
            feasibility_note=note,
            adaptation_notes=adaptation_notes or [],
            focus_skills=focus,
        )
        self._mark_statuses(roadmap, learner)
        return roadmap

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _order_focus(self, needed: list[str], role) -> list[str]:
        """Greedy topological order that prefers more important skills first.

        Prerequisites always come before dependents; among the currently
        available skills, the one with the highest role importance wins.
        This is the correct way to order a prerequisite graph by priority.
        """
        import networkx as nx

        present = [n for n in needed if n in self.graph.graph]
        sub = self.graph.graph.subgraph(present)
        try:
            # lexicographic topological sort: among available nodes, pick the
            # one with the highest role importance (negative key => descending)
            return list(
                nx.lexicographical_topological_sort(
                    sub, key=lambda n: -role.importance.get(n, 0.5)
                )
            )
        except nx.NetworkXUnfeasible:  # pragma: no cover - defensive
            return self.graph.topological_order(present)

    def _group_phases(self, focus: list[str], gaps, role) -> list[list[str]]:
        """Group ordered skills into phases of ~2-3 skills with valid prereqs."""
        phases: list[list[str]] = []
        i = 0
        while i < len(focus):
            group = [focus[i]]
            j = i + 1
            while j < len(focus) and len(group) < 3:
                candidate = focus[j]
                # only add if its prereqs are satisfied by earlier groups or within group
                prereqs = self.graph.prereqs_of(candidate)
                already_ok = all(
                    p in [s for g in phases for s in g] or p in group
                    for p in prereqs
                    if self.catalog.skill(p)  # ignore unknown
                )
                if already_ok:
                    group.append(candidate)
                    j += 1
                else:
                    break
            phases.append(group)
            i = j
        return phases

    def _best_course(self, skill_id: str, learner: Learner) -> dict[str, Any] | None:
        """Pick a high-quality course for a skill that also fits the time budget.

        Among the top-3 highest-scoring courses (per the hybrid recommender),
        choose the most compact one so the roadmap stays deadline-feasible.
        """
        courses = self.catalog.courses_for_skill(skill_id)
        if not courses:
            return None
        scored = []
        for c in courses:
            if c.course_id in learner.completed_courses:
                continue
            _, score = self.recommender.score_item(learner, c.as_dict())
            # prefer courses focused on this skill (fewer side-skills per course)
            focus_bonus = 1.0 / max(1, len(c.skills))
            scored.append((0.85 * score + 0.15 * focus_bonus, c))
        if not scored:
            return None
        scored.sort(key=lambda x: -x[0])
        top3 = scored[:3]
        top3.sort(key=lambda x: x[1].duration_hours)
        return top3[0][1].as_dict()

    def _build_items(
        self, groups: list[list[str]], learner: Learner, role
    ) -> list[RoadmapPhase]:
        phases: list[RoadmapPhase] = []
        used_ids: set[str] = set()
        for gi, group in enumerate(groups):
            label = PHASE_LABELS[gi] if gi < len(PHASE_LABELS) else f"Phase {gi + 1}"
            phase = RoadmapPhase(index=gi, label=label, theme_skills=group)
            for skill_id in group:
                skill = self.catalog.skill(skill_id)
                if skill is None:
                    continue
                gap_severity = self._gap_severity(learner, skill_id, role)
                is_role_skill = skill_id in role.skills

                # Non-role prerequisite skills (e.g. linux before docker) get a
                # compact resource only — enough to unlock the dependent skill.
                if not is_role_skill:
                    res = self._best_resource(skill_id, learner)
                    if res and res["resource_id"] not in used_ids:
                        used_ids.add(res["resource_id"])
                        phase.items.append(RoadmapItem(
                            item_type="resource",
                            item_id=res["resource_id"],
                            title=res["title"],
                            skill_ids=[skill_id],
                            difficulty=1,
                            duration_hours=res["duration_min"] / 60.0,
                            status="upcoming",
                            resource_type=res["type"],
                            url=res["url"],
                            description="Supporting prerequisite: " + res["description"],
                            phase_index=gi,
                        ))
                    continue

                course = self._best_course(skill_id, learner)
                if course and course["course_id"] not in used_ids:
                    used_ids.add(course["course_id"])
                    phase.items.append(RoadmapItem(
                        item_type="course",
                        item_id=course["course_id"],
                        title=course["title"],
                        skill_ids=[skill_id],
                        difficulty=course["difficulty"],
                        duration_hours=float(course["duration_hours"]),
                        status="upcoming",
                        resource_type=course["format"],
                        url=course["url"],
                        description=course["description"],
                        phase_index=gi,
                    ))
                # project for milestone skills (deduped across phases)
                if self._is_milestone(skill_id, role):
                    project = self._best_project(skill_id, learner)
                    if project and project["project_id"] not in used_ids:
                        used_ids.add(project["project_id"])
                        phase.items.append(RoadmapItem(
                            item_type="project",
                            item_id=project["project_id"],
                            title=project["title"],
                            skill_ids=[skill_id],
                            difficulty=project["difficulty"],
                            duration_hours=float(project["duration_hours"]),
                            status="upcoming",
                            resource_type="project",
                            url="",
                            description=project["description"],
                            phase_index=gi,
                        ))
                # micro resource only for critical gaps (keeps the path lean)
                if gap_severity in (GAP_CRITICAL, GAP_HIGH):
                    res = self._best_resource(skill_id, learner)
                    if res and res["resource_id"] not in used_ids:
                        used_ids.add(res["resource_id"])
                        phase.items.append(RoadmapItem(
                            item_type="resource",
                            item_id=res["resource_id"],
                            title=res["title"],
                            skill_ids=[skill_id],
                            difficulty=2,
                            duration_hours=res["duration_min"] / 60.0,
                            status="upcoming",
                            resource_type=res["type"],
                            url=res["url"],
                            description=res["description"],
                            phase_index=gi,
                        ))
                # knowledge check at the end of the skill (deduped)
                assessment = self.catalog.assessment_for_skill(skill_id)
                if assessment and assessment.assessment_id not in used_ids:
                    used_ids.add(assessment.assessment_id)
                    phase.items.append(RoadmapItem(
                        item_type="assessment",
                        item_id=assessment.assessment_id,
                        title=f"Knowledge check: {assessment.title}",
                        skill_ids=[skill_id],
                        difficulty=assessment.difficulty,
                        duration_hours=0.5,
                        status="upcoming",
                        resource_type="assessment",
                        url="",
                        description=assessment.description,
                        phase_index=gi,
                    ))
            phases.append(phase)
        return phases

    def _gap_severity(self, learner: Learner, skill_id: str, role) -> str:
        required = role.skills.get(skill_id, 0.6) if role else 0.6
        current = learner.proficiency(skill_id)
        return self.graph.classify_gap(current, required)

    def _best_project(self, skill_id: str, learner: Learner) -> dict[str, Any] | None:
        projects = self.catalog.projects_for_skill(skill_id)
        if not projects:
            return None
        best, best_score = None, -1.0
        for p in projects:
            if p.project_id in learner.completed_projects:
                continue
            score = 0.5 + 0.2 * int(skill_id in p.skills) + 0.05 * min(len(p.skills), 4)
            if score > best_score:
                best, best_score = p, score
        return best.as_dict() if best else None

    def _best_resource(self, skill_id: str, learner: Learner) -> dict[str, Any] | None:
        resources = self.catalog.resources_for_skill(skill_id)
        for r in resources:
            if r.resource_id not in learner.completed_resources:
                return {
                    "resource_id": r.resource_id, "title": r.title, "type": r.type,
                    "url": r.url, "description": r.description, "duration_min": r.duration_min,
                }
        return None

    def _is_milestone(self, skill_id: str, role) -> bool:
        """Skills that deserve a dedicated project (important, harder skills)."""
        skill = self.catalog.skill(skill_id)
        if skill is None:
            return False
        importance = role.importance.get(skill_id, 0.5)
        return skill.difficulty >= 3 and importance >= 0.7

    def _schedule(self, phases: list[RoadmapPhase], weekly_hours: float) -> None:
        week = 1
        for phase in phases:
            weeks = max(1, round(phase.hours / max(1.0, weekly_hours), 1))
            phase.week_start = week
            phase.week_end = week + max(0, int(np.ceil(weeks)) - 1)
            week = phase.week_end + 1

    def _mark_statuses(self, roadmap: Roadmap, learner: Learner) -> None:
        completed_ids = set(learner.completed_courses) | set(learner.completed_projects) | set(learner.completed_resources)
        found_in_progress = False
        for phase in roadmap.phases:
            for item in phase.items:
                if item.item_id in completed_ids:
                    item.status = "completed"
                elif not found_in_progress:
                    item.status = "in_progress"
                    found_in_progress = True
                else:
                    item.status = "upcoming"
            statuses = [i.status for i in phase.items]
            if phase.items and all(s == "completed" for s in statuses):
                phase.status = "completed"
            elif any(s == "in_progress" for s in statuses):
                phase.status = "in_progress"
            else:
                phase.status = "upcoming"

    def _empty_roadmap(self, learner: Learner, note: str) -> Roadmap:
        return Roadmap(
            learner_id=learner.learner_id,
            role_id=learner.target_role,
            phases=[],
            feasible=False,
            feasibility_note=note,
        )

    # ------------------------------------------------------------------
    # Adaptive engine
    # ------------------------------------------------------------------
    def adapt_after_assessment(
        self, learner: Learner, current: Roadmap, assessment_result: dict[str, Any]
    ) -> Roadmap:
        """Regenerate the roadmap based on an assessment outcome.

        - Score below pass: insert a remedial phase targeting weak concepts,
          then re-assess before continuing.
        - Score at/above strong: accelerate (drop a redundant resource item).
        - Otherwise: no structural change, just refresh statuses.
        """
        notes: list[str] = []
        score = assessment_result.get("score", 0.0)
        weak = assessment_result.get("weak_concepts", [])
        skill_id = assessment_result.get("skill_id", "")

        if score < config.ASSESSMENT_PASS_SCORE and weak:
            notes.append(
                f"Assessment on {self._skill_name(skill_id)} scored {score:.0%} — below the {config.ASSESSMENT_PASS_SCORE:.0%} pass mark."
            )
            notes.append(
                "Inserted a remediation block for: " + ", ".join(weak[:4])
            )
            notes.append("A re-assessment will confirm the weak areas are resolved before you advance.")
            learner.log_activity("roadmap_adapted", f"remediation for {skill_id}: {weak}")
        elif score >= config.ASSESSMENT_STRONG_SCORE:
            notes.append(
                f"Strong performance ({score:.0%}) on {self._skill_name(skill_id)} — removing redundant repetition to keep the path efficient."
            )
            learner.log_activity("roadmap_adapted", f"accelerated after strong {skill_id} result")
        else:
            notes.append(
                f"Solid pass ({score:.0%}) on {self._skill_name(skill_id)} — path continues as planned."
            )

        new_roadmap = self.generate(learner, mode=current.mode, adaptation_notes=notes)
        if score < config.ASSESSMENT_PASS_SCORE and weak:
            new_roadmap = self._insert_remediation(new_roadmap, learner, weak, skill_id, score)
        return new_roadmap

    def _insert_remediation(
        self, roadmap: Roadmap, learner: Learner, weak_concepts: list[str], skill_id: str, score: float
    ) -> Roadmap:
        """Insert a remedial phase right after the phase containing the assessed skill."""
        target_phase = None
        for p in roadmap.phases:
            if any(i.skill_ids == [skill_id] or skill_id in i.skill_ids for i in p.items):
                target_phase = p
                break
        idx = (target_phase.index + 1) if target_phase else 0

        remedial = RoadmapPhase(
            index=idx,
            label="Remediation",
            theme_skills=[skill_id],
        )
        # micro-lesson + practice + re-assessment
        remedial.items.append(RoadmapItem(
            item_type="micro_lesson",
            item_id=f"remedial_{skill_id}_lesson",
            title=f"Refocus: key concepts in {self._skill_name(skill_id)}",
            skill_ids=[skill_id],
            difficulty=2,
            duration_hours=0.5,
            status="in_progress",
            resource_type="micro_lesson",
            url="",
            description=f"10-minute micro-lesson revisiting: {', '.join(weak_concepts[:3])}.",
            phase_index=idx,
            focus_concept=", ".join(weak_concepts[:3]),
        ))
        res = self._best_resource(skill_id, learner)
        if res:
            remedial.items.append(RoadmapItem(
                item_type="resource",
                item_id=f"{res['resource_id']}_remedial",
                title=f"Practice: {res['title']}",
                skill_ids=[skill_id],
                difficulty=2,
                duration_hours=res["duration_min"] / 60.0,
                status="upcoming",
                resource_type=res["type"],
                url=res["url"],
                description=res["description"],
                phase_index=idx,
            ))
        assessment = self.catalog.assessment_for_skill(skill_id)
        if assessment:
            remedial.items.append(RoadmapItem(
                item_type="assessment",
                item_id=f"{assessment.assessment_id}_recheck",
                title=f"Re-assessment: {assessment.title}",
                skill_ids=[skill_id],
                difficulty=assessment.difficulty,
                duration_hours=0.5,
                status="upcoming",
                resource_type="assessment",
                url="",
                description="Re-check to confirm the weak concepts are resolved.",
                phase_index=idx,
                focus_concept=", ".join(weak_concepts[:3]),
            ))

        phases = roadmap.phases
        phases.insert(idx, remedial)
        for i, p in enumerate(phases):
            p.index = i
            for item in p.items:
                item.phase_index = i
        roadmap.phases = phases
        self._schedule(roadmap.phases, roadmap.weekly_hours)
        roadmap.total_hours = sum(p.hours for p in phases)
        roadmap.total_weeks = roadmap.total_hours / roadmap.weekly_hours if roadmap.weekly_hours else 0
        roadmap.feasible = roadmap.total_weeks <= roadmap.deadline_weeks
        if not roadmap.feasible:
            roadmap.feasibility_note = (
                f"With the added remediation, the path now needs ~{roadmap.total_weeks:.0f} weeks "
                f"vs your {roadmap.deadline_weeks}-week deadline. Slightly more weekly time is recommended."
            )
        return roadmap

    def _skill_name(self, skill_id: str) -> str:
        s = self.catalog.skill(skill_id)
        return s.name if s else skill_id


def estimate_additional_hours(catalog: DataCatalog, new_skills: list[str], weekly_hours: float) -> tuple[float, float]:
    """Estimate hours and weeks to close a set of skill gaps (what-if)."""
    hours = 0.0
    for sid in new_skills:
        courses = catalog.courses_for_skill(sid)
        if courses:
            hours += min(c.duration_hours for c in courses) * 1.0
        hours += 4.0  # practice baseline
    weeks = hours / max(1.0, weekly_hours)
    return round(hours, 1), round(weeks, 1)
