"""HTML pages. All behaviour lives in static JS that calls the JSON API."""
from __future__ import annotations

import re

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, url_for

from ..llm.offline import _load

bp = Blueprint("pages", __name__)

_ID = re.compile(r"^[a-f0-9]{16}$")


def _settings():
    return current_app.extensions["skillsage"]["settings"]


def _needs_login():
    return redirect(url_for("pages.login", next=request.path))


@bp.get("/")
def index():
    roles = [t["label"] for t in _load()["tracks"].values()]
    return render_template("index.html", roles=roles, max_resume=_settings().max_resume_chars)


@bp.get("/login")
def login():
    if g.user:
        return redirect(url_for("pages.profile"))
    return render_template("auth.html", mode="login")


@bp.get("/register")
def register():
    if g.user:
        return redirect(url_for("pages.profile"))
    return render_template("auth.html", mode="register")


@bp.get("/profile")
def profile():
    if not g.user:
        return _needs_login()
    return render_template("profile.html")


@bp.get("/history/<interview_id>")
def history_item(interview_id: str):
    if not g.user:
        return _needs_login()
    if not _ID.match(interview_id):
        abort(404)
    return render_template("history.html", interview_id=interview_id)


@bp.get("/interview/<session_id>")
def interview(session_id: str):
    if not _ID.match(session_id):
        abort(404)
    return render_template("interview.html", session_id=session_id, max_answer=_settings().max_answer_chars)