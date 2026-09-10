from __future__ import annotations

import random
import string

from flask import current_app

from app.extensions import db
from app.models import User
from app.services import ledger


def _anon_name() -> str:
    animals = [
        "Badger",
        "Bulldog",
        "Owl",
        "Fox",
        "Heron",
        "Lynx",
        "Marten",
        "Newt",
        "Otter",
        "Puffin",
        "Quail",
        "Raven",
        "Stoat",
        "Teal",
        "Viper",
        "Wren",
    ]
    suffix = "".join(random.choices(string.digits, k=3))
    return f"Anon{random.choice(animals)}{suffix}"


def get_or_create_user(netid: str) -> User:
    netid = netid.strip().lower()
    user = User.query.filter_by(netid=netid).first()
    if user:
        return user

    is_admin = netid == current_app.config["BOOTSTRAP_ADMIN_NETID"].lower()
    user = User(
        netid=netid,
        email=f"{netid}@yale.edu",
        display_name=_anon_name(),
        is_anonymous_display=True,
        is_admin=is_admin,
        notify_email=True,
    )
    db.session.add(user)
    db.session.flush()
    ledger.seed_if_needed(user.id, float(current_app.config["SEED_BALANCE"]))
    db.session.commit()
    return user


def portfolio_value(user: User) -> float:
    cash = user.ledger.balance if user.ledger else 0.0
    marked = 0.0
    for pos in user.positions:
        market = pos.market
        if market.status in {"resolved", "void"}:
            continue
        marked += pos.yes_shares * market.price_yes + pos.no_shares * market.price_no
    return cash + marked
