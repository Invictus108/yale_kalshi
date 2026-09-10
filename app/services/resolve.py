from __future__ import annotations

from datetime import timedelta

from flask import current_app
from sqlalchemy import update

from app.extensions import db
from app.models import Market, Position, User, utcnow
from app.services.email_notify import notify_market_holders, notify_user
from app.services.trading import settle_market


def close_if_expired(market: Market) -> None:
    if market.status == "open" and market.closes_at <= utcnow():
        # A stale page request must never overwrite a concurrent settlement.
        db.session.execute(
            update(Market)
            .where(
                Market.id == market.id,
                Market.status == "open",
                Market.closes_at <= utcnow(),
            )
            .values(status="closed")
            .execution_options(synchronize_session=False)
        )
        db.session.refresh(market)


def maybe_auto_resolve(market: Market) -> bool:
    """
    If a proposal is undisputed past the deadline, settle to the proposed outcome.
    Disputed markets wait for an admin. Returns True if this call settled the market.
    """
    if market.status != "proposed":
        return False
    if not market.dispute_deadline or utcnow() < market.dispute_deadline:
        return False
    outcome = (market.proposed_outcome or "").upper()
    if outcome not in {"YES", "NO"}:
        return False

    now = utcnow()
    # Claim settlement atomically so concurrent requests don't double-pay.
    result = db.session.execute(
        update(Market)
        .where(
            Market.id == market.id,
            Market.status == "proposed",
            Market.dispute_deadline <= now,
            Market.dispute_deadline == market.dispute_deadline,
            Market.proposed_outcome == market.proposed_outcome,
        )
        .values(
            final_outcome=outcome,
            resolved_at=now,
            resolved_by_id=market.proposed_by_id,
            status="resolved",
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.session.refresh(market)
        return False

    db.session.refresh(market)
    _settle_and_notify(market, outcome)
    return True


def refresh_market(market: Market) -> None:
    """Lazy lifecycle: close expired opens, auto-resolve undisputed proposals."""
    close_if_expired(market)
    maybe_auto_resolve(market)


def refresh_active_markets() -> None:
    """Persist due lifecycle changes before building balances and positions."""
    for market in Market.query.filter(Market.status.in_(["open", "proposed"])).order_by(Market.id).all():
        refresh_market(market)
    db.session.commit()


def propose_resolution(
    market: Market,
    *,
    proposer_id: int,
    outcome: str,
    evidence: str,
) -> None:
    close_if_expired(market)
    if market.status not in {"closed", "disputed"}:
        raise ValueError("market must be closed before proposing resolution")
    outcome = outcome.upper()
    if outcome not in {"YES", "NO"}:
        raise ValueError("outcome must be YES or NO")
    if not evidence.strip():
        raise ValueError("evidence required")

    hours = int(current_app.config["DISPUTE_HOURS"])
    market.proposed_outcome = outcome
    market.proposed_by_id = proposer_id
    market.proposed_at = utcnow()
    market.proposal_evidence = evidence.strip()
    market.dispute_deadline = utcnow() + timedelta(hours=hours)
    market.dispute_reason = None
    market.status = "proposed"

    notify_market_holders(
        market,
        f"[Yalshi] Resolution proposed: {market.title}",
        (
            f"A resolution of {outcome} was proposed for:\n\n"
            f"{market.title}\n\nEvidence:\n{evidence}\n\n"
            f"You have {hours} hours to dispute. "
            f"If undisputed, it settles automatically to {outcome}. "
            f"An admin can settle earlier.\n"
        ),
    )


def dispute_resolution(market: Market, *, reason: str) -> None:
    if market.status != "proposed":
        raise ValueError("no active proposal to dispute")
    if market.dispute_deadline and utcnow() > market.dispute_deadline:
        raise ValueError("dispute window has closed")
    if not reason.strip():
        raise ValueError("dispute reason required")
    market.status = "disputed"
    market.dispute_reason = reason.strip()
    notify_market_holders(
        market,
        f"[Yalshi] Resolution disputed: {market.title}",
        f"A trader disputed the proposed {market.proposed_outcome} outcome.\n\nReason:\n{reason}\n",
    )


def finalize_resolution(
    market: Market,
    *,
    admin_id: int,
    outcome: str,
) -> None:
    """Admin settle: applies immediately (no dispute-window wait)."""
    if db.engine.dialect.name == "postgresql":
        db.session.refresh(market, with_for_update=True)
    outcome = outcome.upper()
    if outcome not in {"YES", "NO", "VOID"}:
        raise ValueError("outcome must be YES, NO, or VOID")
    if market.status in {"resolved", "void"}:
        raise ValueError("already resolved")
    close_if_expired(market)
    if market.status not in {"closed", "proposed", "disputed"}:
        raise ValueError("market must be closed before settlement")

    market.final_outcome = outcome
    market.resolved_at = utcnow()
    market.resolved_by_id = admin_id
    market.status = "void" if outcome == "VOID" else "resolved"
    _settle_and_notify(market, outcome)


def _settle_and_notify(market: Market, outcome: str) -> None:
    holder_ids = {
        p.user_id
        for p in Position.query.filter_by(market_id=market.id).all()
        if p.yes_shares > 0 or p.no_shares > 0
    }
    holder_ids.add(market.creator_id)

    settle_market(market)

    users = User.query.filter(User.id.in_(holder_ids)).all() if holder_ids else []
    for user in users:
        notify_user(
            user,
            f"[Yalshi] Resolved: {market.title} → {outcome}",
            (
                f"Market resolved as {outcome}.\n\n"
                f"{market.title}\n\n"
                "Play-money balances have been updated. Check your portfolio.\n"
            ),
            market_id=market.id,
        )
