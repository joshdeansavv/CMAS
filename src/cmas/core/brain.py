"""Brain architecture — neural pathways, dopamine reward, priority detection, consolidation.

Implements neuroscience-inspired cognitive systems:
- Weighted neural pathways (Hebbian learning: strengthen what works)
- Dopamine reward signal (prediction error: actual vs expected quality)
- Priority/urgency detection (amygdala: fast threat/importance assessment)
- Memory consolidation (hippocampal replay: compress episodes into schemas)
- Default Mode Network (background creativity during idle)
- Agent typing (excitatory, inhibitory, modulatory)

Based on research from:
- Schultz (1997): Dopamine prediction error
- Hebb (1949): Synaptic strengthening
- Raichle (2001): Default Mode Network
- Beaty (2018): Creative cognition networks
- Damasio (1994): Somatic markers
- McClelland et al (1995): Complementary Learning Systems
"""
from __future__ import annotations

import json
import math
import time
import random
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from .llm import chat
from .memory import Memory


# ── Neural Pathway Weights ───────────────────────────────────────────

@dataclass
class Connection:
    """A weighted connection between two agents (synapse analog)."""
    source: str
    target: str
    weight: float = 0.5       # 0.0-1.0, initial baseline
    success_count: int = 0
    failure_count: int = 0
    last_used: float = 0.0
    decay_rate: float = 0.01  # weight decays this much per day unused


