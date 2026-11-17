"""JSON API."""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from ..errors import ApiError, NotFound
from ..llm.offline import _load
from ..models import DIMENSIONS
from ..services import auth
from ..services import resume as resume_service

bp = Blueprint("api", __name__, url_prefix="/api")


def _ext():
    return current_app.extensions["skillsage"]


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Send a JSON body.")
    return data


def _uid() -> int | None:
    return g.user.id if g.user else None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            raise ApiError("Please sign in first.", 401)
        return view(*args, **kwargs)
    return wrapper


def _throttle_auth():
    if not _ext()["auth_limiter"].allow(request.remote_addr or "?"):
        raise ApiError("Too many attempts. Please wait a few minutes and try again.", 429)


def _user_payload(user) -> dict:
    return {"name": user.name, "email": user.email, "target_role": user.target_role, "level": user.level,
            "created_at": user.created_at.isoformat() + "Z"}


# -- general ----------------------------------------------------------------------
@bp.get("/health")
def health():
    provider = _ext()["provider"]
    return jsonify(status="ok", provider=provider.name, is_ai=provider.is_ai)


@bp.get("/roles")
def roles():
    tracks = _load()["tracks"]
    return jsonify(roles=[t["label"] for t in tracks.values()], dimensions=list(DIMENSIONS))


# -- accounts ---------------------------------------------------------------------
@bp.post("/auth/register")
def register():
    _throttle_auth()
    body = _body()
    user = auth.register(body.get("email"), body.get("password"), body.get("name"))
    auth.sign_in(user)
    return jsonify(user=_user_payload(user)), 201


@bp.post("/auth/login")
def login():
    _throttle_auth()
    body = _body()
    user = auth.authenticate(body.get("email"), body.get("password"))
    auth.sign_in(user)
    return jsonify(user=_user_payload(user))


@bp.post("/auth/logout")
def logout():
    auth.sign_out()
    return jsonify(ok=True)


@bp.get("/auth/me")
def me():
    return jsonify(user=_user_payload(g.user) if g.user else None)


@bp.get("/profile")
@login_required
def profile():
    history = _ext()["history"]
    return jsonify(user=_user_payload(g.user), stats=history.stats(g.user.id), recent=history.list(g.user.id, limit=30))


@bp.patch("/profile")
@login_required
def update_profile():
    body = _body()
    user = auth.update_profile(g.user, body.get("name"), body.get("target_role"), body.get("level"))
    return jsonify(user=_user_payload(user))


@bp.post("/profile/password")
@login_required
def change_password():
    body = _body()
    auth.change_password(g.user, body.get("current_password"), body.get("new_password"))
    return jsonify(ok=True)


@bp.delete("/profile")
@login_required
def delete_profile():
    auth.delete_account(g.user, _body().get("password"))
    return jsonify(ok=True)


@bp.get("/history")
@login_required
def history_list():
    try:
        limit = max(1, min(100, int(request.args.get("limit", 50))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        raise ApiError("limit and offset must be numbers.")
    return jsonify(interviews=_ext()["history"].list(g.user.id, limit, offset))


@bp.get("/history/<interview_id>")
@login_required
def history_get(interview_id: str):
    record = _ext()["history"].get(g.user.id, interview_id)
    if record is None:
        raise NotFound("That interview was not found.")
    return jsonify(record)


# -- resume -----------------------------------------------------------------------
@bp.post("/resume")
def upload_resume():
    settings = _ext()["settings"]
    file = request.files.get("file")
    if file is None or not file.filename:
        raise ApiError("Choose a PDF or .txt file.")
    data = file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise ApiError("The file is too large (limit 5 MB).", 413)
    text = resume_service.extract_text(file.filename, data, max_pages=settings.max_pdf_pages, limit=settings.max_resume_chars)
    return jsonify(text=text, characters=len(text))


# -- interviews -------------------------------------------------------------------
@bp.post("/sessions")
def start_session():
    body = _body()
    session = _ext()["service"].start(body.get("role"), body.get("level", "junior"), body.get("total", 5),
                                      body.get("resume_text", ""), user_id=_uid())
    return jsonify(session), 201


@bp.get("/sessions/<session_id>")
def get_session(session_id: str):
    return jsonify(_ext()["service"].get(session_id, _uid()))


@bp.post("/sessions/<session_id>/answer")
def answer(session_id: str):
    return jsonify(_ext()["service"].answer(session_id, _body().get("answer"), _uid()))


@bp.get("/sessions/<session_id>/report")
def report(session_id: str):
    return jsonify(_ext()["service"].report(session_id, _uid()))


@bp.post("/sessions/<session_id>/save")
@login_required
def save_session(session_id: str):
    return jsonify(_ext()["service"].claim(session_id, g.user.id))