from datetime import datetime

from database.db import db


class ExpenseCategory(db.Model):

    __tablename__ = "expense_categories"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    society_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "societies.id"
        ),
        nullable=False,
        index=True
    )

    name = db.Column(
        db.String(120),
        nullable=False
    )

    description = db.Column(
        db.String(255),
        nullable=True
    )

    status = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


    __table_args__ = (

        db.UniqueConstraint(
            "society_id",
            "name",
            name="uq_expense_category_society_name"
        ),

    )


    def __repr__(self):

        return (
            f"<ExpenseCategory "
            f"{self.name}>"
        )