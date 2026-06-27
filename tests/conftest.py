"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def temp_config(tmp_path: Path) -> dict:
    """A minimal config dict rooted at a temporary directory."""
    return {
        "_project_root": str(tmp_path),
        "state": {
            "directory": "state",
            "daily_commit_file": "daily_commit_state.json",
            "project_creator_file": "project_creator_state.json",
        },
        "kill_switch": {"enabled": False, "flag_file": "KILL_SWITCH"},
        "daily_commit_agent": {
            "tracking_file": "activity.log",
            "min_commits_per_run": 1,
            "max_commits_per_run": 3,
            "avoid_previous_repo": True,
            "commit_messages": ["chore: test"],
        },
        "project_creator_agent": {
            "repo_name_prefix": "auto-project",
            "languages": ["python", "javascript"],
            "default_language": "python",
            "simple_project_interval_days": 3,
            "fallback_project_ideas": ["A test idea"],
            "external_ai": {"enabled": False},
        },
    }


@pytest.fixture()
def write_config(tmp_path: Path, temp_config: dict) -> Path:
    """Write temp_config to disk and return its path."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps(temp_config), encoding="utf-8")
    return path
