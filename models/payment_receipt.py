from database.db import db


class PaymentReceipt(db.Model):

    __tablename__ = "payment_receipts"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    payment_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_payments.id"),
        nullable=False,
        unique=True
    )

    receipt_number = db.Column(
        db.String(50),
        nullable=False,
        unique=True
    )

    generated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    generated_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    payment = db.relationship(
        "MaintenancePayment",
        backref=db.backref(
            "receipt",
            uselist=False
        )
    )

    generator = db.relationship(
        "User",
        foreign_keys=[generated_by]
    )