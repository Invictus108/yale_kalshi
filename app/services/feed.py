from __future__ import annotations

from flask import current_app
from sqlalchemy import func

from app.models import Market, Position, Trade, User
from app.services.friends import friend_ids
from app.services.resolve import close_if_expired
from app.services.users import portfolio_value


def user_stats(user: User) -> dict:
    seed = float(current_app.config["SEED_BALANCE"])
    total = portfolio_value(user)
    cash = user.ledger.balance if user.ledger else 0.0
    trade_count = Trade.query.filter_by(user_id=user.id).count()
    open_positions = sum(
        1
        for p in user.positions
        if (p.yes_shares > 1e-9 or p.no_shares > 1e-9)
        and p.market.status not in {"resolved", "void"}
    )
    return {
        "cash": cash,
        "portfolio": total,
        "earnings": total - seed,
        "trade_count": trade_count,
        "open_positions": open_positions,
        "seed": seed,
    }


def popular_feed(*, viewer: User | None, limit: int = 40) -> list[dict]:
    """Open/active markets ranked by trade count, with friend participation."""
    statuses = ["open", "closed", "proposed", "disputed"]
    markets = Market.query.filter(Market.status.in_(statuses)).all()
    for m in markets:
        close_if_expired(m)

    # trade counts
    counts = dict(
        Trade.query.with_entities(Trade.market_id, func.count(Trade.id))
        .group_by(Trade.market_id)
        .all()
    )
    unique_traders = dict(
        Trade.query.with_entities(Trade.market_id, func.count(func.distinct(Trade.user_id)))
        .group_by(Trade.market_id)
        .all()
    )

    fids: set[int] = set()
    if viewer is not None and viewer.is_authenticated:
        fids = friend_ids(viewer.id)

    cards = []
    for m in markets:
        friends_here: list[User] = []
        if fids:
            positions = Position.query.filter(
                Position.market_id == m.id,
                Position.user_id.in_(fids),
            ).all()
            active_ids = {
                p.user_id
                for p in positions
                if p.yes_shares > 1e-9 or p.no_shares > 1e-9
            }
            # Also count friends who traded even if flat
            traded_friend_ids = {
                uid
                for (uid,) in Trade.query.with_entities(Trade.user_id)
                .filter(Trade.market_id == m.id, Trade.user_id.in_(fids))
                .distinct()
                .all()
            }
            show_ids = active_ids | traded_friend_ids
            if show_ids:
                friends_here = User.query.filter(User.id.in_(show_ids)).all()

        trade_n = counts.get(m.id, 0)
        trader_n = unique_traders.get(m.id, 0)
        # Popularity: trades + unique traders + slight boost if friends present
        score = trade_n * 2 + trader_n * 3 + (10 if friends_here else 0)
        if m.status == "open":
            score += 5
        cards.append(
            {
                "market": m,
                "trade_count": trade_n,
                "trader_count": trader_n,
                "friends": friends_here,
                "score": score,
            }
        )

    cards.sort(key=lambda c: (c["score"], c["market"].created_at), reverse=True)
    return cards[:limit]
