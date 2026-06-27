#!/usr/bin/env python3
"""Web UI for the GitHub Activity Automation System.

A small Flask app that exposes the same actions as the two CLIs through an
interactive web page: check status, pick a repo and commit, propose / edit /
create a project, toggle the kill switch and view logs.

Run it with:
    python webapp.py
then open http://127.0.0.1:5000 in your browser.

This is a local control panel, not a public service. It binds to localhost by
default and relies on the GITHUB_TOKEN in your environment / .env, exactly
like the CLIs.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from ghauto import service
from ghauto.service import ServiceError

app = Flask(__name__)


def _ok(payload: object, status: int = 200):
    return jsonify(payload), status


@app.errorhandler(ServiceError)
def _handle_service_error(exc: ServiceError):
    return jsonify({"error": exc.message}), exc.status


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def api_status():
    return _ok(service.get_status())


@app.get("/api/repos")
def api_repos():
    return _ok({"repos": service.list_repositories()})


@app.post("/api/commit")
def api_commit():
    data = request.get_json(silent=True) or {}
    repo = data.get("repo", "")
    force = bool(data.get("force", False))
    return _ok(service.run_daily_commit(repo, force=force))


@app.post("/api/project/propose")
def api_project_propose():
    data = request.get_json(silent=True) or {}
    return _ok(service.propose_project(language=data.get("language")))


@app.post("/api/project/create")
def api_project_create():
    data = request.get_json(silent=True) or {}
    return _ok(
        service.create_project(
            name=data.get("name", ""),
            language=data.get("language", ""),
            idea=data.get("idea", ""),
            source=data.get("source", "user-provided"),
        )
    )


@app.post("/api/killswitch")
def api_killswitch():
    data = request.get_json(silent=True) or {}
    return _ok(service.set_kill_switch(bool(data.get("engaged"))))


@app.get("/api/logs")
def api_logs():
    return _ok({"lines": service.tail_log(int(request.args.get("lines", 200)))})


if __name__ == "__main__":
    host = os.environ.get("WEBAPP_HOST", "127.0.0.1")
    port = int(os.environ.get("WEBAPP_PORT", "5000"))
    app.run(host=host, port=port, debug=bool(os.environ.get("WEBAPP_DEBUG")))
