# GitHub Activity Automation System

Two configurable, idempotent automation agents that interact with the GitHub REST API: a **Daily Commit Agent** that keeps your contribution graph active by committing to the **README** of a repository you choose from an interactive list, and a **Project Creator Agent** that periodically scaffolds brand-new starter repositories. Everything is driven by a single config file, guarded by a kill switch, and logged to file and stdout.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Setup](#setup)
3. [Configuration guide](#configuration-guide)
4. [API key setup](#api-key-setup)
5. [Running the agents](#running-the-agents)
6. [Scheduling](#scheduling)
7. [Kill switch](#kill-switch)
8. [Troubleshooting](#troubleshooting)
9. [Project structure](#project-structure)
10. [Design decisions](#design-decisions)
11. [Tests](#tests)

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | Uses modern type-hint syntax (`str \| None`). |
| pip | any recent | To install dependencies. |
| Git | 2.x | Only needed to clone the repo / for scheduling. The agents themselves talk to GitHub over HTTP and do **not** shell out to Git. |
| A GitHub account | — | With a Personal Access Token (see [API key setup](#api-key-setup)). |

Python dependencies (installed via `requirements.txt`):

- `requests` — HTTP client for the GitHub REST API.
- `python-dotenv` — loads the `.env` file.
- `pytest` — test runner (only needed to run the test suite).

No OS-specific dependencies; runs on Windows, macOS and Linux.

---

## Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd GitHub_Automation

# 2. Create and activate a virtual environment
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env from the template and add your token
cp .env.example .env          # Windows: copy .env.example .env
#   then edit .env and set GITHUB_TOKEN=...

# 5. (Optional) set your username and tweak settings in config.json

# 6. Verify the install
pytest -q
```

---

## Configuration guide

All tunable parameters live in [`config.json`](config.json) — no values are hardcoded in the Python source. Paths are resolved relative to the project root.

### `github`

| Key | Default | Description |
|-----|---------|-------------|
| `username` | `""` | Optional. Informational only; the authenticated user is resolved from the token. |
| `api_base_url` | `https://api.github.com` | GitHub API root. Change only for GitHub Enterprise. |
| `request_timeout_seconds` | `30` | Per-request timeout. |
| `max_retries` | `3` | Retry attempts for network/5xx errors. |
| `retry_backoff_seconds` | `2` | Base backoff; wait grows linearly per attempt. |

### `kill_switch`

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | If `true`, both agents exit immediately without any API calls. |
| `flag_file` | `KILL_SWITCH` | If a file with this name exists in the project root, the agents also halt. |

### `logging`

| Key | Default | Description |
|-----|---------|-------------|
| `level` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `log_file` | `logs/automation.log` | Rotating log file path. |
| `max_bytes` | `1048576` | Rotate the log after this many bytes (1 MB). |
| `backup_count` | `3` | Number of rotated log files to keep. |

### `state`

| Key | Default | Description |
|-----|---------|-------------|
| `directory` | `state` | Directory for persisted state files. |
| `daily_commit_file` | `daily_commit_state.json` | Daily Commit Agent state filename. |
| `project_creator_file` | `project_creator_state.json` | Project Creator Agent state filename. |

### `daily_commit_agent`

| Key | Default | Description |
|-----|---------|-------------|
| `tracking_file` | `README.md` | File committed to in the target repo. Activity entries are appended under an "Activity Log" section. Created if missing. |
| `min_commits_per_run` | `1` | Minimum commits per run. |
| `max_commits_per_run` | `3` | Maximum commits per run. |
| `avoid_previous_repo` | `true` | Only used for automatic (non-interactive) selection: avoids re-targeting the last run's repo when alternatives exist. |
| `commit_messages` | list | Pool of commit messages; one is drawn at random per commit. |

### `project_creator_agent`

| Key | Default | Description |
|-----|---------|-------------|
| `repo_name_prefix` | `auto-project` | Prefix for generated repo names (e.g. `auto-project-4821`). |
| `create_private_repos` | `false` | If `true`, created repos are private. The assessment asks for public repos. |
| `simple_project_interval_days` | `3` | Minimum days between project creations (the run-interval guard). |
| `complex_project_interval_days` | `7` | Reserved for a future "complex project" tier. |
| `languages` | `["python","javascript"]` | Languages selectable for starter projects. |
| `default_language` | `python` | Language used when `--language` is omitted. |
| `fallback_project_ideas` | list | Built-in ideas used when external AI is off/unavailable. |
| `external_ai.enabled` | `false` | Enable external AI idea generation. |
| `external_ai.provider` | `huggingface` | Provider label (informational). |
| `external_ai.model` | `mistralai/Mistral-7B-Instruct-v0.2` | Model for the HuggingFace Inference API. |
| `external_ai.api_url` | HF inference URL | Base URL; the model name is appended. |
| `external_ai.timeout_seconds` | `20` | Timeout for the external AI call. |

---

## API key setup

The agents authenticate with a **GitHub Personal Access Token (PAT)** read from the environment — it is never hardcoded or committed.

1. Sign in to GitHub → **Settings** → **Developer settings** → **Personal access tokens**.
2. Choose a token type:
   - **Fine-grained token** (recommended): set **Repository access** to *All repositories* (or select the ones you want), and under **Permissions → Repository permissions** grant **Contents: Read and write** and **Administration: Read and write** (the latter is needed to create repositories).
   - **Classic token**: select the **`repo`** scope (full control of private repositories). Only add **`delete_repo`** if you build a cleanup feature — this project does not require it.
3. Generate the token and **copy it immediately** (you cannot view it again).
4. Put it in your `.env` file:

   ```dotenv
   GITHUB_TOKEN=ghp_your_real_token_here
   ```

   `.env` is listed in [`.gitignore`](.gitignore) and must never be committed.

> **Minimum scopes:** `repo` (classic) or *Contents: write* + *Administration: write* (fine-grained). The Project Creator needs repository-creation permission; the Daily Commit Agent needs contents write.

---

## Running the agents

Activate your virtual environment first, then:

### Daily Commit Agent

```bash
# Normal run - lists your repos and asks which one to commit to
python daily_commit.py

# Target a specific repo by name and skip the prompt (great for automation)
python daily_commit.py --repo front-end
python daily_commit.py --repo Srikar7362/front-end

# Skip the prompt and let the agent auto-select a repo
python daily_commit.py --no-prompt

# Bypass the once-per-day guard (for testing)
python daily_commit.py --force
```

What it does: authenticates, lists your non-forked / non-archived repositories, and **asks you to choose one** (enter the number shown, or `0` to cancel). It then makes 1–3 commits that append timestamped entries to that repo's **`README.md`** (under an "Activity Log" section). It records the date and target so re-running the same day does nothing.

**Selecting the repository:**
- **Interactive** (default): you get a numbered menu and pick one.
- **`--repo NAME`**: target a specific repo (by short name or `owner/repo`), no prompt.
- **`--no-prompt`** or **no terminal** (e.g. cron/CI): the agent auto-selects a repo, avoiding the previous run's repo when possible.

### Project Creator Agent

```bash
# Use the default language from config; no-op if not yet due.
# Shows a confirmation prompt before creating.
python project_creator.py

# Choose a language explicitly
python project_creator.py --language javascript

# Skip the confirmation prompt and create immediately (for automation)
python project_creator.py --yes

# Bypass the interval guard and create now (for testing)
python project_creator.py --force
```

What it does: proposes a new public repo named `<prefix>-<random>` with a generated project idea, **asks you to confirm or edit it**, then creates the repo and seeds it with `README.md`, `.gitignore` and a starter source file for the chosen language. It optionally generates the idea via an external AI (with graceful fallback), and records the repo so it is never recreated.

**Confirmation prompt:** before creating anything, the agent shows the proposed name, language and idea and lets you accept, edit any field, or cancel:

```
About to create a new repository:

  [1] Name:       auto-project-4821
  [2] Language:   python
  [3] Idea:       A CLI password generator with configurable entropy
      Visibility: public  (source: fallback)

  [y] Create   [1/2/3] Edit field   [0] Cancel
Choose:
```

- Press **`y`** to create, **`0`** to cancel.
- Enter **`1`**, **`2`** or **`3`** to edit the name, language or idea (editing the idea marks its source as *user-provided*; a blank name auto-generates a new one).
- The prompt is skipped with **`--yes`**, or automatically when there is no terminal (cron/CI).

---

## Scheduling

Pick whichever fits your environment. The agents are safe to run repeatedly — their idempotency / interval guards make extra runs no-ops.

### GitHub Actions (included)

Two workflows live in [`.github/workflows/`](.github/workflows). They run on a cron and can be triggered manually from the **Actions** tab.

1. In your repo: **Settings → Secrets and variables → Actions → New repository secret**.
2. Add `GH_PAT` = your PAT (the built-in `GITHUB_TOKEN` cannot push to *other* repos, so a PAT is required). Optionally add `HUGGINGFACE_API_TOKEN`.
3. The workflows are enabled automatically once pushed.

> **Note on state in CI:** the `state/` directory is git-ignored and CI runners are ephemeral, so the once-per-day / interval guards reset each run. That is fine because the cron itself controls frequency (the daily workflow runs once per day). For *local* scheduling, on-disk state fully enforces idempotency.

### cron (Linux / macOS)

```cron
# Daily commit at 09:00; project creator each Monday at 09:05.
# cron has no terminal, so pass --repo (or rely on automatic selection).
0 9 * * *  cd /path/to/GitHub_Automation && .venv/bin/python daily_commit.py --repo front-end >> logs/cron.log 2>&1
5 9 * * 1  cd /path/to/GitHub_Automation && .venv/bin/python project_creator.py --yes >> logs/cron.log 2>&1
```

### Task Scheduler (Windows)

```powershell
# Daily commit every day at 09:00
schtasks /Create /SC DAILY /TN "GH Daily Commit" /ST 09:00 ^
  /TR "cmd /c cd /d C:\path\to\GitHub_Automation && .venv\Scripts\python.exe daily_commit.py --repo front-end"
```

---

## Kill switch

Two ways to halt **both** agents immediately — they exit cleanly *before* making any API calls:

1. **Config flag:** set `"enabled": true` under `kill_switch` in `config.json`.
2. **Flag file:** create an empty file named `KILL_SWITCH` in the project root:
   ```bash
   touch KILL_SWITCH        # Windows: type nul > KILL_SWITCH
   ```
   Delete the file (or set the flag back to `false`) to resume.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `GITHUB_TOKEN is not set` (exit 2) | No token in environment / `.env`. | Create `.env` from `.env.example` and set `GITHUB_TOKEN`. Confirm `python-dotenv` is installed. |
| `GitHub rejected the token (401)` | Token invalid, expired, or wrong scopes. | Regenerate the PAT with the `repo` scope (classic) or Contents + Administration write (fine-grained). |
| `... failed (403)` when creating a repo | Token lacks repo-creation permission, or a repo with that name exists. | Grant Administration/`repo` permission; the name generator avoids known duplicates but a manual collision can still occur — just re-run. |
| Agent says *"Already ran today"* and does nothing | Idempotency guard already recorded today's run. | Use `--force`, or delete `state/daily_commit_state.json`. |
| *"Not due to create a project yet"* | Within the configured interval. | Use `--force`, lower `simple_project_interval_days`, or delete `state/project_creator_state.json`. |
| `Rate limited; waiting ...` in logs | Hit GitHub's hourly rate limit. | The client waits automatically for the reset; reduce run frequency if persistent. |
| External AI never used | `external_ai.enabled` is `false` or no `HUGGINGFACE_API_TOKEN`. | Enable it in config and set the token; otherwise the built-in idea list is used (this is expected, not an error). |

---

## Project structure

```
GitHub_Automation/
├── daily_commit.py            # CLI entry point for the Daily Commit Agent
├── project_creator.py         # CLI entry point for the Project Creator Agent
├── config.json                # All configuration (the single source of truth)
├── requirements.txt           # Pinned Python dependencies
├── .env.example               # Template for secrets (copy to .env)
├── .gitignore                 # Excludes .env, logs/, state/, KILL_SWITCH, venvs
├── README.md                  # This file
├── ghauto/                    # Shared package used by both agents
│   ├── __init__.py
│   ├── bootstrap.py           # Loads env/config, builds client, checks kill switch
│   ├── config.py              # Config loading and path resolution
│   ├── logging_setup.py       # Rotating file + stdout logging with timestamps
│   ├── killswitch.py          # Kill-switch detection (config flag or flag file)
│   ├── state.py               # JSON-backed persistent state store
│   ├── github_client.py       # GitHub REST API v3 client (retries, rate limits)
│   ├── ideas.py               # External-AI idea generation with graceful fallback
│   ├── commit_agent.py        # Daily Commit Agent logic (pure helpers + run)
│   └── creator_agent.py       # Project Creator Agent logic (pure helpers + run)
├── tests/                     # Pytest suite
│   ├── conftest.py            # Shared fixtures
│   ├── test_repo_selection.py # Repo selection + commit-count logic
│   └── test_idempotency.py    # Once-per-day guard, scheduling, state persistence
└── .github/workflows/         # Optional GitHub Actions schedules
    ├── daily-commit.yml
    └── project-creator.yml
```

Generated at runtime (git-ignored): `logs/`, `state/`.

---

## Design decisions

- **Raw `requests` over PyGithub.** Keeps dependencies minimal and makes every API interaction explicit and reviewable. The client centralizes auth, retries with linear backoff, rate-limit waiting and error handling.
- **Commits via the Contents API, no local clone.** Each `PUT` to a file is exactly one commit, so making *N* commits is *N* updates to the tracking file — no Git binary or working tree required, which keeps CI and cross-platform use trivial.
- **JSON files for state.** The data is tiny (a few keys, one short list) and benefits from being human-readable and trivially resettable. Writes are atomic (temp file + rename). SQLite would be the next step only if state grew large or needed concurrency.
- **Pure helpers separated from I/O.** Selection, counting, scheduling and name generation are side-effect-free functions, which is what the tests exercise directly.
- **Fail loud in logs, never crash silently.** Every agent run is wrapped in a top-level guard that logs the error and returns a non-zero exit code.

### Assumptions

- "Public repositories" is the default for created projects (toggleable via `create_private_repos`).
- The once-per-day guard uses **UTC** dates for consistency across machines/CI.
- The "complex project" tier (`complex_project_interval_days`) is wired into config but the current creator produces a single starter tier; extending it is straightforward.

---

## Tests

```bash
pytest -q
```

Covers the bonus-rubric items — the **idempotency logic** (once-per-day guard, state persistence across restarts, creator interval scheduling) and the **repository selection function** (empty list, single-repo, previous-repo avoidance, deterministic seeding, commit-count bounds) — plus repo lookup, README activity-log formatting and the project-creation confirmation flow. 28 tests, no network access required.
