<div align="center">

# CMAS

**Cognitive Multi-Agent System**

<sub>An always-on agentic orchestration platform built around a neuroscience-inspired cognitive architecture.</sub>

---

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)
![aiohttp](https://img.shields.io/badge/aiohttp-async-2C5364?style=flat-square)
![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4.1-412991?style=flat-square&logo=openai&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-persistent-003B57?style=flat-square&logo=sqlite&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-vector%20memory-FF6B35?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

</div>

---

## Overview

CMAS is not a chatbot wrapper. It is a persistent cognitive environment that orchestrates multiple specialized AI agents through a structured six-phase loop — Perceive, Plan, Execute, Evaluate, Reflect, Learn — running against goals you define. The system persists state, memory, and learned behaviors across restarts, sessions, and projects.

The architecture draws from cognitive science and neuroscience: Hebbian learning determines agent routing, a dopamine-inspired reward signal calibrates quality expectations, a Default Mode Network generates creative synthesis during idle periods, and a metacognition layer detects and recovers from stuck states.

---

## Table of Contents

- [Architecture](#architecture)
- [Cognitive Loop](#cognitive-loop)
- [Core Modules](#core-modules)
  - [Orchestrator](#orchestrator)
  - [Gateway](#gateway)
  - [Memory](#memory)
  - [Brain](#brain)
  - [Agents](#agents)
  - [Reasoning and Metacognition](#reasoning-and-metacognition)
  - [Scheduler](#scheduler)
- [Tool System](#tool-system)
- [Memory Architecture](#memory-architecture)
- [Database Schemas](#database-schemas)
- [Web Interface](#web-interface)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI Reference](#cli-reference)
- [Channels](#channels)
- [Project Structure](#project-structure)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Mission Control UI                  │
│              React 18 + WebSocket (aiohttp)             │
└────────────────────────┬────────────────────────────────┘
                         │ ws://localhost:8080/ws
┌────────────────────────▼────────────────────────────────┐
│                        Gateway                          │
│         Access Control · Rate Limiting · Audit Log      │
└────┬──────────┬──────────┬──────────┬───────────────────┘
     │          │          │          │
┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼──────────────────┐
│Research│ │Analyst │ │Writer  │ │   Orchestrator        │
│Agent   │ │Agent   │ │Agent   │ │   (The General)       │
└────┬───┘ └───┬────┘ └───┬────┘ └───┬──────────────────┘
     │         │          │          │
     └────┬────┴──────────┘          │
          │                          │
┌─────────▼──────────────────────────▼───────────────────┐
│                    Shared State Hub                     │
│              SQLite (projects · tasks · agents)         │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼──────┐        ┌─────────▼──────────────────────┐
│    Memory    │        │            Brain                │
│ SQLite +     │        │ NeuralPathways · Dopamine       │
│ ChromaDB     │        │ DMN · Consolidator · Priority   │
└──────────────┘        └────────────────────────────────┘
```

Communication between all agents and external tools is routed exclusively through the Gateway. No agent calls a tool directly.

---

## Cognitive Loop

Every execution — whether a one-shot research run or a continuous server session — passes through the same six-phase loop managed by the Orchestrator:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   PERCEIVE ──► PLAN ──► EXECUTE ──► EVALUATE ──► REFLECT       │
│       ▲                                               │         │
│       └───────────────── LEARN ◄─────────────────────┘         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| Phase | Description |
|---|---|
| **PERCEIVE** | Load the goal. Retrieve relevant prior knowledge from memory by semantic similarity. Build context for the reasoning step. |
| **PLAN** | Decompose the goal into a dependency-ordered task tree using structured reasoning. Assign priorities. Identify which agent type should execute each task. |
| **EXECUTE** | Dispatch up to 4 tasks concurrently to agents. Each agent runs its own reason-act-reflect sub-loop. All tool calls are gated through the Gateway. |
| **EVALUATE** | Score each output on relevance, completeness, accuracy, and clarity (0–10 scale). Flag underperforming tasks for retry or reassignment. |
| **REFLECT** | MetaCognition reviews what worked, detects stuck patterns, adapts strategy. Generates alternative approaches when quality thresholds are not met. |
| **LEARN** | Store successful patterns, lessons, and compressed schemas in Memory. Update neural pathway weights. Adjust dopamine baseline. Loop back to PERCEIVE. |

Human-in-the-loop mode (`--human`) pauses at each cycle boundary for steering input before proceeding.

---

## Core Modules

### Orchestrator

`src/cmas/core/orchestrator.py` — 35.2 KB

The Orchestrator is the central coordinator. It owns the cognitive loop and holds references to every other system: the Hub, Gateway, Memory, Brain, Reasoner, Evaluator, and MetaCognition. It does not execute tasks itself — it decomposes, assigns, monitors, and synthesizes.

Key responsibilities:
- Calling `reasoning.py` to produce structured task trees from natural language goals
- Managing the task queue and agent concurrency (max 4 parallel tasks)
- Triggering evaluation after each task completes
- Calling `metacognition.py` when the system detects it is stuck (no quality improvement over N cycles)
- Writing lessons and patterns to Memory at the end of each loop
- Updating `NeuralPathways` weights in `brain.py` based on agent success/failure

### Gateway

`src/cmas/core/gateway.py` — 21.9 KB

Every tool call in the system passes through the Gateway before execution. This is the single point of enforcement for access control, rate limiting, and audit logging.

**Access control** is defined by `DEFAULT_PERMISSIONS`, a dictionary mapping agent types to allowed tool sets:

```python
DEFAULT_PERMISSIONS = {
    "ResearchAgent": ["web_search", "read_file", "list_files", "send_message"],
    "AnalystAgent":  ["run_python", "read_file", "write_file", "run_command"],
    "WriterAgent":   ["read_file", "write_file", "send_message"],
}
```

**Rate limiting** is enforced per agent: 30 calls per 60-second window via a sliding `RateLimitState`.

**Audit logging** captures every action:

```python
{
    "timestamp": "2025-01-15T14:32:01.123Z",
    "agent":     "ResearchAgent-1",
    "action":    "tool_call",
    "tool":      "web_search",
    "args":      {"query": "quantum error correction"},
    "result":    "truncated...",
    "duration":  0.84   # seconds
}
```

**Recursion depth prevention** caps agent self-delegation at 5–15 levels depending on context.

**On-demand package installation**: if an agent requests a tool that requires an uninstalled package, the Gateway installs it dynamically rather than failing.

### Memory

`src/cmas/core/memory.py` — 10.8 KB

CMAS maintains two parallel memory stores that are searched jointly on every retrieval:

| Store | Technology | Purpose |
|---|---|---|
| Knowledge store | SQLite | Structured facts with category, topic, source, confidence (0–1), access count |
| Lessons store | SQLite | What happened + what was learned, keyed to agent types and project context |
| Vector store | ChromaDB | Semantic embedding search for fuzzy, conceptual retrieval |

Memory is **global by default** — it is not scoped to a single project. This allows knowledge gained in one project to surface as relevant context in another.

Key operations:
- `Memory.store(category, topic, content, confidence)` — write a knowledge entry
- `Memory.search(query, top_k)` — returns ranked results combining SQLite keyword match and ChromaDB cosine similarity
- `Memory.learn(what_happened, what_learned, applies_to)` — write a lesson entry
- Access counts are incremented on every retrieval, allowing the system to identify which knowledge is most frequently useful.

### Brain

`src/cmas/core/brain.py` — 25.6 KB

The Brain module implements five neuroscience-inspired subsystems that operate alongside — not instead of — the main reasoning pipeline.

<details>
<summary><strong>NeuralPathways</strong> — Hebbian agent routing</summary>

Maintains a weighted graph where nodes are agent types and edges represent "source delegated to target" relationships. Edge weights strengthen when the downstream agent produces high-quality output and decay when it fails. The Orchestrator consults pathway weights when choosing which agent type to assign a new task to.

```
weight_new = weight_old + (learning_rate * reward_signal)
weight_new = weight_new * decay_factor  # applied each cycle
```

Stored in `brain.db` (SQLite):
```sql
CREATE TABLE pathways (
    source       TEXT,
    target       TEXT,
    weight       REAL DEFAULT 0.5,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used    TIMESTAMP
);
```

</details>

<details>
<summary><strong>DopamineSystem</strong> — Reward signal and prediction error</summary>

Maintains a rolling baseline of expected quality scores. When an agent's output exceeds the baseline, a positive reward signal is emitted and pathway weights are increased. When output falls short, a negative signal triggers weight decay and may escalate to MetaCognition.

```
reward = actual_quality_score - expected_baseline
expected_baseline = baseline * 0.95 + actual_quality_score * 0.05
```

This prevents the system from calibrating to artificially low standards: as average quality improves, the baseline rises.

</details>

<details>
<summary><strong>PriorityDetector</strong> — Amygdala-like urgency detection</summary>

Scans task descriptions and user messages for urgency markers (deadlines, explicit priority language, dependency blockers). Returns a priority score that influences task queue ordering. High-urgency tasks bypass the standard FIFO queue.

</details>

<details>
<summary><strong>Consolidator</strong> — Memory compression</summary>

Periodically sweeps detailed episodic memory entries and compresses them into higher-level schemas. For example, ten separate research tasks about "distributed consensus" might consolidate into a single entry: "Distributed consensus research pattern: start with Byzantine fault tolerance literature, then cross-reference with practical implementations."

This prevents memory from growing unboundedly while preserving generalizable knowledge.

</details>

<details>
<summary><strong>DefaultModeNetwork (DMN)</strong> — Background creative synthesis</summary>

Runs on the Scheduler's proactive cycle (every 5 minutes by default when no task is active). The DMN retrieves recent memory entries and attempts creative recombination — connecting disparate concepts to generate hypotheses the user did not explicitly request. Insights are stored back into Memory with a `dmn_generated` tag.

This is the mechanism behind CMAS's proactive behavior: if you ask it to research quantum computing and later ask about error-correcting codes, there may already be a relevant DMN-synthesized entry waiting.

</details>

### Agents

`src/cmas/core/agent.py` — 17.7 KB

Three concrete agent types share a common `Agent` base class:

| Type | Specialization |
|---|---|
| `ResearchAgent` | Web search, document retrieval, fact synthesis |
| `AnalystAgent` | Code execution, data analysis, file manipulation |
| `WriterAgent` | Document generation, summarization, structured output |

Each agent runs its own sub-loop:

```
1. reason_about_task(task)
   └── retrieve memory context
   └── call reasoning.py for structured step-by-step plan
   └── identify required tools

2. act(plan)
   └── for each step: gateway.call_tool(tool, args)
   └── collect results

3. reflect(task, result)
   └── assess whether the result answers the task
   └── store new knowledge in memory
   └── return result with quality signals
```

Agents carry a `depth` counter to prevent unbounded self-delegation through `delegate_task`. The Gateway enforces a hard cap on recursion depth.

### Reasoning and Metacognition

`src/cmas/core/reasoning.py` — 13.9 KB
`src/cmas/core/metacognition.py` — 13.9 KB

**Reasoning** produces structured JSON from natural language goals:

```json
{
  "understanding": "The user wants to identify the optimal deployment strategy...",
  "assumptions":   ["Current infrastructure is cloud-based", "Cost is a priority"],
  "steps":         ["Research current deployment patterns", "Model cost scenarios", ...],
  "key_insights":  ["Blue-green deployments eliminate downtime but double infra cost"],
  "confidence":    0.82,
  "unknowns":      ["Current monthly infrastructure spend"]
}
```

Methods: `think_step_by_step()`, `hypothesize()`, `identify_cause_effect()`, `transfer_knowledge(source_domain, target_domain)`.

**MetaCognition** monitors the Orchestrator's progress across cycles and intervenes when the system is stuck:

- `reflect(history)` — analyze what approaches worked and why
- `detect_stuck(recent_scores)` — identify flat or declining quality trends
- `adapt_strategy(current_approach)` — generate alternative decomposition strategies
- `generate_novel_angles(goal)` — produce creative reframings when standard approaches fail

When MetaCognition detects a stuck state (quality delta near zero for N consecutive cycles), it signals the Orchestrator to abandon the current task tree and re-plan from a different angle.

### Scheduler

`src/cmas/core/scheduler.py` — 6 KB

Runs as a background coroutine alongside the aiohttp server. Three recurring jobs:

| Job | Interval | Purpose |
|---|---|---|
| Reminder check | 30 seconds | Fire scheduled reminders to active sessions |
| Cron executor | 30 seconds | Run user-defined cron jobs (croniter-based parsing) |
| Proactive cycle | 300 seconds (default) | Trigger DMN idle thinking |

Scheduled jobs are stored in SQLite (`data/cmas.db`) with full cron expressions, making them persistent across restarts.

---

## Tool System

`src/cmas/core/tools.py` — 9.2 KB

Eight tools are available to agents. All calls are routed through the Gateway.

| Tool | Description |
|---|---|
| `web_search` | Tavily API-based internet search. Returns ranked results with source URLs. |
| `write_file` | Create or overwrite files within the project workspace. |
| `read_file` | Read file contents. Respects workspace boundaries. |
| `list_files` | Directory listing with optional glob pattern. |
| `run_python` | Execute Python code in an isolated subprocess. Captures stdout/stderr. |
| `run_command` | Execute shell commands. Restricted by Gateway permissions. |
| `send_message` | Post a message to another agent's inbox via the Hub. |
| `delegate_task` | Spawn a specialist agent for a sub-task. Subject to recursion depth limits. |

---

## Memory Architecture

Two storage systems operate in parallel:

```
Query
  │
  ├── SQLite search (keyword + category + confidence filter)
  │     └── knowledge table
  │     └── lessons table
  │
  └── ChromaDB search (cosine similarity on embeddings)
        └── vector store (./data/vectors/)
  │
  └── Merge + rank results
        └── Return top_k entries to agent context
```

ChromaDB vectors are generated at write time. Retrieval combines both stores with a configurable blend ratio, defaulting to equal weight. Entries with higher `access_count` receive a small boost in ranking.

---

## Database Schemas

<details>
<summary><strong>Memory database</strong> — <code>data/cmas_memory.db</code></summary>

```sql
CREATE TABLE knowledge (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT,
    topic       TEXT,
    content     TEXT,
    source      TEXT,
    project     TEXT,
    confidence  REAL DEFAULT 0.8,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 0
);

CREATE TABLE lessons (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    what_happened TEXT,
    what_learned  TEXT,
    applies_to    TEXT,
    project       TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

</details>

<details>
<summary><strong>State Hub</strong> — <code>workspace/hub.db</code></summary>

```sql
CREATE TABLE projects (
    id         TEXT PRIMARY KEY,
    name       TEXT,
    focus      TEXT,
    status     TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tasks (
    id             TEXT PRIMARY KEY,
    description    TEXT,
    assigned_to    TEXT,
    status         TEXT,    -- PENDING | IN_PROGRESS | DONE | FAILED | BLOCKED | PAUSED | KILLED
    project_id     TEXT,
    result         TEXT,
    parent_task_id TEXT
);

CREATE TABLE agents (
    name         TEXT PRIMARY KEY,
    role         TEXT,
    status       TEXT,
    current_task TEXT,
    project_id   TEXT
);

CREATE TABLE messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sender    TEXT,
    recipient TEXT,
    content   TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

</details>

<details>
<summary><strong>Sessions and Scheduler</strong> — <code>data/cmas.db</code></summary>

```sql
CREATE TABLE sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT,
    project_id  TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP
);

CREATE TABLE messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    role       TEXT,   -- user | assistant | system
    content    TEXT,
    timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE scheduled_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type    TEXT,   -- reminder | cron
    description TEXT,
    schedule    TEXT,   -- ISO timestamp or cron expression
    session_id  TEXT,
    enabled     BOOLEAN DEFAULT 1,
    next_run    TIMESTAMP,
    last_run    TIMESTAMP
);
```

</details>

<details>
<summary><strong>Brain</strong> — <code>project_dir/brain.db</code></summary>

```sql
CREATE TABLE pathways (
    source        TEXT,
    target        TEXT,
    weight        REAL DEFAULT 0.5,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used     TIMESTAMP,
    PRIMARY KEY (source, target)
);
```

</details>

---

## Web Interface

`src/cmas/core/server.py` — 13.1 KB
`src/cmas/web-app/` — React 18, Vite, Tailwind CSS 4, Lucide icons

The server exposes both an HTTP API and a WebSocket endpoint:

| Route | Method | Description |
|---|---|---|
| `/ws` | WebSocket | Real-time swarm feed (audit events, task updates, agent state changes) |
| `/api/workspace` | GET | List workspace projects |
| `/api/projects` | GET / POST | Project CRUD |
| `/api/agents` | GET | Current agent status |
| `/api/tasks` | GET | Task list with status |
| `/*` | GET | Serve compiled Vite bundle |

The server binds to `localhost` only. WebSocket messages are broadcast per-project, so clients only receive events relevant to the active project.

The frontend (`App.jsx`, 64.7 KB) provides:
- Real-time agent activity feed pulled from WebSocket
- Task tree view with status indicators
- Project manager (create, switch, archive)
- Inline audit log viewer per task

Build the frontend:

```bash
cd src/cmas/web-app
npm install
npm run build
```

The compiled bundle lands in `web-app/dist/` and is served directly by the aiohttp server.

---

## Installation

**Requirements:** Python 3.9+, Node.js 18+ (for frontend build), OpenAI API key.

```bash
# Clone and enter the project
git clone https://github.com/joshdeansavv/CMAS.git
cd CMAS/MAIN_FOLDER

# Run the interactive setup wizard
# Checks Python version, creates venv, installs dependencies,
# prompts for API keys, selects models, generates config.yaml
./setup.sh

# Launch
./start.sh
```

`setup.sh` generates both `.env` and `config.yaml` from your inputs. You can re-run it at any time to reconfigure.

After launch, open `http://localhost:8080`.

---

## Configuration

Two configuration surfaces:

**`.env`** — secrets and environment-level overrides:

```bash
OPENAI_API_KEY=sk-...          # Required
TAVILY_API_KEY=tvly-...        # Optional — enables web_search tool
DISCORD_TOKEN=...              # Optional — enables Discord channel
TWILIO_ACCOUNT_SID=...         # Optional — enables WhatsApp channel
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=...
CMAS_PORT=8080
CMAS_TIMEZONE=America/New_York
```

**`config.yaml`** — runtime behavior:

```yaml
server:
  host: localhost
  port: 8080

models:
  default: gpt-4.1-nano        # Used for lightweight reasoning
  research: gpt-4.1-mini       # Used for research and analysis tasks
  temperature: 0.7

scheduler:
  proactive_interval: 300      # DMN idle cycle in seconds
  reminder_check_interval: 30

memory:
  path: ./data/cmas_memory.db
  vector_path: ./data/vectors/

workspace:
  path: ./workspace/

channels:
  web:
    enabled: true
  discord:
    enabled: false
  whatsapp:
    enabled: false
```

Configuration loading follows a precedence chain: `defaults → config.yaml → environment variables`. Environment variables always win.

---

## CLI Reference

```bash
# Start the server (default port 8080)
python3 -m cmas

# Custom port
python3 -m cmas -p 3000

# Custom config file
python3 -m cmas -c /path/to/config.yaml

# One-shot research mode (no server, no UI, prints result to stdout)
python3 -m cmas --run "Summarize recent papers on transformer attention efficiency"

# One-shot with options
python3 -m cmas --run "Goal" \
    --model gpt-4o \
    --iterations 5 \
    --human              # pause at each cycle for steering input

# Timezone override
python3 -m cmas --timezone "Europe/London"
```

One-shot mode (`--run`) bypasses the server and UI entirely. It runs the cognitive loop for the specified number of iterations and exits, writing the final output to stdout. Useful for scripting and automation.

---

## Channels

CMAS supports three input/output channels. All channels converge on the same Orchestrator and memory system.

| Channel | Status | Transport | Notes |
|---|---|---|---|
| Web | Built-in | WebSocket | No additional configuration |
| Discord | Optional | Discord Bot API | Requires `DISCORD_TOKEN` |
| WhatsApp | Optional | Twilio API | Requires Twilio credentials |

Channels are enabled in `config.yaml` and initialized at server startup. Each channel maintains its own session context but shares the global memory store.

---

## Project Structure

```
MAIN_FOLDER/
├── setup.sh                     # Interactive setup wizard
├── start.sh                     # Activate venv and launch server
├── config.example.yaml          # Annotated configuration reference
├── .env.example                 # Environment variable reference
│
└── src/cmas/
    ├── __main__.py              # Entry point (python3 -m cmas)
    ├── cli.py                   # Argument parsing
    │
    ├── core/
    │   ├── orchestrator.py      # Cognitive loop coordinator (35 KB)
    │   ├── brain.py             # NeuralPathways, Dopamine, DMN, Consolidator (26 KB)
    │   ├── chat.py              # Conversational session handler (34 KB)
    │   ├── gateway.py           # Access control, rate limiting, audit (22 KB)
    │   ├── agent.py             # Agent base class and types (18 KB)
    │   ├── reasoning.py         # Structured thinking engine (14 KB)
    │   ├── metacognition.py     # Self-awareness and strategy adaptation (14 KB)
    │   ├── state.py             # Shared state Hub, SQLite-backed (14 KB)
    │   ├── server.py            # aiohttp server and routes (13 KB)
    │   ├── memory.py            # Persistent knowledge store (11 KB)
    │   ├── tools.py             # Tool implementations (9 KB)
    │   ├── llm.py               # OpenAI client with retry logic (8 KB)
    │   ├── session.py           # Session management (8 KB)
    │   ├── scheduler.py         # Background task runner (6 KB)
    │   ├── evaluation.py        # Output quality scoring (7 KB)
    │   ├── config.py            # Config loader with precedence chain (4 KB)
    │   └── vector.py            # ChromaDB wrapper (4 KB)
    │
    ├── channels/
    │   └── web.py               # WebSocket channel handler
    │
    └── web-app/
        ├── src/App.jsx          # Main UI component (65 KB)
        ├── package.json
        └── vite.config.js
```

---

<div align="center">
<sub>Built by joshdeansavv</sub>
</div>
