from flask import Flask
import math

from app.extensions import db, login_manager
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    for key, minimum, inclusive in [("LMSR_B", 0, False), ("SEED_BALANCE", 0, True), ("DISPUTE_HOURS", 0, True)]:
        value = float(app.config[key])
        if not math.isfinite(value) or (value < minimum if inclusive else value <= minimum):
            raise ValueError(f"{key} must be finite and {'nonnegative' if inclusive else 'positive'}")

    db.init_app(app)
    login_manager.init_app(app)
    from app.security import init_security
    init_security(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    from app.blueprints.admin import admin_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import main_bp
    from app.blueprints.markets import markets_bp
    from app.blueprints.social import social_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(markets_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(social_bp)

    @app.cli.command("settle-markets")
    def settle_markets_command():
        """Close expired markets and settle due, undisputed proposals."""
        import click
        from app.services.resolve import refresh_active_markets
        refresh_active_markets()
        click.echo("Market lifecycle updates committed.")

    with app.app_context():
        db.create_all()
        _ensure_bootstrap_admin(app)
        from app.services.demo_seed import seed_demo_social

        seed_demo_social(app)

    return app


def _ensure_bootstrap_admin(app: Flask) -> None:
    """Ensure bootstrap NetID exists and is admin (idempotent)."""
    from app.services.users import get_or_create_user

    netid = app.config["BOOTSTRAP_ADMIN_NETID"].lower()
    user = get_or_create_user(netid)
    if not user.is_admin:
        user.is_admin = True
        db.session.commit()
