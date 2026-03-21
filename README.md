# CMAS — Cognitive Multi-Agent System

**An always-on agentic chatbot with brain-inspired intelligence. Chat with it, give it tasks, set reminders — it thinks, learns, and acts autonomously.**

CMAS is a persistent AI assistant that runs 24/7. It can search the web, run code, manage files, set reminders, launch deep research investigations, and learn from every interaction. Access it through a built-in web UI, Discord, or WhatsApp.

---

## Quick Start

```bash
git clone <repo-url> && cd CMAS
./setup.sh           # Interactive setup — API keys, channels, timezone
./start.sh           # Start the server
# Open http://localhost:8080
```

That's it. The setup wizard walks you through everything.

---

## What It Can Do

**Chat naturally** — ask questions, get help, have conversations

**Take actions** — search the web, write files, run shell commands, execute Python

**Remember things** — "remember that my server IP is 10.0.0.5" — persistent across sessions

**Set reminders** — "remind me to check the deploy in 30 minutes"

**Schedule tasks** — "every morning at 9am, check for new security advisories"

**Deep research** — "do a deep research on quantum computing advances" — launches a full multi-agent investigation with research, analysis, and synthesis agents

**Run 24/7** — background scheduler handles reminders, cron jobs, and proactive creative thinking

---

## Channels

| Channel | Setup | Description |
|---------|-------|-------------|
| **Web UI** | Always on | Chat at `http://localhost:8080` |
| **Discord** | Optional | Bot responds to DMs and mentions |
| **WhatsApp** | Optional | Via Twilio webhook |

Configure channels during `./setup.sh` or edit `config.yaml`.

---

## Architecture

### Cognitive Loop
```
PERCEIVE → PLAN → EXECUTE → EVALUATE → REFLECT → LEARN
    ↑                                                 |
    └─────────────── iterate ─────────────────────────┘
```

### Brain Systems
- **Neural Pathways** — Hebbian learning: strategies that work get stronger
- **Dopamine System** — prediction error signals drive learning
- **Priority Detection** — fast threat/importance assessment
- **Memory Consolidation** — extracts reusable strategy schemas after tasks
- **Default Mode Network** — background creative thinking during idle time

### System Modules

```
src/cmas/
├── core/
│   ├── orchestrator.py    # Cognitive loop coordinator
│   ├── agent.py           # Agent REASON → ACT → REFLECT loop
│   ├── brain.py           # Neural pathways, dopamine, DMN
│   ├── reasoning.py       # Chain-of-thought, hypothesis generation
│   ├── metacognition.py   # Self-reflection, stuck detection
│   ├── evaluation.py      # 5-dimension quality scoring
│   ├── gateway.py         # Access control, rate limiting, audit
│   ├── chat.py            # Conversational chat handler
│   ├── server.py          # aiohttp HTTP/WebSocket server
│   ├── memory.py          # Persistent knowledge store + vector search
│   ├── scheduler.py       # Background reminders, cron, proactive tasks
│   ├── llm.py             # OpenAI client with retry/fallback
│   ├── tools.py           # Web search, file ops, Python exec
│   ├── config.py          # YAML config with defaults
│   ├── session.py         # Conversation history manager
│   ├── state.py           # SQLite task/message hub
│   └── vector.py          # ChromaDB semantic search
├── channels/
│   ├── web.py             # WebSocket chat handler
│   ├── discord_bot.py     # Discord adapter
│   └── whatsapp.py        # WhatsApp via Twilio
└── web/
    ├── index.html          # Chat UI
    ├── style.css
    └── app.js
```

---

## Configuration

### Manual Setup (alternative to ./setup.sh)

```bash
# 1. Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Create .env (see .env.example)
cp .env.example .env
# Edit .env with your API keys

# 3. Optionally create config.yaml (see config.example.yaml)
cp config.example.yaml config.yaml

# 4. Start
./start.sh
```

### One-Shot Research Mode

Run a single research task without starting the server:

```bash
./start.sh --run "Research the latest advances in quantum computing"
./start.sh --run "Analyze the EV battery market" -m gpt-4.1-mini -i 5
```

---

## Research Foundations

| Concept | Source | Implementation |
|---------|--------|---------------|
| Hebbian learning | Hebb (1949) | Neural pathway weight updates |
| Dopamine prediction error | Schultz (1997) | Reward-driven strategy learning |
| Somatic markers | Damasio (1994) | Fast priority/threat assessment |
| Default Mode Network | Raichle (2001) | Background creative processing |
| Creative cognition | Beaty (2018) | Cross-domain insight generation |
| Complementary Learning | McClelland (1995) | Memory consolidation + schemas |

---

## License

This project is under active development.
