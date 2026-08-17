"""Today's Learning Mission + Smart Time Planner.

Turns the roadmap into a concrete daily action plan sized to the
learner's weekly hours, weakest skills, and upcoming milestone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app import config
from app.data.loader import DataCatalog
from app.database.models import Learner
from app.ml.path_optimizer import Roadmap, RoadmapItem
from app.utils import clamp

DAY_WEIGHTS = {
    "Monday": 1.0,
    "Tuesday": 0.8,
    "Wednesday": 1.2,
    "Thursday": 0.8,
    "Friday": 1.4,
    "Saturday": 2.4,
    "Sunday": 1.8,
}


@dataclass
class MissionStep:
    title: str
    minutes: int
    item_type: str = "activity"
    item_id: str = ""
    url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"title": self.title, "minutes": self.minutes,
                "item_type": self.item_type, "item_id": self.item_id, "url": self.url}


@dataclass
class DailyMission:
    date_label: str
    total_minutes: int
    steps: list[MissionStep] = field(default_factory=list)
    focus: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "date_label": self.date_label,
            "total_minutes": self.total_minutes,
            "steps": [s.as_dict() for s in self.steps],
            "focus": self.focus,
        }


def _daily_budget_minutes(learner: Learner) -> int:
    """Daily learning minutes derived from weekly hours (capped at 120)."""
    daily = learner.weekly_hours * 60 / 7.0
    return int(clamp(daily, 30, 120))


def build_daily_mission(
    learner: Learner, roadmap: Roadmap, catalog: DataCatalog
) -> DailyMission:
    budget = _daily_budget_minutes(learner)
    steps: list[MissionStep] = []
    focus = ""

    next_item = roadmap.next_action()
    weak = _weakest_required(learner, roadmap, catalog)

    # 1. Micro-lesson / weak-skill refocus
    if weak:
        sid, gap = weak
        skill = catalog.skill(sid)
        focus = skill.name if skill else sid
        steps.append(MissionStep(
            f"Refocus: key concepts in {focus}", max(15, int(budget * 0.25)),
            "micro_lesson", item_id=f"mission_{sid}_lesson",
        ))
        res = catalog.resources_for_skill(sid)
        if res and budget - _sum(steps) >= 15:
            r = res[0]
            steps.append(MissionStep(
                f"Read: {r.title}", min(r.duration_min, budget - _sum(steps)),
                "resource", item_id=r.resource_id, url=r.url,
            ))

    # 2. Next roadmap item
    if next_item and budget - _sum(steps) >= 20:
        mins = min(int(next_item.duration_hours * 60), budget - _sum(steps))
        if mins >= 15:
            steps.append(MissionStep(
                f"Learn: {next_item.title}", mins,
                next_item.item_type, item_id=next_item.item_id, url=next_item.url,
            ))

    # 3. Practice questions / project work
    if budget - _sum(steps) >= 20:
        practice = roadmap.item("practice_mission")
        if practice is None:
            steps.append(MissionStep(
                "Practice: solve 5 short questions on today's topic", 20,
                "practice", item_id="practice_mission",
            ))
        else:
            steps.append(MissionStep(
                f"Build: {practice.title}", min(30, budget - _sum(steps)),
                "project", item_id=practice.item_id,
            ))

    # 4. Self-assessment wrap-up
    if budget - _sum(steps) >= 10:
        steps.append(MissionStep(
            "Self-check: recap what you learned + rate your confidence", 10,
            "self_check",
        ))

    return DailyMission(
        date_label="Today",
        total_minutes=sum(s.minutes for s in steps),
        steps=steps,
        focus=focus,
    )


def _weakest_required(learner: Learner, roadmap: Roadmap, catalog: DataCatalog):
    """Weakest skill among the roadmap's focus skills."""
    focus = roadmap.focus_skills or list(learner.known_skills.keys())
    worst, worst_gap = None, -1.0
    for sid in focus:
        target = 0.7
        gap = target - learner.proficiency(sid)
        if gap > worst_gap and gap > 0.15:
            worst, worst_gap = sid, gap
    return (worst, worst_gap) if worst else None


def _sum(steps: list[MissionStep]) -> int:
    return sum(s.minutes for s in steps)


def weekly_schedule(learner: Learner, roadmap: Roadmap) -> list[dict[str, Any]]:
    """Distribute weekly hours across days based on weights.

    If the learner missed sessions (fewer recent activity entries than
    planned), the remaining hours are redistributed.
    """
    weekly = learner.weekly_hours
    total_weight = sum(DAY_WEIGHTS.values())
    schedule = []
    for day, w in DAY_WEIGHTS.items():
        minutes = int(weekly * 60 * w / total_weight)
        schedule.append({"day": day, "minutes": minutes, "focus": ""})
    # simple missed-session redistribution: assume one missed session per week
    missed = len([a for a in learner.recent_activity if a.get("event") == "session_missed"])
    if missed and weekly > 0:
        lost = int(weekly * 60 / 7.0) * min(missed, 3)
        # redistribute to the weekend slots
        for entry in reversed(schedule):
            if lost <= 0:
                break
            if entry["day"] in ("Saturday", "Sunday"):
                add = min(lost, 90)
                entry["minutes"] += add
                lost -= add
    # attach focus from roadmap
    next_item = roadmap.next_action()
    if next_item:
        for entry in schedule:
            entry["focus"] = next_item.title
    return schedule
