from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import User
from app.services import friends as friends_svc
from app.services.feed import user_stats
from app.security import safe_next

social_bp = Blueprint("social", __name__)


@social_bp.route("/people")
@login_required
def people():
    q = request.args.get("q", "")
    results = friends_svc.search_users(q) if q else []
    incoming = friends_svc.pending_incoming(current_user.id)
    my_friends = friends_svc.list_friends(current_user.id)
    return render_template(
        "social/people.html",
        q=q,
        results=results,
        incoming=incoming,
        my_friends=my_friends,
        stats_for=user_stats,
        relation=lambda uid: friends_svc.relation_status(current_user.id, uid),
        seed_balance=float(current_app.config["SEED_BALANCE"]),
    )


@social_bp.route("/u/<int:user_id>")
@login_required
def profile(user_id: int):
    user = User.query.get_or_404(user_id)
    stats = user_stats(user)
    status = friends_svc.relation_status(current_user.id, user.id)
    return render_template(
        "social/profile.html",
        profile_user=user,
        stats=stats,
        relation=status,
    )


@social_bp.route("/friends/request/<int:user_id>", methods=["POST"])
@login_required
def friend_request(user_id: int):
    try:
        friends_svc.send_request(current_user.id, user_id)
        db.session.commit()
        flash("Friend request sent.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "warning")
    return redirect(safe_next(request.referrer) if request.referrer else url_for("social.profile", user_id=user_id))


@social_bp.route("/friends/accept/<int:friendship_id>", methods=["POST"])
@login_required
def friend_accept(friendship_id: int):
    try:
        friends_svc.accept_request(current_user.id, friendship_id)
        db.session.commit()
        flash("Friend request accepted.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(safe_next(request.referrer) if request.referrer else url_for("social.people"))


@social_bp.route("/friends/decline/<int:friendship_id>", methods=["POST"])
@login_required
def friend_decline(friendship_id: int):
    try:
        friends_svc.decline_request(current_user.id, friendship_id)
        db.session.commit()
        flash("Friend request declined.", "info")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(safe_next(request.referrer) if request.referrer else url_for("social.people"))


@social_bp.route("/friends/unfriend/<int:user_id>", methods=["POST"])
@login_required
def unfriend(user_id: int):
    try:
        friends_svc.unfriend(current_user.id, user_id)
        db.session.commit()
        flash("Removed friend.", "info")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "warning")
    return redirect(safe_next(request.referrer) if request.referrer else url_for("social.profile", user_id=user_id))


@social_bp.route("/chat")
@login_required
def chat_inbox():
    threads = friends_svc.inbox_threads(current_user.id)
    return render_template("social/chat_inbox.html", threads=threads)


@social_bp.route("/chat/<int:user_id>", methods=["GET", "POST"])
@login_required
def chat_thread(user_id: int):
    other = User.query.get_or_404(user_id)
    if not friends_svc.are_friends(current_user.id, other.id):
        flash("You can only chat with friends. Send a friend request first.", "warning")
        return redirect(url_for("social.profile", user_id=other.id))

    if request.method == "POST":
        try:
            friends_svc.send_dm(current_user.id, other.id, request.form.get("body", ""))
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "warning")
        return redirect(url_for("social.chat_thread", user_id=other.id))

    messages = friends_svc.conversation(current_user.id, other.id)
    return render_template(
        "social/chat_thread.html",
        other=other,
        messages=messages,
    )
