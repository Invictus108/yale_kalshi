from __future__ import annotations

import smtplib
from email.message import EmailMessage

from flask import current_app

from app.extensions import db
from app.models import NotificationLog, User


def send_email(to_addr: str, subject: str, body: str) -> tuple[str, str]:
    host = current_app.config.get("SMTP_HOST") or ""
    if not host:
        return "skipped", "SMTP_HOST not configured"

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = current_app.config["SMTP_FROM"]
        msg["To"] = to_addr
        msg.set_content(body)
        port = current_app.config["SMTP_PORT"]
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if current_app.config.get("SMTP_USE_TLS"):
                smtp.starttls()
            user = current_app.config.get("SMTP_USER") or ""
            password = current_app.config.get("SMTP_PASSWORD") or ""
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return "sent", "ok"
    except Exception as exc:  # noqa: BLE001 - log and continue
        return "failed", str(exc)


def notify_user(
    user: User,
    subject: str,
    body: str,
    *,
    market_id: int | None = None,
) -> None:
    status, detail = "skipped", "notifications disabled"
    if user.notify_email:
        status, detail = send_email(user.email, subject, body)
    db.session.add(
        NotificationLog(
            user_id=user.id,
            market_id=market_id,
            subject=subject,
            status=status,
            detail=detail,
        )
    )


def notify_market_holders(market, subject: str, body: str) -> None:
    from app.models import Position

    user_ids = {
        p.user_id
        for p in Position.query.filter_by(market_id=market.id).all()
        if (p.yes_shares > 0 or p.no_shares > 0 or market.status == "resolved")
    }
    # Also notify creator
    user_ids.add(market.creator_id)
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    for user in users:
        notify_user(user, subject, body, market_id=market.id)
