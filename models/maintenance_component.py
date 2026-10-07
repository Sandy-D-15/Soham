from database.db import db


class MaintenanceComponent(db.Model):
    __tablename__ = "maintenance_components"

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

    description = db.Column(
        db.String(255),
        nullable=True
    )

    purpose = db.Column(
        db.String(255),
        nullable=True
    )

    calculation_method = db.Column(
        db.String(50),
        nullable=False,
        default="Fixed"
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    applicable_to = db.Column(
        db.String(100),
        nullable=False,
        default="All Flats"
    )

    effective_date = db.Column(
        db.Date,
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

    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

    __table_args__ = (
        db.UniqueConstraint(
            "society_id",
            "name",
            name="uq_society_maintenance_component"
        ),
    )