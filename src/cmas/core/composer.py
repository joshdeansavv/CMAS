"""Composer — the CEO agent that orchestrates everything.

The Composer is the ONLY hardcoded agent in the system. Everything else
is dynamically created based on what the goal requires.

When a user sends a prompt, the Composer:
1. ANALYZES the goal deeply — what's really being asked?
2. DESIGNS the org chart — what teams are needed?
3. ALLOCATES resources — what tools, frameworks, databases per team?
4. CREATES teams — each with a mission, budget, and permissions
5. MONITORS progress — are teams delivering? Do we need to pivot?
6. SYNTHESIZES — combines all team outputs into the final deliverable

The Composer thinks like a CEO:
- "I need a Design team, a Development team, and a Marketing team"
- "Design team gets 3 sub-agents and access to web_search + apply_framework"
- "Development team depends on Design team's output"
- "Marketing team should use NLP framework for messaging strategy"

Nothing is hardcoded except this Composer. Teams are created dynamically.
Sub-agents within teams are created dynamically by Team Leads.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable

from .llm import chat
from .tools import TOOL_DEFS
from .state import Hub, Task, TaskStatus
from .gateway import Gateway
from .memory import Memory
from .evaluation import Evaluator
from .reasoning import Reasoner
from .metacognition import MetaCognition
from .brain import (
    NeuralPathways,
    DopamineSystem,
    PriorityDetector,
    Consolidator,
    DefaultModeNetwork,
)
from .team import Team, TeamSpec
from .protocols import (
    TOOL_PROFILES,
    get_standing_orders,
    get_depth_policy,
    VERIFICATION_PROMPT,
)


# All tools an agent could possibly need — Composer allocates subsets
ALL_AVAILABLE_TOOLS = [
    "web_search", "write_file", "read_file", "list_files",
    "run_python", "run_command", "send_message", "delegate_task",
    "apply_framework",
]

# All frameworks available for allocation
ALL_AVAILABLE_FRAMEWORKS = [
    "cbt", "act", "dbt", "stages_of_change", "goal_setting",
    "strategic", "behavioral", "financial", "conflict", "nlp",
]


class Composer:
    """The CEO of the multi-agent system.

    The only hardcoded agent. Everything else is dynamically created.

    Workflow:
    1. Receive user prompt
    2. Deep analysis: what is really needed?
    3. Design organizational structure (teams)
    4. Allocate resources per team
    5. Launch teams in dependency order
    6. Monitor and adapt
    7. Synthesize final deliverable from all team outputs
    """

    def __init__(
        self,
        project_dir: Path,
        model: str = "gpt-4.1-nano",
        team_model: str = "gpt-4.1-nano",
        max_teams: int = 8,
        max_agents_per_team: int = 5,
        hub: Optional[Hub] = None,
        gateway: Optional[Gateway] = None,
        memory: Optional[Memory] = None,
        project_id: str = "",
        progress_callback: Optional[Callable] = None,
    ):
        self.project_dir = project_dir
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.team_model = team_model
        self.max_teams = max_teams
        self.max_agents_per_team = max_agents_per_team
        self.project_id = project_id
        self.progress_callback = progress_callback

        # Core infrastructure
        self.hub = hub or Hub(project_dir)
        self.gateway = gateway or Gateway(
            hub=self.hub, project_dir=project_dir,
            rate_limit_calls=60, rate_limit_window=60.0,
            max_recursion_depth=15,
        )
        self.memory = memory or Memory()

        # Cognitive modules
        self.reasoner = Reasoner(model=model)
        self.evaluator = Evaluator(hub=self.hub, model=model)
        self.metacognition = MetaCognition(hub=self.hub, memory=self.memory, model=model)

        # Brain modules
        brain_db = str(project_dir / "brain.db")
        self.pathways = NeuralPathways(db_path=brain_db)
        self.dopamine = DopamineSystem(pathways=self.pathways, memory=self.memory)
        self.priority = PriorityDetector()
        self.consolidator = Consolidator(memory=self.memory, model=model)
        self.dmn = DefaultModeNetwork(memory=self.memory, model=model)

        # Team tracking
        self.teams: Dict[str, Team] = {}
        self.team_specs: Dict[str, TeamSpec] = {}
        self.team_deps: Dict[str, List[str]] = {}

        self._print("Composer (CEO) initialized — ready to build organizations")

    def _print(self, msg: str):
        print(f"[Composer] {msg}")

    async def _emit(self, text: str):
        if self.progress_callback:
            try:
                await self.progress_callback(text, "Composer")
            except Exception:
                pass

    # ── Phase 1: ANALYZE — Deep understanding of what's needed ──────

    async def _analyze_goal(self, goal: str) -> Dict:
        """CEO-level analysis: what does this goal REALLY require?"""
        self._print("Analyzing goal at CEO level...")
        await self._emit("Analyzing goal — understanding what's really needed...")

        # Pull prior knowledge
        prior = self.memory.search(goal[:50], limit=5)
        lessons = self.memory.get_lessons(applies_to=goal[:50], limit=3)

        prior_text = ""
        if prior:
            prior_text = "\nPRIOR KNOWLEDGE:\n" + self.memory.format_for_context(prior, max_chars=1000)
        if lessons:
            prior_text += "\nLESSONS LEARNED:\n" + "\n".join(
                f"  - {l['what_learned'][:150]}" for l in lessons
            )

        # MCTS reasoning for strategic planning
        self._print("Running MCTS strategic analysis...")
        mcts = await self.reasoner.mcts_search(goal=goal, context=prior_text)

        composer_orders = get_standing_orders("composer")

        # CEO-level decomposition
        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are the CEO/Composer of an AI organization.
A user has given you a goal. You must analyze it at the HIGHEST strategic level.

{composer_orders}

Think like a real CEO planning a company initiative:
- What departments/teams are needed?
- What's the real scope of this work?
- What are the dependencies between workstreams?
- What tools, resources, and expertise does each team need?
- What could go wrong? What constraints exist?
- What order should work happen in?

MCTS ANALYSIS:
{json.dumps(mcts.get('optimal_path', {}), indent=2)}
{prior_text}

AVAILABLE TOOLS that teams can use:
{json.dumps(ALL_AVAILABLE_TOOLS)}

AVAILABLE FRAMEWORKS (evidence-based coaching/strategy/behavioral):
{json.dumps(ALL_AVAILABLE_FRAMEWORKS)}

Return a JSON analysis:
{{
  "true_objective": "What this goal REALLY requires (not just the surface ask)",
  "scope": "small|medium|large|enterprise",
  "key_challenges": ["challenge 1", "challenge 2"],
  "required_capabilities": ["web development", "market research", "legal analysis", etc.],
  "recommended_team_count": 2-{self.max_teams},
  "strategic_approach": "Brief description of overall strategy",
  "missing_dependencies": ["any Python packages, APIs, or tools needed"],
  "constraints": ["time, budget, technical, or other constraints"]
}}

Return ONLY JSON."""},
                {"role": "user", "content": goal},
            ],
            model=self.model,
            temperature=0.3,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            analysis = json.loads(text)
        except Exception as e:
            self._print(f"Analysis parse failed: {e}")
            analysis = {
                "true_objective": goal,
                "scope": "medium",
                "key_challenges": [],
                "required_capabilities": ["research", "analysis"],
                "recommended_team_count": 2,
                "strategic_approach": "Direct approach with research and analysis teams",
                "missing_dependencies": [],
                "constraints": [],
            }

        self._print(f"  True objective: {analysis.get('true_objective', 'N/A')[:80]}")
        self._print(f"  Scope: {analysis.get('scope', 'N/A')}")
        self._print(f"  Teams needed: {analysis.get('recommended_team_count', 'N/A')}")
        self._print(f"  Strategy: {analysis.get('strategic_approach', 'N/A')[:80]}")

        self.hub.remember("composer:analysis", json.dumps(analysis, indent=2))
        return analysis

    # ── Phase 2: DESIGN — Create the organizational structure ───────

    async def _design_organization(self, goal: str, analysis: Dict) -> List[TeamSpec]:
        """Design the team structure: who does what, with what resources."""
        self._print("Designing organizational structure...")
        await self._emit("Designing teams and allocating resources...")

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are the CEO designing an organization to accomplish a goal.

