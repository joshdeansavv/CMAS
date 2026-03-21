"""LLM-powered orchestrator with reasoning, metacognition, evaluation, and memory."""
from __future__ import annotations

import asyncio
import json
import os
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from .llm import chat, chat_with_tools
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
from .agent import (
    Agent,
    create_research_agent,
    create_analyst_agent,
    create_writer_agent,
    create_specialist_agent,
)


class Orchestrator:
    """The cognitive core of the multi-agent system.

    Implements a full cognitive architecture:
    - PERCEIVE: Understand the goal and context (memory + reasoning)
    - PLAN: Decompose into tasks with reasoning about approach (reasoning engine)
    - EXECUTE: Assign to agents who reason-then-act (agents + gateway)
    - EVALUATE: Score quality of outputs (evaluator)
    - REFLECT: What worked? What didn't? Adapt strategy (metacognition)
    - LEARN: Store insights for future runs (persistent memory)

    This loop runs iteratively, with metacognition monitoring for progress
    and triggering creative pivots when the system gets stuck.
    """

    def __init__(
        self,
        project_dir: Path,
        model: str = "gpt-4.1-nano",
        agent_model: str = "gpt-4.1-nano",
        max_iterations: int = 3,
        max_concurrent_agents: int = 4,
        human_in_the_loop: bool = False,
        local_timezone: Optional[str] = None,
    ):
        self.project_dir = project_dir
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.hub = Hub(project_dir)
        self.model = model
        self.agent_model = agent_model
        self.max_iterations = max_iterations
        self.max_concurrent = max_concurrent_agents
        self.human_in_the_loop = human_in_the_loop
        self.local_timezone = local_timezone or os.getenv("CMAS_TIMEZONE")
        self.agents: Dict[str, Agent] = {}

        # Cognitive modules
        self.gateway = Gateway(hub=self.hub, project_dir=project_dir,
                               rate_limit_calls=30, rate_limit_window=60.0, max_recursion_depth=15)
        self.memory = Memory()
        self.evaluator = Evaluator(hub=self.hub, model=self.model)
        self.reasoner = Reasoner(model=self.model)
        self.metacognition = MetaCognition(hub=self.hub, memory=self.memory, model=self.model)

        # Brain modules (neuroscience-inspired)
        brain_db = str(project_dir / "brain.db")
        self.pathways = NeuralPathways(db_path=brain_db)
        self.dopamine = DopamineSystem(pathways=self.pathways, memory=self.memory)
        self.priority = PriorityDetector()
        self.consolidator = Consolidator(memory=self.memory, model=self.model)
        self.dmn = DefaultModeNetwork(memory=self.memory, model=self.model)

        self._print("CMAS initialized (cognitive architecture + brain modules active)")

    def _get_current_date(self) -> str:
        """Get current date/time string, respecting user's configured timezone."""
        if self.local_timezone:
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(self.local_timezone)
                now = datetime.now(tz)
            except Exception:
                # Fallback: treat as UTC offset like "UTC-5" or just use local
                now = datetime.now()
        else:
            now = datetime.now()
        return now.strftime("%B %d, %Y")

    def _print(self, msg: str):
        print(f"[Orchestrator] {msg}")

    # ── Human-in-the-Loop ────────────────────────────────────────

    async def _human_checkpoint(self, phase: str, context: str) -> str:
        if not self.human_in_the_loop:
            return ""
        print(f"\n{'='*60}")
        print(f"  CHECKPOINT: {phase}")
        print(f"{'='*60}")
        print(context[:1000])
        print(f"\nOptions: [enter] Continue | [text] Guidance | 'skip' | 'abort'")
        print(f"{'='*60}")
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: input("Your input: ").strip())
        except (EOFError, KeyboardInterrupt):
            return ""
        if response.lower() == "skip":
            self.human_in_the_loop = False
            return ""
        elif response.lower() == "abort":
            sys.exit(0)
        return response

    # ── Phase -1: PRE-SCREENING (The Architect) ──────────────────

    async def _prescreen_goal(self, goal: str) -> str:
        """Analyze physical/digital blockers, missing tools, and required schemas before executing."""
        self._print("PRE-SCREENING goal for constraints and required toolsets (OpenClaw style)...")

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are the Pre-Screening Architect for an AGI system.
Analyze this goal for:
1. Missing Python Packages needed (e.g. `biopython`, `numpy`, `chromadb`)
2. Missing local databases or datasets that must be created first
3. Foundational scientific/biological constraints that make this goal impossible as stated

