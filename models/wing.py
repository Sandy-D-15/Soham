from database.db import db


class Wing(db.Model):
    __tablename__ = "wings"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=False
    )

    name = db.Column(
        db.String(50),
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
            "building_id",
            "name",
            name="uq_wing_building_name"
        ),
    )

    floors = db.relationship(
        "Floor",
        backref="wing",
        lazy=True,
        cascade="all, delete-orphan"
    )