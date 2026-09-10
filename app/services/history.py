from __future__ import annotations

from app.models import LedgerAccount, LedgerEntry


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
