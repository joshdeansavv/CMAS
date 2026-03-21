"""CMAS CLI — server mode (default) or one-shot research mode."""
from __future__ import annotations

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _project_root() -> Path:
    """Resolve project root (directory containing src/)."""
    return Path(__file__).resolve().parents[2]


def get_project_dir(topic: str) -> Path:
    """Create a project directory for a research task."""
    safe_name = "".join(c if c.isalnum() or c in " _-" else "" for c in topic)
    safe_name = safe_name.strip().replace(" ", "_")[:60]
    return _project_root() / "data" / "projects" / f"project_{safe_name}"


async def run_server(config_path: str = None, port: int = None):
    """Start the always-on CMAS server."""
    from cmas.core.config import Config
    from cmas.core.server import CMASServer

    config = Config(config_path)
    if port:
        config.port = port

    server = CMASServer(config)
    await server.start()


async def run_once(goal: str, model: str = "gpt-4.1-nano", iterations: int = 3,
                   max_agents: int = 4, human: bool = False, timezone: str = None):
    """Run a single research task (one-shot mode)."""
    from cmas.core.orchestrator import Orchestrator

    project_dir = get_project_dir(goal)

    print(f"\n  CMAS — One-Shot Research Mode")
    print(f"  {'─'*40}")
    print(f"  Goal: {goal}")
    print(f"  Model: {model}")
    print(f"  Project dir: {project_dir}")
    print()

    orchestrator = Orchestrator(
        project_dir=project_dir,
        model=model,
        agent_model=model,
        max_iterations=iterations,
        max_concurrent_agents=max_agents,
        human_in_the_loop=human,
        local_timezone=timezone,
    )

    result = await orchestrator.run(goal)
    print(f"\n{'─'*60}")
    print("FINAL OUTPUT:")
    print(f"{'─'*60}")
    print(result)
    print(f"\nReport saved to: {project_dir / 'final_report.md'}")
    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="CMAS — Always-On Agentic Chatbot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""modes:
  Server (default):
    cmas                               Start the chatbot server
    cmas -p 3000                       Start on port 3000
    cmas -c config.yaml                Use custom config file

  One-shot research:
    cmas --run "Research quantum computing advances"
    cmas --run "Analyze EV market" -m gpt-4.1-mini

setup:
  1. ./setup.sh                        Interactive first-run setup
  2. ./start.sh                        Start the server
  3. Open http://localhost:8080         Chat in your browser
""",
    )
    parser.add_argument("-c", "--config", default=None,
                        help="Config file path (default: config.yaml)")
    parser.add_argument("-p", "--port", type=int, default=None,
                        help="Override server port")

    parser.add_argument("--run", type=str, default=None, metavar="GOAL",
                        help="Run a single research task instead of starting the server")
    parser.add_argument("-m", "--model", default="gpt-4.1-nano",
                        help="LLM model (default: gpt-4.1-nano)")
    parser.add_argument("-i", "--iterations", type=int, default=3,
                        help="Max iterations for one-shot mode (default: 3)")
    parser.add_argument("--human", action="store_true",
                        help="Enable human-in-the-loop (one-shot mode)")
    parser.add_argument("--timezone", type=str, default=None,
                        help="Timezone, e.g. America/New_York")

    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set.")
        print("Run ./setup.sh or add it to .env")
        sys.exit(1)

    if args.run:
        asyncio.run(run_once(
            args.run, args.model, args.iterations,
            human=args.human, timezone=args.timezone,
        ))
    else:
        asyncio.run(run_server(args.config, args.port))
