"""Tests for the once-per-day idempotency logic and project-creator scheduling."""

from __future__ import annotations

import logging
from datetime import date

from ghauto.commit_agent import already_ran_today, today_str
from ghauto.creator_agent import (
    confirm_project,
    due_to_run,
    generate_repo_name,
)
from ghauto.state import StateStore

_LOGGER = logging.getLogger("test")


def _confirm(responses, **overrides):
    """Run confirm_project with a scripted sequence of input() responses."""
    import builtins

    answers = iter(responses)
    original = builtins.input
    builtins.input = lambda *_a, **_k: next(answers)
    try:
        kwargs = dict(
            name="auto-project-1234",
            language="python",
            idea="A starter idea",
            source="fallback",
            prefix="auto-project",
            languages=["python", "javascript"],
            existing=[],
            private=False,
            logger=_LOGGER,
        )
        kwargs.update(overrides)
        return confirm_project(
            kwargs.pop("name"),
            kwargs.pop("language"),
            kwargs.pop("idea"),
            kwargs.pop("source"),
            **kwargs,
        )
    finally:
        builtins.input = original


def test_already_ran_today_false_for_fresh_state(temp_config: dict) -> None:
    state = StateStore(temp_config, "daily_commit_state.json")
    assert already_ran_today(state, today_str()) is False


def test_already_ran_today_true_after_recording_run(temp_config: dict) -> None:
    state = StateStore(temp_config, "daily_commit_state.json")
    today = today_str()
    state.set("last_run_date", today)
    state.save()

    # A freshly loaded store must see the persisted date (survives restart).
    reloaded = StateStore(temp_config, "daily_commit_state.json")
    assert already_ran_today(reloaded, today) is True


def test_already_ran_today_false_for_different_day(temp_config: dict) -> None:
    state = StateStore(temp_config, "daily_commit_state.json")
    state.set("last_run_date", "2000-01-01")
    state.save()
    assert already_ran_today(state, today_str()) is False


def test_state_persists_across_instances(temp_config: dict) -> None:
    store = StateStore(temp_config, "project_creator_state.json")
    store.set("created_projects", ["user/auto-project-1234"])
    store.save()

    reloaded = StateStore(temp_config, "project_creator_state.json")
    assert reloaded.get("created_projects") == ["user/auto-project-1234"]


def test_due_to_run_true_when_never_run() -> None:
    assert due_to_run(None, 3, date(2026, 6, 28)) is True


def test_due_to_run_false_within_interval() -> None:
    assert due_to_run("2026-06-27", 3, date(2026, 6, 28)) is False


def test_due_to_run_true_after_interval() -> None:
    assert due_to_run("2026-06-25", 3, date(2026, 6, 28)) is True


def test_due_to_run_handles_corrupt_date() -> None:
    assert due_to_run("not-a-date", 3, date(2026, 6, 28)) is True


def test_generate_repo_name_avoids_existing() -> None:
    existing = [f"prefix-{i}" for i in range(1000, 2000)]
    name = generate_repo_name("prefix", existing)
    assert name not in existing
    assert name.startswith("prefix-")


def test_confirm_accept_returns_unchanged() -> None:
    result = _confirm(["y"])
    assert result == ("auto-project-1234", "python", "A starter idea", "fallback")


def test_confirm_cancel_returns_none() -> None:
    assert _confirm(["0"]) is None
    assert _confirm(["n"]) is None


def test_confirm_edit_language_then_accept() -> None:
    name, language, idea, source = _confirm(["2", "javascript", "y"])
    assert language == "javascript"


def test_confirm_rejects_unknown_language_keeps_current() -> None:
    name, language, idea, source = _confirm(["2", "rust", "y"])
    assert language == "python"  # unchanged


def test_confirm_edit_idea_marks_source_user_provided() -> None:
    name, language, idea, source = _confirm(["3", "My custom idea", "y"])
    assert idea == "My custom idea"
    assert source == "user-provided"


def test_confirm_edit_name() -> None:
    name, language, idea, source = _confirm(["1", "my-cool-repo", "y"])
    assert name == "my-cool-repo"


def test_confirm_blank_name_autogenerates() -> None:
    name, language, idea, source = _confirm(["1", "", "y"], prefix="gen")
    assert name.startswith("gen-")
