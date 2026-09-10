from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.auth import admin_required
from app.extensions import db
from app.models import ChatMessage, Market, Trade, utcnow
from app.services.resolve import (
    dispute_resolution,
    finalize_resolution,
    propose_resolution,
    refresh_market,
)
from app.services.trading import cash_out, execute_trade, quote_sell_proceeds

markets_bp = Blueprint("markets", __name__, url_prefix="/markets")


def _parse_closes_at(raw: str, tz_offset_minutes: str) -> datetime:
    """
    datetime-local is the user's local wall clock (no tz).
    Browser sends getTimezoneOffset() = (UTC - local) in minutes.
    Convert to naive UTC for storage/compare with utcnow().
    """
    closes_local = datetime.fromisoformat(raw)
    if closes_local.tzinfo is not None:
        return closes_local.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        offset = int(tz_offset_minutes or "0")
    except ValueError as exc:
        raise ValueError("invalid timezone offset") from exc
    if not -840 <= offset <= 840:
        raise ValueError("invalid timezone offset")
    # UTC = local + offset_minutes
    return closes_local + timedelta(minutes=offset)


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
            closes_at = _parse_closes_at(
                closes_at_raw, request.form.get("tz_offset_minutes", "0")
            )
        except (ValueError, OverflowError):
            flash("Invalid close time.", "danger")
            return render_template("markets/create.html")

        if not all([title, description, criteria, source]):
            flash("All fields required.", "warning")
            return render_template("markets/create.html")
        # Small skew buffer so "1–2 minutes from now" still works.
        if closes_at <= utcnow() + timedelta(seconds=15):
            flash(
                "Close time must be at least ~30 seconds in the future (use your local time).",
                "warning",
            )
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
    refresh_market(market)
    db.session.commit()
    trades = (
        Trade.query.filter_by(market_id=market.id)
        .order_by(Trade.created_at.desc())
        .limit(30)
        .all()
    )
    messages = (
        ChatMessage.query.filter_by(market_id=market.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(200)
        .all()
    )
    my_pos = None
    cash_out_quotes = {"YES": 0.0, "NO": 0.0}
    if current_user.is_authenticated:
        my_pos = next((p for p in current_user.positions if p.market_id == market.id), None)
        if my_pos and market.status == "open":
            if my_pos.yes_shares > 1e-9:
                cash_out_quotes["YES"] = quote_sell_proceeds(
                    market, "YES", my_pos.yes_shares
                )
            if my_pos.no_shares > 1e-9:
                cash_out_quotes["NO"] = quote_sell_proceeds(
                    market, "NO", my_pos.no_shares
                )
    return render_template(
        "markets/detail.html",
        market=market,
        trades=trades,
        messages=list(reversed(messages)),
        my_pos=my_pos,
        cash_out_quotes=cash_out_quotes,
    )


@markets_bp.route("/<int:market_id>/trade", methods=["POST"])
@login_required
def trade(market_id: int):
    market = Market.query.get_or_404(market_id)
    refresh_market(market)
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


@markets_bp.route("/<int:market_id>/cash-out", methods=["POST"])
@login_required
def cash_out_route(market_id: int):
    """Sell all YES or NO holdings back to the market at the live AMM price."""
    market = Market.query.get_or_404(market_id)
    refresh_market(market)
    side = (request.form.get("side") or "YES").upper()
    try:
        trade = cash_out(user_id=current_user.id, market=market, side=side)
        db.session.commit()
        flash(
            f"Cashed out {trade.shares:.2f} {side} for ~{trade.cost:.2f} pts "
            f"(~{trade.avg_price * 100:.1f}¢/share).",
            "success",
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    next_url = request.form.get("next") or ""
    if next_url.startswith("/portfolio"):
        return redirect(url_for("main.portfolio"))
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
        hours = current_app.config["DISPUTE_HOURS"]
        flash(
            f"Resolution proposed. Auto-settles in {hours}h if undisputed; admin can settle sooner.",
            "success",
        )
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
