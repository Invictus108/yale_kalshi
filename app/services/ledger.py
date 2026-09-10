from __future__ import annotations

from app.extensions import db
from app.models import LedgerAccount, LedgerEntry, utcnow


def get_or_create_account(user_id: int) -> LedgerAccount:
    account = LedgerAccount.query.filter_by(user_id=user_id).first()
    if account:
        return account
    account = LedgerAccount(user_id=user_id, rail="PLAY", balance=0.0)
    db.session.add(account)
    db.session.flush()
    return account


def apply_entry(
    user_id: int,
    amount: float,
    kind: str,
    *,
    ref_type: str | None = None,
    ref_id: int | None = None,
    note: str | None = None,
    allow_negative: bool = False,
) -> LedgerAccount:
    account = get_or_create_account(user_id)
    new_balance = account.balance + amount
    if not allow_negative and new_balance < -1e-9:
        raise ValueError("insufficient balance")
    account.balance = new_balance
    account.updated_at = utcnow()
    db.session.add(
        LedgerEntry(
            account_id=account.id,
            amount=amount,
            kind=kind,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
        )
    )
    return account


def seed_if_needed(user_id: int, seed_amount: float) -> None:
    account = get_or_create_account(user_id)
    if account.balance == 0 and not account.entries:
        apply_entry(user_id, seed_amount, "seed", note="Welcome play-money grant")