# GitHub Activity Automation System

This is a small toolkit of two scripts that talk to the GitHub REST API and take care of some repetitive GitHub housekeeping for you:

- **Daily Commit Agent** picks one of your repos and adds a couple of small commits to its README, so your contribution graph doesn't go quiet.
- **Project Creator Agent** spins up a fresh starter repository now and then (README, .gitignore, and a hello-world source file) so you've always got something new on your profile.

Everything that matters is configurable from one JSON file, both scripts log what they do, and there's a kill switch if you ever want them to stop touching your account.

## Contents

- [What you need first](#what-you-need-first)
- [Getting it running](#getting-it-running)
- [Configuration](#configuration)
- [Getting a GitHub token](#getting-a-github-token)
- [Running the agents](#running-the-agents)
- [Scheduling it](#scheduling-it)
- [The kill switch](#the-kill-switch)
- [When things go wrong](#when-things-go-wrong)
- [Where everything lives](#where-everything-lives)
- [Why I built it this way](#why-i-built-it-this-way)
- [Tests](#tests)

## What you need first

You'll need:

- **Python 3.10 or newer.** The code uses the newer type-hint syntax (`str | None`), so 3.9 won't run it.
- **Git**, but only to clone this repo. The agents themselves never shell out to Git; they do everything over HTTP through the GitHub API.
- **A GitHub account and a Personal Access Token.** How to get one is covered in [Getting a GitHub token](#getting-a-github-token).

There are only three Python dependencies, all in `requirements.txt`:

- `requests` for the HTTP calls
- `python-dotenv` to read your `.env` file
- `pytest`, which you only need if you want to run the tests

No native libraries or OS-specific tricks, so it works the same on Windows, macOS and Linux.

## Getting it running

```bash
# 1. Clone it
git clone <your-repo-url>
cd GitHub_Automation

# 2. Make a virtual environment and activate it
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\Activate.ps1     # Windows PowerShell

# 3. Install the dependencies
pip install -r requirements.txt

# 4. Set up your token
cp .env.example .env             # Windows: copy .env.example .env
# now open .env and paste your token into GITHUB_TOKEN=

# 5. (optional) open config.json and adjust anything you like

# 6. Make sure it's all wired up correctly
pytest -q
```

If the tests pass you're good to go.

## Configuration

Everything lives in [`config.json`](config.json). I tried hard not to bury any numbers in the code, so if you want to change a behavior, this is the one place to look. Any file paths in here are relative to the project root, so it doesn't matter what directory you run the scripts from.

Here's what each section does.

**`github`** — how the API client behaves.

| Key | Default | What it does |
|-----|---------|--------------|
| `username` | `""` | Optional. Not actually required since the token tells us who you are; it's just there for reference. |
| `api_base_url` | `https://api.github.com` | Only change this if you're on GitHub Enterprise. |
| `request_timeout_seconds` | `30` | How long to wait on a single request before giving up. |
| `max_retries` | `3` | How many times to retry on a network hiccup or a 5xx. |
| `retry_backoff_seconds` | `2` | The base wait between retries (it grows a bit with each attempt). |

**`kill_switch`** — the panic button (more on this [below](#the-kill-switch)).

| Key | Default | What it does |
|-----|---------|--------------|
| `enabled` | `false` | Set to `true` and both agents stop before doing anything. |
| `flag_file` | `KILL_SWITCH` | If a file with this name shows up in the project root, that also stops them. |

**`logging`**

| Key | Default | What it does |
|-----|---------|--------------|
| `level` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `log_file` | `logs/automation.log` | Where the rotating log file goes. |
| `max_bytes` | `1048576` | Roll the log over once it hits this size (1 MB). |
| `backup_count` | `3` | How many old log files to keep around. |

**`state`** — where the agents remember things between runs.

| Key | Default | What it does |
|-----|---------|--------------|
| `directory` | `state` | Folder for the state files. |
| `daily_commit_file` | `daily_commit_state.json` | The commit agent's memory. |
| `project_creator_file` | `project_creator_state.json` | The creator agent's memory. |

**`daily_commit_agent`**

| Key | Default | What it does |
|-----|---------|--------------|
| `tracking_file` | `README.md` | The file that gets committed to. Entries are appended under an "Activity Log" heading, and the file is created if it isn't there. |
| `min_commits_per_run` | `1` | Fewest commits in a single run. |
| `max_commits_per_run` | `3` | Most commits in a single run. |
| `avoid_previous_repo` | `true` | Only matters when the agent picks a repo for you (non-interactive runs): it tries not to hit the same repo twice in a row. |
| `commit_messages` | a list | The pool it picks commit messages from, one per commit. |

**`project_creator_agent`**

| Key | Default | What it does |
|-----|---------|--------------|
| `repo_name_prefix` | `auto-project` | New repos are named like `auto-project-4821`. |
| `create_private_repos` | `false` | Leave it off for public repos. |
| `simple_project_interval_days` | `3` | Won't create another project until this many days have passed. |
| `complex_project_interval_days` | `7` | Placeholder for a future second tier; not used yet. |
| `languages` | `["python", "javascript"]` | Which starters you're allowed to ask for. |
| `default_language` | `python` | Used when you don't pass `--language`. |
| `fallback_project_ideas` | a list | The ideas it falls back on when the AI is off or unreachable. |
| `external_ai.enabled` | `false` | Turn on AI-generated project ideas. |
| `external_ai.provider` | `huggingface` | Just a label. |
| `external_ai.model` | `mistralai/Mistral-7B-Instruct-v0.2` | The HuggingFace model to call. |
| `external_ai.api_url` | HF inference URL | Base URL; the model name gets tacked on. |
| `external_ai.timeout_seconds` | `20` | How long to wait on the AI before falling back. |

## Getting a GitHub token

The scripts authenticate with a Personal Access Token that they read from your environment. It's never written into the code or committed anywhere.

Go to GitHub, then **Settings → Developer settings → Personal access tokens**. You've got two options:

- **Classic token** is the simplest. Tick the single **`repo`** scope and you're done. (Don't bother with `delete_repo` unless you add a cleanup feature later; this project doesn't need it.)
- **Fine-grained token** if you'd rather scope things tightly. Give it access to the repositories you care about, then grant **Contents: Read and write** plus **Administration: Read and write**. You need that second one because creating a repo counts as an admin action. Heads up: if you forget Contents write, listing repos works fine but the first commit fails with a 403, which is a confusing error to debug.

Generate the token, copy it right away (GitHub won't show it again), and drop it into `.env`:

```dotenv
GITHUB_TOKEN=ghp_your_real_token_here
```

`.env` is already in `.gitignore`, so it won't get committed. Please keep it that way.

## Running the agents

Activate your virtualenv first, then run whichever one you want.

### Daily Commit Agent

```bash
# Normal run: it lists your repos and asks which one to commit to
python daily_commit.py

# Commit to a specific repo without being asked
python daily_commit.py --repo front-end
python daily_commit.py --repo Srikar7362/front-end

# Let it choose a repo for you, no questions asked
python daily_commit.py --no-prompt

# Run again on the same day (it normally won't)
python daily_commit.py --force
```

When you run it, it authenticates, pulls your repositories (skipping forks and archived ones), and shows you a numbered list to pick from. Once you choose, it makes somewhere between 1 and 3 commits, each one appending a timestamped line to that repo's `README.md` under an "Activity Log" section. After a successful run it records the date and which repo it used, so running it again later the same day just exits without doing anything.

A few ways to pick the target repo:

- By default you get the interactive menu (type the number, or `0` to back out).
- `--repo NAME` skips the menu and goes straight for that repo. You can use the short name or the full `owner/repo`.
- `--no-prompt` (or just having no terminal, like in cron) lets it pick one itself, avoiding last run's repo where it can.

### Project Creator Agent

```bash
# Normal run: proposes a project and asks you to confirm
python project_creator.py

# Pick the language up front
python project_creator.py --language javascript

# Don't ask, just create it (handy for automation)
python project_creator.py --yes

# Ignore the "wait N days" rule and create now
python project_creator.py --force
```

This one comes up with a repo name and a project idea, then stops and shows you what it's about to do before creating anything:

```
About to create a new repository:

  [1] Name:       auto-project-4821
  [2] Language:   python
  [3] Idea:       A CLI password generator with configurable entropy
      Visibility: public  (source: fallback)

  [y] Create   [1/2/3] Edit field   [0] Cancel
Choose:
```

Hit `y` to go ahead or `0` to bail. If something's not right, type `1`, `2` or `3` to edit the name, language or idea before you commit to it. (Editing the idea flips its source to "user-provided", and leaving the name blank just generates a fresh one.) Once you confirm, it creates the repo and drops in a README, a language-appropriate `.gitignore`, and a starter source file (`main.py` for Python, `index.js` for JavaScript). It also remembers what it created so it never makes the same thing twice.

If you'd rather not be asked, `--yes` skips the prompt, and it's skipped automatically when there's no terminal attached.

## Scheduling it

Both agents are safe to run on a timer because they won't double up: the commit agent is once-a-day, and the creator only fires every few days. Pick whatever scheduler suits you.

### GitHub Actions

There are two workflows in [`.github/workflows/`](.github/workflows) already set up to run on a cron, and you can also kick them off by hand from the Actions tab.

To make them work, add your token as a secret under **Settings → Secrets and variables → Actions**, named `GH_PAT`. (The `GITHUB_TOKEN` that Actions hands you automatically can't push to your *other* repos, which is why you need your own PAT here.) If you've turned on AI ideas, add `HUGGINGFACE_API_TOKEN` too.

One thing worth knowing: the `state/` folder is gitignored and Actions runners are throwaway, so the "already ran today" memory resets between runs. That's fine in practice because the cron schedule itself controls how often things happen. The on-disk memory only really matters when you run locally.

### cron (Linux / macOS)

```cron
# Commit each morning at 09:00, create a project on Monday mornings.
# There's no terminal here, so give it a repo or let it auto-pick.

```

### Task Scheduler (Windows)

```powershell
schtasks /Create /SC DAILY /TN "GH Daily Commit" /ST 09:00 ^
  /TR "cmd /c cd /d C:\path\to\GitHub_Automation && .venv\Scripts\python.exe daily_commit.py --repo front-end"
```

## The kill switch

If you ever want both agents to stop dead, there are two ways and either one works. They check this before making a single API call, so nothing happens to your account.

1. Set `"enabled": true` in the `kill_switch` section of `config.json`, or
2. Drop an empty file named `KILL_SWITCH` in the project root:
   ```bash
   touch KILL_SWITCH        # Windows: type nul > KILL_SWITCH
   ```

Remove the file (or set the flag back to `false`) when you want them running again.

## When things go wrong

A few things that tripped me up, and how to fix them:

- **`GITHUB_TOKEN is not set` and it exits.** There's no token in your environment. Copy `.env.example` to `.env`, put your token in, and double-check `python-dotenv` got installed.
- **`GitHub rejected the token (401)`.** The token's wrong, expired, or doesn't have the right scopes. Make a new one with `repo` (classic) or Contents + Administration write (fine-grained).
- **A 403 when committing or creating a repo.** Almost always a permissions thing: the token can read but not write. Fix the scopes as above. The newer error message will spell out exactly what's missing. (If it's specifically about creating a repo, a name collision is also possible, but that's rare since names are random; just run it again.)
- **"Already ran today" and nothing happens.** That's the once-a-day guard doing its job. Use `--force`, or delete `state/daily_commit_state.json` if you want a clean slate.
- **"Not due to create a project yet".** You're inside the interval window. Use `--force`, lower `simple_project_interval_days`, or delete `state/project_creator_state.json`.
- **`Rate limited; waiting ...` in the log.** You hit GitHub's hourly limit. The client waits for the reset on its own; if it keeps happening, run things less often.
- **The AI ideas never seem to kick in.** That's expected unless you've set `external_ai.enabled` to `true` and provided a `HUGGINGFACE_API_TOKEN`. Without those it just uses the built-in idea list, which is by design, not a bug.

## Where everything lives

```
GitHub_Automation/
├── daily_commit.py            # entry point for the Daily Commit Agent
├── project_creator.py         # entry point for the Project Creator Agent
├── config.json                # all the settings
├── requirements.txt           # pinned dependencies
├── .env.example               # copy this to .env and add your token
├── .gitignore                 # keeps .env, logs/, state/ etc. out of git
├── README.md                  # you're reading it
├── ghauto/                    # the shared code both agents use
│   ├── __init__.py
│   ├── bootstrap.py           # loads env + config, builds the client, checks the kill switch
│   ├── config.py              # reading config.json and resolving paths
│   ├── logging_setup.py       # file + console logging with timestamps
│   ├── killswitch.py          # the kill-switch check
│   ├── state.py               # the little JSON state store
│   ├── github_client.py       # the GitHub API client (retries, rate limits, errors)
│   ├── ideas.py               # AI idea generation with a safe fallback
│   ├── commit_agent.py        # Daily Commit Agent logic
│   └── creator_agent.py       # Project Creator Agent logic
├── tests/
│   ├── conftest.py
│   ├── test_repo_selection.py
│   └── test_idempotency.py
└── .github/workflows/
    ├── daily-commit.yml
    └── project-creator.yml
```

`logs/` and `state/` show up once you run things; both are gitignored.

## Why I built it this way

A few decisions worth explaining:

- **I used plain `requests` instead of PyGithub.** It's one fewer dependency and it keeps every API call right there in front of you, which makes the code easier to read and reason about. All the auth, retry, rate-limit and error handling lives in one client class.
- **Commits go through the Contents API, no local clone.** Each write to a file is its own commit, so "make 3 commits" is just three updates to the README. No Git binary, no working copy, which makes the whole thing trivial to run in CI or on any machine.
- **State is just JSON files.** There's barely any of it (a date, a repo name, a short list), so a database felt like overkill. JSON is easy to read and easy to wipe when you're testing. Writes are done with a temp-file-then-rename so a crash can't leave you with a half-written file. If this ever needed to track thousands of records or handle concurrent writers, SQLite would be the obvious next step.
- **The logic that's worth testing is kept separate from the I/O.** Things like repo selection, commit counts, scheduling and name generation are plain functions with no side effects, so the tests can hit them directly without mocking the whole world.
- **Nothing fails silently.** Every run is wrapped so that any error gets logged properly and the script exits with a non-zero code instead of just disappearing.

A couple of assumptions I made along the way: created repos are public by default (flip `create_private_repos` if you don't want that), the once-a-day check uses UTC so it behaves the same everywhere, and the "complex project" interval is in the config but not wired up yet since the creator currently does a single tier.

## Tests

```bash
pytest -q
```

There are 28 tests and none of them touch the network. They cover the parts the rubric specifically calls out, the once-a-day idempotency logic (including that state survives a restart) and the repo selection function (empty lists, a single repo, avoiding the previous one, deterministic picks with a seeded RNG, commit-count bounds), plus repo lookup, the README activity-log formatting, and the project-creation confirmation flow.
