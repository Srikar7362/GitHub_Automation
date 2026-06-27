"""Kill switch.

A safety mechanism that lets an operator halt both agents immediately
without editing code. The switch is considered *engaged* if either:

* the ``kill_switch.enabled`` config key is ``true``, or
* the flag file named by ``kill_switch.flag_file`` exists on disk.

Agents check this before making any API calls and exit cleanly when it is
engaged.
"""

from __future__ import annotations

from typing import Any

from .config import resolve_path


def is_engaged(config: dict[str, Any]) -> tuple[bool, str]:
    """Return ``(engaged, reason)`` describing the kill-switch state."""
    kill_config = config.get("kill_switch", {})

    if kill_config.get("enabled"):
        return True, "kill_switch.enabled is true in config"

    flag_name = kill_config.get("flag_file", "KILL_SWITCH")
    flag_path = resolve_path(config, flag_name)
    if flag_path.exists():
        return True, f"kill-switch flag file present: {flag_path}"

    return False, ""
