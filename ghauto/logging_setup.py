"""Structured logging configuration.

Both agents log to a rotating file *and* stdout. Every record carries a
timestamp and severity level, satisfying the assessment's logging
requirements and keeping a durable audit trail of automated runs.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import Any

from .config import resolve_path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def setup_logging(config: dict[str, Any], name: str) -> logging.Logger:
    """Configure and return a logger for the given agent.

    Args:
        config: The loaded configuration dictionary.
        name: Logger name, typically the agent module name.

    The configuration is read from the ``logging`` section: ``level``,
    ``log_file``, ``max_bytes`` and ``backup_count``.
    """
    log_config = config.get("logging", {})
    level_name = str(log_config.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Avoid duplicate handlers if setup_logging is called more than once.
    if logger.handlers:
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler.
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Rotating file handler.
    log_file = resolve_path(config, log_config.get("log_file", "logs/automation.log"))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=int(log_config.get("max_bytes", 1_048_576)),
        backupCount=int(log_config.get("backup_count", 3)),
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
