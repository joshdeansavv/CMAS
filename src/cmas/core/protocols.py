"""Protocols — reusable patterns adopted from best practices in agent systems.

Inspired by patterns from OpenClaw, enterprise orchestration, and real-world
management. These protocols are used by the Composer, Teams, and Agents to
enforce quality, communication standards, and operational discipline.

Key patterns:
- Tool Profiles: Named bundles of tools allocated by role
- Standing Orders: Persistent authority docs injected into every session
- Execute-Verify-Report: Agents must prove work, not just claim completion
- Depth Policies: Different capabilities at different org levels
- Bootstrap Context: Identity/mission docs auto-injected per agent
"""
from __future__ import annotations

from typing import Dict, List, Set


# ── Tool Profiles ───────────────────────────────────────────────────
# Named bundles of tools. Instead of listing tools individually per team,
# the Composer can assign a profile. Teams can also request specific tools
# on top of their profile.

TOOL_PROFILES: Dict[str, Set[str]] = {
    "minimal": {
        "read_file", "write_file", "list_files", "send_message",
    },
    "research": {
        "web_search", "read_file", "write_file", "list_files",
        "send_message", "apply_framework",
    },
    "coding": {
        "web_search", "read_file", "write_file", "list_files",
        "run_python", "run_command", "send_message",
    },
    "analysis": {
        "web_search", "read_file", "write_file", "list_files",
        "run_python", "send_message", "apply_framework",
    },
    "full": {
        "web_search", "read_file", "write_file", "list_files",
        "run_python", "run_command", "send_message", "delegate_task",
        "apply_framework",
    },
    "operations": {
        "read_file", "write_file", "list_files", "send_message",
        "apply_framework",
    },
}


def get_tools_for_profile(profile: str, extras: List[str] = None) -> Set[str]:
    """Get the tool set for a named profile, with optional extras."""
    tools = set(TOOL_PROFILES.get(profile, TOOL_PROFILES["research"]))
    if extras:
        tools.update(extras)
    return tools


# ── Depth Policies ──────────────────────────────────────────────────
# Different capabilities at different organizational levels.
# Depth 0 = Composer (CEO), Depth 1 = Team Lead, Depth 2 = Sub-agent, etc.

DEPTH_POLICIES: Dict[int, Dict] = {
    0: {
        "label": "Composer (CEO)",
        "can_create_teams": True,
        "can_spawn_agents": True,
        "can_delegate": True,
        "max_children": 8,
        "tool_profile": "full",
        "can_use_frameworks": True,
    },
    1: {
        "label": "Team Lead",
        "can_create_teams": False,
        "can_spawn_agents": True,
        "can_delegate": True,
        "max_children": 5,
        "tool_profile": "full",
        "can_use_frameworks": True,
    },
    2: {
        "label": "Sub-Agent (Employee)",
        "can_create_teams": False,
        "can_spawn_agents": True,  # Can still delegate depth 3+
        "can_delegate": True,
        "max_children": 3,
        "tool_profile": "research",  # More restricted by default
        "can_use_frameworks": True,
    },
    3: {
        "label": "Specialist Worker",
        "can_create_teams": False,
        "can_spawn_agents": False,  # Leaf worker
        "can_delegate": False,
        "max_children": 0,
        "tool_profile": "minimal",
        "can_use_frameworks": False,
    },
}


def get_depth_policy(depth: int) -> Dict:
    """Get the policy for a given organizational depth."""
    if depth in DEPTH_POLICIES:
        return DEPTH_POLICIES[depth]
    # Beyond defined depths, use the most restrictive
    return DEPTH_POLICIES[max(DEPTH_POLICIES.keys())]


# ── Standing Orders ─────────────────────────────────────────────────
# Persistent authority and behavioral rules injected into every agent.
# These are like AGENTS.md — they define HOW agents should operate.

