from database.db import db


class MaintenanceBill(db.Model):

    __tablename__ = "maintenance_bills"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    society_id = db.Column(
        db.Integer,
        db.ForeignKey("societies.id"),
        nullable=False
    )

    flat_id = db.Column(
        db.Integer,
        db.ForeignKey("flats.id"),
        nullable=False
    )

    bill_year = db.Column(
        db.Integer,
        nullable=False
    )

    bill_month = db.Column(
        db.Integer,
        nullable=False
    )

    bill_date = db.Column(
        db.Date,
        nullable=False
    )

    due_date = db.Column(
        db.Date,
        nullable=False
    )

    subtotal = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    penalty_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    total_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    paid_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    balance_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="Unpaid"
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
            "flat_id",
            "bill_year",
            "bill_month",
            name="uq_flat_monthly_bill"
        ),

    )

    flat = db.relationship(
        "Flat",
        backref="maintenance_bills"
    )

    society = db.relationship(
        "Society",
        backref="maintenance_bills"
    )

    @property
    def bill_amount(self):
        return self.total_amount

    @property
    def amount_paid(self):
        return self.paid_amount

    @property
    def late_fee(self):
        return self.penalty_amount

    @property
    def payment_status(self):
        return self.status