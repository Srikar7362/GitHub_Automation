"""Shared startup logic for both agent entry points.

Loads environment variables (including a local ``.env``), the config file
and the GitHub token, wires up logging, checks the kill switch, and builds
an authenticated :class:`GitHubClient`. Centralizing this keeps the two
entry-point scripts tiny and consistent.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from .config import ConfigError, load_config
from .github_client import GitHubAuthError, GitHubClient
from .killswitch import is_engaged
from .logging_setup import setup_logging
from .state import StateStore

try:  # python-dotenv is optional but recommended.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - handled gracefully
    load_dotenv = None


def load_environment() -> None:
    """Load variables from a ``.env`` file if python-dotenv is installed."""
    if load_dotenv is not None:
        load_dotenv()


def build_context(logger_name: str, state_key: str) -> tuple[
    dict[str, Any], GitHubClient, StateStore, Any
]:
    """Prepare config, GitHub client, state store and logger for an agent.

    Exits the process with a clear message if configuration, credentials or
    the kill switch prevent the agent from running.

    Args:
        logger_name: Name for this agent's logger.
        state_key: Config key under ``state`` naming this agent's state file.
    """
    load_environment()

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    logger = setup_logging(config, logger_name)

    engaged, reason = is_engaged(config)
    if engaged:
        logger.warning("Kill switch engaged (%s). Exiting without any API calls.", reason)
        sys.exit(0)

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error(
            "GITHUB_TOKEN is not set. Add it to your environment or a .env file. "
            "See README for how to create a token."
        )
        sys.exit(2)

    gh_cfg = config.get("github", {})
    try:
        client = GitHubClient(
            token,
            api_base_url=gh_cfg.get("api_base_url", "https://api.github.com"),
            timeout=int(gh_cfg.get("request_timeout_seconds", 30)),
            max_retries=int(gh_cfg.get("max_retries", 3)),
            backoff_seconds=int(gh_cfg.get("retry_backoff_seconds", 2)),
            logger=logger,
        )
    except GitHubAuthError as exc:
        logger.error("%s", exc)
        sys.exit(2)

    state_filename = config.get("state", {}).get(state_key, f"{logger_name}_state.json")
    state = StateStore(config, state_filename)

    return config, client, state, logger