GOAL: {goal}

ANALYSIS:
{json.dumps(analysis, indent=2)}

Design teams to accomplish this. Each team is led by a Team Manager agent
who will hire their own sub-agents (employees).

Rules:
- Each team has ONE clear mission. No overlap.
- Teams can depend on other teams' output.
- Allocate specific tools and frameworks to each team based on what they need.
- Don't over-allocate — teams should only get tools they'll actually use.
- Max {self.max_teams} teams. Usually 2-5 is enough.
- Each team gets a budget of 1-{self.max_agents_per_team} sub-agents.
- Think about communication: which teams need to talk to each other?

AVAILABLE TOOLS: {json.dumps(ALL_AVAILABLE_TOOLS)}
AVAILABLE FRAMEWORKS: {json.dumps(ALL_AVAILABLE_FRAMEWORKS)}

TOOL PROFILES (shorthand — you can assign a profile instead of listing individual tools):
{json.dumps({k: sorted(v) for k, v in TOOL_PROFILES.items()}, indent=2)}

Consider adding an Operations/HR team if >3 teams to monitor resources.

Return JSON array of teams:
[
  {{
    "id": "short_unique_id",
    "name": "Human-readable team name",
    "mission": "Detailed mission statement. What must this team deliver?",
    "responsibilities": ["Specific responsibility 1", "Specific responsibility 2"],
    "tools": ["tool1", "tool2"],
    "frameworks": ["framework_id1"],
    "resources": ["Any specific URLs, docs, or resources this team should reference"],
    "budget": 3,
    "depends_on": ["ids of teams whose output this team needs"],
    "priority": 2
  }}
]

