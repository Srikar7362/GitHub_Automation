"""Configuration loading.

All tunable parameters live in ``config.json`` (see the project root).
This module loads that file once and exposes it as a plain dictionary, with
a couple of convenience accessors. Keeping configuration in one place means
no agent ever hardcodes a "magic number".
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# The project root is the parent of this package directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load and return the configuration dictionary.

    Args:
        path: Optional path to a config file. Defaults to ``config.json``
            in the project root, or the ``GHAUTO_CONFIG`` environment
            variable if set.

    Raises:
        ConfigError: if the file is missing or contains invalid JSON.
    """
    config_path = Path(path or os.environ.get("GHAUTO_CONFIG") or DEFAULT_CONFIG_PATH)

    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(config, dict):
        raise ConfigError(f"Configuration root must be an object: {config_path}")

    # Remember where we loaded from so relative paths resolve correctly.
    config["_config_path"] = str(config_path)
    config["_project_root"] = str(config_path.resolve().parent)
    return config


def resolve_path(config: dict[str, Any], relative: str) -> Path:
    """Resolve a config-relative path against the project root.

    Paths in the config file (log files, state directories, the kill-switch
    flag) are interpreted relative to the project root so the system works
    regardless of the current working directory.
    """
    root = Path(config.get("_project_root", PROJECT_ROOT))
    candidate = Path(relative)
    return candidate if candidate.is_absolute() else root / candidate
