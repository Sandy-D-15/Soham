from database.db import db


class FlatMember(db.Model):
    __tablename__ = "flat_members"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    flat_id = db.Column(
        db.Integer,
        db.ForeignKey("flats.id"),
        nullable=False
    )

    relation_type = db.Column(
        db.String(30),
        nullable=False,
        default="Owner"
    )

    is_primary = db.Column(
        db.Boolean,
        default=False
    )

    is_active = db.Column(
        db.Boolean,
        default=True
    )

    start_date = db.Column(
        db.Date,
        nullable=True
    )

    end_date = db.Column(
        db.Date,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "flat_id",
            "relation_type",
            name="uq_user_flat_relation"
        ),
    )

    user = db.relationship(
        "User",
        backref="flat_memberships"
    )

    flat = db.relationship(
        "Flat",
        backref="member_assignments"
    )