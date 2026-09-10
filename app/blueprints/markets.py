from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.auth import admin_required
from app.extensions import db
from app.models import ChatMessage, Market, Trade, utcnow
from app.services.resolve import (
    close_if_expired,
    dispute_resolution,
    finalize_resolution,
    propose_resolution,
)
from app.services.trading import execute_trade

markets_bp = Blueprint("markets", __name__, url_prefix="/markets")


@markets_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        criteria = (request.form.get("resolution_criteria") or "").strip()
        source = (request.form.get("resolution_source") or "").strip()
        closes_at_raw = request.form.get("closes_at") or ""
        try:
            closes_at = datetime.fromisoformat(closes_at_raw)
            # Store as naive UTC-ish local wall time for MVP (see HANDOFF.md).
            if closes_at.tzinfo is not None:
                closes_at = closes_at.replace(tzinfo=None)
        except ValueError:
            flash("Invalid close time.", "danger")
            return render_template("markets/create.html")

        if not all([title, description, criteria, source]):
            flash("All fields required.", "warning")
            return render_template("markets/create.html")
        if closes_at <= utcnow():
            flash("Close time must be in the future.", "warning")
            return render_template("markets/create.html")

        from flask import current_app

        market = Market(
            title=title[:200],
            description=description,
            resolution_criteria=criteria,
            resolution_source=source[:500],
            creator_id=current_user.id,
            status="pending",
            closes_at=closes_at,
            lmsr_b=float(current_app.config["LMSR_B"]),
            q_yes=0.0,
            q_no=0.0,
        )
        db.session.add(market)
        db.session.commit()
        flash("Market submitted for admin approval.", "success")
        return redirect(url_for("markets.detail", market_id=market.id))
    return render_template("markets/create.html")


@markets_bp.route("/<int:market_id>")
def detail(market_id: int):
    market = Market.query.get_or_404(market_id)
    close_if_expired(market)
    db.session.commit()
    trades = (
        Trade.query.filter_by(market_id=market.id)
        .order_by(Trade.created_at.desc())
        .limit(30)
        .all()
    )
    messages = (
        ChatMessage.query.filter_by(market_id=market.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(200)
        .all()
    )
    my_pos = None
    if current_user.is_authenticated:
        my_pos = next((p for p in current_user.positions if p.market_id == market.id), None)
    return render_template(
        "markets/detail.html",
        market=market,
        trades=trades,
        messages=messages,
        my_pos=my_pos,
    )


@markets_bp.route("/<int:market_id>/trade", methods=["POST"])
@login_required
def trade(market_id: int):
    market = Market.query.get_or_404(market_id)
    close_if_expired(market)
    side = request.form.get("side", "YES")
    action = request.form.get("action", "BUY")
    try:
        shares = float(request.form.get("shares") or "0")
        execute_trade(
            user_id=current_user.id,
            market=market,
            side=side,
            action=action,
            shares=shares,
        )
        db.session.commit()
        flash(f"{action} {shares} {side} filled.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("markets.detail", market_id=market.id))


@markets_bp.route("/<int:market_id>/chat", methods=["POST"])
@login_required
def chat(market_id: int):
    market = Market.query.get_or_404(market_id)
    body = (request.form.get("body") or "").strip()[:1000]
    if not body:
        flash("Message empty.", "warning")
    else:
        db.session.add(
            ChatMessage(market_id=market.id, user_id=current_user.id, body=body)
        )
        db.session.commit()
    return redirect(url_for("markets.detail", market_id=market.id) + "#chat")


@markets_bp.route("/<int:market_id>/propose", methods=["POST"])
@login_required
def propose(market_id: int):
    market = Market.query.get_or_404(market_id)
    # Creator or admin may propose
    if current_user.id != market.creator_id and not current_user.is_admin:
        flash("Only the creator or an admin can propose resolution.", "danger")
        return redirect(url_for("markets.detail", market_id=market.id))
    try:
        propose_resolution(
            market,
            proposer_id=current_user.id,
            outcome=request.form.get("outcome", ""),
            evidence=request.form.get("evidence", ""),
        )
        db.session.commit()
        flash("Resolution proposed. Dispute window started.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("markets.detail", market_id=market.id))


@markets_bp.route("/<int:market_id>/dispute", methods=["POST"])
@login_required
def dispute(market_id: int):
    market = Market.query.get_or_404(market_id)
    try:
        dispute_resolution(market, reason=request.form.get("reason", ""))
        db.session.commit()
        flash("Dispute filed. An admin will review.", "warning")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("markets.detail", market_id=market.id))


@markets_bp.route("/<int:market_id>/finalize", methods=["POST"])
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
        flash("Market finalized and settled.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("markets.detail", market_id=market.id))