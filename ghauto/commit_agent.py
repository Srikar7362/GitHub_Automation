"""The Daily Commit Agent.

Makes a small, configurable number of commits to the README of a
user-selected repository, keeping the contribution graph active. Before
committing it lists the user's repositories and asks which one to target
(or accepts a repo name non-interactively via ``--repo``). The agent is
idempotent: running it more than once on the same day is a no-op unless
``--force`` is supplied.

The module is split into pure, testable helpers (``today_str``,
``already_ran_today``, ``select_repository``, ``find_repo_by_name``,
``decide_commit_count``) and a single orchestrating ``run`` function that
performs I/O.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timezone
from typing import Any

from .github_client import GitHubClient, GitHubError
from .state import StateStore

_LAST_RUN_DATE = "last_run_date"
_LAST_REPO = "last_repo"
_ACTIVITY_HEADER = "## Activity Log"


def today_str() -> str:
    """Return today's date (UTC) as an ISO ``YYYY-MM-DD`` string."""
    return datetime.now(timezone.utc).date().isoformat()


def already_ran_today(state: StateStore, today: str) -> bool:
    """Return ``True`` if a successful run has already happened today."""
    return state.get(_LAST_RUN_DATE) == today


def find_repo_by_name(
    repos: list[dict[str, Any]], name: str
) -> dict[str, Any] | None:
    """Find a repository by short name or ``owner/name`` (case-insensitive)."""
    needle = name.strip().lower()
    for repo in repos:
        if repo.get("name", "").lower() == needle or repo.get("full_name", "").lower() == needle:
            return repo
    return None


