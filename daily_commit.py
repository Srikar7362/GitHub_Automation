#!/usr/bin/env python3
"""Entry point for the Daily Commit Agent.

Usage:
    python daily_commit.py [--force]

See README.md for full documentation.
"""

from __future__ import annotations

import argparse
import sys

from ghauto.bootstrap import build_context
from ghauto.commit_agent import run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Make 1-3 commits to a chosen GitHub repository's README, once per day."
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Target this repository by name ('repo' or 'owner/repo') and skip the "
        "interactive prompt. Useful for scheduled/non-interactive runs.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt for a repository; select one automatically. "
        "Ignored when --repo is given.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the once-per-day idempotency guard (for testing).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config, client, state, logger = build_context("daily_commit", "daily_commit_file")
    return run(
        config,
        client,
        state,
        logger,
        force=args.force,
        repo_name=args.repo,
        interactive=not args.no_prompt,
    )


if __name__ == "__main__":
    sys.exit(main())