class NeuralPathways:
    """Hebbian learning for agent routing.

    'Neurons that fire together wire together' — agent combinations
    that produce good results get stronger connections.

    Also implements:
    - Weight decay (synaptic pruning)
    - Homeostatic scaling (prevent any single pathway from dominating)
    """

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pathways (
                source TEXT,
                target TEXT,
                weight REAL DEFAULT 0.5,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                last_used REAL DEFAULT 0,
                PRIMARY KEY (source, target)
            )
        """)
        self._conn.commit()

    def get_weight(self, source: str, target: str) -> float:
        row = self._conn.execute(
            "SELECT weight FROM pathways WHERE source=? AND target=?",
            (source, target),
        ).fetchone()
        return row["weight"] if row else 0.5

    def strengthen(self, source: str, target: str, amount: float = 0.05):
        """LTP — long-term potentiation. Strengthen a successful pathway."""
        self._ensure_exists(source, target)
        self._conn.execute(
            "UPDATE pathways SET weight = MIN(1.0, weight + ?), success_count = success_count + 1, last_used = ? WHERE source=? AND target=?",
            (amount, time.time(), source, target),
        )
        self._conn.commit()

    def weaken(self, source: str, target: str, amount: float = 0.03):
        """LTD — long-term depression. Weaken a failed pathway."""
        self._ensure_exists(source, target)
        self._conn.execute(
            "UPDATE pathways SET weight = MAX(0.0, weight - ?), failure_count = failure_count + 1, last_used = ? WHERE source=? AND target=?",
            (amount, time.time(), source, target),
        )
        self._conn.commit()

    def decay_all(self):
        """Synaptic pruning — unused connections decay toward baseline."""
        now = time.time()
        rows = self._conn.execute("SELECT source, target, weight, last_used FROM pathways").fetchall()
        for r in rows:
            days_unused = (now - r["last_used"]) / 86400
            if days_unused > 1:
                decay = 0.01 * days_unused
                new_weight = max(0.1, min(r["weight"], r["weight"] - decay))  # decay toward 0.1, not 0
                self._conn.execute(
                    "UPDATE pathways SET weight=? WHERE source=? AND target=?",
                    (new_weight, r["source"], r["target"]),
                )
        self._conn.commit()

    def get_best_route(self, source: str, candidates: List[str]) -> str:
        """Choose the best target agent based on pathway weights.

        Uses epsilon-greedy: mostly exploit best path, sometimes explore.
        """
        epsilon = 0.1  # 10% exploration rate
        if random.random() < epsilon:
            return random.choice(candidates)

        weights = [(c, self.get_weight(source, c)) for c in candidates]
        weights.sort(key=lambda x: x[1], reverse=True)
        return weights[0][0]

    def homeostatic_scale(self):
        """Prevent any single agent from accumulating too much weight.

        If one agent's total incoming weight is >2x the average, scale it down.
        """
        rows = self._conn.execute(
            "SELECT target, SUM(weight) as total FROM pathways GROUP BY target"
        ).fetchall()
        if not rows:
            return
        avg = sum(r["total"] for r in rows) / len(rows)
        for r in rows:
            if avg > 0 and r["total"] > avg * 2:
                scale = avg / r["total"]
                self._conn.execute(
                    "UPDATE pathways SET weight = weight * ? WHERE target = ?",
                    (scale, r["target"]),
                )
        self._conn.commit()

    def _ensure_exists(self, source: str, target: str):
        self._conn.execute(
            "INSERT OR IGNORE INTO pathways (source, target, weight, last_used) VALUES (?,?,0.5,?)",
            (source, target, time.time()),
        )

    def get_all(self) -> List[Dict]:
        rows = self._conn.execute("SELECT * FROM pathways ORDER BY weight DESC").fetchall()
        return [dict(r) for r in rows]


# ── Dopamine Reward System ───────────────────────────────────────────

@dataclass
class RewardSignal:
    """A prediction error signal (Schultz 1997)."""
    task_id: str
    agent: str
    expected_quality: float
    actual_quality: float
    prediction_error: float  # actual - expected
    timestamp: float


class DopamineSystem:
    """Reward system based on prediction error.

    Before task: predict expected quality
    After task: compute actual quality
    Prediction error = actual - expected

    Positive error → reinforce strategy (LTP)
    Negative error → weaken strategy (LTD) + trigger after-action review
    """

    def __init__(self, pathways: NeuralPathways, memory: Memory):
        self.pathways = pathways
        self.memory = memory
        self.signals: List[RewardSignal] = []
        self._baseline_scores: Dict[str, List[float]] = defaultdict(list)

    def predict_quality(self, agent_type: str, task_description: str) -> float:
        """Predict expected quality based on past performance.

        Uses running average of past scores for this agent type.
        """
        history = self._baseline_scores.get(agent_type, [])
        if history:
            return sum(history[-10:]) / len(history[-10:])
        return 5.0  # neutral baseline

    def process_reward(self, task_id: str, agent_name: str, agent_type: str,
                       actual_quality: float, task_chain: List[str] = None):
        """Process a completed task and generate reward signals.

        Updates pathway weights based on prediction error.
        Stores signal for analysis.
        """
        expected = self.predict_quality(agent_type, "")
        error = actual_quality - expected

        signal = RewardSignal(
            task_id=task_id, agent=agent_name,
            expected_quality=round(expected, 1),
            actual_quality=round(actual_quality, 1),
            prediction_error=round(error, 1),
            timestamp=time.time(),
        )
        self.signals.append(signal)

        # Update baseline
        self._baseline_scores[agent_type].append(actual_quality)

        # Hebbian update on the pathway chain
        if task_chain and len(task_chain) >= 2:
            for i in range(len(task_chain) - 1):
                if error > 0:
                    # Better than expected — strengthen pathway
                    strength = min(0.1, error * 0.02)
                    self.pathways.strengthen(task_chain[i], task_chain[i+1], strength)
                elif error < 0:
                    # Worse than expected — weaken pathway
                    weakness = min(0.08, abs(error) * 0.015)
                    self.pathways.weaken(task_chain[i], task_chain[i+1], weakness)

        # Store surprisingly good strategies in memory
        if error > 2.0:
            self.memory.store(
                topic=f"surprisingly_effective_strategy",
                content=f"Agent {agent_name} scored {actual_quality}/10 (expected {expected:.1f}) on task {task_id}",
                category="reward",
                source="dopamine_system",
                confidence=0.8,
            )

        return signal

    def get_summary(self) -> str:
        if not self.signals:
            return "No reward signals yet."
        lines = ["=== Dopamine System ==="]
        avg_error = sum(s.prediction_error for s in self.signals) / len(self.signals)
        positive = sum(1 for s in self.signals if s.prediction_error > 0)
        negative = sum(1 for s in self.signals if s.prediction_error < 0)
        lines.append(f"  Signals: {len(self.signals)} ({positive} positive, {negative} negative)")
        lines.append(f"  Avg prediction error: {avg_error:+.1f}")
        # Best surprises
        if self.signals:
            best = max(self.signals, key=lambda s: s.prediction_error)
            worst = min(self.signals, key=lambda s: s.prediction_error)
            lines.append(f"  Best surprise: {best.agent} ({best.prediction_error:+.1f})")
            lines.append(f"  Worst surprise: {worst.agent} ({worst.prediction_error:+.1f})")
        return "\n".join(lines)


# ── Priority Detection (Amygdala) ────────────────────────────────────

class PriorityDetector:
    """Fast threat/importance assessment (Damasio's somatic markers).

    Rapidly evaluates incoming tasks for urgency and priority.
    Maintains learned "threat patterns" from past failures.
    """

    URGENCY_KEYWORDS = {
        "critical", "urgent", "immediately", "asap", "deadline", "emergency",
        "breaking", "security", "failure", "crash", "blocked", "stuck",
    }

    def __init__(self):
        self._threat_patterns: List[Dict] = []

    def fast_assess(self, task_description: str, has_deadline: bool = False,
                    blocking_others: bool = False) -> Dict:
        """Fast path assessment (milliseconds). Coarse priority."""
        desc_lower = task_description.lower()

        # Keyword-based urgency
        urgency_hits = sum(1 for kw in self.URGENCY_KEYWORDS if kw in desc_lower)

        # Threat pattern matching
        threat_match = 0
        for pattern in self._threat_patterns:
            if pattern["pattern"] in desc_lower:
                threat_match += pattern["severity"]

        # Compute priority level
        score = urgency_hits * 2 + threat_match * 3
        if has_deadline:
            score += 5
        if blocking_others:
            score += 4

        if score >= 10:
            level = 0  # Critical
        elif score >= 5:
            level = 1  # Urgent
        elif score >= 2:
            level = 2  # Important
        else:
            level = 3  # Background

        return {
            "level": level,
            "level_name": ["CRITICAL", "URGENT", "IMPORTANT", "BACKGROUND"][level],
            "score": score,
            "urgency_keywords": urgency_hits,
            "threat_matches": threat_match,
        }

    def somatic_marker(self, strategy_description: str, past_results: List[Dict]) -> Dict:
        """Gut check on a strategy based on past experience (Damasio).

        Returns a feeling-like assessment before committing to a plan.
        """
        if not past_results:
            return {"warning": False, "confidence": 0.5, "message": "No prior data"}

        # Check if similar strategies have failed before
        failures = [r for r in past_results if r.get("score", 5) < 4]
        successes = [r for r in past_results if r.get("score", 5) >= 7]

        failure_rate = len(failures) / len(past_results) if past_results else 0

        return {
            "warning": failure_rate > 0.4,
            "confidence": 1.0 - failure_rate,
            "message": (
                f"CAUTION: {failure_rate:.0%} failure rate for similar strategies"
                if failure_rate > 0.4
                else f"Strategy looks viable ({1-failure_rate:.0%} success rate)"
            ),
            "failure_rate": round(failure_rate, 2),
        }

    def learn_threat(self, pattern: str, severity: float = 1.0):
        """Learn a new threat pattern from a failure (fear conditioning)."""
        self._threat_patterns.append({
            "pattern": pattern.lower(),
            "severity": severity,
            "learned_at": time.time(),
        })


# ── Memory Consolidation (Sleep) ────────────────────────────────────

class Consolidator:
    """Background process that organizes and compresses memory.

    Analogous to hippocampal replay during sleep:
    1. Replay recent task executions
    2. Extract strategy schemas (generalized patterns)
    3. Prune old detailed memories, keep schemas
    4. Recombine elements for novel strategy hypotheses
    """

    def __init__(self, memory: Memory, model: str = "gpt-4.1-nano"):
        self.memory = memory
        self.model = model
        self._schemas: List[Dict] = []

    async def consolidate(self, recent_tasks: List[Dict]) -> Dict:
        """Run a consolidation cycle.

        Takes recent task executions and extracts patterns.
        """
        if not recent_tasks:
            return {"schemas_extracted": 0, "hypotheses_generated": 0}

        tasks_text = "\n".join(
            f"- Agent: {t.get('agent', '?')}, Task: {t.get('description', '?')[:100]}, "
            f"Score: {t.get('score', '?')}, Approach: {t.get('approach', '?')[:100]}"
            for t in recent_tasks[-20:]
        )

        response = await chat(
            messages=[
                {"role": "system", "content": """You are a pattern extraction engine.
Analyze recent task executions and extract reusable strategy schemas.

Return JSON:
{
  "schemas": [
    {
      "name": "short name for this strategy pattern",
      "conditions": "when to use this strategy (task type, context)",
      "agent_sequence": ["agent types in order"],
      "success_rate_estimate": 0.0-1.0,
      "key_factors": ["what makes this strategy work"]
    }
  ],
  "novel_hypotheses": [
    {
      "idea": "a new strategy to try, combining elements from successful patterns",
      "reasoning": "why this might work"
    }
  ],
  "anti_patterns": ["strategies or approaches that consistently fail"]
}

Return ONLY JSON."""},
                {"role": "user", "content": f"Recent task executions:\n{tasks_text}"},
            ],
            model=self.model,
            temperature=0.4,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            result = json.loads(text)
        except Exception:
            result = {"schemas": [], "novel_hypotheses": [], "anti_patterns": []}

        # Store schemas in memory
        for schema in result.get("schemas", []):
            self.memory.store(
                topic=f"strategy_schema: {schema.get('name', 'unknown')}",
                content=json.dumps(schema)[:500],
                category="schema",
                source="consolidator",
                confidence=schema.get("success_rate_estimate", 0.5),
            )
            self._schemas.append(schema)

        # Store hypotheses for future testing
        for hyp in result.get("novel_hypotheses", []):
            self.memory.store(
                topic=f"hypothesis: {hyp.get('idea', 'unknown')[:60]}",
                content=json.dumps(hyp)[:500],
                category="hypothesis",
                source="consolidator",
                confidence=0.3,  # low confidence until tested
            )

        # Store anti-patterns as lessons
        for ap in result.get("anti_patterns", []):
            self.memory.store_lesson(
                what_happened=f"Anti-pattern detected: {ap}",
                what_learned=f"Avoid: {ap}",
                applies_to="strategy_selection",
            )

        return {
            "schemas_extracted": len(result.get("schemas", [])),
            "hypotheses_generated": len(result.get("novel_hypotheses", [])),
            "anti_patterns_found": len(result.get("anti_patterns", [])),
        }

    def get_applicable_schemas(self, task_description: str) -> List[Dict]:
        """Find strategy schemas that might apply to a task."""
        results = self.memory.search("strategy_schema", limit=10)
        applicable = []
        for r in results:
            try:
                schema = json.loads(r.content)
                applicable.append(schema)
            except Exception:
                pass
        return applicable


# ── Default Mode Network (Background Creativity) ─────────────────────

class DefaultModeNetwork:
    """Background creative process that runs during idle time.

    Simulates the brain's DMN:
    - Spontaneous recombination of memories
    - Future scenario simulation
    - Problem incubation (revisit old problems with new knowledge)
    - Cross-domain connection discovery
    """

    def __init__(self, memory: Memory, model: str = "gpt-4.1-nano"):
        self.memory = memory
        self.model = model
        self._incubating: List[Dict] = []  # problems to revisit
        self._hypotheses: List[Dict] = []  # generated ideas

    def add_to_incubation(self, problem: str, context: str = ""):
        """Add an unsolved problem to the incubation queue."""
        self._incubating.append({
            "problem": problem,
            "context": context,
            "added_at": time.time(),
            "attempts": 0,
        })

    async def idle_cycle(self) -> Dict:
        """Run one cycle of background creative processing.

        Call this when the system has no active tasks.
        """
        results = {"recombinations": [], "incubation_insights": [], "future_simulations": []}

        # 1. Spontaneous recombination
        all_knowledge = self.memory.get_recent(limit=20)
        if len(all_knowledge) >= 2:
            # Pick two random knowledge entries and look for connections
            pair = random.sample(all_knowledge, min(2, len(all_knowledge)))
            combo_text = f"Knowledge A: {pair[0].content[:200]}\nKnowledge B: {pair[1].content[:200] if len(pair) > 1 else 'N/A'}"

            response = await chat(
                messages=[
                    {"role": "system", "content": """You are a creative connection finder.
Given two pieces of knowledge, find a non-obvious connection or novel insight.
Return JSON: {"connection": "the insight", "confidence": 0.0-1.0, "useful_for": "potential application"}
Return ONLY JSON."""},
                    {"role": "user", "content": combo_text},
                ],
                model=self.model,
                temperature=0.9,
            )

            try:
                text = response.content.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    text = text.rsplit("```", 1)[0]
                insight = json.loads(text)
                if insight.get("confidence", 0) > 0.3:
                    results["recombinations"].append(insight)
                    self.memory.store(
                        topic=f"creative_insight: {insight.get('connection', '')[:50]}",
                        content=json.dumps(insight)[:500],
                        category="creative",
                        source="dmn",
                        confidence=insight.get("confidence", 0.3),
                    )
            except Exception:
                pass

        # 2. Problem incubation
        if self._incubating:
            problem = self._incubating[0]
            problem["attempts"] += 1

            # Get new knowledge since last attempt
            new_knowledge = self.memory.get_recent(limit=5)
            new_context = "\n".join(f"- {k.content[:150]}" for k in new_knowledge)

            response = await chat(
                messages=[
                    {"role": "system", "content": """You are revisiting an unsolved problem with fresh knowledge.
Look for new angles, solutions, or insights that the new knowledge enables.
Return JSON: {"insight": "new angle or solution", "confidence": 0.0-1.0, "breakthrough": true/false}
Return ONLY JSON."""},
                    {"role": "user", "content": f"Problem: {problem['problem']}\n\nNew knowledge:\n{new_context}"},
                ],
                model=self.model,
                temperature=0.7,
            )

            try:
                text = response.content.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    text = text.rsplit("```", 1)[0]
                incubation_result = json.loads(text)
                results["incubation_insights"].append(incubation_result)
                if incubation_result.get("breakthrough"):
                    self._incubating.pop(0)  # Remove solved problem
            except Exception:
                pass

            # Rotate incubation queue
            if self._incubating:
                self._incubating.append(self._incubating.pop(0))

        return results
