from database.db import db


class RegistrationRequest(db.Model):
    __tablename__ = "registration_requests"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    requested_flat_id = db.Column(
        db.Integer,
        db.ForeignKey("flats.id"),
        nullable=False
    )

    relation_type = db.Column(
        db.String(50),
        nullable=False,
        default="Owner"
    )

    notes = db.Column(
        db.String(300),
        nullable=True
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
        index=True
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    reviewed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    rejection_reason = db.Column(
        db.String(255),
        nullable=True
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("registration_requests", lazy=True)
    )

    reviewer = db.relationship(
        "User",
        foreign_keys=[reviewed_by],
        backref="reviewed_requests"
    )

    flat = db.relationship(
        "Flat",
        backref="registration_requests"
    )

    def __repr__(self):
        return f"<RegistrationRequest user={self.user_id} flat={self.requested_flat_id} status={self.status}>"
