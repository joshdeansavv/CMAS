"""Meta-cognition — self-monitoring, strategy adaptation, and creative exploration.

This module gives the system awareness of its own performance and the
ability to adapt its approach. Key AGI capabilities:
- Reflect on what worked and what didn't
- Detect when it's stuck or going in circles
- Adapt strategies based on experience
- Generate creative/novel angles when conventional approaches fail
- Monitor resource usage and efficiency
"""
from __future__ import annotations

import json
import time
from typing import List, Dict, Optional
from collections import defaultdict

from .llm import chat
from .memory import Memory
from .state import Hub


class MetaCognition:
    """Self-awareness and adaptation layer for the multi-agent system.

    Sits above the orchestrator, monitoring system-level patterns:
    - Are we making progress or going in circles?
    - Which strategies work for which types of problems?
    - When should we try something radically different?
    - What have we learned across all our runs?
    """

    def __init__(self, hub: Hub, memory: Memory, model: str = "gpt-4.1-nano"):
        self.hub = hub
        self.memory = memory
        self.model = model
        self._strategy_log: List[Dict] = []
        self._progress_snapshots: List[Dict] = []

    # ── Self-Reflection ──────────────────────────────────────────

    async def reflect(self, goal: str, results: List[Dict], scores: List[Dict]) -> Dict:
        """Reflect on a completed iteration: what worked, what didn't, why.

        This is the core metacognitive ability — thinking about thinking.
        """
        results_text = "\n".join(
            f"- {r.get('task_id', '?')}: {r.get('result', '')[:200]}" for r in results
        )
        scores_text = "\n".join(
            f"- {s.get('task_id', '?')}: {s.get('overall', '?')}/10 — {s.get('feedback', '')[:100]}" for s in scores
        )

        response = await chat(
            messages=[
                {"role": "system", "content": """You are a metacognitive analyzer for an AI system.
Reflect on the system's recent work. Identify patterns in what worked and what didn't.

Return JSON:
{
  "what_worked": ["specific things that produced good results"],
  "what_failed": ["specific things that produced poor results"],
  "why_patterns": ["deeper reasons behind the successes and failures"],
  "blind_spots": ["things the system might be missing or not considering"],
  "strategy_adjustments": [
    {
      "current_approach": "what we're doing now",
      "suggested_change": "what to do differently",
      "reasoning": "why this change would help"
    }
  ],
  "confidence_in_progress": 0.0-1.0,
  "stuck_detection": {
    "is_stuck": true/false,
    "evidence": "why we think we're stuck or not",
    "unstick_suggestions": ["ideas to break out of a rut"]
  }
}

Return ONLY JSON."""},
                {"role": "user", "content": f"Goal: {goal}\n\nResults:\n{results_text}\n\nScores:\n{scores_text}"},
            ],
            model=self.model,
            temperature=0.4,
        )

        reflection = self._parse_json(response.content, {
            "what_worked": [], "what_failed": [], "why_patterns": [],
            "blind_spots": [], "strategy_adjustments": [],
            "confidence_in_progress": 0.5,
            "stuck_detection": {"is_stuck": False, "evidence": "Unknown", "unstick_suggestions": []},
        })

        # Store reflection in memory for future runs
        self.memory.store(
            topic=f"reflection on: {goal[:60]}",
            content=json.dumps(reflection)[:500],
            category="metacognition",
            source="metacognition",
            confidence=0.7,
        )

        # Log strategy adjustments
        for adj in reflection.get("strategy_adjustments", []):
            self._strategy_log.append({
                "time": time.time(),
                "goal": goal[:50],
                "adjustment": adj,
            })

        return reflection

    # ── Stuck Detection ──────────────────────────────────────────

    def detect_loops(self, tasks_history: List[Dict]) -> Dict:
        """Detect if the system is going in circles.

        Checks for:
        - Same tasks being retried without improvement
        - Oscillating scores (up-down-up-down)
        - Diminishing returns on iterations
        """
        if len(tasks_history) < 2:
            return {"stuck": False, "reason": "Not enough history"}

        # Check for repeated task descriptions
        descriptions = [t.get("description", "")[:50] for t in tasks_history]
        unique_ratio = len(set(descriptions)) / len(descriptions)

        # Check for score stagnation
        scores = [t.get("score", 5) for t in tasks_history if "score" in t]
        score_trend = "unknown"
        if len(scores) >= 3:
            recent = scores[-3:]
            if all(s == recent[0] for s in recent):
                score_trend = "stagnant"
            elif recent[-1] > recent[0]:
                score_trend = "improving"
            else:
                score_trend = "declining"

        stuck = unique_ratio < 0.5 or score_trend == "stagnant"

        return {
            "stuck": stuck,
            "unique_task_ratio": round(unique_ratio, 2),
            "score_trend": score_trend,
            "reason": (
                "Repeating similar tasks" if unique_ratio < 0.5
                else "Scores stagnating" if score_trend == "stagnant"
                else "Making progress"
            ),
        }

    # ── Strategy Adaptation ──────────────────────────────────────

    async def adapt_strategy(self, goal: str, current_strategy: str,
                             performance_history: List[Dict]) -> Dict:
        """Recommend strategy changes based on accumulated experience.

        This is self-improvement: the system modifies its own approach.
        """
        # Pull relevant lessons from memory
        lessons = self.memory.get_lessons(applies_to=goal[:30], limit=5)
        lessons_text = "\n".join(f"- {l['what_learned']}" for l in lessons) if lessons else "No prior lessons"

        response = await chat(
            messages=[
                {"role": "system", "content": """You are a strategy advisor for an AI system.
Based on performance history and lessons learned, recommend concrete strategy changes.

Focus on:
- What types of agents/tasks produce the best results
- Which approaches should be abandoned
- What new approaches should be tried
- How to allocate resources (more research vs more analysis vs more synthesis)

Return JSON:
{
  "diagnosis": "what's happening with current strategy",
  "keep_doing": ["effective strategies to continue"],
  "stop_doing": ["ineffective strategies to abandon"],
  "start_doing": ["new strategies to try"],
  "agent_allocation": {
    "research": 0.0-1.0,
    "analysis": 0.0-1.0,
    "writing": 0.0-1.0,
    "specialist": 0.0-1.0
  },
  "model_recommendation": "should we use a different/bigger model for certain tasks?",
  "creative_pivot": "if stuck, a radically different approach to try"
}

Return ONLY JSON."""},
                {"role": "user", "content": (
                    f"Goal: {goal}\n\nCurrent strategy: {current_strategy}\n\n"
                    f"Lessons from memory:\n{lessons_text}\n\n"
                    f"Performance history: {json.dumps(performance_history[-10:])}"
                )},
            ],
            model=self.model,
            temperature=0.5,
        )

        adaptation = self._parse_json(response.content, {
            "diagnosis": "Unable to analyze", "keep_doing": [], "stop_doing": [],
            "start_doing": ["Continue current approach"],
            "agent_allocation": {"research": 0.4, "analysis": 0.3, "writing": 0.2, "specialist": 0.1},
            "model_recommendation": "Continue with current model",
            "creative_pivot": "Try a completely different framing of the problem",
        })

        # Store adaptation as a lesson
        self.memory.store_lesson(
            what_happened=f"Strategy adapted for: {goal[:60]}",
            what_learned=f"Diagnosis: {adaptation.get('diagnosis', 'N/A')[:100]}. New strategies: {str(adaptation.get('start_doing', []))[:100]}",
            applies_to=goal[:50],
        )

        return adaptation

    # ── Creative Exploration ─────────────────────────────────────

    async def creativity_boost(self, topic: str, what_we_know: str,
                               what_hasnt_worked: str = "") -> Dict:
        """Generate novel, unconventional angles when standard approaches are exhausted.

        This simulates creative thinking — making unexpected connections,
        reframing problems, considering contrarian viewpoints.
        """
        response = await chat(
            messages=[
                {"role": "system", "content": """You are a creative thinking engine.
Generate genuinely novel, unconventional approaches to a problem.

Rules:
- Do NOT suggest obvious or standard approaches
- MUST include at least one contrarian/counter-intuitive idea
- MUST include cross-domain analogies
- Consider: What would an expert from a completely different field suggest?
- Consider: What if the opposite of the conventional wisdom is true?
- Consider: What would happen if we solved a different problem entirely?

Return JSON:
{
  "reframed_problem": "the problem restated in a way that opens new solutions",
  "unconventional_angles": [
    {
      "idea": "the novel approach",
      "inspiration": "where this idea comes from",
      "why_it_might_work": "reasoning",
      "risk": "what could go wrong"
    }
  ],
  "contrarian_view": {
    "conventional_wisdom": "what most people believe",
    "contrarian_take": "the opposite perspective",
    "evidence": "why the contrarian view might have merit"
  },
  "cross_domain_insights": [
    {
      "domain": "field name",
      "insight": "what we can borrow from this field",
      "application": "how to apply it here"
    }
  ],
  "wildcard": "one truly out-of-the-box suggestion"
}

Return ONLY JSON."""},
                {"role": "user", "content": (
                    f"Topic: {topic}\n\nWhat we know so far: {what_we_know}\n\n"
                    + (f"What hasn't worked: {what_hasnt_worked}" if what_hasnt_worked else "")
                )},
            ],
            model=self.model,
            temperature=0.9,  # High temp for creativity
        )

        return self._parse_json(response.content, {
            "reframed_problem": topic,
            "unconventional_angles": [],
            "contrarian_view": {"conventional_wisdom": "", "contrarian_take": "", "evidence": ""},
            "cross_domain_insights": [],
            "wildcard": "Try approaching from a completely different discipline",
        })

    # ── Progress Monitoring ──────────────────────────────────────

    def snapshot_progress(self, iteration: int, scores: List[float], tasks_done: int, tasks_total: int):
        """Record a progress snapshot for trend analysis."""
        avg_score = sum(scores) / len(scores) if scores else 0
        self._progress_snapshots.append({
            "iteration": iteration,
            "timestamp": time.time(),
            "avg_score": round(avg_score, 1),
            "tasks_done": tasks_done,
            "tasks_total": tasks_total,
            "completion_rate": round(tasks_done / tasks_total, 2) if tasks_total > 0 else 0,
        })

    def get_progress_trend(self) -> Dict:
        """Analyze progress trend across iterations."""
        if len(self._progress_snapshots) < 2:
            return {"trend": "insufficient_data", "snapshots": self._progress_snapshots}

        scores = [s["avg_score"] for s in self._progress_snapshots]
        first_half = scores[:len(scores)//2]
        second_half = scores[len(scores)//2:]

        first_avg = sum(first_half) / len(first_half) if first_half else 0
        second_avg = sum(second_half) / len(second_half) if second_half else 0

        if second_avg > first_avg + 0.5:
            trend = "improving"
        elif second_avg < first_avg - 0.5:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "first_half_avg": round(first_avg, 1),
            "second_half_avg": round(second_avg, 1),
            "total_snapshots": len(self._progress_snapshots),
            "snapshots": self._progress_snapshots,
        }

    def get_summary(self) -> str:
        """Human-readable metacognition summary."""
        lines = ["=== Meta-Cognition Summary ==="]

        trend = self.get_progress_trend()
        lines.append(f"  Progress trend: {trend['trend']}")
        if trend.get('first_half_avg'):
            lines.append(f"  Score trajectory: {trend['first_half_avg']} -> {trend['second_half_avg']}")

        lines.append(f"  Strategy adjustments made: {len(self._strategy_log)}")
        for adj in self._strategy_log[-3:]:
            change = adj.get("adjustment", {}).get("suggested_change", "?")
            lines.append(f"    - {change[:80]}")

        return "\n".join(lines)

    def _parse_json(self, text: str, fallback):
        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            return json.loads(text)
        except Exception:
            return fallback
