from datetime import datetime
from database.db import db


class Vendor(db.Model):
    __tablename__ = "vendors"

    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey("societies.id"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    service_type = db.Column(db.String(100), nullable=False)  # Lift AMC, Security, Generator, Gardening, etc.
    contact_person = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    gst_number = db.Column(db.String(30), nullable=True)
    pan_number = db.Column(db.String(20), nullable=True)
    bank_account_details = db.Column(db.String(255), nullable=True)
    status = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    society = db.relationship("Society", backref="vendors")

    __table_args__ = (
        db.UniqueConstraint("society_id", "name", name="uq_society_vendor_name"),
    )

    def __repr__(self):
        return f"<Vendor {self.id} {self.name} - {self.service_type}>"
