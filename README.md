<div align="center">
  <h1>CMAS - Cognitive Multi-Agent System</h1>
  <h3>An autonomous, steerable agentic framework powered by cognitive architecture.</h3>

  <p>
    <a href="#"><img alt="License" src="https://img.shields.io/badge/License-Non--Commercial-blue.svg"></a>
    <a href="#"><img alt="Python version" src="https://img.shields.io/badge/python-3.9+-blue.svg"></a>
    <a href="#"><img alt="React UI" src="https://img.shields.io/badge/UI-React%20%2B%20Vite-61DAFB?logo=react&logoColor=white"></a>
    <a href="#"><img alt="Stars" src="https://img.shields.io/github/stars/joshdeansavv/CMAS?style=social"></a>
  </p>
</div>

---

**CMAS** is an advanced, persistent Artificial General Intelligence (AGI) framework designed to run continuously. It seamlessly manages specialized sub-agents, executes deep-dive multi-stage research operations, safely interacts with isolated file systems, and continuously learns from interactions via localized dopamine-reward pathways and an autonomous Curiosity Engine.

## Overview

Unlike standard reactive chatbots, CMAS is built on a proactive, neuroscience-inspired cognitive loop. 

* **Complete Autonomy:** Engineered for persistent, background task execution.
* **Brain-Inspired Architecture:** Integrates Hebbian learning algorithms and Default-Mode Network (DMN) states for idle-time self-improvement and memory abstraction.
* **Live Steerability:** Interrupt the cognitive reasoning loop at any point to force a course correction without terminating the core process.
* **Open & Private:** No forced cloud vendors. Securely proxy the orchestrator through your own `.env` configuration to use OpenAI, Local HuggingFace TGI endpoints, or Ollama servers.

---

## Quick Start

Initialize the CMAS framework via the interactive setup wizard.

```bash
# 1. Clone the repository
git clone https://github.com/joshdeansavv/CMAS.git
cd CMAS

# 2. Run the automated interactive wizard
./setup.sh

# 3. Boot the environment
./start.sh
```

---

## How it Works

CMAS replaces standard linear dialogue generation with a highly recursive, autonomous intelligence loop modeled specifically after biological cognition. 

When a user submits a prompt, the system does not simply output text. Instead:
1. **Perception & Threat Assessment:** The Gateway hub normalizes the input and processes it through a Somatic Marker (Priority Detector) which determines the urgency and structural depth required to answer it.
2. **Context Hydration:** The memory layer cross-references both the immediate `Working Memory` buffer and the vectorized `Semantic Memory` (ChromaDB) to load associated facts and user preferences natively.
3. **Agent Delegation:** The central Orchestrator constructs a topological plan and spawns highly specialized temporary sub-agents (e.g., `ResearchAgent`, `AnalystAgent`) to execute structural tools on its behalf.
4. **Execution & Circuit Breaking:** Tools are invoked locally, monitored by hardware anti-spam heuristics to ensure recursive depth loops are abruptly severed if they begin hallucinating.

---

## Why it Works

The fundamental thesis of CMAS relies on shifting execution away from pre-trained static logic and into dynamic, self-correcting memory networks.

CMAS is successful because it is mathematically engineered to learn autonomously:
* **Hebbian Pathway Weighting:** When agents collaborate successfully, the system adjusts relational weights (`W = W + alpha * Error`), meaning efficient routing logic becomes statistically more likely in the future.
* **Dopamine Prediction Errors:** Before executing a heavy functional block, CMAS "guesses" its likelihood of success. By comparing the expectation against the actual execution, it calculates a formal prediction error, updating its baseline heuristics autonomously.
* **Idle-Time Curiosity Engine:** Through the Default Mode Network (DMN), CMAS recognizes its own knowledge gaps. While the user is not actively chatting, it recursively pulls Wikipedia and academic literature (via Tavily) to formulate synthetic schemas, abstracting them into permanent memory vectors.

---

## Tool Integrations & Tavily Suggestion

