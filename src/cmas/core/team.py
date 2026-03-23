"""Team — a dynamic group of sub-agents managed by a Team Lead agent.

A Team is the primary unit of work in CMAS. Think of it like a department:
- The Team has a name, mission, and allocated resources
- The Team Lead (agent) plans how to accomplish the mission
- The Team Lead spawns sub-agents (employees) as needed
- Sub-agents do the actual work and report back to the Team Lead
- The Team has its own communication hub and knowledge store
- Teams communicate with other Teams and the Composer via the central Hub

Nothing about a Team is hardcoded — the Composer creates teams dynamically
based on what the goal requires. A "build a website" goal gets different
teams than a "research quantum computing" goal.
"""
from __future__ import annotations

import asyncio
import json
import uuid
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable

from .llm import chat, chat_with_tools
from .tools import TOOL_DEFS, TOOL_HANDLERS
from .state import Hub, Task, TaskStatus
from .memory import Memory
from .reasoning import Reasoner
from .agent import Agent
from .protocols import (
    get_standing_orders,
    build_bootstrap_context,
    get_depth_policy,
    get_tools_for_profile,
)


# ── Team Data Model ─────────────────────────────────────────────────

@dataclass
class TeamSpec:
    """Specification for a team, created by the Composer."""
    id: str
    name: str                           # e.g. "Design Team", "Legal Research"
    mission: str                        # What this team must accomplish
    responsibilities: List[str]         # Specific responsibilities
    tools: List[str]                    # Tools this team is allowed to use
    frameworks: List[str]               # Which frameworks to apply
    resources: List[str]                # Any specific resources (URLs, docs, etc.)
    budget: int = 5                     # Max sub-agents this team can spawn
    depends_on: List[str] = field(default_factory=list)  # Other team IDs this depends on
    priority: int = 2                   # 0=critical, 1=high, 2=normal, 3=low


@dataclass
class SubAgentRecord:
    """Tracks a sub-agent within a team."""
    id: str
    name: str
    role: str
    status: str = "idle"                # idle, working, done, failed
    task_description: str = ""
    result: str = ""
    created_at: float = field(default_factory=time.time)


class Team:
    """A dynamic team of sub-agents led by a Team Lead agent.

    The Team Lead:
    - Receives a mission from the Composer
    - Analyzes what sub-agents (employees) are needed
    - Spawns sub-agents with specific roles
    - Coordinates their work
    - Aggregates results
    - Reports back to the Composer

    Each team gets:
    - Its own workspace directory
    - Its own section in the Hub for internal communication
    - Access to specified tools and frameworks
    - A budget for how many sub-agents it can spawn
    """

    def __init__(
        self,
        spec: TeamSpec,
        hub: Hub,
        project_dir: Path,
        model: str = "gpt-4.1-nano",
        gateway: Any = None,
        memory: Optional[Memory] = None,
        progress_callback: Optional[Callable] = None,
    ):
        self.spec = spec
        self.hub = hub
        self.project_dir = project_dir
        self.model = model
        self.gateway = gateway
        self.memory = memory
        self.progress_callback = progress_callback

        # Team workspace
        self.workspace = project_dir / "teams" / spec.id
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Internal state
        self.sub_agents: Dict[str, SubAgentRecord] = {}
        self.lead_agent: Optional[Agent] = None
        self.status: str = "idle"  # idle, planning, executing, done, failed
        self.result: str = ""
        self.reasoner = Reasoner(model=model)

        self._log(f"Team '{spec.name}' created | Mission: {spec.mission[:80]}")

    def _log(self, msg: str):
        line = f"[Team:{self.spec.name}] {msg}"
        print(line)

    async def _emit(self, text: str):
        if self.progress_callback:
            try:
                await self.progress_callback(text, f"Team:{self.spec.name}")
            except Exception:
                pass

    # ── Phase 1: Plan — Team Lead analyzes mission and plans staff ───

    async def plan(self) -> Dict:
        """Team Lead analyzes the mission and decides what sub-agents to hire."""
        self.status = "planning"
        self._log("Planning team composition...")
        await self._emit(f"Team '{self.spec.name}' planning sub-agent composition...")

        # Gather context from dependencies (other teams' results)
        dep_context = ""
        if self.spec.depends_on:
            dep_context = "\n\nINPUT FROM OTHER TEAMS:\n"
            for dep_id in self.spec.depends_on:
                msgs = self.hub.get_messages(f"team:{self.spec.id}")
                for m in msgs:
                    if m.get("sender", "").startswith(f"team:{dep_id}"):
                        dep_context += f"  [{m['sender']}]: {m['content'][:500]}\n"

        # Get framework guidance if specified
        framework_context = ""
        if self.spec.frameworks:
            from .frameworks import apply_framework
            for fw_id in self.spec.frameworks[:2]:
                framework_context += f"\n{apply_framework(fw_id, self.spec.mission)}\n"

        team_lead_orders = get_standing_orders("team_lead")

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are a Team Lead managing the "{self.spec.name}" team.

