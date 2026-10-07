from flask_login import UserMixin
from database.db import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    mobile = db.Column(
        db.String(15),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(50),
        nullable=False,
        default="member"
    )

    is_active = db.Column(
        db.Boolean,
        default=True
    )

    approval_status = db.Column(
        db.String(20),
        nullable=False,
        default="approved"
    )

    approved_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    approved_at = db.Column(
        db.DateTime,
        nullable=True
    )

    rejection_reason = db.Column(
        db.String(255),
        nullable=True
    )

    failed_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    locked_until = db.Column(
        db.DateTime,
        nullable=True
    )

    last_login_at = db.Column(
        db.DateTime,
        nullable=True
    )

    must_change_password = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

    approver = db.relationship(
        "User",
        remote_side=[id],
        foreign_keys=[approved_by],
        backref="approved_users"
    )

    def __repr__(self):
        return f"<User {self.email} ({self.role}/{self.approval_status})>"