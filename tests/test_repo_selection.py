"""Tests for the repository selection logic of the Daily Commit Agent."""

from __future__ import annotations

import random

from ghauto.commit_agent import (
    _append_activity,
    decide_commit_count,
    find_repo_by_name,
    select_repository,
)


def _repos(*names: str) -> list[dict]:
    return [{"full_name": n, "name": n.split("/")[-1]} for n in names]


def test_returns_none_for_empty_list() -> None:
    assert select_repository([], None) is None


def test_single_repo_is_always_chosen_even_if_previous() -> None:
    repos = _repos("user/only")
    chosen = select_repository(repos, "user/only", avoid_previous=True)
    assert chosen["full_name"] == "user/only"


def test_avoids_previous_repo_when_alternatives_exist() -> None:
    repos = _repos("user/a", "user/b")
    rng = random.Random(0)
    # Run many times; the previous repo must never be selected.
    for _ in range(50):
        chosen = select_repository(repos, "user/a", avoid_previous=True, rng=rng)
        assert chosen["full_name"] == "user/b"


def test_can_select_previous_when_avoidance_disabled() -> None:
    repos = _repos("user/a", "user/b")
    rng = random.Random(1)
    seen = {select_repository(repos, "user/a", avoid_previous=False, rng=rng)["full_name"]
            for _ in range(50)}
    assert "user/a" in seen  # avoidance off => previous is eligible


def test_deterministic_with_seeded_rng() -> None:
    repos = _repos("user/a", "user/b", "user/c")
    first = select_repository(repos, None, rng=random.Random(42))
    second = select_repository(repos, None, rng=random.Random(42))
    assert first["full_name"] == second["full_name"]


def test_decide_commit_count_within_bounds() -> None:
    rng = random.Random(7)
    for _ in range(100):
        count = decide_commit_count(1, 3, rng=rng)
        assert 1 <= count <= 3


def test_decide_commit_count_clamps_invalid_range() -> None:
    # min below 1 and max below min should still yield a sane value.
    assert decide_commit_count(0, 0) == 1
    assert decide_commit_count(5, 2) == 5


def test_find_repo_by_short_name() -> None:
    repos = _repos("user/front-end", "user/back-end")
    assert find_repo_by_name(repos, "front-end")["full_name"] == "user/front-end"


def test_find_repo_by_full_name_case_insensitive() -> None:
    repos = _repos("user/front-end", "user/back-end")
    assert find_repo_by_name(repos, "USER/BACK-END")["full_name"] == "user/back-end"


def test_find_repo_returns_none_when_absent() -> None:
    repos = _repos("user/front-end")
    assert find_repo_by_name(repos, "nope") is None


def test_append_activity_adds_header_to_empty_readme() -> None:
    out = _append_activity("", "- entry 1\n")
    assert "## Activity Log" in out
    assert out.rstrip().endswith("- entry 1")


def test_append_activity_reuses_existing_header() -> None:
    base = "# My Project\n\n## Activity Log\n\n- old entry\n"
    out = _append_activity(base, "- new entry\n")
    # Header must not be duplicated.
    assert out.count("## Activity Log") == 1
    assert out.rstrip().endswith("- new entry")