If specialized Python packages or databases are needed, you MUST demand a Developer agent to build them first.
Return JSON ONLY:
{{
  "is_feasible": true/false,
  "missing_dependencies": ["package1", "package2"],
  "developer_tasks_needed": ["Write a script to seed a local SQLite db with molecules", "pip install biopython"],
  "scientific_constraints": ["Constraint 1"]
}}"""},
                {"role": "user", "content": goal},
            ],
            model=self.model,
            temperature=0.2,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            screen = json.loads(text)
        except Exception as e:
            self._print(f"Pre-screen parse failed: {e}")
            return goal

        # If developer tasks are needed, inject them immediately into the Hub!
        dev_tasks = screen.get("developer_tasks_needed", [])
        deps = screen.get("missing_dependencies", [])
        
        if deps:
            self._print(f"  Missing Dependencies detected: {', '.join(deps)}")
            # Auto-install missing packages using a shell agent
            task_id = "prescreen_pip"
            task_desc = f"Ensure the following Python packages are installed via pip: {', '.join(deps)}"
            t = Task(id=task_id, description=task_desc, status=TaskStatus.PENDING)
            self.hub.add_task(t)
            self._task_agent_map[task_id] = "specialist:Developer"
            self._task_deps[task_id] = []
            
        for i, dt in enumerate(dev_tasks):
            self._print(f"  Architect injecting prerequisite task: {dt}")
            task_id = f"prescreen_dev_{i}"
            t = Task(id=task_id, description=f"PRE-REQUISITE: {dt}", status=TaskStatus.PENDING)
            self.hub.add_task(t)
            self._task_agent_map[task_id] = "specialist:Developer"
            self._task_deps[task_id] = ["prescreen_pip"] if deps else []

        # Return an augmented goal string with the identified constraints
        constraints = screen.get("scientific_constraints", [])
        constraint_text = ("\n\nKNOWN CONSTRAINTS TO CONSIDER:\n" + "\n".join(f"- {c}" for c in constraints)) if constraints else ""
        
        return goal + constraint_text

    # ── Phase 0: PERCEIVE — understand goal + context ────────────

    async def _perceive(self, goal: str) -> Dict:
        """Build a rich understanding of the goal using memory + reasoning."""
        self._print("Perceiving goal context...")

        # Pull from persistent memory
        prior_knowledge = self.memory.search(goal[:50], limit=5)
        prior_lessons = self.memory.get_lessons(applies_to=goal[:50], limit=5)

        # Reason about the goal using MCTS (AlphaGo Style)
        self._print("Running Monte-Carlo Tree Search (MCTS) simulations...")
        mcts_result = await self.reasoner.mcts_search(
            goal=goal,
            context=self.memory.format_for_context(prior_knowledge) if prior_knowledge else "",
        )
        
        # Broadcast MCTS simulation states to the Live Web UI
        if self.gateway:
            for sim in mcts_result.get("simulations", []):
                msg = f"Branch {sim.get('branch_id')}: {sim.get('end_state_prediction', '')[:60]} (Score: {sim.get('score')})"
                self.gateway._audit("MCTS_Engine", "tree_search", "simulation", msg, "", True)
                
            optimal = mcts_result.get("optimal_path", {})
            opt_msg = f"Selected {optimal.get('branch_id')} - {optimal.get('reasoning', '')[:60]}"
            self.gateway._audit("MCTS_Engine", "path_verified", "reasoning", opt_msg, "", True)

        # Map MCTS optimal path to standard orchestration parameters
        optimal = mcts_result.get("optimal_path", {})
        reasoning = {
            "key_insight": optimal.get("reasoning", "MCTS converged on optimal path."),
            "confidence": 0.95,
            "unknowns": []
        }
        
        plan = {
            "recommended_approach": optimal.get("branch_id", "MCTS Optimal Branch"),
            "approaches": [
                {
                    "name": optimal.get("branch_id", "MCTS Optimal Branch"),
                    "steps": optimal.get("recommended_action_plan", [])
                }
            ]
        }

        self._print(f"  Key insight: {reasoning.get('key_insight', 'N/A')[:80]}")
        self._print(f"  Recommended approach: {plan.get('recommended_approach', 'N/A')[:80]}")
        self._print(f"  Confidence: {reasoning.get('confidence', 0.5):.0%}")

        return {
            "reasoning": reasoning,
            "plan": plan,
            "prior_knowledge": prior_knowledge,
            "prior_lessons": prior_lessons,
        }

    # ── Phase 1: PLAN — decompose goal into tasks ────────────────

    async def decompose_goal(self, goal: str, perception: Dict) -> List[Task]:
        """Decompose goal into tasks, informed by reasoning and prior knowledge."""
        self._print(f"Decomposing goal: {goal}")

        plan = perception.get("plan", {})
        reasoning = perception.get("reasoning", {})
        prior_lessons = perception.get("prior_lessons", [])

        # Build rich context for the planner
        approach = plan.get("recommended_approach", "Direct approach")
        approach_details = ""
        for a in plan.get("approaches", []):
            if a.get("name") == approach:
                approach_details = f"\nRecommended steps: {json.dumps(a.get('steps', []))}"
                break

        memory_context = ""
        if prior_lessons:
            memory_context = "\n\nLESSONS FROM PAST RUNS:\n" + "\n".join(
                f"  - {l['what_learned'][:150]}" for l in prior_lessons
            )

        unknowns = reasoning.get("unknowns", [])
        unknowns_text = ""
        if unknowns:
            unknowns_text = f"\n\nKEY UNKNOWNS TO INVESTIGATE: {json.dumps(unknowns)}"

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are a project planner for a multi-agent AI system.
Break the user's goal into 3-6 concrete, actionable tasks.

REASONING ABOUT THIS GOAL:
  Key insight: {reasoning.get('key_insight', 'N/A')}
  Recommended approach: {approach}{approach_details}
  Confidence: {reasoning.get('confidence', 0.5):.0%}
{unknowns_text}
{memory_context}

Available agent types:
- ResearchAgent: Web search, information gathering, source finding
- AnalystAgent: Data analysis, pattern finding, critical evaluation, Python computation
- WriterAgent: Synthesizing findings into reports
- Specialist agents: Any specific domain (use "specialist:<domain>")

Return a JSON array of tasks. Each task must have:
- "id": short unique id (e.g., "research_1")
- "description": clear, specific description (2-3 sentences). Include what to look for and WHY.
- "agent_type": one of "research", "analyst", "writer", or "specialist:<domain>"
- "depends_on": array of task ids this depends on (empty for independent tasks)

Make tasks SPECIFIC — not "research X" but "search for Y because Z, focusing on A and B".
Return ONLY the JSON array."""},
                {"role": "user", "content": goal},
            ],
            model=self.model,
            temperature=0.4,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            tasks_data = json.loads(text)
        except Exception as e:
            self._print(f"Parse failed: {e}, using fallback")
            tasks_data = [
                {"id": "research_1", "description": f"Research: {goal}", "agent_type": "research", "depends_on": []},
                {"id": "analysis_1", "description": f"Analyze findings about: {goal}", "agent_type": "analyst", "depends_on": ["research_1"]},
                {"id": "report_1", "description": f"Write report on: {goal}", "agent_type": "writer", "depends_on": ["analysis_1"]},
            ]

        tasks = []
        for td in tasks_data:
            task = Task(id=td["id"], description=td["description"], status=TaskStatus.PENDING)
            self.hub.add_task(task)
            tasks.append(task)
            self._print(f"  Task: [{td['id']}] {td['description'][:80]}...")

        self._task_agent_map.update({td["id"]: td.get("agent_type", "research") for td in tasks_data})
        self._task_deps.update({td["id"]: td.get("depends_on", []) for td in tasks_data})

        # Make the first conceptual tasks depend on the pre-screening dev tasks if any exist
        existing_dev_tasks = [t.id for t in self.hub.get_all_tasks() if t.id.startswith('prescreen_dev_')]
        if existing_dev_tasks:
            for td in tasks_data:
                # If a task has no dependencies, force it to wait for the infra to finish building
                if not self._task_deps[td["id"]]:
                    self._task_deps[td["id"]] = existing_dev_tasks

        self.hub.remember("goal", goal)
        self.hub.remember("task_plan", json.dumps(tasks_data, indent=2))

        # Human checkpoint
        human_input = await self._human_checkpoint(
            "Task Plan Review",
            f"Goal: {goal}\n\nKey insight: {reasoning.get('key_insight', 'N/A')}\n\nTasks:\n" +
            "\n".join(f"  [{td['id']}] ({td.get('agent_type','?')}) {td['description']}" for td in tasks_data),
        )
        if human_input:
            self.hub.remember("human_guidance_plan", human_input)

        return tasks

    # ── Phase 2: EXECUTE — run agents ────────────────────────────

    def _get_or_create_agent(self, agent_type: str) -> Agent:
        if agent_type in self.agents:
            return self.agents[agent_type]

        workspace = self.project_dir / "agents"
        kwargs = dict(hub=self.hub, workspace=workspace, model=self.agent_model,
                      gateway=self.gateway, memory=self.memory)

        if agent_type == "research":
            agent = create_research_agent(**kwargs)
        elif agent_type == "analyst":
            agent = create_analyst_agent(**kwargs)
        elif agent_type == "writer":
            agent = create_writer_agent(**kwargs)
        elif agent_type.startswith("specialist:"):
            domain = agent_type.split(":", 1)[1]
            name = f"Specialist_{domain.replace(' ', '_')[:20]}"
            agent = create_specialist_agent(name, domain, **kwargs)
        else:
            agent = create_research_agent(**kwargs)

        self.agents[agent_type] = agent
        self.gateway.register_agent(agent.name, agent)
        return agent

    def _get_ready_tasks(self) -> List[Task]:
        """Get tasks ready to run, sorted by priority (amygdala fast-assess)."""
        all_tasks = self.hub.get_all_tasks()
        done_ids = {t.id for t in all_tasks if t.status == "done"}
        ready = [t for t in all_tasks if t.status == "pending"
                 and all(d in done_ids for d in self._task_deps.get(t.id, []))]

        # Sort by priority (critical first)
        for task in ready:
            deps = self._task_deps.get(task.id, [])
            blocking = any(
                t.status == "pending" and task.id in self._task_deps.get(t.id, [])
                for t in all_tasks
            )
            task._priority = self.priority.fast_assess(
                task.description, blocking_others=blocking,
            )

        ready.sort(key=lambda t: t._priority.get("level", 3))
        return ready

    async def _run_tasks_batch(self, tasks: List[Task]):
        if not tasks:
            return

        all_done = self.hub.get_tasks(status="done")
        context_results = {t.id: t.result[:1000] for t in all_done if t.result}

        async def run_one(task: Task):
            agent_type = self._task_agent_map.get(task.id, "research")
            agent = self._get_or_create_agent(agent_type)

            deps = self._task_deps.get(task.id, [])
            if deps:
                dep_context = "\n\n--- CONTEXT FROM PRIOR TASKS ---\n"
                for dep_id in deps:
                    if dep_id in context_results:
                        dep_context += f"\n[{dep_id}]: {context_results[dep_id]}\n"
                task_with_context = Task(
                    id=task.id, description=task.description + dep_context,
                    status=task.status, parent_task_id=task.parent_task_id)
                return await agent.execute(task_with_context)
            return await agent.execute(task)

        sem = asyncio.Semaphore(self.max_concurrent)
        async def bounded(task):
            async with sem:
                return await run_one(task)

        await asyncio.gather(*(bounded(t) for t in tasks))

    # ── Phase 3: EVALUATE — score outputs ────────────────────────

    async def _evaluate_and_retry(self, goal: str):
        self._print("Evaluating agent outputs...")
        scores = await self.evaluator.evaluate_all(goal)
        if not scores:
            return

        for s in scores:
            status = "GOOD" if s.overall >= 6 else "RETRY" if s.overall >= 3 else "FAILED"
            self._print(f"  {s.task_id}: {s.overall}/10 [{status}] — {s.feedback[:60]}")

        # Process dopamine reward signals for each score
        for s in scores:
            agent_type = self._task_agent_map.get(s.task_id, "research")
            task_deps = self._task_deps.get(s.task_id, [])
            task_chain = task_deps + [s.task_id] if task_deps else [s.task_id]
            signal = self.dopamine.process_reward(
                task_id=s.task_id, agent_name=agent_type,
                agent_type=agent_type, actual_quality=s.overall,
                task_chain=task_chain,
            )
            if signal.prediction_error < -2:
                # Learn threat pattern from bad surprises
                task = self.hub.get_task(s.task_id)
                if task:
                    keywords = [w for w in task.description.split()[:3] if len(w) > 3]
                    if keywords:
                        self.priority.learn_threat(" ".join(keywords), severity=0.5)

        low_scores = [s for s in scores if s.overall < 5.0]
        for s in low_scores:
            original_task = self.hub.get_task(s.task_id)
            if not original_task:
                continue
            retry_id = f"retry_{s.task_id}"
            retry_desc = (
                f"RETRY (scored {s.overall}/10). Feedback: {s.feedback}. "
                f"Original: {original_task.description[:200]}. "
                f"Address the feedback specifically. Try a different approach."
            )
            retry_task = Task(id=retry_id, description=retry_desc)
            self.hub.add_task(retry_task)
            original_type = self._task_agent_map.get(s.task_id, "research")
            self._task_agent_map[retry_id] = original_type
            self._task_deps[retry_id] = []
            self._print(f"  Retrying {s.task_id} as {retry_id}")

    # ── Phase 4: REFLECT — metacognition ─────────────────────────

    async def _reflect_and_adapt(self, goal: str, iteration: int) -> Dict:
        """Metacognitive reflection: analyze performance and adapt strategy."""
        done_tasks = self.hub.get_tasks(status="done")

        # Build data for reflection
        results_data = [{"task_id": t.id, "result": t.result[:300]} for t in done_tasks]
        scores_data = [{"task_id": s.task_id, "overall": s.overall, "feedback": s.feedback}
                       for s in self.evaluator.scores]

        # Reflect
        reflection = await self.metacognition.reflect(goal, results_data, scores_data)

        # Snapshot progress
        score_values = [s.overall for s in self.evaluator.scores]
        total_tasks = len(self.hub.get_all_tasks())
        self.metacognition.snapshot_progress(iteration, score_values, len(done_tasks), total_tasks)

        # Check if stuck
        stuck = reflection.get("stuck_detection", {})
        if stuck.get("is_stuck"):
            self._print(f"  STUCK DETECTED: {stuck.get('evidence', 'unknown')[:80]}")

            # Trigger creative exploration
            what_we_know = "\n".join(t.result[:200] for t in done_tasks[-3:])
            creativity = await self.metacognition.creativity_boost(
                topic=goal,
                what_we_know=what_we_know,
                what_hasnt_worked=stuck.get("evidence", ""),
            )
            self._print(f"  Creative pivot: {creativity.get('reframed_problem', 'N/A')[:80]}")
            reflection["creativity"] = creativity

            # Add stuck problem to DMN incubation for background processing
            self.dmn.add_to_incubation(goal, what_we_know)

        # Log strategy adjustments
        adjustments = reflection.get("strategy_adjustments", [])
        for adj in adjustments:
            self._print(f"  Strategy change: {adj.get('suggested_change', 'N/A')[:80]}")

        return reflection

    # ── Phase 5: ITERATE — review and generate follow-ups ────────

    async def review_and_iterate(self, goal: str, iteration: int, reflection: Dict) -> List[Task]:
        """Generate follow-up tasks informed by evaluation and reflection."""
        done_tasks = self.hub.get_tasks(status="done")
        if not done_tasks:
            return []

        results_summary = "\n\n".join(
            f"[{t.id}] {t.description[:100]}\nResult: {t.result[:600]}" for t in done_tasks
        )
        eval_summary = self.evaluator.get_summary()

        # Include metacognitive insights
        blind_spots = reflection.get("blind_spots", [])
        blind_spots_text = ""
        if blind_spots:
            blind_spots_text = f"\n\nBLIND SPOTS IDENTIFIED: {json.dumps(blind_spots)}"

        creativity = reflection.get("creativity", {})
        creative_text = ""
        if creativity:
            reframed = creativity.get("reframed_problem", "")
            angles = creativity.get("unconventional_angles", [])
            if reframed:
                creative_text += f"\n\nREFRAMED PROBLEM: {reframed}"
            if angles:
                creative_text += f"\nNOVEL ANGLES: {json.dumps([a.get('idea','') for a in angles[:3]])}"

        self._print(f"Reviewing results (iteration {iteration})...")

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are reviewing a multi-agent system's work.
Based on the goal, results, quality scores, and metacognitive insights, decide what to do next.

