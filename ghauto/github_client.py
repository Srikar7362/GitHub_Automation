"""A thin GitHub REST API v3 client built on ``requests``.

Raw ``requests`` is used (rather than PyGithub) to keep dependencies light
and to make the exact API interactions explicit and easy to review. The
client centralizes authentication, retries with backoff, rate-limit
awareness and error handling so the agents stay focused on their logic.

Only the handful of endpoints the agents need are wrapped:
    * the authenticated user
    * listing repositories
    * reading and writing file contents (the Contents API)
    * creating repositories

Writing files through the Contents API means commits are created without
cloning any repository locally - each ``PUT`` to a file is one commit.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import requests


class GitHubError(Exception):
    """Raised for unrecoverable GitHub API failures."""


class GitHubAuthError(GitHubError):
    """Raised when credentials are missing or rejected (401)."""


class GitHubClient:
    """Minimal GitHub REST API client with retries and rate-limit handling."""

    def __init__(
        self,
        token: str,
        *,
        api_base_url: str = "https://api.github.com",
        timeout: int = 30,
        max_retries: int = 3,
        backoff_seconds: int = 2,
        logger: Any = None,
    ) -> None:
        if not token:
            raise GitHubAuthError(
                "No GitHub token supplied. Set GITHUB_TOKEN in your environment or .env file."
            )
        self._base = api_base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._log = logger
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "github-activity-automation",
            }
        )

    # ------------------------------------------------------------------ #
    # Low-level request helper
    # ------------------------------------------------------------------ #
    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Perform a request with retries for transient network/server errors."""
        url = path if path.startswith("http") else f"{self._base}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._session.request(
                    method, url, timeout=self._timeout, **kwargs
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                self._warn(f"Network error on {method} {url} (attempt {attempt}): {exc}")
                self._sleep_backoff(attempt)
                continue

            # Primary rate limit: 403/429 with remaining == 0.
            if response.status_code in (403, 429) and self._is_rate_limited(response):
                wait = self._rate_limit_wait(response)
                self._warn(f"Rate limited; waiting {wait}s before retry.")
                time.sleep(wait)
                continue

            # Retry transient server errors.
            if response.status_code >= 500 and attempt < self._max_retries:
                self._warn(
                    f"Server error {response.status_code} on {method} {url} "
                    f"(attempt {attempt}); retrying."
                )
                self._sleep_backoff(attempt)
                continue

            if response.status_code == 401:
                raise GitHubAuthError(
                    "GitHub rejected the token (401). Check that it is valid and has the 'repo' scope."
                )

            return response

        raise GitHubError(
            f"Request failed after {self._max_retries} attempts: {method} {url} ({last_exc})"
        )

    def _sleep_backoff(self, attempt: int) -> None:
        time.sleep(self._backoff * attempt)

    @staticmethod
    def _is_rate_limited(response: requests.Response) -> bool:
        return response.headers.get("X-RateLimit-Remaining") == "0"

    @staticmethod
    def _rate_limit_wait(response: requests.Response) -> int:
        reset = response.headers.get("X-RateLimit-Reset")
        if reset and reset.isdigit():
            return max(1, int(reset) - int(time.time()) + 1)
        return 60

    def _warn(self, message: str) -> None:
        if self._log:
            self._log.warning(message)

    @staticmethod
    def _ensure_ok(response: requests.Response, action: str) -> dict[str, Any]:
        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json().get("message", "")
            except ValueError:
                detail = response.text[:200]
            hint = ""
            if response.status_code == 403 and "not accessible by personal access token" in detail.lower():
                hint = (
                    " | HINT: your token authenticated but lacks write permission. "
                    "For a fine-grained PAT, grant 'Contents: Read and write' (and "
                    "'Administration: Read and write' to create repos) and ensure the "
                    "repository is in the token's repository access. For a classic PAT, "
                    "enable the 'repo' scope. See README -> API key setup."
                )
            raise GitHubError(f"{action} failed ({response.status_code}): {detail}{hint}")
        try:
            return response.json()
        except ValueError:
            return {}

    # ------------------------------------------------------------------ #
    # High-level endpoints
    # ------------------------------------------------------------------ #
    def get_authenticated_user(self) -> dict[str, Any]:
        """Return the authenticated user's profile (verifies the token)."""
        response = self._request("GET", "/user")
        return self._ensure_ok(response, "Fetching authenticated user")

    def list_owned_repos(
        self, *, include_forks: bool = False, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """Return repositories owned by the authenticated user.

        Forks and archived repositories are excluded by default, matching
        the Daily Commit Agent's requirement to only touch real, active
        repositories.
        """
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            response = self._request(
                "GET",
                "/user/repos",
                params={
                    "per_page": 100,
                    "page": page,
                    "affiliation": "owner",
                    "sort": "full_name",
                },
            )
            batch = self._ensure_ok(response, "Listing repositories")
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1

        return [
            repo
            for repo in repos
            if (include_forks or not repo.get("fork"))
            and (include_archived or not repo.get("archived"))
        ]

    def get_repo(self, owner: str, name: str) -> dict[str, Any] | None:
        """Return a repository, or ``None`` if it does not exist."""
        response = self._request("GET", f"/repos/{owner}/{name}")
        if response.status_code == 404:
            return None
        return self._ensure_ok(response, f"Fetching repo {owner}/{name}")

    def get_file(
        self, owner: str, repo: str, path: str, *, ref: str | None = None
    ) -> dict[str, Any] | None:
        """Return file metadata (including ``sha`` and decoded content) or ``None``."""
        params = {"ref": ref} if ref else None
        response = self._request(
            "GET", f"/repos/{owner}/{repo}/contents/{path}", params=params
        )
        if response.status_code == 404:
            return None
        data = self._ensure_ok(response, f"Reading {path}")
        if isinstance(data, dict) and data.get("content"):
            try:
                data["decoded_content"] = base64.b64decode(data["content"]).decode(
                    "utf-8", errors="replace"
                )
            except (ValueError, TypeError):
                data["decoded_content"] = ""
        return data

    def put_file(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        content: str,
        message: str,
        sha: str | None = None,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a file. Each call produces exactly one commit."""
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha
        if branch:
            payload["branch"] = branch

        response = self._request(
            "PUT", f"/repos/{owner}/{repo}/contents/{path}", json=payload
        )
        return self._ensure_ok(response, f"Committing {path}")

    def create_repo(
        self,
        name: str,
        *,
        description: str = "",
        private: bool = False,
        auto_init: bool = True,
    ) -> dict[str, Any]:
        """Create a repository under the authenticated user's account."""
        payload = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
        }
        response = self._request("POST", "/user/repos", json=payload)
        return self._ensure_ok(response, f"Creating repository {name}")