{team_lead_orders}

YOUR MISSION: {self.spec.mission}

YOUR RESPONSIBILITIES:
{chr(10).join(f'- {r}' for r in self.spec.responsibilities)}

AVAILABLE TOOLS: {', '.join(self.spec.tools)}
AVAILABLE FRAMEWORKS: {', '.join(self.spec.frameworks) if self.spec.frameworks else 'none specified'}
MAX SUB-AGENTS YOU CAN HIRE: {self.spec.budget}
{dep_context}
{framework_context}

You must decide:
1. How many sub-agents to hire (min 1, max {self.spec.budget})
2. What role/specialty each sub-agent should have
3. What specific task each sub-agent should do
4. What order they should work in (dependencies)

Think like a real team manager. You have a mission. You need to hire the right people.
Don't hire more than you need. Each sub-agent is a specialist at one thing.

Return JSON ONLY:
{{
  "strategy": "Brief description of your approach",
  "sub_agents": [
    {{
      "id": "unique_short_id",
      "role": "Specific role title (e.g., 'UX Researcher', 'Backend Developer', 'Color Theory Analyst')",
      "task": "Detailed description of what this sub-agent must do. Be VERY specific.",
      "depends_on": ["ids of sub-agents whose output this one needs"],
      "tools_needed": ["which tools this sub-agent needs from your available set"]
    }}
  ]
}}"""},
                {"role": "user", "content": f"Plan how to accomplish this mission:\n\n{self.spec.mission}"},
            ],
            model=self.model,
            temperature=0.4,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            plan = json.loads(text)
        except Exception as e:
            self._log(f"Plan parse failed: {e}, using fallback")
            plan = {
                "strategy": "Direct execution",
                "sub_agents": [{
                    "id": "worker_1",
                    "role": "General Specialist",
                    "task": self.spec.mission,
                    "depends_on": [],
                    "tools_needed": self.spec.tools[:3],
                }]
            }

        self._log(f"Strategy: {plan.get('strategy', 'N/A')[:80]}")
        self._log(f"Hiring {len(plan.get('sub_agents', []))} sub-agents")
        self.hub.remember(f"team:{self.spec.id}:plan", json.dumps(plan, indent=2))

        return plan

    # ── Phase 2: Execute — Spawn sub-agents and run them ────────────

    async def execute(self, plan: Dict) -> str:
        """Spawn sub-agents according to the plan and coordinate their work."""
        self.status = "executing"
        sub_agent_specs = plan.get("sub_agents", [])

        if not sub_agent_specs:
            self.status = "failed"
            return "No sub-agents planned. Cannot execute."

        # Build dependency graph
        deps: Dict[str, List[str]] = {}
        for sa in sub_agent_specs:
            deps[sa["id"]] = sa.get("depends_on", [])

        # Create tasks in the Hub for each sub-agent
        tasks: Dict[str, Task] = {}
        agents: Dict[str, Agent] = {}

        for sa in sub_agent_specs:
            task_id = f"{self.spec.id}_{sa['id']}"
            task = Task(
                id=task_id,
                description=sa["task"],
                status=TaskStatus.PENDING,
                project_id=self.hub.recall("current_project_id") or "",
                parent_task_id=self.spec.id,
            )
            self.hub.add_task(task)
            tasks[sa["id"]] = task

            # Create the sub-agent with full bootstrap context
            agent_name = f"{self.spec.name}_{sa['role'].replace(' ', '_')[:25]}_{sa['id']}"
            bootstrap = build_bootstrap_context(
                agent_name=agent_name,
                role=sa["role"],
                mission=sa["task"],
                team_name=self.spec.name,
                depth=2,  # Sub-agents are depth 2
                tools=sa.get("tools_needed", self.spec.tools),
                frameworks=self.spec.frameworks,
                standing_orders=get_standing_orders("sub_agent"),
            )
            agent = Agent(
                name=agent_name,
                role=bootstrap,
                hub=self.hub,
                workspace=self.workspace / sa["id"],
                model=self.model,
                gateway=self.gateway,
                memory=self.memory,
                depth=2,  # Sub-agents are depth 2 (can delegate to depth 3-5)
                progress_callback=self.progress_callback,
            )

            if self.gateway:
                self.gateway.register_agent(agent_name, agent)

            agents[sa["id"]] = agent
            self.sub_agents[sa["id"]] = SubAgentRecord(
                id=sa["id"], name=agent_name, role=sa["role"],
                task_description=sa["task"],
            )

            self._log(f"  Hired: {agent_name} ({sa['role']})")

        await self._emit(
            f"Team '{self.spec.name}' has {len(agents)} sub-agents. Executing..."
        )

        # Execute in dependency order
        done_ids: set = set()
        results: Dict[str, str] = {}
        max_rounds = 10

        for round_num in range(max_rounds):
            # Find sub-agents whose dependencies are satisfied
            ready = [
                sa_id for sa_id, sa_deps in deps.items()
                if sa_id not in done_ids
                and all(d in done_ids for d in sa_deps)
            ]

            if not ready:
                if done_ids == set(deps.keys()):
                    break  # All done
                # Deadlock detection
                remaining = set(deps.keys()) - done_ids
                self._log(f"  WARNING: Deadlock detected. Remaining: {remaining}")
                # Force-run remaining
                ready = list(remaining)

            self._log(f"  Round {round_num + 1}: Running {len(ready)} sub-agents: {ready}")

            # Run ready sub-agents concurrently
            sem = asyncio.Semaphore(min(len(ready), self.spec.budget))

            async def run_sub_agent(sa_id: str):
                async with sem:
                    agent = agents[sa_id]
                    task = tasks[sa_id]

                    # Inject context from completed dependencies
                    dep_results = ""
                    for dep_id in deps.get(sa_id, []):
                        if dep_id in results:
                            dep_results += f"\n\n--- FROM {dep_id} ---\n{results[dep_id][:1000]}"

                    if dep_results:
                        enriched_task = Task(
                            id=task.id,
                            description=task.description + dep_results,
                            status=task.status,
                            project_id=task.project_id,
                            parent_task_id=task.parent_task_id,
                        )
                        result = await agent.execute(enriched_task)
                    else:
                        result = await agent.execute(task)

                    self.sub_agents[sa_id].status = "done"
                    self.sub_agents[sa_id].result = result[:2000]
                    results[sa_id] = result
                    done_ids.add(sa_id)

                    self._log(f"  Sub-agent {sa_id} complete ({len(result)} chars)")
                    return result

            await asyncio.gather(*(run_sub_agent(sa_id) for sa_id in ready))

        # ── Phase 3: Aggregate — Team Lead synthesizes results ───────

        self._log("Aggregating sub-agent results...")
        all_results = "\n\n".join(
            f"## [{sa_id}] {self.sub_agents[sa_id].role}\n{results.get(sa_id, 'No result')[:1500]}"
            for sa_id in results
        )

        synthesis = await chat(
            messages=[
                {"role": "system", "content": f"""You are the Team Lead of "{self.spec.name}".
