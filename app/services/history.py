from __future__ import annotations

from app.extensions import db
from app.models import LedgerAccount, LedgerEntry, Market, Trade, utcnow
from app.services.amm import lmsr_price_yes


def cash_balance_series(user_id: int) -> list[dict]:
    """
    Running cash balance after each ledger entry (oldest → newest).
    Returns [{t: iso, balance: float, kind, note}, ...]
    """
    account = LedgerAccount.query.filter_by(user_id=user_id).first()
    if not account:
        return []

    entries = (
        LedgerEntry.query.filter_by(account_id=account.id)
        .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
        .all()
    )
    running = 0.0
    series = []
    for e in entries:
        running += e.amount
        series.append(
            {
                "t": e.created_at.isoformat(sep=" ", timespec="minutes"),
                "balance": round(running, 2),
                "kind": e.kind,
                "note": e.note or "",
            }
        )
    # Ensure current balance is the last point if drift
    if series and abs(series[-1]["balance"] - account.balance) > 0.05:
        series.append(
            {
                "t": "now",
                "balance": round(account.balance, 2),
                "kind": "current",
                "note": "live balance",
            }
        )
    return series


def position_value_series(user_id: int, market_id: int) -> list[dict]:
    """
    Mark-to-market value of a user's stake in one market over time.

    Replays all market trades through LMSR for prices, tracks the user's YES/NO
    inventory, and records mark = yes*p_yes + no*p_no after each event once the
    user has traded. Settlement is appended when the market resolves.
    """
    market = db.session.get(Market, market_id)
    if not market:
        return []

    b = float(market.lmsr_b)
    trades = (
        Trade.query.filter_by(market_id=market_id)
        .order_by(Trade.created_at.asc(), Trade.id.asc())
        .all()
    )

    q_yes = 0.0
    q_no = 0.0
    yes_shares = 0.0
    no_shares = 0.0
    user_active = False
    series: list[dict] = []

    def _append(t, *, kind: str, note: str = "") -> None:
        p_yes = lmsr_price_yes(q_yes, q_no, b)
        mark = yes_shares * p_yes + no_shares * (1.0 - p_yes)
        series.append(
            {
                "t": t,
                "mark": round(mark, 2),
                "price_yes": round(p_yes * 100, 1),
                "yes_shares": round(yes_shares, 4),
                "no_shares": round(no_shares, 4),
                "kind": kind,
                "note": note,
            }
        )

    for trade in trades:
        delta = trade.shares if trade.action == "BUY" else -trade.shares
        if trade.side == "YES":
            q_yes += delta
        else:
            q_no += delta

        if trade.user_id == user_id:
            user_active = True
            if trade.side == "YES":
                yes_shares += delta
            else:
                no_shares += delta
            yes_shares = max(0.0, yes_shares)
            no_shares = max(0.0, no_shares)

        if not user_active:
            continue

        note = ""
        kind = "mark"
        if trade.user_id == user_id:
            kind = "trade"
            note = f"{trade.action} {trade.shares:g} {trade.side}"
        _append(
            trade.created_at.isoformat(sep=" ", timespec="minutes"),
            kind=kind,
            note=note,
        )

    if not user_active:
        return []

    if market.status in {"resolved", "void"} and (yes_shares > 1e-9 or no_shares > 1e-9):
        outcome = (market.final_outcome or "").upper()
        if outcome == "YES":
            payout = yes_shares
        elif outcome == "NO":
            payout = no_shares
        elif outcome == "VOID":
            payout = (yes_shares + no_shares) * 0.5
        else:
            p_yes = lmsr_price_yes(q_yes, q_no, b)
            payout = yes_shares * p_yes + no_shares * (1.0 - p_yes)
        settle_t = (
            market.resolved_at.isoformat(sep=" ", timespec="minutes")
            if market.resolved_at
            else "settled"
        )
        p_yes = lmsr_price_yes(q_yes, q_no, b)
        series.append(
            {
                "t": settle_t,
                "mark": round(payout, 2),
                "price_yes": round(p_yes * 100, 1),
                "yes_shares": round(yes_shares, 4),
                "no_shares": round(no_shares, 4),
                "kind": "settle",
                "note": f"Settled {outcome or '—'}",
            }
        )
        series.append(
            {
                "t": settle_t,
                "mark": 0.0,
                "price_yes": round(p_yes * 100, 1),
                "yes_shares": 0.0,
                "no_shares": 0.0,
                "kind": "closed",
                "note": "Position closed",
            }
        )
    elif yes_shares > 1e-9 or no_shares > 1e-9:
        live = yes_shares * market.price_yes + no_shares * market.price_no
        if not series or abs(series[-1]["mark"] - live) > 0.05:
            series.append(
                {
                    "t": utcnow().isoformat(sep=" ", timespec="minutes"),
                    "mark": round(live, 2),
                    "price_yes": round(market.price_yes * 100, 1),
                    "yes_shares": round(yes_shares, 4),
                    "no_shares": round(no_shares, 4),
                    "kind": "now",
                    "note": "Live mark",
                }
            )

    return series


def open_position_charts(user_id: int, positions) -> list[dict]:
    """Build chart payloads for each open position with enough history."""
    charts = []
    for pos in positions:
        series = position_value_series(user_id, pos.market_id)
        if len(series) < 2:
            continue
        charts.append(
            {
                "market_id": pos.market_id,
                "title": pos.market.title,
                "status": pos.market.status,
                "series": series,
            }
        )
    return charts