Order teams by execution priority. Independent teams run in parallel.
Return ONLY the JSON array."""},
                {"role": "user", "content": f"Design the organization for: {goal}"},
            ],
            model=self.model,
            temperature=0.4,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            teams_data = json.loads(text)
        except Exception as e:
            self._print(f"Design parse failed: {e}, using fallback")
            teams_data = [
                {
                    "id": "research",
                    "name": "Research Team",
                    "mission": f"Research everything needed for: {goal}",
                    "responsibilities": ["Web research", "Data gathering", "Source verification"],
                    "tools": ["web_search", "write_file", "read_file", "apply_framework"],
                    "frameworks": ["strategic"],
                    "resources": [],
                    "budget": 3,
                    "depends_on": [],
                    "priority": 1,
                },
                {
                    "id": "execution",
                    "name": "Execution Team",
                    "mission": f"Execute the work for: {goal}",
                    "responsibilities": ["Implementation", "Delivery"],
                    "tools": ALL_AVAILABLE_TOOLS.copy(),
                    "frameworks": ["goal_setting"],
                    "resources": [],
                    "budget": 3,
                    "depends_on": ["research"],
                    "priority": 2,
                },
            ]

        # Convert to TeamSpec objects
        specs = []
        for td in teams_data:
            spec = TeamSpec(
                id=td["id"],
                name=td["name"],
                mission=td["mission"],
                responsibilities=td.get("responsibilities", []),
                tools=td.get("tools", ["web_search", "write_file", "read_file"]),
                frameworks=td.get("frameworks", []),
                resources=td.get("resources", []),
                budget=min(td.get("budget", 3), self.max_agents_per_team),
                depends_on=td.get("depends_on", []),
                priority=td.get("priority", 2),
            )
            specs.append(spec)
            self._print(f"  Team: {spec.name} | Budget: {spec.budget} | Deps: {spec.depends_on}")

        self.hub.remember("composer:org_design", json.dumps(teams_data, indent=2))
        await self._emit(f"Organization designed: {len(specs)} teams")

        return specs

    # ── Phase 3: LAUNCH — Create and run teams ──────────────────────

    async def _launch_teams(self, specs: List[TeamSpec]) -> Dict[str, str]:
        """Create Team objects and launch them in dependency order."""
        self._print(f"Launching {len(specs)} teams...")
        await self._emit(f"Launching {len(specs)} teams...")

        # Build dependency graph
        for spec in specs:
            self.team_specs[spec.id] = spec
            self.team_deps[spec.id] = spec.depends_on

        # Create all Team objects
        for spec in specs:
            team = Team(
                spec=spec,
                hub=self.hub,
                project_dir=self.project_dir,
                model=self.team_model,
                gateway=self.gateway,
                memory=self.memory,
                progress_callback=self.progress_callback,
            )
            self.teams[spec.id] = team

        # Execute in dependency waves
        done_teams: set = set()
        team_results: Dict[str, str] = {}
        max_waves = 10

        for wave in range(max_waves):
            # Find teams whose dependencies are satisfied
            ready = [
                tid for tid, deps in self.team_deps.items()
                if tid not in done_teams
                and all(d in done_teams for d in deps)
            ]

            if not ready:
                if done_teams == set(self.team_deps.keys()):
                    break
                remaining = set(self.team_deps.keys()) - done_teams
                self._print(f"  WARNING: Team deadlock. Forcing: {remaining}")
                ready = list(remaining)

            self._print(f"\n  Wave {wave + 1}: Launching teams: {ready}")
            await self._emit(f"Wave {wave + 1}: Launching {len(ready)} teams: {', '.join(ready)}")

            # Run ready teams concurrently
            async def run_team(team_id: str):
                team = self.teams[team_id]
                try:
                    result = await team.run()
                    team_results[team_id] = result
                    done_teams.add(team_id)
                    self._print(f"  Team '{team.spec.name}' DONE ({len(result)} chars)")
                except Exception as e:
                    team_results[team_id] = f"TEAM FAILED: {e}"
                    done_teams.add(team_id)
                    self._print(f"  Team '{team.spec.name}' FAILED: {e}")

            await asyncio.gather(*(run_team(tid) for tid in ready))

        return team_results

    # ── Phase 4: EVALUATE — Score team outputs ──────────────────────

    async def _evaluate_teams(self, goal: str, team_results: Dict[str, str]) -> Dict:
        """Evaluate each team's output and decide if more work is needed."""
        self._print("Evaluating team deliverables...")
        await self._emit("Evaluating team deliverables...")

        results_summary = "\n\n".join(
            f"## Team: {self.team_specs[tid].name}\n"
            f"Mission: {self.team_specs[tid].mission[:200]}\n"
            f"Result:\n{result[:1500]}"
            for tid, result in team_results.items()
        )

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are the CEO reviewing your teams' work.