{eval_summary}
{blind_spots_text}
{creative_text}

If the goal is well-addressed: {{"done": true, "summary": "brief summary"}}

If more work is needed:
{{
  "done": false,
  "gaps": "what's missing",
  "new_tasks": [
    {{"id": "followup_1", "description": "SPECIFIC task addressing a gap or blind spot", "agent_type": "research|analyst|writer|specialist:<domain>", "depends_on": []}}
  ]
}}

IMPORTANT: If blind spots or creative angles were identified, incorporate them into new tasks.
Return ONLY JSON. Limit to 1-3 high-impact tasks."""},
                {"role": "user", "content": f"GOAL: {goal}\n\nCOMPLETED WORK:\n{results_summary}"},
            ],
            model=self.model,
            temperature=0.3,
        )

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            review = json.loads(text)
        except Exception:
            return []

        if review.get("done"):
            self._print(f"Review complete: {review.get('summary', 'Goal addressed')}")
            self.hub.remember("final_summary", review.get("summary", ""))
            return []

        self._print(f"Gaps: {review.get('gaps', 'N/A')}")
        new_tasks = []
        for td in review.get("new_tasks", []):
            task = Task(id=td["id"], description=td["description"])
            self.hub.add_task(task)
            self._task_agent_map[td["id"]] = td.get("agent_type", "research")
            self._task_deps[td["id"]] = td.get("depends_on", [])
            new_tasks.append(task)
            self._print(f"  Follow-up: [{td['id']}] {td['description'][:80]}...")

        # Human checkpoint
        human_input = await self._human_checkpoint(
            f"Iteration {iteration} Review",
            f"Goal: {goal}\n\n{eval_summary}\n\nGaps: {review.get('gaps', 'N/A')}",
        )
        if human_input:
            self.hub.remember(f"human_guidance_iter_{iteration}", human_input)

        return new_tasks

    # ── Phase 6: SYNTHESIZE ──────────────────────────────────────

    async def synthesize(self, goal: str) -> str:
        done_tasks = self.hub.get_tasks(status="done")
        all_results = "\n\n---\n\n".join(
            f"## {t.id}: {t.description[:100]}\n{t.result}" for t in done_tasks
        )
        self._print("Synthesizing final output...")

        current_date = self._get_current_date()

        response = await chat(
            messages=[
                {"role": "system", "content": f"""You are producing the final output for a multi-agent research system.