def select_repository(
    repos: list[dict[str, Any]],
    previous_repo: str | None,
    *,
    avoid_previous: bool = True,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Pick a repository at random, avoiding ``previous_repo`` when possible.

    Used as the non-interactive fallback (e.g. scheduled runs without a
    ``--repo`` argument). Interactive runs use ``prompt_repo_selection``.

    Args:
        repos: Candidate repositories (each a dict with at least ``full_name``).
        previous_repo: ``full_name`` targeted on the previous run, if any.
        avoid_previous: When ``True``, exclude ``previous_repo`` unless it is
            the only candidate.
        rng: Optional random source (injected for deterministic tests).

    Returns:
        The chosen repository dict, or ``None`` if ``repos`` is empty.
    """
    if not repos:
        return None

    rng = rng or random.Random()
    candidates = repos
    if avoid_previous and previous_repo and len(repos) > 1:
        filtered = [r for r in repos if r.get("full_name") != previous_repo]
        if filtered:
            candidates = filtered

    return rng.choice(candidates)


def prompt_repo_selection(
    repos: list[dict[str, Any]], logger: Any
) -> dict[str, Any] | None:
    """Print a numbered list of repos and ask the user to choose one.

    Returns the chosen repository dict, or ``None`` if the user cancels.
    Reads from stdin via ``input()``; the caller is responsible for
    ensuring an interactive terminal is available.
    """
    print("\nSelect a repository to commit to:\n")
    for index, repo in enumerate(repos, start=1):
        visibility = "private" if repo.get("private") else "public"
        print(f"  [{index:>2}] {repo['full_name']} ({visibility})")
    print("  [ 0] Cancel\n")

    while True:
        try:
            raw = input(f"Enter a number (0-{len(repos)}): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            logger.info("Selection cancelled by user.")
            return None

        if not raw.isdigit():
            print("  Please enter a valid number.")
            continue

        choice = int(raw)
        if choice == 0:
            logger.info("Selection cancelled by user.")
            return None
        if 1 <= choice <= len(repos):
            return repos[choice - 1]
        print(f"  Out of range. Choose between 0 and {len(repos)}.")


def decide_commit_count(
    min_commits: int, max_commits: int, rng: random.Random | None = None
) -> int:
    """Return how many commits to make this run, clamped to a sane range."""
    low = max(1, int(min_commits))
    high = max(low, int(max_commits))
    rng = rng or random.Random()
    return rng.randint(low, high)


def _activity_entry(index: int, count: int) -> str:
    """Build a single Markdown activity line for one commit."""
    stamp = datetime.now(timezone.utc).isoformat()
    return f"- {stamp} - automated activity commit {index}/{count}\n"


def _append_activity(content: str, entry: str) -> str:
    """Append an activity entry to README content under an Activity Log section."""
    if _ACTIVITY_HEADER not in content:
        separator = "" if content.endswith("\n\n") or content == "" else (
            "\n" if content.endswith("\n") else "\n\n"
        )
        content += f"{separator}{_ACTIVITY_HEADER}\n\n"
    elif not content.endswith("\n"):
        content += "\n"
    return content + entry


def _resolve_target(
    repos: list[dict[str, Any]],
    *,
    repo_name: str | None,
    interactive: bool,
    state: StateStore,
    agent_cfg: dict[str, Any],
    logger: Any,
) -> dict[str, Any] | None:
    """Resolve which repository to target, or ``None`` to abort cleanly."""
    if repo_name:
        chosen = find_repo_by_name(repos, repo_name)
        if not chosen:
            logger.error(
                "Requested repository %r not found among your %d eligible repos.",
                repo_name,
                len(repos),
            )
        return chosen

    if interactive and sys.stdin.isatty():
        return prompt_repo_selection(repos, logger)

    # Non-interactive and no --repo given: fall back to safe random selection.
    logger.info(
        "No --repo given and no interactive terminal; selecting a repository automatically."
    )
    return select_repository(
        repos,
        state.get(_LAST_REPO),
        avoid_previous=agent_cfg.get("avoid_previous_repo", True),
    )


def run(
    config: dict[str, Any],
    client: GitHubClient,
    state: StateStore,
    logger: Any,
    *,
    force: bool = False,
    repo_name: str | None = None,
    interactive: bool = True,
) -> int:
    """Execute the Daily Commit Agent.

    Args:
        force: Bypass the once-per-day idempotency guard.
        repo_name: Target a specific repo by name (skips the prompt).
        interactive: When ``True`` and a TTY is present, prompt the user to
            choose a repository.

    Returns a process exit code (0 = success / no-op, non-zero = error).
    """
    agent_cfg = config["daily_commit_agent"]
    today = today_str()

    if not force and already_ran_today(state, today):
        logger.info("Already ran today (%s); nothing to do. Use --force to override.", today)
        return 0

    try:
        user = client.get_authenticated_user()
        owner = user["login"]
        logger.info("Authenticated as %s", owner)

        repos = client.list_owned_repos()
        logger.info("Found %d eligible (non-fork, non-archived) repositories.", len(repos))
        if not repos:
            logger.warning("No eligible repositories to commit to. Exiting.")
            return 0

        chosen = _resolve_target(
            repos,
            repo_name=repo_name,
            interactive=interactive,
            state=state,
            agent_cfg=agent_cfg,
            logger=logger,
        )
        if not chosen:
            logger.info("No repository selected; nothing to do.")
            return 0

        repo = chosen["name"]
        repo_full = chosen["full_name"]
        branch = chosen.get("default_branch") or "main"
        logger.info("Selected repository: %s (branch: %s)", repo_full, branch)

        count = decide_commit_count(
            agent_cfg.get("min_commits_per_run", 1),
            agent_cfg.get("max_commits_per_run", 3),
        )
        logger.info("Will make %d commit(s) this run.", count)

        tracking_file = agent_cfg["tracking_file"]
        messages = agent_cfg.get("commit_messages") or ["chore: update README activity log"]

        _make_commits(
            client, owner, repo, branch, tracking_file, messages, count, logger
        )

        state.set(_LAST_RUN_DATE, today)
        state.set(_LAST_REPO, repo_full)
        state.save()
        logger.info("Run complete. Made %d commit(s) to %s.", count, repo_full)
        return 0

    except GitHubError as exc:
        logger.error("GitHub API error: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level guard; agent must not crash silently
        logger.exception("Unexpected error during commit run: %s", exc)
        return 1


def _make_commits(
    client: GitHubClient,
    owner: str,
    repo: str,
    branch: str,
    tracking_file: str,
    messages: list[str],
    count: int,
    logger: Any,
) -> str | None:
    """Append ``count`` activity entries to the README, one commit each.

    Returns the URL of the last commit (or ``None`` if unavailable).
    """
    existing = client.get_file(owner, repo, tracking_file, ref=branch)
    content = existing.get("decoded_content", "") if existing else ""
    sha = existing.get("sha") if existing else None
    last_commit_url: str | None = None

    for index in range(1, count + 1):
        content = _append_activity(content, _activity_entry(index, count))
        message = random.choice(messages)
        result = client.put_file(
            owner,
            repo,
            tracking_file,
            content=content,
            message=message,
            sha=sha,
            branch=branch,
        )
        # The new blob sha is required for the next update in the loop.
        sha = result.get("content", {}).get("sha")
        last_commit_url = result.get("commit", {}).get("html_url") or last_commit_url
        logger.info("Commit %d/%d: %r", index, count, message)

    return last_commit_url


def commit_to_repo(
    config: dict[str, Any],
    client: GitHubClient,
    state: StateStore,
    logger: Any,
    *,
    repo: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    """Commit to an already-chosen repository (used by the web UI).

    ``repo`` is a repository dict (as returned by ``list_owned_repos``).
    Honours the once-per-day guard unless ``force`` is set. Returns a result
    dict describing what happened. Raises ``GitHubError`` on API failure.
    """
    agent_cfg = config["daily_commit_agent"]
    today = today_str()

    if not force and already_ran_today(state, today):
        return {
            "status": "skipped",
            "reason": f"Already ran today ({today}). Enable 'force' to override.",
        }

    user = client.get_authenticated_user()
    owner = user["login"]
    repo_name = repo["name"]
    repo_full = repo["full_name"]
    branch = repo.get("default_branch") or "main"

    count = decide_commit_count(
        agent_cfg.get("min_commits_per_run", 1),
        agent_cfg.get("max_commits_per_run", 3),
    )
    logger.info("Committing %d time(s) to %s (branch: %s).", count, repo_full, branch)

    tracking_file = agent_cfg["tracking_file"]
    messages = agent_cfg.get("commit_messages") or ["chore: update README activity log"]
    commit_url = _make_commits(
        client, owner, repo_name, branch, tracking_file, messages, count, logger
    )

    state.set(_LAST_RUN_DATE, today)
    state.set(_LAST_REPO, repo_full)
    state.save()
    logger.info("Run complete. Made %d commit(s) to %s.", count, repo_full)
    return {
        "status": "committed",
        "repo": repo_full,
        "branch": branch,
        "count": count,
        "file": tracking_file,
        "commit_url": commit_url,
    }
