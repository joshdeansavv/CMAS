"""Shared test fixtures for CMAS."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    """Ensure tests never touch real data directories or API keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    monkeypatch.setenv("CMAS_CONFIG", str(tmp_path / "config.yaml"))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


@pytest.fixture
def project_dir(tmp_path):
    """Provide a temporary project directory."""
    d = tmp_path / "test_project"
    d.mkdir()
    return d