CMAS operates natively with deep execution capabilities out of the box (e.g., executing Python, sandboxed terminal access). However, its intelligence shines when tethered to high-quality external search architecture.

<details>
<summary><strong>Required: Tavily Search API</strong></summary>

We explicitly suggest and implement **Tavily API** for our deep research agents. Standard search interfaces (Google Custom Search, Bing) return algorithmic UI data that confuses agent ingestion. Tavily is purpose-built to return synthesized, factual extraction blocks, allowing CMAS to rapidly index search materials without exhausting LLM context limits.

Get an API key at [tavily.com](https://tavily.com/) and place it inside your `.env` as `TAVILY_API_KEY`.
</details>

<details>
<summary><strong>Local Operating System Mutability</strong></summary>

CMAS features strict hardware isolation per session. Native `read_file`, `write_file`, and `run_python` commands are structurally jailed within a generated `/workspace/` subfolder, preventing the framework from corrupting host registries or arbitrarily deleting vital system elements.
</details>

---

## Platform Ecosystem

The framework is composed of autonomous nodes, dynamic channels, and observability interfaces.

### Integration Channels
Data streams sync universally across all connected endpoints.
* **WebChat:** Locally hosted Vite/React GUI via `http://localhost:8080`.
* **Discord:** Native bot integration via `@Mentions` and Direct Messages.
* **WhatsApp:** Enterprise hooks via the Twilio messaging layer.

### Applications & Nodes
* **Live Observability HUD:** The React web app directly streams gateway events, rendering internal loop thoughts and tool callbacks without mutating the active chat.
* **Agent System Roster:** Observe independent sub-agents scale up and terminate dynamically in response to varying load requirements.
* **Background Scheduler:** Dispatch automated chron-jobs via natural language input.

---

## Is it AI? (Frequently Asked Questions)

<details>
<summary><strong>Is CMAS considered "AGI" (Artificial General Intelligence)?</strong></summary>

CMAS is not a sentient entity, but it utilizes standard AGI architectural paradigms to mimic robust autonomy. While the underlying inference engine (e.g., GPT-4o, Llama) remains narrow AI, the cognitive wrappers bridging vector memory, dynamic agent-spawning, and continual-learning abstractions allow CMAS to exhibit profound generalized competence without fixed logic constraints. 
</details>

<details>
<summary><strong>Is CMAS just a "wrapper" over OpenAI?</strong></summary>

No. A wrapper simply takes an input string and funnels it to an API. CMAS operates a locally-hosted, complex psychological state machine. The LLM simply provides the "syntactic capability", while CMAS provides the Memory, Heuristics, Curiosity Mapping, Hardware Tool Execution, and Routing logic. You can entirely unplug OpenAI and run CMAS using offline/local HuggingFace models through the `personality.yaml` settings.
</details>

<details>
<summary><strong>Can I stop CMAS once it spirals out of control?</strong></summary>

Yes. The **Live Steerability** mechanics natively integrated into the Web UI act as interactive circuit breakers. Bypassing the conversational node entirely, the `Steer` command forces a hardware interrupt on the async event loop, forcing the orchestrator to dynamically ingest your localized command and shift trajectory mid-thought.
</details>

---

## Technical Foundations Summary

CMAS logic is fundamentally mapped to verified academic architectures:

| Concept | Source | Engineering Implementation |
|---------|--------|--------------------------|
| Hebbian learning | *Hebb (1949)* | Neural pathway structural weighting |
| Dopamine prediction error | *Schultz (1997)* | Heuristic-driven strategy modification |
| Somatic markers | *Damasio (1994)* | Fast-path threat and priority assessment |
| Default Mode Network | *Raichle (2001)* | Autonomous Background Exploration Agent |
| Creative cognition | *Beaty (2018)* | Cross-domain episodic insight synthesis |
| Complementary Learning | *McClelland (1995)* | Long-term memory vector compression |

---

<div align="center">
  <i>Developed algorithmically by joshdeansavv. Released under a Non-Commercial Open-Source License to ensure ethical deployment.</i>
</div>
