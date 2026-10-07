from database.db import db


class ComplaintHistory(db.Model):
    __tablename__ = "complaint_history"

    id = db.Column(db.Integer, primary_key=True)

    complaint_id = db.Column(
        db.Integer,
        db.ForeignKey("complaints.id"),
        nullable=False,
        index=True
    )

    changed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    old_status = db.Column(
        db.String(50),
        nullable=True
    )

    new_status = db.Column(
        db.String(50),
        nullable=False
    )

    note = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    complaint = db.relationship(
        "Complaint",
        backref=db.backref("history_entries", lazy=True, order_by="ComplaintHistory.created_at.desc()")
    )

    actor = db.relationship(
        "User",
        backref="complaint_status_changes"
    )

    def __repr__(self):
        return f"<ComplaintHistory {self.id} for Complaint {self.complaint_id}: {self.old_status} -> {self.new_status}>"