Your mission was: {self.spec.mission}

Your sub-agents have completed their work. Synthesize their results into a
coherent team deliverable. Be comprehensive but focused on actionable output.
Include key findings, recommendations, and any deliverables produced."""},
                {"role": "user", "content": f"SUB-AGENT RESULTS:\n\n{all_results}"},
            ],
            model=self.model,
        )

        self.result = synthesis.content if hasattr(synthesis, 'content') else str(synthesis)
        self.status = "done"

        # Save team deliverable
        deliverable_path = self.workspace / "team_deliverable.md"
        deliverable_path.write_text(
            f"# {self.spec.name} — Team Deliverable\n\n"
            f"## Mission\n{self.spec.mission}\n\n"
            f"## Strategy\n{plan.get('strategy', 'N/A')}\n\n"
            f"## Result\n{self.result}"
        )

        # Report back to Composer via Hub
        self.hub.send_message(
            sender=f"team:{self.spec.id}",
            recipient="composer",
            content=self.result[:2000],
        )

        # Also broadcast to other teams that might depend on us
        self.hub.send_message(
            sender=f"team:{self.spec.id}",
            recipient="all_teams",
            content=f"[{self.spec.name}] COMPLETED. Summary: {self.result[:500]}",
        )

        self._log(f"DONE — Deliverable saved to {deliverable_path}")
        await self._emit(f"Team '{self.spec.name}' delivered results.")

        return self.result

    # ── Full lifecycle: Plan + Execute ──────────────────────────────

    async def run(self) -> str:
        """Full team lifecycle: plan sub-agents, execute, aggregate, report."""
        try:
            plan = await self.plan()
            result = await self.execute(plan)
            return result
        except Exception as e:
            self.status = "failed"
            self.result = f"Team failed: {e}"
            self._log(f"FAILED: {e}")
            self.hub.send_message(
                sender=f"team:{self.spec.id}",
                recipient="composer",
                content=f"TEAM FAILED: {e}",
            )
            return self.result

    def get_status(self) -> Dict:
        """Get team status summary."""
        return {
            "id": self.spec.id,
            "name": self.spec.name,
            "status": self.status,
            "mission": self.spec.mission[:100],
            "sub_agents": [
                {
                    "id": sa.id,
                    "name": sa.name,
                    "role": sa.role,
                    "status": sa.status,
                }
                for sa in self.sub_agents.values()
            ],
            "result_preview": self.result[:200] if self.result else "",
        }
