from database.db import db


class Building(db.Model):
    __tablename__ = "buildings"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    society_id = db.Column(
        db.Integer,
        db.ForeignKey("societies.id"),
        nullable=False
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    address = db.Column(
        db.String(255),
        nullable=True
    )

    status = db.Column(
        db.Boolean,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    __table_args__ = (
        db.UniqueConstraint(
            "society_id",
            "name",
            name="uq_building_society_name"
        ),
    )

    wings = db.relationship(
        "Wing",
        backref="building",
        lazy=True,
        cascade="all, delete-orphan"
    )