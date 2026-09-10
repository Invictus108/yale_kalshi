"""Idempotent demo friends / DMs / ledger history for local UX testing."""

from __future__ import annotations

from datetime import timedelta

from flask import Flask

from app.extensions import db
from app.models import DirectMessage, Friendship, LedgerEntry, utcnow
from app.services import ledger
from app.services.users import get_or_create_user


DEMO_FRIENDS = (
    {
        "netid": "demo_maya",
        "display_name": "Maya Chen",
        "is_anonymous_display": False,
        "messages_to_admin": [
            "yo are you trading the dining hall market?",
            "I took YES at 42¢ — feels free",
        ],
        "messages_from_admin": [
            "ha maybe. price looks soft though",
        ],
    },
    {
        "netid": "demo_sam",
        "display_name": "AnonPuffin418",
        "is_anonymous_display": True,
        "messages_to_admin": [
            "leaderboard climb incoming",
        ],
        "messages_from_admin": [
            "respect the anonymity king",
            "want to co-create a Masters’ Cup market?",
        ],
    },
    {
        "netid": "demo_rio",
        "display_name": "Rio Alvarez",
        "is_anonymous_display": False,
        "messages_to_admin": [
            "dispute window on that YCC market is wild",
            "void it if the source is unclear imo",
        ],
        "messages_from_admin": [],
    },
)


def seed_demo_social(app: Flask) -> None:
    if not app.config.get("SEED_DEMO_DATA"):
        return

    admin = get_or_create_user(app.config["BOOTSTRAP_ADMIN_NETID"])
    created_any = False

    for spec in DEMO_FRIENDS:
        user = get_or_create_user(spec["netid"])
        # Stabilize display for demos
        if user.display_name != spec["display_name"] or user.is_anonymous_display != spec[
            "is_anonymous_display"
        ]:
            user.display_name = spec["display_name"]
            user.is_anonymous_display = spec["is_anonymous_display"]
            created_any = True

        fr = Friendship.query.filter(
            (
                (Friendship.requester_id == admin.id)
                & (Friendship.addressee_id == user.id)
            )
            | (
                (Friendship.requester_id == user.id)
                & (Friendship.addressee_id == admin.id)
            )
        ).first()
        if not fr:
            fr = Friendship(
                requester_id=admin.id,
                addressee_id=user.id,
                status="accepted",
            )
            db.session.add(fr)
            created_any = True
        elif fr.status != "accepted":
            fr.status = "accepted"
            created_any = True

        # Seed DMs once (if thread empty)
        existing = DirectMessage.query.filter(
            (
                (DirectMessage.sender_id == admin.id)
                & (DirectMessage.recipient_id == user.id)
            )
            | (
                (DirectMessage.sender_id == user.id)
                & (DirectMessage.recipient_id == admin.id)
            )
        ).count()
        if existing == 0:
            t0 = utcnow() - timedelta(hours=6)
            offset = 0
            for body in spec["messages_from_admin"]:
                db.session.add(
                    DirectMessage(
                        sender_id=admin.id,
                        recipient_id=user.id,
                        body=body,
                        created_at=t0 + timedelta(minutes=offset),
                    )
                )
                offset += 12
                created_any = True
            for body in spec["messages_to_admin"]:
                db.session.add(
                    DirectMessage(
                        sender_id=user.id,
                        recipient_id=admin.id,
                        body=body,
                        created_at=t0 + timedelta(minutes=offset),
                    )
                )
                offset += 12
                created_any = True

    _seed_admin_balance_history(admin.id)
    if created_any:
        db.session.commit()
    else:
        db.session.commit()  # still commit history inserts if any


def _seed_admin_balance_history(admin_id: int) -> None:
    """Backdated ledger moves so the portfolio chart isn’t a flat line."""
    from flask import current_app

    account = ledger.get_or_create_account(admin_id)
    already = LedgerEntry.query.filter_by(
        account_id=account.id, note="demo:history-seed"
    ).first()
    if already:
        return

    # Demo mode: rebuild a clean history once (keeps ending balance at SEED_BALANCE).
    LedgerEntry.query.filter_by(account_id=account.id).delete()
    seed_amt = float(current_app.config["SEED_BALANCE"])
    base = utcnow() - timedelta(days=14)

    db.session.add(
        LedgerEntry(
            account_id=account.id,
            amount=seed_amt,
            kind="seed",
            note="Welcome play-money grant",
            created_at=base,
        )
    )

    moves = [
        (1, -120, "trade", "BUY YES dining"),
        (2, 80, "trade", "SELL YES dining"),
        (4, -200, "trade", "BUY NO YCC"),
        (5, 310, "settle", "YCC resolved NO"),
        (7, -90, "trade", "BUY YES The Game"),
        (9, -40, "trade", "BUY YES Masters’"),
        (11, 150, "settle", "Masters’ resolved YES"),
        (12, -90, "trade", "demo:history-seed"),
    ]
    running = seed_amt
    for day, delta, kind, note in moves:
        running += delta
        db.session.add(
            LedgerEntry(
                account_id=account.id,
                amount=delta,
                kind=kind,
                note=note,
                created_at=base + timedelta(days=day, hours=10),
            )
        )
    account.balance = running
    account.updated_at = utcnow()
