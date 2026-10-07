from database.db import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    title = db.Column(
        db.String(150),
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    link_url = db.Column(
        db.String(255),
        nullable=True
    )

    kind = db.Column(
        db.String(50),
        nullable=False,
        default="info"
    )

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    __table_args__ = (
        db.Index("ix_notifications_user_unread", "user_id", "is_read"),
    )

    user = db.relationship(
        "User",
        backref=db.backref("notifications", lazy=True, order_by="desc(Notification.created_at)")
    )

    def __repr__(self):
        return f"<Notification {self.id} for User {self.user_id} - read={self.is_read}>"
