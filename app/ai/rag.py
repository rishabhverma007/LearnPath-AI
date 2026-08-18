"""RAG knowledge base + context-aware AI coach.

The knowledge base is built from the catalogue (skills, courses,
projects, resources, assessments) plus the learner's roadmap. Retrieval
uses the semantic index. The coach:

  1. detects intent from the question (rules),
  2. retrieves relevant knowledge (vector retrieval),
  3. composes an answer — deterministically in local mode (never
     hallucinating), or via the configured LLM with retrieved context.

Honesty rule: if retrieval finds nothing relevant, the coach says so
instead of inventing content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app import config
from app.ai.embeddings import cached_semantic_index
from app.ai.llm import get_llm_provider
from app.ai.prompts import COACH_SYSTEM, COACH_USER
from app.data.loader import DataCatalog
from app.database.models import Learner
from app.ml.daily_mission import build_daily_mission
from app.ml.path_optimizer import Roadmap
from app.ml.personalization import learner_level_estimate
from app.utils import get_logger

log = get_logger("rag")


@dataclass
class CoachReply:
    text: str
    intent: str = "general"
    sources: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)   # UI actions (e.g., mark complete)

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "intent": self.intent, "sources": self.sources, "actions": self.actions}


class KnowledgeBase:
    def __init__(self, catalog: DataCatalog) -> None:
        self.catalog = catalog
        self.chunks: dict[str, str] = {}
        self._build()

    def _add(self, chunk_id: str, text: str) -> None:
        if text.strip():
            self.chunks[chunk_id] = text.strip()

    def _build(self) -> None:
        for s in self.catalog.skills.values():
            prereqs = [self._skill_name(p) for p in s.prerequisites if self.catalog.skill(p)]
            self._add(
                f"skill:{s.skill_id}",
                f"SKILL: {s.name} ({s.category}, difficulty {s.difficulty}/5). {s.description} "
                f"Prerequisites: {', '.join(prereqs) if prereqs else 'none'}.",
            )
        for c in self.catalog.courses.values():
            skills = ", ".join(self._skill_name(x) for x in c.skills)
            self._add(
                f"course:{c.course_id}",
                f"COURSE: {c.title} by {c.provider}. Skills covered: {skills}. "
                f"Estimated {c.duration_hours:g} hours, {c.format} format. URL: {c.url}",
            )
        for p in self.catalog.projects.values():
            skills = ", ".join(self._skill_name(x) for x in p.skills)
            self._add(
                f"project:{p.project_id}",
                f"PROJECT: {p.title}. Skills practiced: {skills}. Deliverables: {p.deliverables}. "
                f"Dataset suggestion: {p.dataset_hint}.",
            )
        for r in self.catalog.resources.values():
            self._add(
                f"resource:{r.resource_id}",
                f"RESOURCE ({r.type}): {r.title}. About {self._skill_name(r.skill_id)}. "
                f"{r.description} ~{r.duration_min} min. URL: {r.url}",
            )
        for a in self.catalog.assessments.values():
            concepts = ", ".join(a.concepts)
            self._add(
                f"assessment:{a.assessment_id}",
                f"ASSESSMENT: {a.title} for {self._skill_name(a.skill_id)}. "
                f"Topics covered: {concepts}. {a.description}",
            )

    def _skill_name(self, skill_id: str) -> str:
        s = self.catalog.skill(skill_id)
        return s.name if s else skill_id

    def get(self, chunk_id: str) -> str:
        return self.chunks.get(chunk_id, "")

    def index(self):
        return cached_semantic_index([(k, v) for k, v in self.chunks.items()])

    def retrieve(self, query: str, k: int = config.COACH_RETRIEVAL_K) -> list[dict[str, Any]]:
        results = self.index().query(query, k=k)
        out = []
        for chunk_id, score in results:
            out.append({"chunk_id": chunk_id, "score": score, "text": self.chunks.get(chunk_id, "")})
        return out


# ----------------------------------------------------------------------
# Intent detection (deterministic)
# ----------------------------------------------------------------------
def detect_intent(text: str) -> str:
    t = text.lower()
    # gamification intents
    if re.search(r"level up|reach level|next level|how (much|many) xp|to level", t):
        return "level"
    if re.search(r"leaderboard|ranking|rank (up|down|improve)|improve my rank|top of the|compete", t):
        return "rank"
    if re.search(r"(challenge|weekly challenge)s?\b|what challenges", t):
        return "challenge"
    if re.search(r"easiest way to (get|earn) xp|farm xp|fastest way to (get|earn) xp|quick xp", t):
        return "xp_farm"
    if re.search(r"how many badges|my badges|what badges|badge", t):
        return "badge"
    if re.search(r"what should i do today|today'?s mission|plan for today|what do i do today", t):
        return "mission"
    if re.search(r"what'?s next|what should i (learn|do) next|next step", t):
        return "next"
    if re.search(r"can i skip|skip (this|it|the)|do i (really )?need (to learn )?(\w+)", t):
        return "skip"
    if re.search(r"why (should i learn|do i need|is \w+ important)", t):
        return "why_skill"
    if re.search(r"which skill should i focus|what skill (should i )?focus|focus on today", t):
        return "focus"
    if re.search(r"struggl|having trouble|hard time|can'?t (understand|grasp)|confus", t):
        return "struggling"
    if re.search(r"i (just )?(completed|finished|done with)|finished (the|this)", t):
        return "completed"
    if re.search(r"explain|what is|what are|how does|tell me about|define", t):
        return "explain"
    return "general"


_SKILL_QUERY = re.compile(r"(?:why should i learn|do i need|explain|what is|about|struggling with|trouble with)\s+([a-zA-Z][a-zA-Z \-]{1,40})", re.IGNORECASE)


class CoachService:
    def __init__(self, catalog: DataCatalog, graph=None) -> None:
        self.catalog = catalog
        self.kb = KnowledgeBase(catalog)
        if graph is None:
            from app.graph.skill_graph import SkillGraph

            graph = SkillGraph(catalog)
        self._graph = graph

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def chat(self, learner: Learner, roadmap: Roadmap | None, message: str) -> CoachReply:
        intent = detect_intent(message)
        try:
            if intent == "level":
                return self._answer_level(learner, roadmap)
            if intent == "rank":
                return self._answer_rank(learner, roadmap)
            if intent == "challenge":
                return self._answer_challenge(learner, roadmap)
            if intent == "xp_farm":
                return self._answer_xp_farm(learner, roadmap)
            if intent == "badge":
                return self._answer_badge(learner)
            if intent == "mission":
                return self._answer_mission(learner, roadmap)
            if intent == "next":
                return self._answer_next(learner, roadmap)
            if intent == "skip":
                return self._answer_skip(learner, message)
            if intent == "why_skill":
                return self._answer_why_skill(learner, message)
            if intent == "focus":
                return self._answer_focus(learner, roadmap)
            if intent == "struggling":
                return self._answer_struggling(learner, message)
            if intent == "completed":
                return self._answer_completed(learner, roadmap, message)
            if intent == "explain":
                return self._answer_explain(learner, message)
            return self._answer_general(learner, roadmap, message)
        except Exception as exc:  # noqa: BLE001
            log.error("coach error: %s", exc)
            return CoachReply(
                text="I hit an unexpected issue while answering. Please rephrase — or try "
                     "\"What should I do today?\" or \"Explain cross-validation\".",
                intent=intent,
            )

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------
    def _learner_context_text(self, learner: Learner, roadmap: Roadmap | None) -> str:
        role = self.catalog.role(learner.target_role)
        lines = [
            f"Goal: {learner.goal_text}",
            f"Target role: {role.title if role else learner.target_role}",
            f"Experience: {learner.experience_level}; weekly availability: {learner.weekly_hours:g} hrs; deadline: {learner.deadline_weeks} weeks.",
            f"Learning preference: {', '.join(learner.learning_preferences) or 'hands-on'}.",
        ]
        top = sorted(learner.known_skills.items(), key=lambda kv: -kv[1])[:5]
        if top:
            lines.append("Current skills: " + ", ".join(f"{self._skill_name(s)} ({c:.0%})" for s, c in top))
        if roadmap and roadmap.phases:
            current = roadmap.next_action()
            if current:
                lines.append(f"Current milestone: {current.title} (phase {current.phase_index + 1}).")
            lines.append(f"Roadmap: {len(roadmap.phases)} phases, {roadmap.total_weeks:.0f} weeks, feasible={roadmap.feasible}.")
        if learner.assessment_scores:
            scores = ", ".join(f"{self._skill_name(s)} {sc:.0%}" for s, sc in list(learner.assessment_scores.items())[:4])
            lines.append(f"Latest assessment scores: {scores}.")
        g = self._gam_state(learner)
        if g:
            lines.append(f"LearnPath XP: Level {g.get('level', 1)} ({g.get('level_title', 'Explorer')}), {g.get('total_xp', 0):,} XP, "
                         f"rank #{g.get('leaderboard_position') or '?'} of {g.get('leaderboard_size', 0)}, "
                         f"{g.get('current_streak', 0)}-day streak, {g.get('badge_count', 0)} badges.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Gamification-aware intents (retrieve real state; never invent XP)
    # ------------------------------------------------------------------
    def _gam_state(self, learner: Learner) -> dict:
        try:
            from app.services.gamification_service import GamificationService

            return GamificationService().get_state(learner, include_meta=False)
        except Exception:  # noqa: BLE001
            return {}

    def _answer_level(self, learner: Learner, roadmap: Roadmap | None) -> CoachReply:
        g = self._gam_state(learner)
        if not g:
            return CoachReply("I couldn't load your gamification state right now.", intent="level")
        xp = g["total_xp"]
        need = g["xp_to_next_level"]
        lines = [f"You are **Level {g['level']} — {g['level_title']}** with **{xp:,} XP**."]
        if need:
            lines.append(f"You need **{need:,} more XP** to reach the next level.")
        # next roadmap milestone is the fastest meaningful source
        if roadmap and roadmap.next_action():
            item = roadmap.next_action()
            lines.append(f"Your next milestone is **{item.title}** — completing it is the fastest meaningful progress toward your goal.")
        weak = min(learner.known_skills.items(), key=lambda kv: kv[1], default=None)
        if weak:
            s = self.catalog.skill(weak[0])
            lines.append(f"Strengthening **{s.name if s else weak[0]}** (now {weak[1]:.0%}) would also raise your skill-mastery XP.")
        return CoachReply("\n".join(lines), intent="level")

    def _answer_rank(self, learner: Learner, roadmap: Roadmap | None) -> CoachReply:
        g = self._gam_state(learner)
        if not g:
            return CoachReply("I couldn't load your ranking right now.", intent="rank")
        pos = g.get("leaderboard_position")
        size = g.get("leaderboard_size", 0)
        lines = [f"You're **#{pos} of {size}** learners on the all-time leaderboard with **{g['total_xp']:,} XP**."]
        if size:
            pct = round(pos / size * 100) if pos else None
            if pct is not None:
                lines.append(f"That puts you in the top {pct}% of the cohort.")
        lines.append("The weekly board resets every Monday — new learners can compete on this week's XP.")
        lines.append("Your fastest honest way up: complete the next roadmap milestone and master your weakest skill.")
        return CoachReply("\n".join(lines), intent="rank")

    def _answer_challenge(self, learner: Learner, roadmap: Roadmap | None) -> CoachReply:
        try:
            from app.services.gamification_service import GamificationService

            gs = GamificationService()
            challenges = gs._challenge_states(learner)
        except Exception:  # noqa: BLE001
            challenges = []
        if not challenges:
            return CoachReply("No weekly challenges are active right now — check back on Monday.", intent="challenge")
        lines = ["This week's challenges:"]
        for c in challenges:
            pct = min(100, int(c["progress"] / max(1, c["target"]) * 100))
            done = "✓ done" if c["completed"] else f"{pct}% done"
            lines.append(f"• **{c['title']}** — {c['description']} ({done}) · +{c['xp_reward']} XP")
        lines.append("Challenges reward real learning — assessments, projects, mastery — never busywork.")
        return CoachReply("\n".join(lines), intent="challenge")

    def _answer_xp_farm(self, learner: Learner, roadmap: Roadmap | None) -> CoachReply:
        """Explicitly steer away from XP farming."""
        lines = [
            "There is no shortcut worth taking — LearnPath XP rewards mastery, not repetition.",
            "Repeating the same course or resource earns 0 XP, and there's no XP for logging in, clicking around, or chatting.",
            "Your fastest meaningful progress is to complete the next roadmap milestone and strengthen your current weak skill.",
            "Focus on learning well; the XP, level-ups and ranking follow from that.",
        ]
        if roadmap and roadmap.next_action():
            lines.append(f"Start with: **{roadmap.next_action().title}**.")
        return CoachReply("\n".join(lines), intent="xp_farm")

    def _answer_badge(self, learner: Learner) -> CoachReply:
        from app.ml import gamification as gam

        earned = {b["badge_id"] for b in self._repo_badges(learner)}
        owned = [b for b in gam.all_badge_definitions() if b["badge_id"] in earned]
        total = len(gam.all_badge_definitions())
        if not owned:
            return CoachReply(
                f"You haven't earned any badges yet — complete your first learning activity to unlock **First Step**.",
                intent="badge",
            )
        lines = [f"You've earned **{len(owned)} of {total}** badges:"]
        lines += [f"• {b['icon']} **{b['name']}** — {b['description']}" for b in owned[:8]]
        if len(owned) > 8:
            lines.append(f"…and {len(owned) - 8} more. See the Achievements page for the full list.")
        return CoachReply("\n".join(lines), intent="badge")

    def _repo_badges(self, learner: Learner) -> list[dict]:
        from app.database.repository import LearnerRepository

        return LearnerRepository().learner_badges(learner.learner_id)

    def _answer_mission(self, learner: Learner, roadmap: Roadmap | None) -> CoachReply:
        if not roadmap or not roadmap.phases:
            return CoachReply(
                "Your roadmap hasn't been generated yet. Finish onboarding so I can plan your day.",
                intent="mission",
            )
        mission = build_daily_mission(learner, roadmap, self.catalog)
        lines = [f"Today's mission — about {mission.total_minutes} minutes."]
        for i, step in enumerate(mission.steps, 1):
            lines.append(f"{i}. {step.title} — {step.minutes} min")
        lines.append("Finish with a quick self-check on how confident you feel.")
        return CoachReply("\n".join(lines), intent="mission")

    def _answer_next(self, learner: Learner, roadmap: Roadmap | None) -> CoachReply:
        if not roadmap or not roadmap.phases:
            return CoachReply("No roadmap yet — generate one in My Learning Journey first.", intent="next")
        item = roadmap.next_action()
        if item is None:
            return CoachReply("You've completed your entire roadmap — congratulations! Time to update your portfolio and start applying.", intent="next")
        skill_names = ", ".join(self._skill_name(s) for s in item.skill_ids)
        phase = next((p for p in roadmap.phases if p.index == item.phase_index), None)
        return CoachReply(
            f"Next up: **{item.title}** (Phase {item.phase_index + 1}: {phase.label if phase else ''}).\n"
            f"Skills you'll build: {skill_names}.\n"
            f"Estimated {item.duration_hours:g} hours. {item.description}",
            intent="next",
        )

    def _answer_skip(self, learner: Learner, message: str) -> CoachReply:
        m = _SKILL_QUERY.search(message)
        skill_id = self._resolve_skill(m.group(1) if m else message)
        if skill_id is None:
            return CoachReply(
                "I couldn't identify which skill you mean. Try \"Can I skip statistics?\"",
                intent="skip",
            )
        skill = self.catalog.skill(skill_id)
        dependents = self._dependents_names(skill_id)
        role = self.catalog.role(learner.target_role)
        required = role and skill_id in role.required_skills
        lines = [f"About skipping **{skill.name}**:"]
        if required:
            lines.append(f"It is part of your {role.title if role else 'target'} role's competency map, so it matters for your goal.")
        if dependents:
            lines.append(f"Later skills depend on it: {', '.join(dependents[:4])}. Skipping it will make those much harder.")
        else:
            lines.append("Nothing later in your path depends on it directly.")
        prof = learner.proficiency(skill_id)
        if prof >= config.PREREQ_READY_THRESHOLD:
            lines.append(f"Your current proficiency ({prof:.0%}) already clears the ready threshold, so you can move fast through this area.")
        else:
            res = self.catalog.resources_for_skill(skill_id)
            if res:
                lines.append(f"Instead of skipping, spend ~{res[0].duration_min} min on '{res[0].title}' to unlock the next phase safely.")
        return CoachReply("\n".join(lines), intent="skip")

    def _answer_why_skill(self, learner: Learner, message: str) -> CoachReply:
        m = _SKILL_QUERY.search(message)
        skill_id = self._resolve_skill(m.group(1) if m else message)
        if skill_id is None:
            return CoachReply(
                "Which skill? Try \"Why should I learn statistics?\"",
                intent="why_skill",
            )
        skill = self.catalog.skill(skill_id)
        role = self.catalog.role(learner.target_role)
        lines = [f"Why **{skill.name}** matters for you:"]
        if role and skill_id in role.skills:
            target = role.skills[skill_id]
            lines.append(f"Your goal is {role.title}, and this competency is expected at ~{target:.0%} proficiency.")
        else:
            lines.append(f"It belongs to the {skill.category} area and supports your broader goal.")
        dependents = self._dependents_names(skill_id)
        if dependents:
            lines.append(f"It unlocks: {', '.join(dependents[:4])}.")
        lines.append(f"Current level: {learner.proficiency(skill_id):.0%} → target {role.skills.get(skill_id, 0.7):.0%}.")
        chunk = self.kb.get(f"skill:{skill_id}")
        if chunk:
            lines.append(chunk.replace("SKILL:", "Reference:"))
        return CoachReply("\n".join(lines), intent="why_skill")

    def _answer_focus(self, learner: Learner, roadmap: Roadmap | None) -> CoachReply:
        if not learner.known_skills:
            return CoachReply("Once you finish onboarding I can recommend a daily focus.", intent="focus")
        weak = min(
            learner.known_skills.items(), key=lambda kv: kv[1],
            default=("python", 0.3),
        )
        skill = self.catalog.skill(weak[0])
        name = skill.name if skill else weak[0]
        lines = [
            f"Focus on **{name}** today (confidence {weak[1]:.0%}).",
            "Suggested 30 minutes: read a short reference, then solve 3–5 small exercises.",
        ]
        res = self.catalog.resources_for_skill(weak[0])
        if res:
            lines.append(f"Start with: {res[0].title} — {res[0].url}")
        return CoachReply("\n".join(lines), intent="focus")

    def _answer_struggling(self, learner: Learner, message: str) -> CoachReply:
        m = _SKILL_QUERY.search(message)
        skill_id = self._resolve_skill(m.group(1) if m else message)
        if skill_id is None:
            return CoachReply(
                "I hear you — which topic are you struggling with? e.g. \"I'm struggling with classification\".",
                intent="struggling",
            )
        skill = self.catalog.skill(skill_id)
        lines = [
            f"It's normal to hit a wall with **{skill.name}** — here's a concrete recovery plan:",
            "1. Re-read the skill definition below and identify exactly which concept feels unclear.",
            "2. Do one short reference (10–20 min) instead of a long course.",
            "3. Solve 5 small exercises, then re-attempt your last project step.",
        ]
        chunk = self.kb.get(f"skill:{skill_id}")
        if chunk:
            lines.append(chunk.replace("SKILL:", "Reference:"))
        res = self.catalog.resources_for_skill(skill_id)
        if res:
            lines.append(f"Start here: {res[0].title} — {res[0].url}")
        assessment = self.catalog.assessment_for_skill(skill_id)
        if assessment:
            lines.append(
                f"When you feel readier, take the '{assessment.title}' knowledge check to confirm the weak areas are resolved."
            )
            return CoachReply("\n".join(lines), intent="struggling",
                              actions=[{"type": "open_assessment", "assessment_id": assessment.assessment_id}])
        return CoachReply("\n".join(lines), intent="struggling")

    def _answer_completed(self, learner: Learner, roadmap: Roadmap | None, message: str) -> CoachReply:
        # find the item by fuzzy title match against roadmap items
        item = None
        if roadmap:
            for p in roadmap.phases:
                for i in p.items:
                    if i.title.lower()[:20] in message.lower() or any(
                        w in message.lower() for w in i.title.lower().split()[:3]
                    ):
                        item = i
                        break
                if item:
                    break
        if item:
            return CoachReply(
                f"Nice work completing **{item.title}**! Mark it done in the journey view and I'll refresh your next steps.",
                intent="completed",
                actions=[{"type": "mark_complete", "item_id": item.item_id, "item_type": item.item_type}],
            )
        return CoachReply(
            "Great progress! Tell me which course or project you finished (exact title helps), "
            "and I'll help you mark it complete and see what's next.",
            intent="completed",
        )

    def _answer_explain(self, learner: Learner, message: str) -> CoachReply:
        hits = self.kb.retrieve(message, k=4)
        good = [h for h in hits if h["score"] >= 0.18]
        if not good:
            return CoachReply(
                "I don't have reliable information about that in the LearnPath knowledge base yet. "
                "Try asking about a specific skill, course, or concept like \"explain cross-validation\".",
                intent="explain",
            )
        lines = ["Here's what I found in the knowledge base:"]
        sources: list[str] = []
        seen_types: set[str] = set()
        for hit in good:
            kind = hit["chunk_id"].split(":", 1)[0]
            if kind in seen_types:
                continue
            seen_types.add(kind)
            lines.append(hit["text"])
            sources.append(hit["chunk_id"])
        return CoachReply("\n".join(lines), intent="explain", sources=sources)

    def _answer_general(self, learner: Learner, roadmap: Roadmap | None, message: str) -> CoachReply:
        hits = self.kb.retrieve(message, k=config.COACH_RETRIEVAL_K)
        good = [h for h in hits if h["score"] >= 0.15]
        context = self._learner_context_text(learner, roadmap)
        if not good:
            return CoachReply(
                "I don't have that information in my knowledge base. I can help with: "
                "today's mission, what's next, why a skill matters, skipping modules, "
                "explaining concepts, and recovery plans when you're stuck.",
                intent="general",
            )
        retrieved = "\n\n".join(h["text"] for h in good)
        provider = get_llm_provider()
        if provider.available() and provider.name != "local":
            try:
                answer = provider.complete(
                    COACH_SYSTEM,
                    COACH_USER.format(
                        learner_context=context,
                        retrieved_knowledge=retrieved,
                        question=message,
                    ),
                    max_tokens=500,
                )
                if answer and answer.strip():
                    return CoachReply(answer, intent="general",
                                      sources=[h["chunk_id"] for h in good])
            except Exception as exc:  # noqa: BLE001
                log.warning("LLM coach failed, using local composition: %s", exc)
        lines = ["Based on your profile and the LearnPath knowledge base:"]
        lines.extend(h["text"] for h in good[:3])
        return CoachReply("\n".join(lines), intent="general", sources=[h["chunk_id"] for h in good])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_skill(self, text: str) -> str | None:
        if not text:
            return None
        t = text.strip().lower().rstrip("?.")
        # direct id match
        if t in self.catalog.skills:
            return t
        matches = self.catalog.search_skills(t)
        if matches:
            return matches[0].skill_id
        for skill_id, synonyms in [
            (sid, syns) for sid, syns in [
                ("ml_fundamentals", ["machine learning", "ml", "ml fundamentals"]),
                ("deep_learning", ["deep learning", "neural networks"]),
                ("statistics", ["statistics", "stats"]),
                ("python", ["python"]),
                ("classification", ["classification", "classifier"]),
                ("model_evaluation", ["cross-validation", "cross validation", "model evaluation"]),
                ("feature_engineering", ["feature engineering", "features"]),
                ("docker", ["docker", "containers"]),
                ("sql", ["sql", "databases"]),
            ]
        ]:
            if any(s in t for s in synonyms):
                return skill_id
        return None

    def _dependents_names(self, skill_id: str) -> list[str]:
        return [self._skill_name(d) for d in self._graph.dependents_of(skill_id)]

    def _skill_name(self, skill_id: str) -> str:
        s = self.catalog.skill(skill_id)
        return s.name if s else skill_id
