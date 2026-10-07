from database.db import db


class FinancialTransaction(db.Model):

    __tablename__ = "financial_transactions"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    society_id = db.Column(
        db.Integer,
        db.ForeignKey("societies.id"),
        nullable=False,
        index=True
    )

    account_id = db.Column(
        db.Integer,
        db.ForeignKey("financial_accounts.id"),
        nullable=False,
        index=True
    )

    transaction_date = db.Column(
        db.Date,
        nullable=False,
        index=True
    )

    transaction_type = db.Column(
        db.String(30),
        nullable=False
    )

    direction = db.Column(
        db.String(10),
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    reference_number = db.Column(
        db.String(100),
        nullable=True
    )

    description = db.Column(
        db.String(255),
        nullable=False
    )

    source_type = db.Column(
        db.String(50),
        nullable=True
    )

    source_id = db.Column(
        db.Integer,
        nullable=True
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    society = db.relationship(
        "Society",
        backref="financial_transactions"
    )

    account = db.relationship(
        "FinancialAccount",
        backref=db.backref(
            "transactions",
            lazy=True
        )
    )

    creator = db.relationship(
        "User",
        foreign_keys=[created_by]
    )

    __table_args__ = (

        db.CheckConstraint(
            "amount > 0",
            name="ck_financial_transaction_positive_amount"
        ),

        db.CheckConstraint(
            "direction IN ('Credit', 'Debit')",
            name="ck_financial_transaction_direction"
        ),

        db.UniqueConstraint(
            "source_type",
            "source_id",
            "account_id",
            "direction",
            name="uq_financial_transaction_source"
        ),

    )