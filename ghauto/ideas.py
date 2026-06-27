"""Project idea generation for the Project Creator Agent.

Optionally calls an external AI text-generation API (HuggingFace Inference
by default) to produce a fresh project idea. If the external API is
disabled, unreachable, unauthenticated, or returns garbage, this module
falls back to a built-in list from the config - it never raises.
"""

from __future__ import annotations

import os
import random
from typing import Any

import requests

_PROMPT = (
    "Suggest one concise, original software project idea suitable for a small "
    "starter repository. Reply with a single sentence describing the project."
)


def generate_idea(config: dict[str, Any], logger: Any) -> tuple[str, str]:
    """Return ``(idea_text, source)`` where source is 'external-ai' or 'fallback'."""
    agent_cfg = config.get("project_creator_agent", {})
    ai_cfg = agent_cfg.get("external_ai", {})
    fallback_ideas = agent_cfg.get("fallback_project_ideas", ["A small starter project"])

    if ai_cfg.get("enabled"):
        idea = _try_external_ai(ai_cfg, logger)
        if idea:
            return idea, "external-ai"
        logger.info("External AI unavailable or returned no idea; using fallback list.")

    return random.choice(fallback_ideas), "fallback"


def _try_external_ai(ai_cfg: dict[str, Any], logger: Any) -> str | None:
    """Attempt an external AI call. Returns the idea text or ``None`` on any failure."""
    token = os.environ.get("HUGGINGFACE_API_TOKEN") or os.environ.get("AI_API_TOKEN")
    if not token:
        logger.warning("External AI enabled but no HUGGINGFACE_API_TOKEN set; skipping.")
        return None

    model = ai_cfg.get("model", "")
    url = ai_cfg.get("api_url", "").rstrip("/") + "/" + model
    timeout = int(ai_cfg.get("timeout_seconds", 20))

    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"inputs": _PROMPT, "parameters": {"max_new_tokens": 60}},
            timeout=timeout,
        )
        if response.status_code != 200:
            logger.warning(f"External AI returned HTTP {response.status_code}; falling back.")
            return None
        return _parse_response(response.json())
    except (requests.RequestException, ValueError) as exc:
        logger.warning(f"External AI call failed ({exc}); falling back.")
        return None


def _parse_response(data: Any) -> str | None:
    """Extract generated text from a HuggingFace-style response."""
    text: str | None = None
    if isinstance(data, list) and data:
        text = data[0].get("generated_text") if isinstance(data[0], dict) else None
    elif isinstance(data, dict):
        text = data.get("generated_text")

    if not text:
        return None
    # Keep the first sentence and strip the echoed prompt if present.
    cleaned = text.replace(_PROMPT, "").strip()
    first_line = cleaned.splitlines()[0].strip() if cleaned else ""
    return first_line or None
