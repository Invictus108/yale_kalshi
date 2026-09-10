from __future__ import annotations

from app.extensions import db
from app.models import Market, Position, Trade, utcnow
from app.services import amm, ledger


def get_or_create_position(user_id: int, market_id: int) -> Position:
    pos = Position.query.filter_by(user_id=user_id, market_id=market_id).first()
    if pos:
        return pos
    pos = Position(user_id=user_id, market_id=market_id)
    db.session.add(pos)
    db.session.flush()
    return pos


def execute_trade(
    *,
    user_id: int,
    market: Market,
    side: str,
    action: str,
    shares: float,
) -> Trade:
    if market.status != "open":
        raise ValueError("market is not open for trading")
    if market.closes_at <= utcnow():
        market.status = "closed"
        raise ValueError("market has closed")

    side = side.upper()
    action = action.upper()
    shares = float(shares)
    if shares <= 0:
        raise ValueError("shares must be > 0")

    pos = get_or_create_position(user_id, market.id)
    if action == "SELL":
        held = pos.yes_shares if side == "YES" else pos.no_shares
        if shares > held + 1e-9:
            raise ValueError("not enough shares to sell")

    cost, new_yes, new_no = amm.trade_cost(
        market.q_yes, market.q_no, market.lmsr_b, side, action, shares
    )

    # BUY: trader pays cost (>=0). SELL: cost is negative => credit -cost
    if action == "BUY":
        ledger.apply_entry(
            user_id,
            -cost,
            "trade",
            ref_type="market",
            ref_id=market.id,
            note=f"BUY {shares:.4f} {side}",
        )
        if side == "YES":
            pos.yes_shares += shares
        else:
            pos.no_shares += shares
        pos.cost_basis += cost
    else:
        proceeds = -cost  # positive cash to trader
        ledger.apply_entry(
            user_id,
            proceeds,
            "trade",
            ref_type="market",
            ref_id=market.id,
            note=f"SELL {shares:.4f} {side}",
        )
        if side == "YES":
            pos.yes_shares -= shares
        else:
            pos.no_shares -= shares
        pos.cost_basis = max(0.0, pos.cost_basis - proceeds)

    market.q_yes = new_yes
    market.q_no = new_no
    pos.updated_at = utcnow()

    trade = Trade(
        market_id=market.id,
        user_id=user_id,
        side=side,
        action=action,
        shares=shares,
        cost=cost if action == "BUY" else -cost,
        avg_price=amm.avg_price(cost, shares),
    )
    db.session.add(trade)
    db.session.flush()
    return trade


def settle_market(market: Market) -> None:
    """Pay $1 per winning share; void refunds cost basis approximately via share burn at 0.5."""
    if market.final_outcome not in {"YES", "NO", "VOID"}:
        raise ValueError("final outcome required")

    positions = Position.query.filter_by(market_id=market.id).all()
    for pos in positions:
        payout = 0.0
        if market.final_outcome == "YES":
            payout = pos.yes_shares * 1.0
        elif market.final_outcome == "NO":
            payout = pos.no_shares * 1.0
        else:  # VOID — return 0.5 per share held (neutral unwind)
            payout = (pos.yes_shares + pos.no_shares) * 0.5

        if payout > 0:
            ledger.apply_entry(
                pos.user_id,
                payout,
                "settle" if market.final_outcome != "VOID" else "void",
                ref_type="market",
                ref_id=market.id,
                note=f"Settlement {market.final_outcome}",
            )
        pos.yes_shares = 0.0
        pos.no_shares = 0.0
        pos.cost_basis = 0.0
        pos.updated_at = utcnow()