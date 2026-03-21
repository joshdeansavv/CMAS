"""Reasoning engine — chain-of-thought, hypothesis generation, causal analysis.

This module gives agents the ability to THINK before they ACT.
Instead of just pattern-matching, agents can:
- Decompose problems into logical steps
- Generate and evaluate multiple hypotheses
- Identify cause-effect relationships
- Plan multi-step approaches with alternatives
- Combine knowledge from different domains (transfer)
"""
from __future__ import annotations

import json
from typing import List, Dict, Optional

from .llm import chat


class Reasoner:
    """LLM-powered reasoning engine.

    Provides structured thinking capabilities that go beyond
    simple prompt-and-respond patterns.
    """

    def __init__(self, model: str = "gpt-4.1-nano"):
        self.model = model

    async def think_step_by_step(self, problem: str, context: str = "") -> Dict:
        """Chain-of-thought decomposition of a problem.

        Returns structured reasoning with steps, assumptions, and conclusions.
        """
        response = await chat(
            messages=[
                {"role": "system", "content": """You are a rigorous analytical thinker.
Given a problem, produce structured chain-of-thought reasoning.

Return JSON:
{
  "understanding": "restate the problem in your own words to verify comprehension",
  "assumptions": ["list key assumptions"],
  "steps": [
    {"step": 1, "reasoning": "first logical step", "conclusion": "what this tells us"},
    {"step": 2, "reasoning": "next step building on step 1", "conclusion": "..."}
  ],
  "key_insight": "the most important realization from this reasoning",
  "confidence": 0.0-1.0,
  "unknowns": ["things we need to find out"]
}

Be rigorous. Flag where reasoning is uncertain. Return ONLY JSON."""},
                {"role": "user", "content": f"Problem: {problem}\n\nContext: {context}" if context else f"Problem: {problem}"},
            ],
            model=self.model,
            temperature=0.3,
        )

        return self._parse_json(response.content, {
            "understanding": problem,
            "assumptions": [],
            "steps": [{"step": 1, "reasoning": "Direct analysis", "conclusion": "Needs investigation"}],
            "key_insight": "Needs more analysis",
            "confidence": 0.3,
            "unknowns": ["Requires further research"],
        })

    async def generate_hypotheses(self, topic: str, observations: str = "", num: int = 3) -> List[Dict]:
        """Generate multiple competing hypotheses about a topic.

        This is key for AGI-like reasoning: considering multiple possibilities
        rather than jumping to a single conclusion.
        """
        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are a hypothesis generator.
Given a topic and observations, generate {num} distinct hypotheses that could explain
or address the situation. Hypotheses should be:
- Diverse (not minor variations of each other)
- Testable (suggest how to verify/falsify)
- Ranked by initial plausibility

Return JSON array:
[
  {{
    "id": 1,
    "hypothesis": "clear statement",
    "reasoning": "why this is plausible",
    "evidence_for": ["supporting observations"],
    "evidence_against": ["contradicting observations"],
    "how_to_test": "what would confirm or refute this",
    "plausibility": 0.0-1.0
  }}
]

Return ONLY the JSON array."""},
                {"role": "user", "content": f"Topic: {topic}\n\nObservations: {observations}" if observations else f"Topic: {topic}"},
            ],
            model=self.model,
            temperature=0.7,
        )

        result = self._parse_json(response.content, [
            {"id": 1, "hypothesis": f"Primary hypothesis about {topic}", "reasoning": "Needs investigation",
             "evidence_for": [], "evidence_against": [], "how_to_test": "Research needed", "plausibility": 0.5}
        ])
        return result if isinstance(result, list) else [result]

    async def evaluate_hypotheses(self, hypotheses: List[Dict], new_evidence: str) -> List[Dict]:
        """Update hypothesis plausibility based on new evidence.

        Bayesian-style updating: which hypotheses are strengthened or weakened?
        """
        response = await chat(
            messages=[
                {"role": "system", "content": """You are evaluating hypotheses against new evidence.
For each hypothesis, determine if the new evidence supports, refutes, or is neutral.
Update plausibility scores accordingly.

Return JSON array with updated hypotheses:
[
  {
    "id": <original id>,
    "hypothesis": "...",
    "updated_plausibility": 0.0-1.0,
    "evidence_impact": "supports|refutes|neutral",
    "reasoning": "why the evidence affects this hypothesis"
  }
]

Return ONLY the JSON array."""},
                {"role": "user", "content": f"Hypotheses:\n{json.dumps(hypotheses, indent=2)}\n\nNew Evidence:\n{new_evidence}"},
            ],
            model=self.model,
            temperature=0.2,
        )

        result = self._parse_json(response.content, hypotheses)
        return result if isinstance(result, list) else [result]

    async def causal_analysis(self, observations: str, domain: str = "") -> Dict:
        """Identify cause-effect relationships in observations.

        Goes beyond correlation to reason about causation.
        """
        response = await chat(
            messages=[
                {"role": "system", "content": """You are a causal reasoning expert.
Analyze the given observations to identify cause-effect relationships.
Distinguish between correlation and likely causation.

