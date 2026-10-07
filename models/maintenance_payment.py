from database.db import db


class MaintenancePayment(db.Model):

    __tablename__ = "maintenance_payments"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    bill_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_bills.id"),
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    payment_date = db.Column(
        db.Date,
        nullable=False
    )

    payment_mode = db.Column(
        db.String(50),
        nullable=False
    )

    reference_number = db.Column(
        db.String(100),
        nullable=True
    )

    notes = db.Column(
        db.String(255),
        nullable=True
    )

    recorded_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    bill = db.relationship(
        "MaintenanceBill",
        backref=db.backref(
            "payments",
            lazy=True
        )
    )

    recorder = db.relationship(
        "User",
        foreign_keys=[recorded_by]
    )