STANDING_ORDERS = {
    "composer": """## Standing Orders: Composer (CEO)

AUTHORITY: You have full authority to create, modify, and dissolve teams.
You are the ONLY agent authorized to design organizational structure.

RULES:
1. Never create more teams than necessary. Lean organizations outperform bloated ones.
2. Every team must have a clear, non-overlapping mission.
3. Always allocate the minimum tools needed — over-allocation wastes resources.
4. Monitor team progress. If a team is stuck, intervene or reassign.
5. Your job is STRATEGY and COORDINATION, not execution. Let teams do the work.
6. When evaluating results, be rigorous. A 6/10 is not good enough for the user.
7. Always think: "What would a great CEO do here?"

COMMUNICATION PROTOCOL:
- Broadcast strategic decisions to all teams
- Receive reports from team leads
- Escalate blockers that span multiple teams
""",

    "team_lead": """## Standing Orders: Team Lead

AUTHORITY: You manage your team's sub-agents. You decide who to hire,
what they work on, and how to organize the work.

RULES:
1. Understand your mission completely before hiring anyone.
2. Hire specialists, not generalists. Each sub-agent should do ONE thing well.
3. Don't hire more people than you need. 2-3 focused sub-agents beat 5 scattered ones.
4. Set clear, specific tasks. "Research X" is too vague. "Find the top 5 Y because Z" is good.
5. Coordinate dependencies — don't let sub-agents duplicate work.
6. Aggregate results into a coherent team deliverable, not a pile of raw outputs.
7. Report back to the Composer with: what was accomplished, confidence level, gaps remaining.

COMMUNICATION PROTOCOL:
- Give clear task briefs to sub-agents
- Monitor their progress via messages
- Resolve conflicts between sub-agents
- Report team results to Composer
- Share relevant findings with other teams when beneficial
""",

    "sub_agent": """## Standing Orders: Sub-Agent (Employee)

AUTHORITY: You are a specialist on your team. You execute your assigned task
to the highest standard.

RULES:
1. Follow your task brief precisely. Don't scope-creep.
2. Use your tools effectively. Web search for facts, write_file for deliverables.
3. If you're stuck, message your team lead — don't spin in circles.
4. Save all important findings to files in your workspace.
5. When done, provide: (a) key deliverables, (b) confidence level, (c) what you couldn't find.
6. Cite sources. Never make up information.
7. If another sub-agent's work would help you, request it via send_message.

EXECUTE-VERIFY-REPORT PROTOCOL:
- EXECUTE: Do the work using your tools
- VERIFY: Check your own output — is it complete? Accurate? Cited?
- REPORT: Summarize what you did, what you found, and what remains unknown
""",
}


def get_standing_orders(role: str) -> str:
    """Get standing orders for a role (composer, team_lead, sub_agent)."""
    return STANDING_ORDERS.get(role, STANDING_ORDERS["sub_agent"])


# ── Bootstrap Context ───────────────────────────────────────────────
# Identity and mission docs auto-injected into agent system prompts.
# Each agent gets a tailored bootstrap based on their role and context.

def build_bootstrap_context(
    agent_name: str,
    role: str,
    mission: str,
    team_name: str = "",
    depth: int = 2,
    tools: List[str] = None,
    frameworks: List[str] = None,
    standing_orders: str = "",
) -> str:
    """Build the complete bootstrap context for an agent's system prompt.

    This replaces ad-hoc system prompt construction with a structured,
    consistent context injection — similar to OpenClaw's bootstrap files.
    """
    policy = get_depth_policy(depth)

    sections = []

    # Identity
    sections.append(f"# Agent Identity\n"
                    f"- **Name**: {agent_name}\n"
                    f"- **Role**: {role}\n"
                    f"- **Level**: {policy['label']} (depth {depth})\n")

    if team_name:
        sections.append(f"- **Team**: {team_name}\n")

    # Mission
    sections.append(f"\n# Mission\n{mission}\n")

    # Standing Orders
    if standing_orders:
        sections.append(f"\n{standing_orders}\n")

    # Available Tools
    if tools:
        sections.append(f"\n# Available Tools\n"
                        f"{', '.join(tools)}\n")

    # Available Frameworks
    if frameworks:
        sections.append(f"\n# Available Frameworks\n"
                        f"Use `apply_framework` tool to apply these when relevant:\n"
                        f"{', '.join(frameworks)}\n")

    # Capabilities based on depth
    caps = []
    if policy["can_delegate"]:
        caps.append("You CAN delegate tasks to sub-agents using `delegate_task`")
    else:
        caps.append("You CANNOT delegate. You must do the work yourself.")

    if not policy["can_spawn_agents"]:
        caps.append("You are a leaf worker. Complete your task and report back.")

    sections.append(f"\n# Capabilities\n" + "\n".join(f"- {c}" for c in caps))

    # Execute-Verify-Report reminder
    sections.append("""
# Output Protocol: Execute-Verify-Report
1. **EXECUTE**: Do the work thoroughly using your available tools
2. **VERIFY**: Before reporting, check your own output:
   - Is it complete? Does it fully address the task?
   - Is it accurate? Are claims supported by evidence?
   - Are sources cited? Never fabricate references.
3. **REPORT**: Structure your final output as:
   - **Deliverables**: What you produced (files, findings, analysis)
   - **Key Findings**: The most important things discovered
   - **Confidence**: How certain you are (and why)
   - **Gaps**: What you couldn't find or are unsure about
""")

    return "\n".join(sections)


# ── Verification Protocol ───────────────────────────────────────────
# Used by Team Leads and Composer to verify agent outputs.

VERIFICATION_PROMPT = """Review this agent's output against their task brief.

TASK: {task}
OUTPUT: {output}

Score each dimension 1-5:
1. COMPLETENESS: Did they address the full task? (1=barely started, 5=thorough)
2. ACCURACY: Is the information correct and well-sourced? (1=fabricated, 5=verified)
3. ACTIONABILITY: Can someone act on this output? (1=vague, 5=concrete)
4. EVIDENCE: Are claims supported with sources/data? (1=none, 5=well-cited)

Return JSON:
{{
  "completeness": N,
  "accuracy": N,
  "actionability": N,
  "evidence": N,
  "overall": N,
  "passed": true/false,
  "feedback": "specific feedback"
}}

A score of 3+ on all dimensions = passed. Below that = failed, needs retry.
Return ONLY JSON."""
