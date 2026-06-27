"""The Project Creator Agent.

Periodically creates a brand-new public repository seeded with a README,
a .gitignore and a starter source file for the selected language. It tracks
created projects locally to avoid duplicates and honours a configurable
run interval.

Pure helpers (``generate_repo_name``, ``due_to_run``, language templates)
are kept separate from the I/O-performing ``run`` function so they can be
unit-tested in isolation.
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, timezone
from typing import Any

from .github_client import GitHubClient, GitHubError
from .ideas import generate_idea
from .state import StateStore

_CREATED_PROJECTS = "created_projects"
_LAST_CREATED_DATE = "last_created_date"


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def generate_repo_name(prefix: str, existing: list[str], rng: random.Random | None = None) -> str:
    """Generate a repository name that is not already in ``existing``."""
    rng = rng or random.Random()
    existing_set = set(existing)
    for _ in range(1000):
        suffix = rng.randint(1000, 9999)
        name = f"{prefix}-{suffix}"
        if name not in existing_set:
            return name
    # Extremely unlikely fallback: timestamp-based uniqueness.
    return f"{prefix}-{int(datetime.now(timezone.utc).timestamp())}"


def due_to_run(last_created_date: str | None, interval_days: int, today: date) -> bool:
    """Return ``True`` if enough days have passed since the last creation."""
    if not last_created_date:
        return True
    try:
        last = date.fromisoformat(last_created_date)
    except ValueError:
        return True
    return (today - last).days >= max(1, int(interval_days))


def choose_language(config: dict[str, Any], requested: str | None) -> str:
    """Resolve the language to use, validating against the configured list."""
    agent_cfg = config["project_creator_agent"]
    languages = [lang.lower() for lang in agent_cfg.get("languages", ["python"])]
    default = agent_cfg.get("default_language", languages[0] if languages else "python").lower()

    if requested:
        requested = requested.lower()
        if requested not in languages:
            raise ValueError(
                f"Language {requested!r} not in configured languages: {languages}"
            )
        return requested
    return default


def confirm_project(
    name: str,
    language: str,
    idea: str,
    source: str,
    *,
    prefix: str,
    languages: list[str],
    existing: list[str],
    private: bool,
    logger: Any,
) -> tuple[str, str, str, str] | None:
    """Review and confirm the proposed project before creating it.

    Shows the proposed name, language and idea, and lets the user accept,
    edit any field, or cancel. Returns the (possibly edited)
    ``(name, language, idea, source)`` tuple, or ``None`` if cancelled.
    """
    languages = [lang.lower() for lang in languages]
    while True:
        visibility = "private" if private else "public"
        print("\nAbout to create a new repository:\n")
        print(f"  [1] Name:       {name}")
        print(f"  [2] Language:   {language}")
        print(f"  [3] Idea:       {idea}")
        print(f"      Visibility: {visibility}  (source: {source})\n")
        print("  [y] Create   [1/2/3] Edit field   [0] Cancel")

        try:
            choice = input("Choose: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if choice in ("y", "yes"):
            return name, language, idea, source
        if choice in ("0", "n", "no", "c", "cancel", "q"):
            return None

        if choice == "1":
            entered = _ask("New name (blank to auto-generate another): ")
            name = entered or generate_repo_name(prefix, existing)
        elif choice == "2":
            entered = _ask(f"Language {languages}: ").lower()
            if entered in languages:
                language = entered
            else:
                print(f"  '{entered}' is not a configured language; keeping '{language}'.")
        elif choice == "3":
            entered = _ask("New project idea: ")
            if entered:
                idea, source = entered, "user-provided"
        else:
            print("  Unrecognized choice; enter y, 1, 2, 3 or 0.")


def _ask(prompt: str) -> str:
    """Read one line of input, returning '' on EOF/interrupt."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


# --------------------------------------------------------------------------- #
# File templates
# --------------------------------------------------------------------------- #
def _readme(name: str, idea: str, language: str, source: str) -> str:
    return (
        f"# {name}\n\n"
        f"> {idea}\n\n"
        f"An auto-generated **{language}** starter project.\n\n"
        f"_Project idea source: {source}._\n\n"
        "## Getting Started\n\n"
        "This repository was scaffolded automatically. Replace this README and "
        "the starter source file with your real implementation.\n"
    )


def _gitignore(language: str) -> str:
    common = "# Editor / OS\n.DS_Store\n.idea/\n.vscode/\n*.log\n"
    if language == "python":
        return (
            "# Python\n__pycache__/\n*.py[cod]\n.venv/\nvenv/\n"
            "*.egg-info/\n.pytest_cache/\nbuild/\ndist/\n.env\n\n" + common
        )
    if language == "javascript":
        return "# Node\nnode_modules/\nnpm-debug.log*\ndist/\nbuild/\n.env\n\n" + common
    return common


