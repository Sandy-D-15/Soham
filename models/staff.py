from datetime import datetime
from database.db import db


class Staff(db.Model):
    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey("societies.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(80), nullable=False)  # Security Guard, Cleaner, Electrician, Plumber, Manager, etc.
    phone = db.Column(db.String(20), nullable=False)
    salary = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    joining_date = db.Column(db.Date, nullable=False)
    id_proof_number = db.Column(db.String(50), nullable=True)  # Aadhaar / PAN / Voter ID
    emergency_contact = db.Column(db.String(50), nullable=True)
    status = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    society = db.relationship("Society", backref="staff_members")

    def __repr__(self):
        return f"<Staff {self.id} {self.name} - {self.role}>"
