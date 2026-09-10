from __future__ import annotations

from sqlalchemy import and_, or_

from app.extensions import db
from app.models import DirectMessage, Friendship, User, utcnow


def get_friendship(user_a: int, user_b: int) -> Friendship | None:
    return Friendship.query.filter(
        or_(
            and_(Friendship.requester_id == user_a, Friendship.addressee_id == user_b),
            and_(Friendship.requester_id == user_b, Friendship.addressee_id == user_a),
        )
    ).first()


def relation_status(viewer_id: int, other_id: int) -> str:
    if viewer_id == other_id:
        return "self"
    fr = get_friendship(viewer_id, other_id)
    if not fr:
        return "none"
    if fr.status == "accepted":
        return "friends"
    if fr.status == "pending":
        if fr.requester_id == viewer_id:
            return "outgoing"
        return "incoming"
    return "declined"


def friend_ids(user_id: int) -> set[int]:
    rows = Friendship.query.filter(
        Friendship.status == "accepted",
        or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
    ).all()
    out: set[int] = set()
    for r in rows:
        out.add(r.addressee_id if r.requester_id == user_id else r.requester_id)
    return out


def list_friends(user_id: int) -> list[User]:
    ids = friend_ids(user_id)
    if not ids:
        return []
    return User.query.filter(User.id.in_(ids)).order_by(User.display_name.asc()).all()


def pending_incoming(user_id: int) -> list[Friendship]:
    return (
        Friendship.query.filter_by(addressee_id=user_id, status="pending")
        .order_by(Friendship.created_at.desc())
        .all()
    )


def send_request(requester_id: int, addressee_id: int) -> Friendship:
    if requester_id == addressee_id:
        raise ValueError("cannot friend yourself")
    if db.session.get(User, addressee_id) is None:
        raise ValueError("user not found")
    existing = get_friendship(requester_id, addressee_id)
    if existing:
        if existing.status == "accepted":
            raise ValueError("already friends")
        if existing.status == "pending":
            raise ValueError("request already pending")
        # Re-open declined
        existing.requester_id = requester_id
        existing.addressee_id = addressee_id
        existing.status = "pending"
        existing.updated_at = utcnow()
        return existing
    fr = Friendship(requester_id=requester_id, addressee_id=addressee_id, status="pending")
    db.session.add(fr)
    db.session.flush()
    return fr


def accept_request(user_id: int, friendship_id: int) -> Friendship:
    fr = db.session.get(Friendship, friendship_id)
    if fr is None:
        raise ValueError("request not found")
    if fr.addressee_id != user_id:
        raise ValueError("not your request to accept")
    if fr.status != "pending":
        raise ValueError("request is not pending")
    fr.status = "accepted"
    fr.updated_at = utcnow()
    return fr


def decline_request(user_id: int, friendship_id: int) -> Friendship:
    fr = db.session.get(Friendship, friendship_id)
    if fr is None:
        raise ValueError("request not found")
    if fr.addressee_id != user_id:
        raise ValueError("not your request to decline")
    if fr.status != "pending":
        raise ValueError("request is not pending")
    fr.status = "declined"
    fr.updated_at = utcnow()
    return fr


def unfriend(user_id: int, other_id: int) -> None:
    fr = get_friendship(user_id, other_id)
    if not fr or fr.status != "accepted":
        raise ValueError("not friends")
    db.session.delete(fr)


def search_users(query: str, *, limit: int = 30) -> list[User]:
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    return (
        User.query.filter(
            or_(User.display_name.ilike(like), and_(User.is_anonymous_display.is_(False), User.netid.ilike(like)))
        )
        .order_by(User.display_name.asc())
        .limit(limit)
        .all()
    )


def are_friends(a: int, b: int) -> bool:
    return relation_status(a, b) == "friends"


def conversation(user_a: int, user_b: int, *, limit: int = 200) -> list[DirectMessage]:
    messages = (
        DirectMessage.query.filter(
            or_(
                and_(DirectMessage.sender_id == user_a, DirectMessage.recipient_id == user_b),
                and_(DirectMessage.sender_id == user_b, DirectMessage.recipient_id == user_a),
            )
        )
        .order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(messages))


def send_dm(sender_id: int, recipient_id: int, body: str) -> DirectMessage:
    if not are_friends(sender_id, recipient_id):
        raise ValueError("you can only message friends")
    text = (body or "").strip()
    if not text:
        raise ValueError("message empty")
    msg = DirectMessage(
        sender_id=sender_id,
        recipient_id=recipient_id,
        body=text[:2000],
    )
    db.session.add(msg)
    db.session.flush()
    return msg


def inbox_threads(user_id: int) -> list[dict]:
    """Latest message per friend conversation."""
    friends = list_friends(user_id)
    threads = []
    for friend in friends:
        latest = (
            DirectMessage.query.filter(
                or_(
                    and_(
                        DirectMessage.sender_id == user_id,
                        DirectMessage.recipient_id == friend.id,
                    ),
                    and_(
                        DirectMessage.sender_id == friend.id,
                        DirectMessage.recipient_id == user_id,
                    ),
                )
            )
            .order_by(DirectMessage.created_at.desc())
            .first()
        )
        threads.append({"friend": friend, "latest": latest})
    threads.sort(
        key=lambda t: t["latest"].created_at if t["latest"] else utcnow().replace(year=1970),
        reverse=True,
    )
    return threads
