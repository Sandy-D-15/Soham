from datetime import datetime
from database.db import db


class Notice(db.Model):
    __tablename__ = "notices"

    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey("societies.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default="General", nullable=False)  # General, Meeting, Maintenance, Emergency, Event
    priority = db.Column(db.String(20), default="Normal", nullable=False)  # Normal, Important, Urgent
    attachment_path = db.Column(db.String(255), nullable=True)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.Date, nullable=True)

    society = db.relationship("Society", backref="notices")
    author = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Notice {self.id} {self.title}>"