def _starter_source(language: str, name: str, idea: str) -> tuple[str, str]:
    """Return ``(filename, contents)`` for the starter source file."""
    if language == "python":
        return (
            "main.py",
            (
                '"""' + f"{name}\n\n{idea}\n" + '"""\n\n\n'
                "def main() -> None:\n"
                f'    print("Hello from {name}!")\n\n\n'
                'if __name__ == "__main__":\n'
                "    main()\n"
            ),
        )
    if language == "javascript":
        return (
            "index.js",
            (
                f"// {name}\n// {idea}\n\n"
                "function main() {\n"
                f'  console.log("Hello from {name}!");\n'
                "}\n\n"
                "main();\n"
            ),
        )
    return ("README_SOURCE.txt", f"{name}: {idea}\n")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def propose_project(
    config: dict[str, Any],
    state: StateStore,
    logger: Any,
    *,
    language: str | None = None,
) -> dict[str, Any]:
    """Build a project proposal (name, language, idea) without creating anything.

    Shared by the CLI and the web UI so the user can review/edit before
    committing to creation. Reads state only; performs no GitHub writes.
    """
    agent_cfg = config["project_creator_agent"]
    chosen_language = choose_language(config, language)
    created: list[str] = list(state.get(_CREATED_PROJECTS, []))
    prefix = agent_cfg.get("repo_name_prefix", "auto-project")
    name = generate_repo_name(prefix, created)
    idea, source = generate_idea(config, logger)
    logger.info("Proposed %s project: %s (idea source: %s)", chosen_language, name, source)
    return {"name": name, "language": chosen_language, "idea": idea, "source": source}


def create_project(
    config: dict[str, Any],
    client: GitHubClient,
    state: StateStore,
    logger: Any,
    *,
    name: str,
    language: str,
    idea: str,
    source: str = "user-provided",
) -> dict[str, Any]:
    """Create the repository, seed its files and record it. Returns repo info.

    Validates the language and ensures a non-empty name. Raises ``ValueError``
    on bad input and ``GitHubError`` on API failures (callers handle these).
    """
    agent_cfg = config["project_creator_agent"]
    language = choose_language(config, language)  # validates against config
    name = (name or "").strip()
    if not name:
        raise ValueError("Repository name must not be empty.")

    user = client.get_authenticated_user()
    owner = user["login"]

    logger.info("Creating %s repository %r ...", language, name)
    repo = client.create_repo(
        name,
        description=idea[:300],
        private=agent_cfg.get("create_private_repos", False),
        auto_init=True,
    )
    repo_full = repo["full_name"]
    branch = repo.get("default_branch") or "main"
    logger.info("Created repository: %s", repo_full)

    _seed_files(client, owner, name, branch, language, idea, source, name, logger)

    created: list[str] = list(state.get(_CREATED_PROJECTS, []))
    created.append(repo_full)
    state.set(_CREATED_PROJECTS, created)
    state.set(_LAST_CREATED_DATE, datetime.now(timezone.utc).date().isoformat())
    state.save()
    logger.info("Project creation complete: %s", repo.get("html_url", repo_full))
    return repo


def run(
    config: dict[str, Any],
    client: GitHubClient,
    state: StateStore,
    logger: Any,
    *,
    language: str | None = None,
    force: bool = False,
    interactive: bool = True,
) -> int:
    """Execute the Project Creator Agent (CLI). Returns a process exit code.

    Args:
        language: Starter language (validated against config); ``None`` uses
            the configured default.
        force: Bypass the run-interval guard.
        interactive: When ``True`` and a TTY is present, show a confirmation
            prompt to review/edit the name, language and idea before creating.
    """
    agent_cfg = config["project_creator_agent"]
    today = datetime.now(timezone.utc).date()

    interval = agent_cfg.get("simple_project_interval_days", 3)
    if not force and not due_to_run(state.get(_LAST_CREATED_DATE), interval, today):
        logger.info(
            "Not due to create a project yet (interval: %d days). Use --force to override.",
            interval,
        )
        return 0

    try:
        proposal = propose_project(config, state, logger, language=language)
        name = proposal["name"]
        chosen_language = proposal["language"]
        idea = proposal["idea"]
        source = proposal["source"]

        if interactive and sys.stdin.isatty():
            decision = confirm_project(
                name,
                chosen_language,
                idea,
                source,
                prefix=agent_cfg.get("repo_name_prefix", "auto-project"),
                languages=agent_cfg.get("languages", [chosen_language]),
                existing=list(state.get(_CREATED_PROJECTS, [])),
                private=agent_cfg.get("create_private_repos", False),
                logger=logger,
            )
            if decision is None:
                logger.info("Project creation cancelled by user.")
                return 0
            name, chosen_language, idea, source = decision

        create_project(
            config,
            client,
            state,
            logger,
            name=name,
            language=chosen_language,
            idea=idea,
            source=source,
        )
        return 0

    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return 1
    except GitHubError as exc:
        logger.error("GitHub API error: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level guard; agent must not crash silently
        logger.exception("Unexpected error during project creation: %s", exc)
        return 1


def _seed_files(
    client: GitHubClient,
    owner: str,
    repo: str,
    branch: str,
    language: str,
    idea: str,
    source: str,
    name: str,
    logger: Any,
) -> None:
    """Write README.md, .gitignore and a starter source file into the new repo."""
    # README.md already exists from auto_init, so fetch its sha to overwrite.
    existing_readme = client.get_file(owner, repo, "README.md", ref=branch)
    client.put_file(
        owner,
        repo,
        "README.md",
        content=_readme(name, idea, language, source),
        message="docs: add project README",
        sha=existing_readme.get("sha") if existing_readme else None,
        branch=branch,
    )
    logger.info("Wrote README.md")

    client.put_file(
        owner,
        repo,
        ".gitignore",
        content=_gitignore(language),
        message="chore: add .gitignore",
        branch=branch,
    )
    logger.info("Wrote .gitignore")

    src_name, src_content = _starter_source(language, name, idea)
    client.put_file(
        owner,
        repo,
        src_name,
        content=src_content,
        message=f"feat: add starter {language} source",
        branch=branch,
    )
    logger.info("Wrote %s", src_name)
