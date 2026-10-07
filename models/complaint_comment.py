from database.db import db


class ComplaintComment(db.Model):
    __tablename__ = "complaint_comments"

    id = db.Column(db.Integer, primary_key=True)

    complaint_id = db.Column(
        db.Integer,
        db.ForeignKey("complaints.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    comment = db.Column(
        db.Text,
        nullable=False
    )

    is_internal = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    complaint = db.relationship(
        "Complaint",
        backref=db.backref("comments", lazy=True, order_by="ComplaintComment.created_at.asc()")
    )

    user = db.relationship(
        "User",
        backref="complaint_comments"
    )

    def __repr__(self):
        return f"<ComplaintComment {self.id} on Complaint {self.complaint_id}>"
