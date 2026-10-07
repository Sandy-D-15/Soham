from database.db import db


class MaintenanceBillItem(db.Model):

    __tablename__ = "maintenance_bill_items"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    bill_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_bills.id"),
        nullable=False
    )

    component_id = db.Column(
        db.Integer,
        db.ForeignKey("maintenance_components.id"),
        nullable=True
    )

    component_name = db.Column(
        db.String(100),
        nullable=False
    )

    calculation_method = db.Column(
        db.String(50),
        nullable=False
    )

    rate = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    quantity = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=1
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    bill = db.relationship(
        "MaintenanceBill",
        backref=db.backref(
            "items",
            lazy=True,
            cascade="all, delete-orphan"
        )
    )

    component = db.relationship(
        "MaintenanceComponent"
    )