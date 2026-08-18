"""LearnPath XP — event pipeline service.

The frontend signals *what happened* (a course was completed, an
assessment was submitted); this service decides how many XP that was
worth, writes the immutable transaction ledger, updates the aggregate
gamification state, detects level-ups, evaluates badges, advances
streaks, and tracks weekly challenges.

All XP arithmetic is server-side. The client can never submit XP.
"""
from __future__ import annotations

from typing import Any

from app import config
from app.database.models import Learner
from app.database.repository import LearnerRepository
from app.ml import gamification as gam


class GamificationService:
    def __init__(self, repo: LearnerRepository | None = None) -> None:
        self.repo = repo or LearnerRepository()

    # ------------------------------------------------------------------
    # Aggregate state
    # ------------------------------------------------------------------
    def get_state(self, learner: Learner, include_meta: bool = True) -> dict[str, Any]:
        row = self.repo.get_gamification(learner.learner_id)
        if row is None:
            row = self._default_state()
            # initialize the aggregate row so leaderboards see every learner
            self.repo.upsert_gamification(learner.learner_id, {
                "total_xp": 0, "weekly_xp": 0, "monthly_xp": 0,
                "current_streak": 0, "longest_streak": 0,
                "last_learning_date": None, "rank": config.RANKS[0],
                "level": 1, "updated_at": gam.now_iso(),
            })
        # badges are derived state: re-evaluate against the current twin so
        # conditions that were met but never fired (e.g. events before a
        # deployment) are backfilled deterministically. earn_badge dedupes.
        self.evaluate_and_reward_badges(learner)
        level, level_title, _, xp_to_next = gam.level_for_xp(row["total_xp"])
        frac, into, within = gam.level_progress(row["total_xp"])  # noqa: F841 - into/within used by UI
        badges = [b["badge_id"] for b in self.repo.learner_badges(learner.learner_id)]
        cohort_xp = [g["total_xp"] for g in self.repo.all_gamification_rows()]
        rank = gam.rank_for_xp(row["total_xp"], cohort_xp)
        # leaderboard position
        rows = self.repo.all_gamification_rows()
        rows_sorted = sorted(rows, key=lambda r: -r["total_xp"])
        position = next((i + 1 for i, r in enumerate(rows_sorted) if r["learner_id"] == learner.learner_id), None)

        weekly = self.repo.xp_since(learner.learner_id, gam.week_start_iso())
        monthly = self.repo.xp_since(learner.learner_id, gam.month_start_iso())
        row["weekly_xp"] = weekly
        row["monthly_xp"] = monthly

        state = {
            "learner_id": learner.learner_id,
            "total_xp": row["total_xp"],
            "weekly_xp": weekly,
            "monthly_xp": monthly,
            "current_streak": row["current_streak"],
            "longest_streak": row["longest_streak"],
            "last_learning_date": row["last_learning_date"],
            "level": level,
            "level_title": level_title,
            "level_floor": gam.level_for_xp(row["total_xp"])[2],
            "level_progress": round(frac, 4),
            "level_into": into,
            "xp_to_next_level": xp_to_next,
            "rank": rank,
            "leaderboard_position": position,
            "leaderboard_size": len(rows),
            "badges": badges,
            "badge_count": len(badges),
            "badge_definitions": gam.all_badge_definitions() if include_meta else [],
            "weekly_challenges": gam.current_challenges(self.repo) if include_meta else [],
            "challenges": self._challenge_states(learner) if include_meta else [],
            "breakdown": self.repo.xp_breakdown(learner.learner_id) if include_meta else [],
        }
        return state

    def _default_state(self) -> dict[str, Any]:
        return {
            "total_xp": 0, "weekly_xp": 0, "monthly_xp": 0,
            "current_streak": 0, "longest_streak": 0, "last_learning_date": None,
            "rank": config.RANKS[0], "level": 1, "leaderboard_opt_out": 0,
        }

    # ------------------------------------------------------------------
    # Challenges
    # ------------------------------------------------------------------
    def _challenge_states(self, learner: Learner) -> list[dict[str, Any]]:
        out = []
        for c in gam.current_challenges(self.repo):
            progress = gam.challenge_progress_value(learner, c["challenge_type"], self.repo)
            row = self.repo.get_learner_challenge(learner.learner_id, c["id"]) or {}
            completed = bool(row.get("completed")) or progress >= float(c["target"])
            out.append({
                "challenge_id": c["id"], "title": c["title"], "description": c["description"],
                "challenge_type": c["challenge_type"], "target": float(c["target"]),
                "xp_reward": int(c["xp_reward"]), "progress": min(progress, float(c["target"])),
                "completed": completed, "claimed": bool(row.get("claimed")),
            })
        return out

    def update_challenge_progress(self, learner: Learner) -> None:
        """Refresh challenge progress for the learner (called after events)."""
        for c in gam.current_challenges(self.repo):
            progress = gam.challenge_progress_value(learner, c["challenge_type"], self.repo)
            row = self.repo.get_learner_challenge(learner.learner_id, c["id"]) or {}
            completed = bool(row.get("completed")) or progress >= float(c["target"])
            self.repo.upsert_learner_challenge(learner.learner_id, {
                "challenge_id": c["id"], "progress": progress,
                "completed": completed, "completed_at": row.get("completed_at"),
                "claimed": bool(row.get("claimed")),
            })

    def claim_challenge(self, learner: Learner, challenge_id: str) -> dict[str, Any]:
        c = self.repo.get_challenge(challenge_id)
        if c is None:
            return {"ok": False, "error": "Unknown challenge"}
        state = self.repo.get_learner_challenge(learner.learner_id, challenge_id) or {}
        # recompute progress live (stored rows can lag by one event)
        progress = gam.challenge_progress_value(learner, c["challenge_type"], self.repo)
        completed = bool(state.get("completed")) or progress >= float(c["target"])
        if not completed:
            return {"ok": False, "error": "Challenge not completed yet"}
        if state.get("claimed"):
            return {"ok": False, "error": "Already claimed"}
        result = self._award(
            learner,
            event_type="challenge_completed",
            activity_id=challenge_id,
            base_override=int(c["xp_reward"]),
            reason=f"Weekly challenge: {c['title']}",
        )
        self.repo.upsert_learner_challenge(learner.learner_id, {
            "challenge_id": challenge_id, "progress": progress,
            "completed": True, "completed_at": gam.now_iso(),
            "claimed": True,
        })
        return {"ok": True, **result}

    # ------------------------------------------------------------------
    # Main event entry
    # ------------------------------------------------------------------
    def handle_event(
        self,
        learner: Learner,
        event_type: str,
        activity_id: str = "",
        *,
        difficulty: int = 3,
        assessment_score: float | None = None,
        prev_best_score: float | None = None,
        is_capstone: bool = False,
        is_remediation: bool = False,
        completed_early: bool = False,
        phase_completed: bool = False,
        base_override: int | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Process a learning event end-to-end. Returns a summary dict the
        frontend can use for animations and banners:
        {xp_awarded, is_duplicate, level_up, new_level, new_badges,
         streak_milestone, state}
        """
        if event_type not in gam.EVENT_TYPES and base_override is None:
            return {"xp_awarded": 0, "is_duplicate": True, "level_up": None,
                    "new_badges": [], "streak_milestone": None}

        # 1. anti-farm: has this (learner, type, activity) already been rewarded?
        existing = self.repo.get_gamification(learner.learner_id)
        is_dup = self._already_rewarded(learner.learner_id, event_type, activity_id)

        # 2. compute XP (server-side, deterministic)
        #    flat events (mission/streak/challenge) carry no difficulty multiplier
        flat_events = {"daily_mission_completed", "weekly_milestone_completed",
                       "challenge_completed", "remediation_completed"}
        if event_type in flat_events:
            difficulty = 0
        calc = gam.calculate_xp(
            event_type, activity_id, difficulty=difficulty,
            assessment_score=assessment_score, prev_best_score=prev_best_score,
            is_capstone=is_capstone, is_remediation=is_remediation,
            completed_early=completed_early,
        )
        if base_override is not None:
            calc["base_xp"] = base_override
            calc["final_xp"] = base_override
            calc["multiplier"] = 1.0
            calc["reason"] = reason or calc["reason"]

        row = existing or self._default_state()
        prev_total = int(row["total_xp"])
        prev_level = gam.level_for_xp(prev_total)[0]  # noqa: PLW2901

        xp_awarded = 0
        # 3. write the immutable ledger (anti-farm: unique (learner,type,activity))
        tx_id = self.repo.add_xp_transaction(learner.learner_id, {
            "activity_id": activity_id, "activity_type": event_type,
            "base_xp": calc["base_xp"], "bonus_xp": calc["bonus_xp"],
            "multiplier": calc["multiplier"], "final_xp": calc["final_xp"],
            "reason": calc["reason"], "created_at": gam.now_iso(),
        })
        if not tx_id:
            is_dup = True
            # repeats earn no base XP, but a re-assessment can still earn the
            # improvement (comeback) bonus — rewarded learning progress.
            if event_type == "assessment_completed" and assessment_score is not None \
                    and prev_best_score is not None:
                gain = assessment_score - prev_best_score
                if gain >= config.IMPROVEMENT_BONUS_MIN_GAIN:
                    xp_awarded = config.IMPROVEMENT_BONUS_XP
                    calc["bonus_xp"] = xp_awarded
                    calc["final_xp"] = xp_awarded
                    calc["reason"] = "improvement bonus: re-assessment beat previous best"
                    self.repo.add_xp_transaction(learner.learner_id, {
                        "activity_id": f"{activity_id}_improvement", "activity_type": event_type,
                        "base_xp": 0, "bonus_xp": xp_awarded, "multiplier": 1.0,
                        "final_xp": xp_awarded, "reason": calc["reason"], "created_at": gam.now_iso(),
                    })
        else:
            xp_awarded = calc["final_xp"]

        # 4. streak (only meaningful learning counts)
        streak, longest, last_date, streak_milestone = gam.update_streak(
            int(row.get("current_streak", 0)), int(row.get("longest_streak", 0)),
            row.get("last_learning_date"),
        )

        new_total = prev_total + xp_awarded
        new_level = gam.level_for_xp(new_total)[0]

        # 5. persist aggregate
        self.repo.upsert_gamification(learner.learner_id, {
            "total_xp": new_total,
            "weekly_xp": self.repo.xp_since(learner.learner_id, gam.week_start_iso()),
            "monthly_xp": self.repo.xp_since(learner.learner_id, gam.month_start_iso()),
            "current_streak": streak, "longest_streak": longest,
            "last_learning_date": last_date,
            "rank": gam.rank_for_xp(new_total, [g["total_xp"] for g in self.repo.all_gamification_rows()]),
            "level": new_level,
            "updated_at": gam.now_iso(),
        })

        # 6. streak milestone bonus XP
        if streak_milestone:
            bonus_xp = config.STREAK_MILESTONES[streak][0]
            self._award(learner, "weekly_milestone_completed",
                        activity_id=f"streak_{streak}", base_override=bonus_xp,
                        reason=f"{streak}-day learning streak")
            new_total += bonus_xp
            self.repo.upsert_gamification(learner.learner_id, {
                "total_xp": new_total, "level": gam.level_for_xp(new_total)[0],
                "updated_at": gam.now_iso(),
            })

        # 7. badges (deterministic)
        new_badge_ids = gam.evaluate_badges(
            learner, self.repo,
            phase_completed=phase_completed,
            capstone_completed=is_capstone,
            early_milestone=completed_early,
            remediation_pass=is_remediation and (assessment_score or 0) >= config.ASSESSMENT_PASS_SCORE,
            streak=streak,
        )
        new_badges = gam.reward_badges(learner, self.repo, new_badge_ids)

        # 8. challenges
        self.update_challenge_progress(learner)

        # 9. summary for the UI
        level_up = None
        if new_level > prev_level and xp_awarded > 0:
            level_up = {
                "from": prev_level, "to": new_level,
                "title": gam.level_for_xp(new_total)[1],
                "xp_earned": xp_awarded,
            }

        return {
            "xp_awarded": xp_awarded,
            "event_type": event_type,
            "is_duplicate": is_dup,
            "breakdown": {"base_xp": calc["base_xp"], "bonus_xp": calc["bonus_xp"],
                          "multiplier": calc["multiplier"], "final_xp": calc["final_xp"],
                          "reason": calc["reason"]},
            "level_up": level_up,
            "new_badges": new_badges,
            "streak_milestone": (streak if streak_milestone else None),
            "streak": streak,
            "total_xp": new_total,
            "state": self.get_state(learner, include_meta=False),
        }

    def evaluate_and_reward_badges(self, learner: Learner, *, streak: int | None = None,
                                   phase_completed: bool = False, capstone_completed: bool = False,
                                   early_milestone: bool = False, remediation_pass: bool = False) -> list[dict]:
        """Re-evaluate badges against the CURRENT twin (call after twin updates)."""
        if streak is None:
            row = self.repo.get_gamification(learner.learner_id) or self._default_state()
            streak = int(row.get("current_streak", 0))
        new_ids = gam.evaluate_badges(
            learner, self.repo, streak=streak, phase_completed=phase_completed,
            capstone_completed=capstone_completed, early_milestone=early_milestone,
            remediation_pass=remediation_pass,
        )
        return gam.reward_badges(learner, self.repo, new_ids)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _already_rewarded(self, learner_id: str, event_type: str, activity_id: str) -> bool:
        if not activity_id:
            return False
        txs = self.repo.xp_transactions(learner_id, limit=500)
        return any(t["activity_type"] == event_type and t["activity_id"] == activity_id for t in txs)

    def _award(self, learner: Learner, event_type: str, activity_id: str, *,
               base_override: int, reason: str) -> dict[str, Any]:
        """Award XP without the full event pipeline (used for bonuses)."""
        if self._already_rewarded(learner.learner_id, event_type, activity_id):
            return {"xp_awarded": 0, "is_duplicate": True}
        tx_id = self.repo.add_xp_transaction(learner.learner_id, {
            "activity_id": activity_id, "activity_type": event_type,
            "base_xp": base_override, "bonus_xp": 0, "multiplier": 1.0,
            "final_xp": base_override, "reason": reason, "created_at": gam.now_iso(),
        })
        if not tx_id:
            return {"xp_awarded": 0, "is_duplicate": True}
        row = self.repo.get_gamification(learner.learner_id) or self._default_state()
        new_total = int(row["total_xp"]) + base_override
        self.repo.upsert_gamification(learner.learner_id, {
            "total_xp": new_total,
            "level": gam.level_for_xp(new_total)[0],
            "updated_at": gam.now_iso(),
        })
        return {"xp_awarded": base_override, "is_duplicate": False}
