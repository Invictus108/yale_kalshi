"""Session-bound form protection and local redirect validation."""
import secrets
from urllib.parse import urlsplit, urlunsplit

from flask import abort, request, session, url_for
from sqlalchemy import text

from app.extensions import db


def safe_next(target):
    target = target or ""
    try:
        parts = urlsplit(target)
    except ValueError:
        return url_for("main.index")
    if parts.scheme == request.scheme and parts.netloc == request.host:
        target = urlunsplit(("", "", parts.path or "/", parts.query, parts.fragment))
        parts = urlsplit(target)
    if (parts.scheme or parts.netloc or not target.startswith("/")
            or target.startswith("//") or "\\" in target
            or any(ord(c) < 32 for c in target)):
        return url_for("main.index")
    return target


def init_security(app):
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_mutations():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = session.get("csrf_token", "")
            actual = request.form.get("csrf_token", "")
            if not expected or not secrets.compare_digest(expected.encode(), actual.encode()):
                abort(400, description="This form has expired. Refresh the page and try again.")
            # Acquire SQLite's write lock before reading balances/market state.
            # This serializes trades and settlement across server workers.
            if db.engine.dialect.name == "sqlite":
                db.session.execute(text("BEGIN IMMEDIATE"))

    @app.errorhandler(400)
    def bad_request(error):
        from flask import render_template
        return render_template("error.html", message=error.description), 400