Synthesize all agent results into a clear, comprehensive, well-structured report.

Today's date is: {current_date}

IMPORTANT RULES:
- Only cite sources (URLs, papers, institutions) that appear in the agent results below. Do NOT invent or hallucinate references.
- If no specific sources were found by the agents, state "Sources: Based on agent research" — do NOT fabricate citations.
- Use the correct date ({current_date}) in the report footer.
- Be thorough but concise. Include key findings, analysis, and actionable conclusions.
- Structure with clear headers and sections.
- End the report with a "References" section listing ONLY URLs/sources that actually appear in the agent results."""},
                {"role": "user", "content": f"GOAL: {goal}\n\nALL RESULTS:\n{all_results}"},
            ],
            model=self.model,
        )

        result = response.content if hasattr(response, 'content') else str(response)

        # Always save the final report to disk — don't rely on LLM tool calls
        report_path = self.project_dir / "final_report.md"
        report_path.write_text(result)
        self._print(f"Final report saved to: {report_path}")

        self.hub.remember("synthesis", result[:2000])
        self.memory.store(
            topic=goal[:100], content=result[:1000], category="synthesis",
            source="orchestrator", project=str(self.project_dir.name), confidence=0.7,
        )
        return result

    # ── Main Cognitive Loop ──────────────────────────────────────

    async def run(self, goal: str) -> str:
        """Full cognitive loop: perceive -> plan -> execute -> evaluate -> reflect -> learn."""
        self._print(f"{'='*60}")
        self._print(f"GOAL: {goal}")
        self._print(f"{'='*60}\n")
        
        # Ensure task maps are initialized before we start modifying them in pre-screen
        self._task_agent_map = {}
        self._task_deps = {}

        # Phase -1: PRE-SCREENING
        augmented_goal = await self._prescreen_goal(goal)

        # Phase 0: PERCEIVE
        perception = await self._perceive(augmented_goal)

        # Phase 1: PLAN
        tasks = await self.decompose_goal(augmented_goal, perception)

        # Phases 2-5: Execute -> Evaluate -> Reflect -> Iterate
        for iteration in range(1, self.max_iterations + 1):
            self._print(f"\n{'─'*40}")
            self._print(f"Iteration {iteration}/{self.max_iterations}")
            self._print(f"{'─'*40}")

            # EXECUTE
            while True:
                ready = self._get_ready_tasks()
                if not ready:
                    break
                self._print(f"Running {len(ready)} tasks concurrently...")
                await self._run_tasks_batch(ready)

            print(self.hub.get_status_summary())

            # EVALUATE
            await self._evaluate_and_retry(goal)

            # Execute retries
            while True:
                ready = self._get_ready_tasks()
                if not ready:
                    break
                self._print(f"Running {len(ready)} retry tasks...")
                await self._run_tasks_batch(ready)

            # REFLECT
            reflection = await self._reflect_and_adapt(goal, iteration)

            # ITERATE
            if iteration < self.max_iterations:
                new_tasks = await self.review_and_iterate(goal, iteration, reflection)
                if not new_tasks:
                    self._print("No follow-up needed. Moving to synthesis.")
                    break
            else:
                self._print("Max iterations reached. Moving to synthesis.")

        # Phase 6: SYNTHESIZE
        final = await self.synthesize(goal)

        # LEARN — store everything for future runs
        print(self.evaluator.get_summary())
        print(self.metacognition.get_summary())
        print(self.gateway.get_audit_summary())

        comparison = await self.evaluator.compare_iterations(goal, self.max_iterations)
        self.memory.store_lesson(
            what_happened=f"Ran CMAS on: {goal[:100]}",
            what_learned=f"{comparison.get('message', 'N/A')}. {len(self.hub.get_tasks(status='done'))} tasks done.",
            applies_to=goal[:50],
            project=str(self.project_dir.name),
        )

        # ── Brain: Consolidation (sleep analog) ──────────────────
        self._print("Running memory consolidation...")
        done_tasks = self.hub.get_tasks(status="done")
        consolidation_data = [
            {
                "agent": self._task_agent_map.get(t.id, "unknown"),
                "description": t.description[:200],
                "score": next((s.overall for s in self.evaluator.scores if s.task_id == t.id), 5),
                "approach": t.result[:150] if t.result else "",
            }
            for t in done_tasks
        ]
        consolidation = await self.consolidator.consolidate(consolidation_data)
        self._print(f"  Schemas: {consolidation['schemas_extracted']}, Hypotheses: {consolidation['hypotheses_generated']}")

        # ── Brain: Pathway maintenance ────────────────────────────
        self.pathways.decay_all()
        self.pathways.homeostatic_scale()

        # ── Brain: DMN idle cycle (background creativity) ─────────
        self._print("Running DMN idle cycle...")
        dmn_results = await self.dmn.idle_cycle()
        if dmn_results.get("recombinations"):
            self._print(f"  Creative insights: {len(dmn_results['recombinations'])}")
        if dmn_results.get("incubation_insights"):
            self._print(f"  Incubation insights: {len(dmn_results['incubation_insights'])}")

        # ── Brain: Summaries ──────────────────────────────────────
        print(self.dopamine.get_summary())

        mem_stats = self.memory.get_stats()
        self._print(f"Memory: {mem_stats['total_entries']} entries, {mem_stats['total_lessons']} lessons")
        self._print(f"\n{'='*60}")
        self._print(f"COMPLETE — {self.project_dir}")
        self._print(f"{'='*60}")

        return final
