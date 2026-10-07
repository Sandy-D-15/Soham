from datetime import datetime
from database.db import db


class Complaint(db.Model):
    __tablename__ = "complaints"

    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey("societies.id"), nullable=False, index=True)
    member_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    flat_id = db.Column(db.Integer, db.ForeignKey("flats.id"), nullable=True)
    
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Plumbing, Electrical, Lift, Security, Cleanliness, Noise, Other
    priority = db.Column(db.String(20), default="Medium", nullable=False)  # Low, Medium, High, Emergency
    status = db.Column(db.String(30), default="Open", nullable=False, index=True)  # Open, In Progress, Resolved, Closed
    
    assigned_to_type = db.Column(db.String(30), nullable=True)  # Staff, Vendor, Committee
    assigned_name = db.Column(db.String(120), nullable=True)
    
    resolution_notes = db.Column(db.Text, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    society = db.relationship("Society", backref="complaints")
    member = db.relationship("User", foreign_keys=[member_id], backref="filed_complaints")
    flat = db.relationship("Flat", foreign_keys=[flat_id])
    resolver = db.relationship("User", foreign_keys=[resolved_by])

    def __repr__(self):
        return f"<Complaint {self.id} {self.title} - {self.status}>"