Return JSON:
{
  "causal_chains": [
    {
      "cause": "...",
      "effect": "...",
      "mechanism": "how the cause produces the effect",
      "confidence": 0.0-1.0,
      "confounders": ["possible alternative explanations"]
    }
  ],
  "correlations_not_causation": ["things that co-occur but may not be causally linked"],
  "missing_information": ["what we'd need to establish causation more firmly"],
  "key_insight": "the most important causal relationship identified"
}

Return ONLY JSON."""},
                {"role": "user", "content": f"Domain: {domain}\n\nObservations:\n{observations}" if domain else f"Observations:\n{observations}"},
            ],
            model=self.model,
            temperature=0.3,
        )

        return self._parse_json(response.content, {
            "causal_chains": [],
            "correlations_not_causation": [],
            "missing_information": ["Needs more data"],
            "key_insight": "Insufficient data for causal analysis",
        })

    async def plan_approach(self, goal: str, constraints: str = "", prior_attempts: str = "") -> Dict:
        """Generate a structured plan with alternatives and contingencies.

        Unlike simple task decomposition, this considers:
        - Multiple possible approaches
        - Risk assessment for each
        - Contingency plans
        - Resource requirements
        """
        context = ""
        if constraints:
            context += f"\nConstraints: {constraints}"
        if prior_attempts:
            context += f"\nPrior attempts and their outcomes: {prior_attempts}"

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are a strategic planner.
Create a structured plan to achieve a goal. Consider multiple approaches,
assess risks, and prepare contingencies.

Return JSON:
{{
  "goal_analysis": "deeper understanding of what success looks like",
  "approaches": [
    {{
      "name": "approach name",
      "steps": ["step 1", "step 2"],
      "strengths": ["why this might work"],
      "risks": ["what could go wrong"],
      "contingency": "what to do if this fails",
      "estimated_effectiveness": 0.0-1.0
    }}
  ],
  "recommended_approach": "name of the best approach",
  "recommendation_reasoning": "why this approach is best given constraints",
  "critical_unknowns": ["things that could change the recommended approach"],
  "success_criteria": ["how to know if we succeeded"]
}}

Return ONLY JSON."""},
                {"role": "user", "content": f"Goal: {goal}{context}"},
            ],
            model=self.model,
            temperature=0.4,
        )

        return self._parse_json(response.content, {
            "goal_analysis": goal,
            "approaches": [{"name": "Direct approach", "steps": ["Research", "Analyze", "Report"],
                           "strengths": ["Simple"], "risks": ["May miss nuance"],
                           "contingency": "Iterate", "estimated_effectiveness": 0.5}],
            "recommended_approach": "Direct approach",
            "recommendation_reasoning": "Simplest starting point",
            "critical_unknowns": [],
            "success_criteria": ["Goal addressed"],
        })

    async def cross_domain_transfer(self, problem: str, known_domains: List[str]) -> Dict:
        """Apply knowledge from other domains to a problem.

        This is transfer learning at the reasoning level — finding
        analogies and applicable patterns from other fields.
        """
        response = await chat(
            messages=[
                {"role": "system", "content": """You are an interdisciplinary thinker.
Given a problem and a list of domains you have knowledge about,
find useful analogies, patterns, and transferable insights.

Return JSON:
{
  "analogies": [
    {
      "from_domain": "...",
      "analogy": "how this domain relates to the problem",
      "transferable_insight": "what we can apply",
      "limitations": "where the analogy breaks down"
    }
  ],
  "novel_approaches": ["approaches suggested by cross-domain thinking"],
  "synthesis": "how combining insights from multiple domains suggests a path forward"
}

Return ONLY JSON."""},
                {"role": "user", "content": f"Problem: {problem}\n\nKnown domains: {', '.join(known_domains)}"},
            ],
            model=self.model,
            temperature=0.8,  # Higher temp for creative connections
        )

        return self._parse_json(response.content, {
            "analogies": [],
            "novel_approaches": [],
            "synthesis": "Needs more domain knowledge",
        })

    async def identify_assumptions(self, plan: str) -> List[Dict]:
        """Surface hidden assumptions in a plan or analysis.

        Critical for avoiding blind spots — a key AGI capability.
        """
        response = await chat(
            messages=[
                {"role": "system", "content": """You are an assumption auditor.
Identify hidden, implicit, or unstated assumptions in the given plan or analysis.
For each assumption, assess how critical it is and what happens if it's wrong.

Return JSON array:
[
  {
    "assumption": "what is being assumed",
    "why_hidden": "why this assumption is easy to miss",
    "criticality": "high|medium|low",
    "if_wrong": "what happens if this assumption is false",
    "how_to_verify": "how to check this assumption"
  }
]

Return ONLY the JSON array."""},
                {"role": "user", "content": plan},
            ],
            model=self.model,
            temperature=0.4,
        )

        result = self._parse_json(response.content, [])
        return result if isinstance(result, list) else []

    def _parse_json(self, text: str, fallback):
        """Parse JSON from LLM response, with code fence stripping."""
        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            return json.loads(text)
        except Exception:
            return fallback
