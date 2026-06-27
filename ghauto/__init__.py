"""GitHub Activity Automation System.

A configurable toolkit of two automation agents that interact with the
GitHub REST API:

* ``commit_agent`` - the Daily Commit Agent
* ``creator_agent`` - the Project Creator Agent

Shared infrastructure (config loading, logging, the GitHub HTTP client,
state persistence and the kill switch) lives in this package so both
agents stay small and focused.
"""

__version__ = "1.0.0"
