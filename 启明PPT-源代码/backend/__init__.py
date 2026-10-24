"""Flask application factory for 启明 PPT."""
from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory

from .config import (
    APP_NAME,
    APP_VERSION,
    DATA_DIR,
    FRONTEND_DIR,
    LOG_DIR,
    ensure_directories,
    load_runtime,
)
from .db import close_db, init_db

__version__ = APP_VERSION
__all__ = ["create_app", "__version__"]


def _configure_logging(app: Flask) -> None:
    ensure_directories()
    if not any(isinstance(handler, logging.FileHandler) for handler in app.logger.handlers):
        handler = logging.FileHandler(LOG_DIR / "qiming.log", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)


def create_app(**config) -> Flask:
    ensure_directories()
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR / "assets"),
        static_url_path="/assets",
        template_folder=str(FRONTEND_DIR),
    )
    runtime = load_runtime()
    app.secret_key = os.environ.get("QIMING_SECRET_KEY") or runtime["secret_key"]
    app.config.update(
        MAX_CONTENT_LENGTH=64 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        JSON_SORT_KEYS=False,
        TEMPLATES_AUTO_RELOAD=False,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    app.config.update(config)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    init_db()
    _configure_logging(app)
    app.teardown_appcontext(close_db)

    from .api import api_bp
    from .auth import auth_bp, load_current_user

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    @app.before_request
    def _security_checks():
        load_current_user()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.path.startswith("/api/"):
            origin = request.headers.get("Origin", "")
            if origin:
                parsed = urlparse(origin)
                if parsed.netloc and parsed.netloc != request.host:
                    return jsonify({"ok": False, "error": "请求来源不合法", "code": "BAD_ORIGIN"}), 403
        return None

    @app.after_request
    def _headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https:; "
            "media-src 'self' blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        if request.path.startswith("/assets/") or response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
        if request.path.startswith("/api/") and not request.path.startswith("/api/templates/online/thumb/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path in {"/", "/admin"}:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/admin")
    def admin_page():
        return send_from_directory(FRONTEND_DIR, "admin.html")

    @app.get("/favicon.ico")
    def favicon():
        icon = FRONTEND_DIR / "assets" / "icon.ico"
        if icon.exists():
            return send_from_directory(icon.parent, icon.name, mimetype="image/x-icon")
        return ("", 404)

    @app.get("/manifest.webmanifest")
    def manifest():
        return jsonify(
            {
                "name": APP_NAME,
                "short_name": "启明PPT",
                "start_url": "/",
                "display": "standalone",
                "background_color": "#0B0F19",
                "theme_color": "#0B0F19",
                "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png"}],
            }
        )

    @app.errorhandler(413)
    def too_large(_error):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "提交内容过大", "code": "TOO_LARGE"}), 413
        return "文件过大", 413

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "接口不存在", "code": "NOT_FOUND"}), 404
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.errorhandler(500)
    def server_error(_error):
        app.logger.exception("internal server error")
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "服务器出现异常，请稍后重试", "code": "SERVER_ERROR"}), 500
        return "服务器出现异常", 500

    app.logger.info("%s %s started (data: %s)", APP_NAME, APP_VERSION, DATA_DIR)
    return app
