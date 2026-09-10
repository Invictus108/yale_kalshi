from functools import wraps
from urllib.parse import urlencode

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.services import cas as cas_svc
from app.services.users import get_or_create_user

auth_bp = Blueprint("auth", __name__)


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("main.index"))
        return fn(*args, **kwargs)

    return wrapper


@auth_bp.route("/login")
def login():
    """
    Redirect to Yale CAS — same pattern as Yale_Books.
    Ticket returns to /login_callback (not here).
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if current_app.config["DEV_AUTH_BYPASS"] and request.args.get("dev") == "1":
        return redirect(url_for("auth.dev_login"))

    nxt = request.args.get("next") or url_for("main.index")
    session["post_login_next"] = nxt

    params = {"service": cas_svc.service_url()}
    cas_url = f"{cas_svc.cas_login_url()}?{urlencode(params)}"
    current_app.logger.info("CAS login redirect service=%s url=%s", params["service"], cas_url)
    return redirect(cas_url)


@auth_bp.route("/login_callback")
def login_callback():
    """CAS returns here with ?ticket=… — validate then create session."""
    ticket = request.args.get("ticket")
    if not ticket:
        flash("Missing CAS ticket.", "danger")
        return redirect(url_for("main.index"))

    try:
        netid = cas_svc.validate_ticket(ticket)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("CAS validate failed: %s", exc)
        flash(f"CAS authentication failed: {exc}", "danger")
        return redirect(url_for("main.index"))

    user = get_or_create_user(netid)
    login_user(user, remember=True)
    flash("Signed in with Yale CAS.", "success")
    nxt = session.pop("post_login_next", None) or url_for("main.index")
    return redirect(nxt)


@auth_bp.route("/dev-login", methods=["GET", "POST"])
def dev_login():
    if not current_app.config["DEV_AUTH_BYPASS"]:
        flash("Dev login is disabled. Use Yale CAS.", "warning")
        return redirect(url_for("auth.login"))
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        netid = (request.form.get("netid") or "").strip().lower()
        if not netid:
            flash("Enter a NetID.", "warning")
            return render_template("auth/dev_login.html")
        user = get_or_create_user(netid)
        login_user(user, remember=True)
        flash(f"Dev login as {netid}.", "success")
        return redirect(request.args.get("next") or url_for("main.index"))
    return render_template("auth/dev_login.html")


@auth_bp.route("/logout")
def logout():
    """Local logout (matches Yale_Books — clear session, return home)."""
    logout_user()
    session.clear()
    flash("Signed out.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        display_name = (request.form.get("display_name") or "").strip()[:80]
        is_anon = request.form.get("is_anonymous_display") == "on"
        notify = request.form.get("notify_email") == "on"
        if not display_name:
            flash("Display name required.", "warning")
        else:
            current_user.display_name = display_name
            current_user.is_anonymous_display = is_anon
            current_user.notify_email = notify
            from app.extensions import db

            db.session.commit()
            flash("Settings saved.", "success")
            return redirect(url_for("auth.settings"))
    return render_template(
        "auth/settings.html",
        cas_enabled=not current_app.config["DEV_AUTH_BYPASS"],
        service_url=cas_svc.service_url(),
        cas_login_url=cas_svc.cas_login_url(),
    )
