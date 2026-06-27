"""Persistent state.

State must survive process restarts (last run date, last targeted repo,
the set of already-created projects), so it is stored as JSON files on disk.

Why JSON files rather than SQLite or a database? The data is tiny
(a handful of keys and a short list), human-readable JSON makes the state
trivial to inspect and reset during development, and it adds zero
dependencies. SQLite would be the next step if state grew to thousands of
records or needed concurrent writers, neither of which applies here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import resolve_path


class StateStore:
    """A small JSON-backed key/value store for a single agent."""

    def __init__(self, config: dict[str, Any], filename: str) -> None:
        state_dir = resolve_path(config, config.get("state", {}).get("directory", "state"))
        state_dir.mkdir(parents=True, exist_ok=True)
        self._path: Path = state_dir / filename
        self._data: dict[str, Any] = self._read()

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable state should not crash an agent; start
            # fresh rather than propagate. The caller's logging will note it
            # via the empty return.
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def save(self) -> None:
        """Atomically persist the current state to disk."""
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2, sort_keys=True)
        tmp_path.replace(self._path)

    @property
    def path(self) -> Path:
        return self._path
