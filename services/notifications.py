from database.db import db
from models.notification import Notification
from models.user import User


def create_notification(user_id, title, message, link_url=None, kind="info"):
    """Creates an in-app notification for a given user."""
    try:
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            link_url=link_url,
            kind=kind,
            is_read=False
        )
        db.session.add(notif)
        db.session.commit()
        return notif
    except Exception as e:
        db.session.rollback()
        return None


def notify_all_admins(title, message, link_url=None, kind="info"):
    """Dispatches a notification to all active society secretaries/admins."""
    admins = User.query.filter_by(role="secretary", is_active=True).all()
    created = []
    for admin in admins:
        n = create_notification(admin.id, title, message, link_url=link_url, kind=kind)
        if n:
            created.append(n)
    return created


def unread_count(user_id):
    """Returns the count of unread notifications for a user."""
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()


def get_user_notifications(user_id, limit=30):
    """Fetches user notifications ordered newest first."""
    return (
        Notification.query
        .filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def mark_as_read(notification_id, user_id=None):
    """Marks a single notification as read."""
    query = Notification.query.filter_by(id=notification_id)
    if user_id:
        query = query.filter_by(user_id=user_id)
    notif = query.first()
    if notif:
        notif.is_read = True
        db.session.commit()
        return True
    return False


def mark_all_read(user_id):
    """Marks all notifications for a user as read."""
    Notification.query.filter_by(user_id=user_id, is_read=False).update({"is_read": True})
    db.session.commit()
    return True
