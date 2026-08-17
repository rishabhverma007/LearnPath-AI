"""Skill knowledge graph built on NetworkX.

Responsibilities:
- Build a directed graph: edge A -> B means "A is a prerequisite of B".
- Validate prerequisites (no cycles, no dangling references).
- Compute topological ordering of any skill subset (valid learning order).
- Compute the prerequisite closure needed to reach a set of target skills.
- Classify skill-gap severity using proficiency vs required targets.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from app.data.loader import DataCatalog
from app.utils import get_logger

log = get_logger("skill_graph")

# Gap severity buckets
GAP_CRITICAL = "critical"     # proficiency 0 or far below target
GAP_HIGH = "high"             # well below target
GAP_MEDIUM = "medium"         # below target
GAP_LOW = "low"               # near target
GAP_NONE = "none"             # at/above target


@dataclass(frozen=True)
class GapAnalysis:
    skill_id: str
    name: str
    category: str
    current: float
    required: float
    gap: float                # required - current, clamped >= 0
    severity: str
    is_required: bool = True
    action: str = ""


@dataclass
class SkillGraph:
    """Wraps a NetworkX DiGraph of prerequisite edges."""

    catalog: DataCatalog
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)

    def __post_init__(self) -> None:
        self._build()

    # ------------------------------------------------------------------
    # Construction / validation
    # ------------------------------------------------------------------
    def _build(self) -> None:
        g = nx.DiGraph()
        for skill in self.catalog.skills.values():
            g.add_node(skill.skill_id, name=skill.name, category=skill.category,
                       difficulty=skill.difficulty)
        for skill in self.catalog.skills.values():
            for prereq in skill.prerequisites:
                if prereq in self.catalog.skills:
                    g.add_edge(prereq, skill.skill_id)
                else:
                    log.warning("skill %s references unknown prerequisite %s", skill.skill_id, prereq)
        self.graph = g
        if not nx.is_directed_acyclic_graph(g):
            cycles = list(nx.simple_cycles(g))
            log.error("skill graph contains cycles: %s", cycles[:3])
            raise ValueError(f"Skill graph must be a DAG; found cycles {cycles[:3]}")

    def validate(self) -> list[str]:
        """Return a list of human-readable validation warnings (empty if valid)."""
        warnings: list[str] = []
        dangling = [s for s in self.graph.nodes if s not in self.catalog.skills]
        if dangling:
            warnings.append(f"dangling skill ids in graph: {dangling}")
        for s in self.catalog.skills.values():
            for p in s.prerequisites:
                if p not in self.catalog.skills:
                    warnings.append(f"{s.skill_id} -> missing prereq {p}")
        return warnings

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------
    def prereqs_of(self, skill_id: str) -> set[str]:
        return set(self.graph.predecessors(skill_id)) if skill_id in self.graph else set()

    def dependents_of(self, skill_id: str) -> set[str]:
        return set(self.graph.successors(skill_id)) if skill_id in self.graph else set()

    def prerequisite_closure(self, targets: list[str]) -> set[str]:
        """All skills that must be learned before `targets` can be reached."""
        needed: set[str] = set()
        frontier = list(targets)
        seen: set[str] = set()
        while frontier:
            node = frontier.pop()
            if node in seen:
                continue
            seen.add(node)
            if node in self.graph:
                for p in self.graph.predecessors(node):
                    if p not in seen:
                        frontier.append(p)
                    needed.add(p)
        return needed

    def topological_order(self, nodes: list[str]) -> list[str]:
        """A valid learning order for `nodes` (prerequisites before dependents).

        Falls back to difficulty/category ordering if the subgraph is cyclic
        (it should never be, since the full graph is a DAG).
        """
        present = [n for n in nodes if n in self.graph]
        sub = self.graph.subgraph(present)
        try:
            ordered = list(nx.topological_sort(sub))
        except nx.NetworkXUnfeasible:  # pragma: no cover - defensive
            ordered = sorted(
                present,
                key=lambda n: (self.catalog.skill(n).difficulty if self.catalog.skill(n) else 9, n),
            )
        return ordered

    def longest_path_from(self, skill_id: str) -> int:
        """How many edges deep the dependency chain goes below this skill."""
        if skill_id not in self.graph:
            return 0
        depth = {n: 0 for n in self.graph.nodes}
        for n in nx.topological_sort(self.graph):
            for succ in self.graph.successors(n):
                depth[succ] = max(depth[succ], depth[n] + 1)
        return depth.get(skill_id, 0)

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------
    def analyze_gaps(
        self,
        proficiencies: dict[str, float],
        role_targets: dict[str, float] | None = None,
    ) -> list[GapAnalysis]:
        """Compare current proficiencies against required targets.

        If role_targets is None, all skills in the catalogue are considered
        with a generic target of 0.6.
        """
        results: list[GapAnalysis] = []
        targets = role_targets or {s: 0.6 for s in self.catalog.skills}
        for skill_id, required in targets.items():
            skill = self.catalog.skill(skill_id)
            if skill is None:
                continue
            current = max(0.0, min(1.0, proficiencies.get(skill_id, 0.0)))
            gap = max(0.0, required - current)
            severity = self.classify_gap(current, required)
            results.append(
                GapAnalysis(
                    skill_id=skill_id,
                    name=skill.name,
                    category=skill.category,
                    current=round(current, 2),
                    required=round(required, 2),
                    gap=round(gap, 2),
                    severity=severity,
                    action=self._action_for(severity, skill_id),
                )
            )
        results.sort(key=lambda r: (-r.gap, r.skill_id))
        return results

    @staticmethod
    def classify_gap(current: float, required: float) -> str:
        gap = required - current
        if gap <= 0.05:
            return GAP_NONE
        if current <= 0.05 or gap >= 0.6:
            return GAP_CRITICAL
        if gap >= 0.35:
            return GAP_HIGH
        if gap >= 0.15:
            return GAP_MEDIUM
        return GAP_LOW

    def _action_for(self, severity: str, skill_id: str) -> str:
        skill = self.catalog.skill(skill_id)
        name = skill.name if skill else skill_id
        if severity == GAP_CRITICAL:
            return f"Learn {name} from the fundamentals — it is essential and currently missing."
        if severity == GAP_HIGH:
            return f"Prioritize a structured course or project for {name}."
        if severity == GAP_MEDIUM:
            return f"Strengthen {name} with focused practice and a project."
        if severity == GAP_LOW:
            return f"Polish {name} with targeted practice to reach the target."
        return f"{name} is at/above target — maintain it."

    def gap_summary(self, gaps: list[GapAnalysis]) -> dict[str, list[GapAnalysis]]:
        by_severity: dict[str, list[GapAnalysis]] = {k: [] for k in
                                                     (GAP_CRITICAL, GAP_HIGH, GAP_MEDIUM, GAP_LOW, GAP_NONE)}
        for g in gaps:
            by_severity[g.severity].append(g)
        return by_severity
