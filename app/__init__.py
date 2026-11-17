"""SkillSage: an AI mock-interview coach."""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from .config import Settings
from .db import db
from .errors import ApiError
from .llm.base import LLMProvider
from .llm.factory import build_provider
from .ratelimit import RateLimiter
from .services import auth
from .services.history import HistoryService
from .services.interview import InterviewService
from .services.store import SessionStore

log = logging.getLogger("skillsage")

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

ROOT = Path(__file__).resolve().parent.parent


def _secret_key(settings: Settings, instance: Path) -> str:
    """Use SECRET_KEY if given; otherwise create one once and keep it so logins survive restarts."""
    if settings.secret_key:
        return settings.secret_key
    key_file = instance / ".secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> Flask:
    settings = settings or Settings.from_env()
    provider = provider or build_provider(settings)

    instance = ROOT / "instance"
    instance.mkdir(exist_ok=True)

    app = Flask(__name__)
    app.json.sort_keys = False          # keep rubric order: relevance, depth, clarity, structure, grammar
    app.config.update(
        MAX_CONTENT_LENGTH=settings.max_upload_bytes + 64 * 1024,
        SECRET_KEY=_secret_key(settings, instance),
        SQLALCHEMY_DATABASE_URI=settings.database_url or "sqlite:///" + (instance / "skillsage.db").as_posix(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.cookie_secure,
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()

    history = HistoryService()
    service = InterviewService(SessionStore(settings.session_ttl_minutes, settings.max_sessions), provider, settings, history)
    limiter = RateLimiter(settings.rate_limit_per_minute)
    app.extensions["skillsage"] = {
        "service": service, "provider": provider, "settings": settings, "history": history,
        "auth_limiter": RateLimiter(settings.auth_rate_limit, 300),
    }

    from .routes.api import bp as api_bp
    from .routes.pages import bp as pages_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)

    @app.context_processor
    def inject_globals():
        return {"provider_name": provider.name, "is_ai": provider.is_ai, "current_user": g.get("user")}

    @app.before_request
    def same_origin_only():
        # Cookies + JSON: refuse state-changing requests that come from another website.
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc != request.host:
                raise ApiError("Cross-site request blocked.", 403)

    @app.before_request
    def throttle():
        if request.method == "POST" and request.path.startswith("/api/") and not limiter.allow(request.remote_addr or "?"):
            raise ApiError("You are going a bit fast. Please wait a moment and try again.", 429)

    @app.before_request
    def load_user():
        g.user = None if request.endpoint == "static" else auth.current_user()

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if request.path.startswith("/api/") or request.path in ("/profile", "/login", "/register") or request.path.startswith("/history/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(ApiError)
    def api_error(err: ApiError):
        return jsonify(error=err.message), err.status

    @app.errorhandler(HTTPException)
    def http_error(err: HTTPException):
        if request.path.startswith("/api/"):
            message = "The file is too large." if err.code == 413 else err.description
            return jsonify(error=message), err.code
        return err

    @app.errorhandler(Exception)
    def unexpected(err: Exception):
        log.exception("Unhandled error")
        if request.path.startswith("/api/"):
            return jsonify(error="Something went wrong on our side. Please try again."), 500
        raise err

    return app