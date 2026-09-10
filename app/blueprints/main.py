from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.models import User
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
    positions = [p for p in current_user.positions if p.yes_shares > 1e-9 or p.no_shares > 1e-9]
    cash = current_user.ledger.balance if current_user.ledger else 0.0
    from app.services.history import cash_balance_series

    series = cash_balance_series(current_user.id)
    return render_template(
        "portfolio.html",
        positions=positions,
        cash=cash,
        total=portfolio_value(current_user),
        stats=user_stats(current_user),
        balance_series=series,
    )
