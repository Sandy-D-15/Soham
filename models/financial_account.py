from database.db import db


class FinancialAccount(db.Model):

    __tablename__ = "financial_accounts"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    society_id = db.Column(
        db.Integer,
        db.ForeignKey("societies.id"),
        nullable=False
    )

    name = db.Column(
        db.String(120),
        nullable=False
    )

    account_type = db.Column(
        db.String(30),
        nullable=False
    )

    opening_balance = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    status = db.Column(
        db.Boolean,
        nullable=False,
        default=True
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
            "society_id",
            "name",
            name="uq_society_financial_account"
        ),

    )

    society = db.relationship(
        "Society",
        backref="financial_accounts"
    )