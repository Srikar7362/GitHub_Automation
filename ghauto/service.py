"""Web-facing service layer.

The CLI bootstrap (``ghauto.bootstrap``) calls ``sys.exit`` and prompts on
stdin, which is wrong for a long-running web server. This module wraps the
same agent logic in functions that return plain data structures and raise
:class:`ServiceError` instead of exiting, so a Flask (or any) frontend can
call them and turn the result into JSON.

Each call builds a fresh config/client/state so the server always reflects
the latest config and on-disk state, and concurrent requests don't share
mutable objects.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

from . import commit_agent, creator_agent
from .bootstrap import load_environment
from .config import ConfigError, load_config, resolve_path
from .github_client import GitHubAuthError, GitHubClient, GitHubError
from .killswitch import is_engaged
from .logging_setup import setup_logging
from .state import StateStore

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"


class ServiceError(Exception):
    """A user-facing error with an HTTP-ish status code."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@contextmanager
def _capture(logger: logging.Logger) -> Iterator[list[str]]:
    """Collect this logger's records during a block into a list of strings."""
    records: list[str] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(self.format(record))

    handler = _ListHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


def _context() -> tuple[dict[str, Any], logging.Logger]:
    """Load config + logger (no client; used for read-only/status calls)."""
    load_environment()
    try:
        config = load_config()
    except ConfigError as exc:
        raise ServiceError(f"Configuration error: {exc}", status=500) from exc
    logger = setup_logging(config, "webapp")
    return config, logger


def _client(config: dict[str, Any], logger: logging.Logger) -> GitHubClient:
    """Build an authenticated GitHub client, or raise ServiceError."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ServiceError(
            "GITHUB_TOKEN is not set. Add it to your .env file (see the token guide).",
            status=400,
        )
    gh_cfg = config.get("github", {})
    try:
        return GitHubClient(
            token,
            api_base_url=gh_cfg.get("api_base_url", "https://api.github.com"),
            timeout=int(gh_cfg.get("request_timeout_seconds", 30)),
            max_retries=int(gh_cfg.get("max_retries", 3)),
            backoff_seconds=int(gh_cfg.get("retry_backoff_seconds", 2)),
            logger=logger,
        )
    except GitHubAuthError as exc:
        raise ServiceError(str(exc), status=401) from exc


def _state(config: dict[str, Any], key: str) -> StateStore:
    filename = config.get("state", {}).get(key)
    return StateStore(config, filename)


def _guard_kill_switch(config: dict[str, Any]) -> None:
    engaged, reason = is_engaged(config)
    if engaged:
        raise ServiceError(f"Kill switch is engaged ({reason}). Actions are blocked.", status=423)


# --------------------------------------------------------------------------- #
# Public operations
# --------------------------------------------------------------------------- #
def get_status() -> dict[str, Any]:
    """Return overall status: token presence, kill switch, who we are, config bits."""
    config, logger = _context()
    engaged, reason = is_engaged(config)
    token_present = bool(os.environ.get("GITHUB_TOKEN"))

    user_login: str | None = None
    user_error: str | None = None
    if token_present:
        try:
            user = _client(config, logger).get_authenticated_user()
            user_login = user.get("login")
        except (ServiceError, GitHubError) as exc:
            user_error = str(getattr(exc, "message", exc))

    creator_cfg = config.get("project_creator_agent", {})
    return {
        "token_present": token_present,
        "user": user_login,
        "user_error": user_error,
        "kill_switch": {"engaged": engaged, "reason": reason},
        "languages": creator_cfg.get("languages", ["python"]),
        "default_language": creator_cfg.get("default_language", "python"),
        "last_commit_repo": _state(config, "daily_commit_file").get("last_repo"),
        "last_commit_date": _state(config, "daily_commit_file").get("last_run_date"),
        "created_projects": _state(config, "project_creator_file").get("created_projects", []),
    }


def list_repositories() -> list[dict[str, Any]]:
    """Return the user's eligible repositories, trimmed to UI-relevant fields."""
    config, logger = _context()
    client = _client(config, logger)
    try:
        repos = client.list_owned_repos()
    except GitHubError as exc:
        raise ServiceError(str(exc), status=502) from exc
    return [
        {
            "name": r["name"],
            "full_name": r["full_name"],
            "private": bool(r.get("private")),
            "default_branch": r.get("default_branch") or "main",
            "html_url": r.get("html_url"),
        }
        for r in repos
    ]


def run_daily_commit(repo_full_name: str, *, force: bool = False) -> dict[str, Any]:
    """Commit to the chosen repository. Returns result + captured log lines."""
    config, logger = _context()
    _guard_kill_switch(config)
    if not repo_full_name:
        raise ServiceError("Please choose a repository first.")

    client = _client(config, logger)
    state = _state(config, "daily_commit_file")

    repo = commit_agent.find_repo_by_name(list_owned_dicts(client), repo_full_name)
    if not repo:
        raise ServiceError(f"Repository {repo_full_name!r} not found among your repos.", status=404)

    with _capture(logger) as logs:
        try:
            result = commit_agent.commit_to_repo(config, client, state, logger, repo=repo, force=force)
        except GitHubError as exc:
            raise ServiceError(str(exc), status=502) from exc
    result["logs"] = logs
    return result


def list_owned_dicts(client: GitHubClient) -> list[dict[str, Any]]:
    """Full repo dicts (with default_branch) needed for committing."""
    try:
        return client.list_owned_repos()
    except GitHubError as exc:
        raise ServiceError(str(exc), status=502) from exc


def propose_project(language: str | None = None) -> dict[str, Any]:
    """Return a project proposal (name, language, idea, source) for review."""
    config, logger = _context()
    state = _state(config, "project_creator_file")
    try:
        with _capture(logger) as logs:
            proposal = creator_agent.propose_project(config, state, logger, language=language)
    except ValueError as exc:
        raise ServiceError(str(exc)) from exc
    proposal["logs"] = logs
    proposal["languages"] = config.get("project_creator_agent", {}).get("languages", ["python"])
    return proposal


def create_project(*, name: str, language: str, idea: str, source: str = "user-provided") -> dict[str, Any]:
    """Create the repository from reviewed values. Returns repo info + logs."""
    config, logger = _context()
    _guard_kill_switch(config)
    client = _client(config, logger)
    state = _state(config, "project_creator_file")

    with _capture(logger) as logs:
        try:
            repo = creator_agent.create_project(
                config, client, state, logger,
                name=name, language=language, idea=idea, source=source,
            )
        except ValueError as exc:
            raise ServiceError(str(exc)) from exc
        except GitHubError as exc:
            raise ServiceError(str(exc), status=502) from exc

    return {
        "full_name": repo.get("full_name"),
        "html_url": repo.get("html_url"),
        "logs": logs,
    }


def set_kill_switch(engaged: bool) -> dict[str, Any]:
    """Engage/disengage the kill switch via its flag file. Returns new status."""
    config, _ = _context()
    flag_name = config.get("kill_switch", {}).get("flag_file", "KILL_SWITCH")
    flag_path = resolve_path(config, flag_name)
    if engaged:
        flag_path.touch(exist_ok=True)
    elif flag_path.exists():
        flag_path.unlink()
    now_engaged, reason = is_engaged(config)
    return {"engaged": now_engaged, "reason": reason}


def tail_log(lines: int = 200) -> list[str]:
    """Return the last ``lines`` lines of the configured log file."""
    config, _ = _context()
    log_file = resolve_path(config, config.get("logging", {}).get("log_file", "logs/automation.log"))
    if not log_file.exists():
        return []
    with log_file.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read().splitlines()[-lines:]
