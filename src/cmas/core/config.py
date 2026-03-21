"""Configuration loader with sane defaults. Works without a config file."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Optional: yaml support
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from dotenv import load_dotenv
load_dotenv()

# Project root: src/cmas/core/config.py -> parents[3] = project root
BASE_DIR = Path(__file__).resolve().parents[3]

DEFAULTS = {
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
    },
    "model": {
        "default": "gpt-4.1-nano",
        "research": "gpt-4.1-mini",
        "temperature": 0.7,
        "base_url": None,
    },
    "timezone": None,
    "channels": {
        "web": {"enabled": True},
        "discord": {"enabled": False, "token": ""},
        "whatsapp": {
            "enabled": False,
            "twilio_sid": "",
            "twilio_token": "",
            "phone": "",
        },
    },
    "memory": {
        "vector_db_path": str(BASE_DIR / ".c2_mission_data" / "vectors"),
        "sqlite_path": str(BASE_DIR / ".c2_mission_data" / "hub.db"),
        "max_context_messages": 50,
    },
    "scheduler": {
        "enabled": True,
        "proactive_interval": 300,
    },
    "workspace": {
        "base_dir": str(BASE_DIR / ".c2_mission_workspace"),
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


class Config:
    """Loads config from YAML file (optional) merged with env vars and defaults."""

    def __init__(self, path: Optional[str] = None):
        raw = {}
        config_path = path or os.getenv("CMAS_CONFIG", "config.yaml")
        if HAS_YAML and Path(config_path).exists():
            with open(config_path) as f:
                raw = yaml.safe_load(f) or {}

        self._data = _deep_merge(DEFAULTS, raw)

        # Env var overrides (highest priority)
        self.openai_key = os.getenv("OPENAI_API_KEY") or ""
        self.tavily_key = os.getenv("TAVILY_API_KEY") or ""

        # Server
        self.host = self._data["server"]["host"]
        self.port = int(os.getenv("CMAS_PORT", self._data["server"]["port"]))

        # Models
        self.model = self._data["model"]["default"]
        self.research_model = self._data["model"]["research"]
        self.temperature = self._data["model"]["temperature"]
        self.base_url = os.getenv("OPENAI_BASE_URL", self._data["model"].get("base_url"))

        # Timezone
        self.timezone = os.getenv("CMAS_TIMEZONE") or self._data.get("timezone")

        # Channels
        self.channels = self._data["channels"]
        self.discord_enabled = self.channels["discord"]["enabled"]
        self.discord_token = (
            os.getenv("DISCORD_TOKEN") or self.channels["discord"]["token"]
        )
        self.whatsapp_enabled = self.channels["whatsapp"]["enabled"]

        # Memory
        mem = self._data["memory"]
        self.vector_db_path = mem["vector_db_path"]
        self.sqlite_path = mem["sqlite_path"]
        self.max_context_messages = mem["max_context_messages"]

        # Scheduler
        sched = self._data["scheduler"]
        self.scheduler_enabled = sched["enabled"]
        self.proactive_interval = sched["proactive_interval"]

        # Workspace
        self.workspace_dir = Path(self._data["workspace"]["base_dir"])

        # Ensure data directories exist
        Path(self.vector_db_path).mkdir(parents=True, exist_ok=True)
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def get(self, dotted_key: str, default=None):
        """Get a nested config value like 'server.port'."""
        keys = dotted_key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val