ORIGINAL GOAL: {goal}

Evaluate whether the combined team outputs fully address the goal.
Score each team's contribution and identify any gaps.

Return JSON:
{{
  "overall_score": 0-10,
  "goal_addressed": true/false,
  "team_scores": {{
    "team_id": {{
      "score": 0-10,
      "strengths": "what they did well",
      "gaps": "what's missing"
    }}
  }},
  "remaining_gaps": ["gap 1", "gap 2"],
  "needs_additional_teams": true/false,
  "additional_team_suggestions": [
    {{
      "name": "Suggested Team Name",
      "mission": "What this new team should do",
      "why": "Why it's needed"
    }}
  ]
}}

Return ONLY JSON."""},
                {"role": "user", "content": f"TEAM RESULTS:\n\n{results_summary}"},
            ],
            model=self.model,
            temperature=0.3,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            evaluation = json.loads(text)
        except Exception:
            evaluation = {"overall_score": 7, "goal_addressed": True, "remaining_gaps": []}

        self._print(f"  Overall score: {evaluation.get('overall_score', 'N/A')}/10")
        self._print(f"  Goal addressed: {evaluation.get('goal_addressed', 'unknown')}")

        gaps = evaluation.get("remaining_gaps", [])
        if gaps:
            self._print(f"  Remaining gaps: {', '.join(gaps[:3])}")

        return evaluation

    # ── Phase 5: SYNTHESIZE — Final deliverable ─────────────────────

    async def _synthesize(self, goal: str, team_results: Dict[str, str]) -> str:
        """Combine all team outputs into the final deliverable."""
        self._print("Synthesizing final deliverable from all teams...")
        await self._emit("Synthesizing final deliverable from all teams...")

        all_outputs = "\n\n---\n\n".join(
            f"# {self.team_specs[tid].name}\n"
            f"**Mission:** {self.team_specs[tid].mission}\n\n"
            f"{result}"
            for tid, result in team_results.items()
        )

        current_date = datetime.now().strftime("%B %d, %Y")

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are the CEO producing the final deliverable.

Multiple teams worked on this goal. Synthesize ALL their work into one
comprehensive, well-structured final output.

Today's date: {current_date}

Rules:
- Include ALL key findings, deliverables, and recommendations from every team
- Structure with clear sections and headers
- Be actionable — the user should know exactly what to do next
- Only cite sources that appear in the team outputs
- End with a clear "Next Steps" section

This is the final product. Make it excellent."""},
                {"role": "user", "content": f"GOAL: {goal}\n\nALL TEAM OUTPUTS:\n\n{all_outputs}"},
            ],
            model=self.model,
        )

        result = response.content if hasattr(response, 'content') else str(response)

        # Save final report
        report_path = self.project_dir / "final_report.md"
        report_path.write_text(result)
        self._print(f"Final report saved: {report_path}")

        # Save org chart
        org_chart = {
            "goal": goal,
            "teams": {
                tid: {
                    "name": team.spec.name,
                    "mission": team.spec.mission,
                    "status": team.status,
                    "sub_agents": [
                        {"name": sa.name, "role": sa.role, "status": sa.status}
                        for sa in team.sub_agents.values()
                    ],
                }
                for tid, team in self.teams.items()
            },
        }
        org_path = self.project_dir / "org_chart.json"
        org_path.write_text(json.dumps(org_chart, indent=2))

        return result

    # ── Main Entry Point ────────────────────────────────────────────

    async def run(self, goal: str) -> str:
        """Full Composer lifecycle: Analyze → Design → Launch → Evaluate → Synthesize.

        This is the single entry point. A user sends a prompt, and the
        Composer builds an entire organization to accomplish it.
        """
        start = time.time()
        self._print(f"{'='*60}")
        self._print(f"GOAL: {goal}")
        self._print(f"{'='*60}\n")

        self.hub.remember("current_project_id", self.project_id)

        # ── Phase 1: ANALYZE ────────────────────────────────────
        analysis = await self._analyze_goal(goal)

        # ── Phase 2: DESIGN ─────────────────────────────────────
        specs = await self._design_organization(goal, analysis)

        # ── Phase 3: LAUNCH ─────────────────────────────────────
        team_results = await self._launch_teams(specs)

        # ── Phase 4: EVALUATE ───────────────────────────────────
        evaluation = await self._evaluate_teams(goal, team_results)

        # If gaps remain and score is low, run additional teams
        if (not evaluation.get("goal_addressed", True)
                and evaluation.get("overall_score", 10) < 6
                and evaluation.get("additional_team_suggestions")):

            self._print("Gaps detected — spinning up additional teams...")
            await self._emit("Gaps detected — creating additional teams to fill gaps...")

            additional_specs = []
            for suggestion in evaluation["additional_team_suggestions"][:2]:
                spec = TeamSpec(
                    id=f"gap_{len(self.teams) + 1}",
                    name=suggestion.get("name", "Gap Team"),
                    mission=suggestion.get("mission", "Address remaining gaps"),
                    responsibilities=[suggestion.get("why", "Fill identified gaps")],
                    tools=ALL_AVAILABLE_TOOLS.copy(),
                    frameworks=["strategic", "goal_setting"],
                    resources=[],
                    budget=3,
                    depends_on=[],
                    priority=1,
                )
                additional_specs.append(spec)

            if additional_specs:
                gap_results = await self._launch_teams(additional_specs)
                team_results.update(gap_results)

        # ── Phase 5: SYNTHESIZE ─────────────────────────────────
        final = await self._synthesize(goal, team_results)

        # ── LEARN — Store insights for future runs ──────────────
        self._print("Running post-mission learning cycle...")

        # Memory consolidation
        done_tasks = self.hub.get_tasks(status="done")
        if done_tasks:
            consolidation_data = [
                {
                    "agent": t.assigned_to or "unknown",
                    "description": t.description[:200],
                    "score": 7,
                    "approach": t.result[:150] if t.result else "",
                }
                for t in done_tasks[:20]
            ]
            try:
                consolidation = await self.consolidator.consolidate(consolidation_data)
                self._print(f"  Schemas: {consolidation['schemas_extracted']}, "
                            f"Hypotheses: {consolidation['hypotheses_generated']}")
            except Exception:
                pass

        # Store lesson
        team_names = [s.name for s in specs]
        self.memory.store_lesson(
            what_happened=f"Composer ran goal: {goal[:100]} with teams: {', '.join(team_names)}",
            what_learned=(
                f"Used {len(specs)} teams. Score: {evaluation.get('overall_score', 'N/A')}/10. "
                f"Strategy: {analysis.get('strategic_approach', 'N/A')[:100]}"
            ),
            applies_to=goal[:50],
            project=str(self.project_dir.name),
        )

        # Store synthesis in long-term memory
        self.memory.store(
            topic=goal[:100],
            content=final[:1000],
            category="synthesis",
            source="composer",
            project=str(self.project_dir.name),
            confidence=0.8,
        )

        # Brain maintenance
        self.pathways.decay_all()
        self.pathways.homeostatic_scale()

        # DMN background creativity
        try:
            dmn_results = await self.dmn.idle_cycle()
            if dmn_results.get("recombinations"):
                self._print(f"  Creative insights: {len(dmn_results['recombinations'])}")
        except Exception:
            pass

        elapsed = time.time() - start
        total_agents = sum(len(t.sub_agents) for t in self.teams.values())
        self._print(f"\n{'='*60}")
        self._print(f"COMPLETE — {len(self.teams)} teams, {total_agents} sub-agents, {elapsed:.0f}s")
        self._print(f"{'='*60}")

        return final

    # ── Status & Monitoring ─────────────────────────────────────────

    def get_status(self) -> Dict:
        """Get full organizational status."""
        return {
            "teams": {
                tid: team.get_status()
                for tid, team in self.teams.items()
            },
            "total_teams": len(self.teams),
            "total_sub_agents": sum(len(t.sub_agents) for t in self.teams.values()),
            "active_teams": sum(1 for t in self.teams.values() if t.status == "executing"),
            "done_teams": sum(1 for t in self.teams.values() if t.status == "done"),
            "failed_teams": sum(1 for t in self.teams.values() if t.status == "failed"),
        }
