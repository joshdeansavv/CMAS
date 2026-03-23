"""Frameworks Engine — evidence-based coaching and transformation frameworks.

Provides a tool that agents can call to select and apply the right framework
for any given situation. The engine analyzes context and returns structured
guidance, questions, and protocols from proven frameworks.

Frameworks are stored as JSON for machine-parseability and loaded on demand.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Any


# ── Framework Registry ──────────────────────────────────────────────

FRAMEWORK_DIR = Path(__file__).parent

# Map of framework_id -> loaded JSON data (lazy-loaded)
_cache: Dict[str, dict] = {}

# All available framework files
FRAMEWORK_FILES = {
    "cbt":              "cbt.json",
    "act":              "act.json",
    "dbt":              "dbt.json",
    "stages_of_change": "stages_of_change.json",
    "goal_setting":     "goal_setting.json",
    "strategic":        "strategic.json",
    "behavioral":       "behavioral.json",
    "financial":        "financial.json",
    "conflict":         "conflict.json",
    "nlp":              "nlp_framework.json",
}

# Context keywords that signal which framework to use
CONTEXT_SIGNALS = {
    "cbt": [
        "stuck", "circular", "overthinking", "assumption", "distorted",
        "catastroph", "all-or-nothing", "should", "failure", "hopeless",
        "can't", "impossible", "always fail", "never work", "cognitive",
        "reframe", "thinking pattern", "mental block", "self-doubt"
    ],
    "act": [
        "uncertain", "perfecti", "paralyz", "afraid", "incomplete info",
        "not ready", "waiting for", "ambiguity", "procrastinat",
        "avoidance", "values", "acceptance", "flexibility", "commit"
    ],
    "dbt": [
        "overwhelm", "crisis", "conflict between", "high pressure",
        "deadline", "emotional", "interpersonal", "distress",
        "regulate", "mindful", "dialectic", "both true"
    ],
    "stages_of_change": [
        "readiness", "not ready", "considering", "thinking about",
        "ambivalent", "should i", "maintaining", "relapse", "stage"
    ],
    "goal_setting": [
        "goal", "objective", "want to achieve", "plan", "target",
        "milestone", "measure", "track", "okr", "smart goal",
        "vague", "unclear direction", "what should i aim"
    ],
    "strategic": [
        "prioriti", "swot", "strengths", "weakness", "opportunit",
        "threat", "urgent", "important", "80/20", "pareto",
        "focus", "too many", "overwhelm", "triage", "strategic"
    ],
    "behavioral": [
        "habit", "routine", "trigger", "cue", "reward", "consistency",
        "discipline", "motivation", "accountability", "keep starting",
        "can't stick", "fall off", "behavior change"
    ],
    "financial": [
        "money", "financ", "invest", "budget", "debt", "income",
        "revenue", "profit", "wealth", "business model", "cash flow",
        "savings", "retire", "quadrant"
    ],
    "conflict": [
        "conflict", "argument", "blame", "victim", "rescue", "self-sabotag",
        "inner critic", "competing", "torn between", "resistance",
        "relationship", "communication breakdown"
    ],
    "nlp": [
        "reframe", "language", "belief", "perspective", "communication",
        "limiting", "always", "never", "can't", "persuad",
        "motivat", "stuck mindset", "perception"
    ],
}


def _load(framework_id: str) -> dict:
    """Load a framework JSON file, with caching."""
    if framework_id in _cache:
        return _cache[framework_id]

    filename = FRAMEWORK_FILES.get(framework_id)
    if not filename:
        return {}

    path = FRAMEWORK_DIR / filename
    if not path.exists():
        return {}

    with open(path, "r") as f:
        data = json.load(f)

    _cache[framework_id] = data
    return data


def list_frameworks() -> List[Dict[str, str]]:
    """List all available frameworks with their descriptions."""
    result = []
    for fid in FRAMEWORK_FILES:
        data = _load(fid)
        if data:
            result.append({
                "id": data.get("id", fid),
                "name": data.get("name", fid),
                "category": data.get("category", ""),
                "description": data.get("description", ""),
            })
    return result


def detect_frameworks(context: str, max_results: int = 3) -> List[str]:
    """Analyze context text and return the most relevant framework IDs.

    Scores each framework based on keyword matches in the context.
    Returns up to max_results framework IDs, sorted by relevance.
    """
    context_lower = context.lower()
    scores: Dict[str, int] = {}

    for fid, keywords in CONTEXT_SIGNALS.items():
        score = 0
        for kw in keywords:
            if kw in context_lower:
                score += 1
        if score > 0:
            scores[fid] = score

    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [fid for fid, _ in ranked[:max_results]]


def get_framework(framework_id: str) -> dict:
    """Get the full framework data by ID."""
    return _load(framework_id)


def apply_framework(framework_id: str, context: str = "", component: str = "") -> str:
    """Apply a specific framework to a given context.

    Args:
        framework_id: The framework to apply (e.g., "cbt", "act", "goal_setting")
        context: The situation or problem description
        component: Optional specific component (e.g., "socratic_questions",
                   "smart", "eisenhower", "habit_loop")

    Returns:
        Structured guidance text the agent can use directly.
    """
    data = _load(framework_id)
    if not data:
        return f"Unknown framework: {framework_id}. Available: {list(FRAMEWORK_FILES.keys())}"

    lines = [f"## {data['name']}", f"_{data['description']}_", ""]

    # If a specific component is requested, return just that part
    if component:
        extracted = _extract_component(data, component)
        if extracted:
            lines.append(extracted)
            return "\n".join(lines)

    # Otherwise, provide contextual guidance
    if context:
        lines.append(f"**Applied to:** {context[:200]}")
        lines.append("")

    # Build guidance based on framework type
    if framework_id == "cbt":
        lines.extend(_apply_cbt(data, context))
    elif framework_id == "act":
        lines.extend(_apply_act(data, context))
    elif framework_id == "dbt":
        lines.extend(_apply_dbt(data, context))
    elif framework_id == "stages_of_change":
        lines.extend(_apply_stages(data, context))
    elif framework_id == "goal_setting":
        lines.extend(_apply_goals(data, context, component))
    elif framework_id == "strategic":
        lines.extend(_apply_strategic(data, context, component))
    elif framework_id == "behavioral":
        lines.extend(_apply_behavioral(data, context, component))
    elif framework_id == "financial":
        lines.extend(_apply_financial(data, context, component))
    elif framework_id == "conflict":
        lines.extend(_apply_conflict(data, context, component))
    elif framework_id == "nlp":
        lines.extend(_apply_nlp(data, context))
    else:
        # Generic: return when_to_use and top-level keys
        lines.append("**When to use:**")
        for use in data.get("when_to_use", []):
            lines.append(f"  - {use}")

    return "\n".join(lines)


def select_and_apply(context: str) -> str:
    """Auto-detect the best framework(s) for the context and apply them.

    This is the main entry point for agents — they describe the situation
    and get back structured guidance from the most relevant framework(s).
    """
    detected = detect_frameworks(context, max_results=2)

    if not detected:
        return (
            "No strong framework match detected. Available frameworks:\n"
            + "\n".join(f"  - **{f['name']}** ({f['id']}): {f['description']}"
                        for f in list_frameworks())
            + "\n\nSpecify a framework_id to apply directly."
        )

    parts = []
    for fid in detected:
        parts.append(apply_framework(fid, context))

    return "\n\n---\n\n".join(parts)


# ── Framework-Specific Application Logic ────────────────────────────

def _apply_cbt(data: dict, context: str) -> List[str]:
    lines = []

    # Check for cognitive distortions
    lines.append("### Cognitive Distortion Check")
    for did, d in data.get("cognitive_distortions", {}).items():
        lines.append(f"- **{d['name']}**: {d['description']}")
        lines.append(f"  - Reframe: {d['reframe']}")

    # Provide relevant Socratic questions
    lines.append("")
    lines.append("### Socratic Questions to Apply")
    context_lower = context.lower()

    # Pick the most relevant question categories
    if any(w in context_lower for w in ["evidence", "proof", "fact", "true"]):
        category = "examining_evidence"
    elif any(w in context_lower for w in ["option", "alternative", "other", "else"]):
        category = "exploring_alternatives"
    elif any(w in context_lower for w in ["worst", "best", "happen", "consequence"]):
        category = "examining_consequences"
    elif any(w in context_lower for w in ["assum", "believe", "think", "expect"]):
        category = "questioning_assumptions"
    else:
        category = "testing_reasoning"

    questions = data.get("socratic_questions", {}).get(category, [])
    for q in questions:
        lines.append(f"  - {q}")

    # Include thought record if dealing with a specific stuck point
    if any(w in context_lower for w in ["stuck", "block", "can't", "fail"]):
        lines.append("")
        lines.append("### Thought Record Protocol")
        for step in data.get("thought_record", {}).get("steps", []):
            lines.append(f"  {step['step']}. **{step['name']}**: {step['prompt']}")

    return lines


def _apply_act(data: dict, context: str) -> List[str]:
    lines = []
    context_lower = context.lower()

    # Determine most relevant ACT process
    if any(w in context_lower for w in ["avoid", "wait", "not ready", "uncertain"]):
        focus = ["acceptance", "committed_action"]
    elif any(w in context_lower for w in ["thought", "belief", "predict", "assum"]):
        focus = ["cognitive_defusion", "present_moment"]
    elif any(w in context_lower for w in ["value", "purpose", "meaning", "why"]):
        focus = ["values_clarification", "committed_action"]
    else:
        focus = ["self_as_context", "acceptance", "committed_action"]

    for process_id in focus:
        process = data.get("core_processes", {}).get(process_id, {})
        if process:
            lines.append(f"### {process_id.replace('_', ' ').title()}")
            lines.append(f"_{process['agent_application']}_")
            lines.append("")
            for q in process.get("questions", []):
                lines.append(f"  - {q}")
            lines.append("")

    # Always include the flexibility protocol
    lines.append("### Flexibility Protocol")
    for step in data.get("flexibility_protocol", {}).get("steps", []):
        lines.append(f"  {step['step']}. **{step['name']}**: {step['prompt']}")

    return lines


def _apply_dbt(data: dict, context: str) -> List[str]:
    lines = []
    context_lower = context.lower()

    # Detect which DBT module is most relevant
    if any(w in context_lower for w in ["crisis", "emergency", "panic", "overwhelm"]):
        module = "distress_tolerance"
        lines.append("### Crisis Protocol (STOP)")
        for step in data["modules"]["distress_tolerance"]["crisis_protocol"]:
            lines.append(f"  - {step}")
    elif any(w in context_lower for w in ["conflict", "communicat", "team", "interpersonal"]):
        module = "interpersonal_effectiveness"
        dear = data["modules"]["interpersonal_effectiveness"]["skills"]["dear_man"]
        lines.append("### DEAR MAN Communication Protocol")
        for key, val in dear.items():
            lines.append(f"  - **{key}**: {val}")
    elif any(w in context_lower for w in ["react", "impulse", "emotion", "frustrat"]):
        module = "emotion_regulation"
    else:
        module = "mindfulness"

    mod_data = data["modules"].get(module, {})
    if mod_data:
        lines.append(f"### {module.replace('_', ' ').title()}")
        for prompt in mod_data.get("agent_prompts", []):
            lines.append(f"  - {prompt}")

    # Always include dialectical thinking
    lines.append("")
    lines.append("### Dialectical Thinking")
    dt = data.get("dialectical_thinking", {})
    lines.append(f"_{dt.get('core_principle', '')}_")
    for ex in dt.get("examples", []):
        lines.append(f"  - {ex}")

    return lines


def _apply_stages(data: dict, context: str) -> List[str]:
    lines = []

    lines.append("### Stage Detection")
    for q in data.get("stage_detection_prompts", []):
        lines.append(f"  - {q}")

    lines.append("")
    lines.append("### Stages Reference")
    for stage_id, stage in data.get("stages", {}).items():
        lines.append(f"**{stage_id.title()}**: {stage['description']}")
        lines.append(f"  Appropriate: {', '.join(stage['appropriate_actions'][:2])}")
        lines.append(f"  Avoid: {', '.join(stage['inappropriate_actions'][:1])}")

    return lines


def _apply_goals(data: dict, context: str, component: str) -> List[str]:
    lines = []
    frameworks = data.get("frameworks", {})

    # If a specific sub-framework was requested
    target = component if component in frameworks else None

    # Auto-detect based on context
    if not target:
        context_lower = context.lower()
        if any(w in context_lower for w in ["emotion", "passion", "motivat", "heartfelt"]):
            target = "hard"
        elif any(w in context_lower for w in ["okr", "key result", "objective", "quarter"]):
            target = "okr"
        elif any(w in context_lower for w in ["coach", "reflect", "option", "reality"]):
            target = "grow"
        else:
            target = "smart"

    fw = frameworks.get(target, {})
    lines.append(f"### {fw.get('name', target)}")
    lines.append(f"_{fw.get('description', '')}_")
    lines.append(f"**Best for:** {fw.get('best_for', '')}")
    lines.append("")

    if target == "smart":
        for crit, info in fw.get("criteria", {}).items():
            lines.append(f"  - **{crit.upper()}**: {info['question']}")
            lines.append(f"    Test: {info['test']}")
    elif target == "hard":
        for crit, info in fw.get("criteria", {}).items():
            lines.append(f"  - **{crit.upper()}**: {info['question']}")
            lines.append(f"    {info['prompt']}")
    elif target == "grow":
        for stage, info in fw.get("stages", {}).items():
            lines.append(f"  **{stage.upper()}** — {info['purpose']}")
            for q in info["questions"][:3]:
                lines.append(f"    - {q}")
    elif target == "okr":
        lines.append("  **Objective rules:**")
        for r in fw.get("structure", {}).get("objective", {}).get("rules", []):
            lines.append(f"    - {r}")
        lines.append("  **Key Results rules:**")
        for r in fw.get("structure", {}).get("key_results", {}).get("rules", []):
            lines.append(f"    - {r}")

    return lines


def _apply_strategic(data: dict, context: str, component: str) -> List[str]:
    lines = []
    frameworks = data.get("frameworks", {})
    context_lower = context.lower()

    if component and component in frameworks:
        target = component
    elif any(w in context_lower for w in ["strength", "weakness", "swot"]):
        target = "swot"
    elif any(w in context_lower for w in ["urgent", "important", "prioriti", "triage"]):
        target = "eisenhower"
    elif any(w in context_lower for w in ["80/20", "pareto", "leverage", "vital few"]):
        target = "pareto"
    elif any(w in context_lower for w in ["habit", "proactiv", "effective", "renewal"]):
        target = "seven_habits"
    else:
        target = "eisenhower"

    fw = frameworks.get(target, {})
    lines.append(f"### {fw.get('name', target)}")

    if target == "swot":
        for dim, info in fw.get("dimensions", {}).items():
            lines.append(f"  **{dim.upper()}** — {info['description']}")
            for q in info["questions"][:2]:
                lines.append(f"    - {q}")
        action = fw.get("action_prompt", "")
        if action:
            lines.append(f"\n  **Action:** {action}")
    elif target == "eisenhower":
        for qid, info in fw.get("quadrants", {}).items():
            lines.append(f"  **{info['label']}**: {info['description']}")
            lines.append(f"    Action: {info['action']}")
            lines.append(f"    Signal: {info['agent_signal']}")
    elif target == "pareto":
        for step in fw.get("application_steps", []):
            lines.append(f"  {step['step']}. {step['action']}")
        lines.append("")
        for q in fw.get("questions", []):
            lines.append(f"  - {q}")
    elif target == "seven_habits":
        for hid, habit in fw.get("habits", {}).items():
            lines.append(f"  **{hid.replace('_', ' ').title()}**: {habit['principle']}")
            lines.append(f"    Agent: {habit['agent_application']}")

    return lines


def _apply_behavioral(data: dict, context: str, component: str) -> List[str]:
    lines = []
    frameworks = data.get("frameworks", {})
    context_lower = context.lower()

    if component and component in frameworks:
        target = component
    elif any(w in context_lower for w in ["trigger", "cue", "reward", "loop", "break habit"]):
        target = "habit_loop"
    elif any(w in context_lower for w in ["tiny", "easy", "friction", "prompt", "ability"]):
        target = "fogg"
    elif any(w in context_lower for w in ["tendenc", "accountability", "expect", "obliger", "rebel"]):
        target = "four_tendencies"
    else:
        target = "habit_loop"

    fw = frameworks.get(target, {})
    lines.append(f"### {fw.get('name', target)}")
    lines.append(f"_{fw.get('description', '')}_")

    if target == "habit_loop":
        for comp, info in fw.get("components", {}).items():
            lines.append(f"  **{comp.upper()}**: {info['description']}")
            for q in info["questions"][:2]:
                lines.append(f"    - {q}")
        lines.append("\n  **Change Protocol:**")
        for step in fw.get("change_protocol", []):
            lines.append(f"    - {step}")
    elif target == "fogg":
        lines.append(f"\n  **Tiny Habits Recipe:** {fw.get('tiny_habits_recipe', '')}")
        lines.append("\n  **If behavior isn't happening:**")
        for diag in fw.get("failure_diagnosis", []):
            lines.append(f"    - {diag}")
    elif target == "four_tendencies":
        for tid, info in fw.get("tendencies", {}).items():
            lines.append(f"  **{tid.title()}**: {info['description']}")
            lines.append(f"    Strategy: {info['strategy']}")

    return lines


def _apply_financial(data: dict, context: str, component: str) -> List[str]:
    lines = []
    frameworks = data.get("frameworks", {})
    context_lower = context.lower()

    if component and component in frameworks:
        target = component
    elif any(w in context_lower for w in ["pyramid", "emergency", "debt", "foundation", "insurance"]):
        target = "wealth_pyramid"
    elif any(w in context_lower for w in ["profit first", "allocat", "account", "revenue"]):
        target = "profit_first"
    elif any(w in context_lower for w in ["quadrant", "employee", "business owner", "investor", "passive"]):
        target = "cashflow_quadrant"
    else:
        target = "wealth_pyramid"

    fw = frameworks.get(target, {})
    lines.append(f"### {fw.get('name', target)}")

    if target == "wealth_pyramid":
        for level in fw.get("levels", []):
            lines.append(f"  **Level {level['level']} — {level['name']}**")
            lines.append(f"    {level['question']}")
            lines.append(f"    Priority: {level['priority']}")
    elif target == "profit_first":
        lines.append(f"  **Core:** {fw.get('core_formula', '')}")
        lines.append(f"  **Principle:** {fw.get('key_principle', '')}")
        lines.append("  **Steps:**")
        for step in fw.get("implementation_steps", []):
            lines.append(f"    - {step}")
    elif target == "cashflow_quadrant":
        for qid, info in fw.get("quadrants", {}).items():
            lines.append(f"  **{qid}**: {info['description']}")
            lines.append(f"    Mindset: {info['mindset']}")
            lines.append(f"    Path: {info['path_forward']}")

    return lines


def _apply_conflict(data: dict, context: str, component: str) -> List[str]:
    lines = []
    frameworks = data.get("frameworks", {})
    context_lower = context.lower()

    if component and component in frameworks:
        target = component
    elif any(w in context_lower for w in ["victim", "blame", "rescue", "triangle", "dynamic"]):
        target = "drama_triangle"
    elif any(w in context_lower for w in ["inner", "part", "critic", "sabotag", "competing", "torn"]):
        target = "ifs"
    else:
        # Apply both for general conflict
        target = "drama_triangle"

    fw = frameworks.get(target, {})
    lines.append(f"### {fw.get('name', target)}")

    if target == "drama_triangle":
        for rid, info in fw.get("roles", {}).items():
            lines.append(f"  **{rid.title()}**: {info['description']}")
            lines.append(f"    Shift to: {info['empowerment_shift']}")
        lines.append("\n  **Detection Questions:**")
        for q in fw.get("detection_questions", []):
            lines.append(f"    - {q}")
    elif target == "ifs":
        lines.append(f"  _{fw.get('core_concept', '')}_")
        lines.append("\n  **Integration Process:**")
        for step in fw.get("process", []):
            lines.append(f"    {step['step']}. **{step['name']}**: {step['prompt']}")

    return lines


def _apply_nlp(data: dict, context: str) -> List[str]:
    lines = []
    context_lower = context.lower()

    techniques = data.get("techniques", {})

    if any(w in context_lower for w in ["reframe", "perspective", "meaning"]):
        rf = techniques.get("reframing", {})
        lines.append("### Reframing")
        for rt, info in rf.get("types", {}).items():
            lines.append(f"  **{rt.replace('_', ' ').title()}**: {info['description']}")
            lines.append(f"    Template: {info['template']}")
    elif any(w in context_lower for w in ["vague", "always", "never", "can't", "language"]):
        mm = techniques.get("meta_model", {})
        lines.append("### Meta Model (Precision Language)")
        for pattern, info in mm.get("patterns", {}).items():
            lines.append(f"  **{pattern.title()}**: {info['description']}")
            for c in info["challenges"]:
                lines.append(f"    - {c}")
    else:
        # Outcome specification as default
        os_data = techniques.get("outcome_specification", {})
        lines.append("### Outcome Specification")
        for q in os_data.get("questions", []):
            lines.append(f"  - {q}")

    return lines


def _extract_component(data: dict, component: str) -> Optional[str]:
    """Recursively search for a named component in the framework data."""
    def _search(obj, target):
        if isinstance(obj, dict):
            if target in obj:
                return json.dumps(obj[target], indent=2)
            for v in obj.values():
                result = _search(v, target)
                if result:
                    return result
        return None

    return _search(data, component)
