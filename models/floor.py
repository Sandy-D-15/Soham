from database.db import db


class Floor(db.Model):
    __tablename__ = "floors"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    wing_id = db.Column(
        db.Integer,
        db.ForeignKey("wings.id"),
        nullable=False
    )

    floor_number = db.Column(
        db.Integer,
        nullable=False
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
            "wing_id",
            "floor_number",
            name="uq_floor_wing_number"
        ),
    )

    flats = db.relationship(
        "Flat",
        backref="floor",
        lazy=True,
        cascade="all, delete-orphan"
    )