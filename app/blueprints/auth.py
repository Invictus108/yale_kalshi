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


@auth_bp.route("/cas-debug")
def cas_debug():
    """Public: show which CAS URLs the server is using (no secrets)."""
    return cas_svc.cas_public_status()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Login hub.
    - CAS button → /login/cas (Yale_Books redirect)
    - Friend NetID form when FRIEND_ACCESS_CODE or DEV_AUTH_BYPASS is set
      (needed on Render: test CAS only allowlists localhost services)
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    friend_mode = bool(current_app.config.get("ENABLE_NETID_LOGIN"))
    require_code = bool(current_app.config.get("FRIEND_ACCESS_CODE"))

    if request.method == "POST" and friend_mode:
        netid = (request.form.get("netid") or "").strip().lower()
        code = (request.form.get("access_code") or "").strip()
        expected = current_app.config.get("FRIEND_ACCESS_CODE") or ""

        if require_code and code != expected:
            flash("Wrong access code.", "danger")
            return render_template(
                "auth/login.html",
                friend_mode=friend_mode,
                require_code=require_code,
                cas_status=cas_svc.cas_public_status(),
            )
        if not netid:
            flash("Enter your Yale NetID.", "warning")
            return render_template(
                "auth/login.html",
                friend_mode=friend_mode,
                require_code=require_code,
                cas_status=cas_svc.cas_public_status(),
            )

        user = get_or_create_user(netid)
        login_user(user, remember=True)
        flash(f"Signed in as {netid}.", "success")
        return redirect(request.args.get("next") or url_for("main.index"))

    return render_template(
        "auth/login.html",
        friend_mode=friend_mode,
        require_code=require_code,
        cas_status=cas_svc.cas_public_status(),
    )


@auth_bp.route("/login/cas")
def login_cas():
    """Exact Yale_Books redirect: CAS login with service=ORIGIN/login_callback."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    nxt = request.args.get("next") or url_for("main.index")
    session["post_login_next"] = nxt

    # Yale_Books:
    #   params = {"service": SERVICE_URL}
    #   cas_url = f"{CAS_LOGIN_URL}?{urlencode(params)}"
    params = {"service": cas_svc.service_url()}
    cas_url = f"{cas_svc.cas_login_url()}?{urlencode(params)}"
    current_app.logger.info("CAS redirect → %s", cas_url)
    return redirect(cas_url)


@auth_bp.route("/login_callback")
def login_callback():
    """Yale_Books callback: ticket → validate → session."""
    ticket = request.args.get("ticket")
    if not ticket:
        flash("Missing CAS ticket.", "danger")
        return redirect(url_for("auth.login"))

    try:
        netid = cas_svc.validate_ticket(ticket)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("CAS validate failed: %s", exc)
        flash(f"CAS authentication failed: {exc}", "danger")
        return redirect(url_for("auth.login"))

    user = get_or_create_user(netid)
    login_user(user, remember=True)
    flash("Signed in with Yale CAS.", "success")
    nxt = session.pop("post_login_next", None) or url_for("main.index")
    return redirect(nxt)


@auth_bp.route("/dev-login", methods=["GET", "POST"])
def dev_login():
    return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
def logout():
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
        cas_enabled=True,
        service_url=cas_svc.service_url(),
        cas_login_url=cas_svc.cas_login_url(),
    )
