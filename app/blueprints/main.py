from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Market, User
from app.services.feed import popular_feed, user_stats
from app.services.users import portfolio_value

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    viewer = current_user if current_user.is_authenticated else None
    feed = popular_feed(viewer=viewer, limit=40)
    db.session.commit()
    return render_template("index.html", feed=feed)


@main_bp.route("/leaderboard")
@login_required
def leaderboard():
    from app.services.resolve import refresh_active_markets
    refresh_active_markets()
    users = User.query.all()
    rows = []
    for u in users:
        stats = user_stats(u)
        rows.append(
            {
                "user": u,
                "value": stats["portfolio"],
                "cash": stats["cash"],
                "earnings": stats["earnings"],
            }
        )
    rows.sort(key=lambda r: r["value"], reverse=True)
    return render_template("leaderboard.html", rows=rows)


@main_bp.route("/portfolio")
@login_required
def portfolio():
    from app.services.resolve import refresh_active_markets
    refresh_active_markets()
    from app.services.history import cash_balance_series, open_position_charts
    from app.services.trading import quote_sell_proceeds

    positions = [p for p in current_user.positions if p.yes_shares > 1e-9 or p.no_shares > 1e-9]
    cash = current_user.ledger.balance if current_user.ledger else 0.0
    series = cash_balance_series(current_user.id)
    position_rows = []
    for p in positions:
        yes_out = (
            quote_sell_proceeds(p.market, "YES", p.yes_shares)
            if p.market.can_cash_out and p.yes_shares > 1e-9
            else 0.0
        )
        no_out = (
            quote_sell_proceeds(p.market, "NO", p.no_shares)
            if p.market.can_cash_out and p.no_shares > 1e-9
            else 0.0
        )
        position_rows.append(
            {
                "pos": p,
                "mark": p.yes_shares * p.market.price_yes + p.no_shares * p.market.price_no,
                "yes_cash_out": yes_out,
                "no_cash_out": no_out,
            }
        )
    return render_template(
        "portfolio.html",
        positions=positions,
        position_rows=position_rows,
        cash=cash,
        total=portfolio_value(current_user),
        stats=user_stats(current_user),
        balance_series=series,
        position_charts=open_position_charts(current_user.id, positions),
        my_markets=Market.query.filter_by(creator_id=current_user.id).order_by(Market.created_at.desc(), Market.id.desc()).limit(50).all(),
    )
