from __future__ import annotations
import math

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
    side = side.upper()
    action = action.upper()
    shares = float(shares)
    if not math.isfinite(shares) or shares <= 0:
        raise ValueError("shares must be finite and greater than 0")
    if side not in {"YES", "NO"} or action not in {"BUY", "SELL"}:
        raise ValueError("invalid side/action")
    if action == "BUY" and shares > 1_000_000:
        raise ValueError("buy at most 1,000,000 shares per trade")
    # Lock before deciding eligibility or calculating a price on PostgreSQL.
    # SQLite HTTP writes already hold BEGIN IMMEDIATE from app.security.
    if db.engine.dialect.name == "postgresql":
        db.session.refresh(market, with_for_update=True)
    if not market.can_cash_out:
        raise ValueError("market is not available for trading")
    if action == "BUY" and (market.status != "open" or market.closes_at <= utcnow()):
        raise ValueError("buying has closed; held shares can still be sold before settlement")

    pos = get_or_create_position(user_id, market.id)
    if action == "SELL":
        held = pos.yes_shares if side == "YES" else pos.no_shares
        if shares > held + 1e-9:
            raise ValueError("not enough shares to sell")
        shares = min(shares, held)
        if shares <= 0:
            raise ValueError("no shares to sell")

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


def quote_sell_proceeds(market: Market, side: str, shares: float) -> float:
    """Cash you'd receive selling `shares` of `side` at the current book (no mutation)."""
    side = side.upper()
    shares = float(shares)
    if side not in {"YES", "NO"} or not math.isfinite(shares) or shares < 0:
        raise ValueError("invalid cash-out side or shares")
    if shares == 0:
        return 0.0
    if not market.can_cash_out:
        raise ValueError("market is not available for cash-out")
    cost, _, _ = amm.trade_cost(
        market.q_yes, market.q_no, market.lmsr_b, side, "SELL", shares
    )
    return max(0.0, -cost)


def cash_out(
    *,
    user_id: int,
    market: Market,
    side: str,
) -> Trade:
    """Sell all holdings of YES or NO back to the AMM at the live price."""
    side = side.upper()
    if side not in {"YES", "NO"}:
        raise ValueError("side must be YES or NO")
    if db.engine.dialect.name == "postgresql":
        db.session.refresh(market, with_for_update=True)
    pos = Position.query.filter_by(user_id=user_id, market_id=market.id).first()
    if pos is None:
        raise ValueError(f"no {side} shares to cash out")
    held = pos.yes_shares if side == "YES" else pos.no_shares
    if held <= 1e-9:
        raise ValueError(f"no {side} shares to cash out")
    return execute_trade(
        user_id=user_id,
        market=market,
        side=side,
        action="SELL",
        shares=held,
    )


def settle_market(market: Market) -> None:
    """Pay 1 point per winning share or 0.5 per VOID share, then close positions."""
    if market.final_outcome not in {"YES", "NO", "VOID"}:
        raise ValueError("final outcome required")

    positions = (Position.query.filter_by(market_id=market.id)
                 .order_by(Position.user_id).populate_existing().all())
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
