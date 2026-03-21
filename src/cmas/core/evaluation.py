"""Evaluation system — agents score each other's work for quality feedback loops."""
from __future__ import annotations

import json
import time
from typing import List, Dict, Optional
from dataclasses import dataclass

from .llm import chat
from .state import Hub, Task


@dataclass
class Score:
    task_id: str
    evaluator: str
    completeness: float   # 0-10: did the agent fully address the task?
    accuracy: float       # 0-10: is the information correct and well-sourced?
    actionability: float  # 0-10: are the results useful and concrete?
    novelty: float        # 0-10: did the agent find non-obvious insights?
    overall: float        # 0-10: overall quality
    feedback: str         # specific improvement suggestions
    timestamp: float


class Evaluator:
    """LLM-powered evaluation of agent outputs.

    Can be used for:
    - Agents reviewing each other's work
    - Orchestrator quality-checking before synthesis
    - Scoring iterations to measure improvement over time
    """

    def __init__(self, hub: Hub, model: str = "gpt-4.1-nano"):
        self.hub = hub
        self.model = model
        self.scores: List[Score] = []

    async def evaluate_task(self, task: Task, goal: str) -> Score:
        """Evaluate a completed task's result against the original goal."""
        if not task.result:
            return Score(
                task_id=task.id, evaluator="system",
                completeness=0, accuracy=0, actionability=0, novelty=0, overall=0,
                feedback="No result produced.", timestamp=time.time(),
            )

        response = await chat(
            messages=[
                {"role": "system", "content": """You are a quality evaluator for a multi-agent AI system.
Score the agent's work on these dimensions (0-10 each):

1. completeness: Did the agent fully address what was asked?
2. accuracy: Is the information correct and well-sourced?
3. actionability: Are the results concrete and useful?
4. novelty: Did the agent find non-obvious insights?
5. overall: Overall quality considering all factors

Return ONLY a JSON object:
{
  "completeness": <0-10>,
  "accuracy": <0-10>,
  "actionability": <0-10>,
  "novelty": <0-10>,
  "overall": <0-10>,
  "feedback": "specific suggestions for improvement"
}"""},
                {"role": "user", "content": f"GOAL: {goal}\n\nTASK: {task.description}\n\nRESULT:\n{task.result[:2000]}"},
            ],
            model=self.model,
            temperature=0.2,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            data = json.loads(text)
        except Exception:
            data = {"completeness": 5, "accuracy": 5, "actionability": 5, "novelty": 5, "overall": 5, "feedback": "Could not parse evaluation"}

        score = Score(
            task_id=task.id,
            evaluator="evaluator",
            completeness=float(data.get("completeness", 5)),
            accuracy=float(data.get("accuracy", 5)),
            actionability=float(data.get("actionability", 5)),
            novelty=float(data.get("novelty", 5)),
            overall=float(data.get("overall", 5)),
            feedback=data.get("feedback", ""),
            timestamp=time.time(),
        )
        self.scores.append(score)

        # Store score in hub for persistence
        self.hub.remember(
            f"score_{task.id}",
            json.dumps({"overall": score.overall, "feedback": score.feedback}),
        )

        return score

    async def evaluate_all(self, goal: str) -> List[Score]:
        """Evaluate all completed tasks."""
        done_tasks = self.hub.get_tasks(status="done")
        scores = []
        for task in done_tasks:
            # Skip already-scored tasks
            existing = self.hub.recall(f"score_{task.id}")
            if existing:
                continue
            score = await self.evaluate_task(task, goal)
            scores.append(score)
            print(f"[Evaluator] {task.id}: {score.overall}/10 — {score.feedback[:80]}")
        return scores

    async def compare_iterations(self, goal: str, iteration: int) -> Dict:
        """Compare quality across iterations to measure improvement."""
        if len(self.scores) < 2:
            return {"improving": True, "message": "Not enough data to compare"}

        # Split scores by time — rough proxy for iterations
        mid = len(self.scores) // 2
        early = self.scores[:mid]
        late = self.scores[mid:]

        early_avg = sum(s.overall for s in early) / len(early) if early else 0
        late_avg = sum(s.overall for s in late) / len(late) if late else 0

        return {
            "improving": late_avg >= early_avg,
            "early_avg": round(early_avg, 1),
            "late_avg": round(late_avg, 1),
            "delta": round(late_avg - early_avg, 1),
            "message": f"Quality {'improved' if late_avg >= early_avg else 'declined'}: {early_avg:.1f} -> {late_avg:.1f}",
        }

    def get_summary(self) -> str:
        """Human-readable evaluation summary."""
        if not self.scores:
            return "No evaluations performed."

        lines = ["=== Evaluation Summary ==="]
        avg_overall = sum(s.overall for s in self.scores) / len(self.scores)
        lines.append(f"  Tasks evaluated: {len(self.scores)}")
        lines.append(f"  Average score: {avg_overall:.1f}/10")

        # Best and worst
        best = max(self.scores, key=lambda s: s.overall)
        worst = min(self.scores, key=lambda s: s.overall)
        lines.append(f"  Best: {best.task_id} ({best.overall}/10)")
        lines.append(f"  Worst: {worst.task_id} ({worst.overall}/10) — {worst.feedback[:60]}")

        # Dimension averages
        dims = ["completeness", "accuracy", "actionability", "novelty"]
        for dim in dims:
            avg = sum(getattr(s, dim) for s in self.scores) / len(self.scores)
            lines.append(f"  {dim}: {avg:.1f}/10")

        return "\n".join(lines)

    def get_low_scores(self, threshold: float = 5.0) -> List[Score]:
        """Get tasks that scored below a threshold — candidates for retry."""
        return [s for s in self.scores if s.overall < threshold]

    def should_retry_task(self, task_id: str, threshold: float = 4.0) -> bool:
        """Check if a specific task should be retried based on its score."""
        for s in self.scores:
            if s.task_id == task_id and s.overall < threshold:
                return True
        return False
