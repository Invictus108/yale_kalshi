from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.blueprints.auth import admin_required
from app.extensions import db
from app.models import Market, User, utcnow
from app.services.resolve import finalize_resolution, refresh_market

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@admin_required
def dashboard():
    for market in Market.query.filter(Market.status.in_(["open", "proposed"])).all():
        refresh_market(market)
    db.session.commit()
    pending = Market.query.filter_by(status="pending").order_by(Market.created_at.asc()).all()
    needs_resolve = Market.query.filter(
        Market.status.in_(["closed", "proposed", "disputed"])
    ).order_by(Market.closes_at.asc()).all()
    users = User.query.order_by(User.created_at.desc()).limit(100).all()
    return render_template(
        "admin/dashboard.html",
        pending=pending,
        needs_resolve=needs_resolve,
        users=users,
    )


@admin_bp.route("/markets/<int:market_id>/approve", methods=["POST"])
@admin_required
def approve(market_id: int):
    market = Market.query.get_or_404(market_id)
    if market.status != "pending":
        flash("Market is not pending.", "warning")
    elif market.closes_at <= utcnow():
        flash("This market has expired and cannot be approved. Reject it and submit a new market.", "warning")
    else:
        market.status = "open"
        market.approved_at = utcnow()
        market.approved_by_id = current_user.id
        db.session.commit()
        flash("Market approved and opened.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/markets/<int:market_id>/reject", methods=["POST"])
@admin_required
def reject(market_id: int):
    market = Market.query.get_or_404(market_id)
    if market.status != "pending":
        flash("Only pending markets can be rejected. Use settlement for approved markets.", "warning")
        return redirect(url_for("admin.dashboard"))
    reason = (request.form.get("reason") or "").strip()
    market.status = "void"
    market.final_outcome = "VOID"
    market.resolved_at = utcnow()
    market.resolved_by_id = current_user.id
    market.rejection_reason = reason or "Rejected by admin"
    db.session.commit()
    flash("Market rejected.", "info")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/markets/<int:market_id>/finalize", methods=["POST"])
@admin_required
def finalize(market_id: int):
    market = Market.query.get_or_404(market_id)
    try:
        finalize_resolution(
            market,
            admin_id=current_user.id,
            outcome=request.form.get("outcome", ""),
        )
        db.session.commit()
        flash("Resolved.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def toggle_admin(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot demote yourself.", "warning")
        return redirect(url_for("admin.dashboard"))
    user.is_admin = not user.is_admin
    db.session.commit()
    flash(
        f"{user.public_name} is now {'an admin' if user.is_admin else 'a regular user'}.",
        "success",
    )
    return redirect(url_for("admin.dashboard"))
