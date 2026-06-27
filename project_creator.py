#!/usr/bin/env python3
"""Entry point for the Project Creator Agent.

Usage:
    python project_creator.py [--language python|javascript] [--force]

See README.md for full documentation.
"""

from __future__ import annotations

import argparse
import sys

from ghauto.bootstrap import build_context
from ghauto.creator_agent import run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a new GitHub repository seeded with starter files."
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language for the starter project (must be in config 'languages'). "
        "Defaults to config 'default_language'.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the run-interval guard and create a project now (for testing).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt and create immediately (for automation).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config, client, state, logger = build_context("project_creator", "project_creator_file")
    return run(
        config,
        client,
        state,
        logger,
        language=args.language,
        force=args.force,
        interactive=not args.yes,
    )


if __name__ == "__main__":
    sys.exit(main())
