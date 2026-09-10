from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint

from app.extensions import db


def utcnow():
    # Naive UTC for SQLite compatibility (avoid aware/naive compare bugs).
    return datetime.utcnow()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    netid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    is_anonymous_display = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    notify_email = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    ledger = db.relationship("LedgerAccount", back_populates="user", uselist=False)
    positions = db.relationship("Position", back_populates="user")
    messages = db.relationship("ChatMessage", back_populates="user")

    @property
    def public_name(self) -> str:
        if self.is_anonymous_display:
            return self.display_name or f"Anon-{self.netid[:2].upper()}**"
        return self.display_name or self.netid


class LedgerAccount(db.Model):
    __tablename__ = "ledger_accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    rail = db.Column(db.String(16), default="PLAY", nullable=False)
    balance = db.Column(db.Float, default=0.0, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", back_populates="ledger")
    entries = db.relationship("LedgerEntry", back_populates="account")


class LedgerEntry(db.Model):
    __tablename__ = "ledger_entries"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("ledger_accounts.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # +credit / -debit
    kind = db.Column(db.String(32), nullable=False)  # seed, trade, settle, void, adjust
    ref_type = db.Column(db.String(32))
    ref_id = db.Column(db.Integer)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    account = db.relationship("LedgerAccount", back_populates="entries")


class Market(db.Model):
    __tablename__ = "markets"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    resolution_criteria = db.Column(db.Text, nullable=False)
    resolution_source = db.Column(db.String(500), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(
        db.String(32), default="pending", nullable=False, index=True
    )  # pending, open, closed, proposed, disputed, resolved, void
    closes_at = db.Column(db.DateTime, nullable=False)
    approved_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    rejection_reason = db.Column(db.Text)

    # LMSR state: outstanding YES/NO share quantities in the market maker
    q_yes = db.Column(db.Float, default=0.0, nullable=False)
    q_no = db.Column(db.Float, default=0.0, nullable=False)
    lmsr_b = db.Column(db.Float, nullable=False)

    proposed_outcome = db.Column(db.String(8))  # YES / NO
    proposed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    proposed_at = db.Column(db.DateTime)
    proposal_evidence = db.Column(db.Text)
    dispute_deadline = db.Column(db.DateTime)
    dispute_reason = db.Column(db.Text)

    final_outcome = db.Column(db.String(8))  # YES / NO / VOID
    resolved_at = db.Column(db.DateTime)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    creator = db.relationship("User", foreign_keys=[creator_id])
    positions = db.relationship("Position", back_populates="market")
    trades = db.relationship("Trade", back_populates="market")
    messages = db.relationship("ChatMessage", back_populates="market")

    @property
    def price_yes(self) -> float:
        from app.services.amm import lmsr_price_yes

        return lmsr_price_yes(self.q_yes, self.q_no, self.lmsr_b)

    @property
    def price_no(self) -> float:
        return 1.0 - self.price_yes

    @property
    def can_cash_out(self) -> bool:
        return self.status in {"open", "closed", "proposed", "disputed"} and not self.final_outcome


class Position(db.Model):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "market_id", name="uq_user_market"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    market_id = db.Column(db.Integer, db.ForeignKey("markets.id"), nullable=False)
    yes_shares = db.Column(db.Float, default=0.0, nullable=False)
    no_shares = db.Column(db.Float, default=0.0, nullable=False)
    cost_basis = db.Column(db.Float, default=0.0, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", back_populates="positions")
    market = db.relationship("Market", back_populates="positions")


class Trade(db.Model):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("side IN ('YES','NO')", name="ck_trade_side"),
        CheckConstraint("action IN ('BUY','SELL')", name="ck_trade_action"),
    )

    id = db.Column(db.Integer, primary_key=True)
    market_id = db.Column(db.Integer, db.ForeignKey("markets.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    side = db.Column(db.String(8), nullable=False)
    action = db.Column(db.String(8), nullable=False)
    shares = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)  # points spent (positive) or received
    avg_price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    market = db.relationship("Market", back_populates="trades")
    user = db.relationship("User")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    market_id = db.Column(db.Integer, db.ForeignKey("markets.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    market = db.relationship("Market", back_populates="messages")
    user = db.relationship("User", back_populates="messages")


class NotificationLog(db.Model):
    __tablename__ = "notification_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    market_id = db.Column(db.Integer, db.ForeignKey("markets.id"))
    channel = db.Column(db.String(16), default="email", nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(32), nullable=False)  # sent, skipped, failed
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Friendship(db.Model):
    """Directed request; accepted friendships are treated as mutual in services."""

    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("requester_id", "addressee_id", name="uq_friend_pair"),
        CheckConstraint("status IN ('pending','accepted','declined')", name="ck_friend_status"),
        CheckConstraint("requester_id != addressee_id", name="ck_friend_not_self"),
    )

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    addressee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(16), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    requester = db.relationship("User", foreign_keys=[requester_id])
    addressee = db.relationship("User", foreign_keys=[addressee_id])


class DirectMessage(db.Model):
    __tablename__ = "direct_messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    body = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    read_at = db.Column(db.DateTime)

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])
