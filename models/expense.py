from datetime import datetime

from database.db import db


class Expense(db.Model):

    __tablename__ = "expenses"

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

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("expense_categories.id"),
        nullable=False,
        index=True
    )

    vendor_name = db.Column(
        db.String(150),
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    expense_date = db.Column(
        db.Date,
        nullable=False,
        index=True
    )

    invoice_reference = db.Column(
        db.String(150),
        nullable=True
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    attachment_path = db.Column(
        db.String(255),
        nullable=True
    )

    # -------------------------
    # APPROVAL WORKFLOW
    # -------------------------

    approval_status = db.Column(
        db.String(30),
        nullable=False,
        default="Pending Approval",
        index=True
    )

    approved_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    approved_at = db.Column(
        db.DateTime,
        nullable=True
    )

    rejected_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    rejected_at = db.Column(
        db.DateTime,
        nullable=True
    )

    rejection_reason = db.Column(
        db.String(255),
        nullable=True
    )

    # -------------------------
    # PAYMENT
    # -------------------------

    payment_status = db.Column(
        db.String(20),
        nullable=False,
        default="Unpaid",
        index=True
    )

    payment_mode = db.Column(
        db.String(30),
        nullable=True
    )

    financial_account_id = db.Column(
        db.Integer,
        db.ForeignKey("financial_accounts.id"),
        nullable=True,
        index=True
    )

    payment_reference = db.Column(
        db.String(150),
        nullable=True
    )

    paid_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    paid_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # -------------------------
    # CREATED BY
    # -------------------------

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
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

        db.CheckConstraint(
            "amount > 0",
            name="ck_expense_amount_positive"
        ),

    )


    category = db.relationship(
        "ExpenseCategory",
        backref="expenses"
    )

    financial_account = db.relationship(
        "FinancialAccount",
        foreign_keys=[financial_account_id]
    )


    def __repr__(self):

        return (
            f"<Expense "
            f"{self.id} "
            f"{self.vendor_name} "
            f"{self.amount}>"
        )