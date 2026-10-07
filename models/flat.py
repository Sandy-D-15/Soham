from database.db import db


class Flat(db.Model):
    __tablename__ = "flats"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    floor_id = db.Column(
        db.Integer,
        db.ForeignKey("floors.id"),
        nullable=False
    )

    flat_number = db.Column(
        db.String(20),
        nullable=False
    )

    flat_type = db.Column(
        db.String(50),
        nullable=True
    )

    carpet_area = db.Column(
        db.Float,
        nullable=True
    )

    built_up_area = db.Column(
        db.Float,
        nullable=True
    )

    maintenance_category = db.Column(
        db.String(100),
        nullable=True
    )

    ownership_status = db.Column(
        db.String(50),
        default="Owned"
    )

    occupancy_status = db.Column(
        db.String(50),
        default="Vacant"
    )

    parking_information = db.Column(
        db.String(150),
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
            "floor_id",
            "flat_number",
            name="uq_flat_floor_number"
        ),
    )