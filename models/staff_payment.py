from datetime import datetime
from database.db import db


class StaffPayment(db.Model):
    __tablename__ = "staff_payments"

    id = db.Column(db.Integer, primary_key=True)
    society_id = db.Column(db.Integer, db.ForeignKey("societies.id"), nullable=False, index=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False, index=True)
    month_year = db.Column(db.String(7), nullable=False, index=True)  # e.g. "2026-10"
    base_salary = db.Column(db.Numeric(10, 2), nullable=False)
    bonus_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    deduction_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    net_amount = db.Column(db.Numeric(10, 2), nullable=False)
    
    status = db.Column(db.String(20), default="Pending Approval", nullable=False, index=True) # Pending Approval, Approved, Paid, Rejected
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    
    payment_date = db.Column(db.Date, nullable=True)
    payment_mode = db.Column(db.String(30), nullable=True)  # Bank Transfer, Cheque, Cash, UPI
    account_id = db.Column(db.Integer, db.ForeignKey("financial_accounts.id"), nullable=True)
    reference_number = db.Column(db.String(100), nullable=True)
    remarks = db.Column(db.String(255), nullable=True)
    paid_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    staff = db.relationship("Staff", backref="payments")
    account = db.relationship("FinancialAccount", foreign_keys=[account_id])
    creator = db.relationship("User", foreign_keys=[created_by])
    approver = db.relationship("User", foreign_keys=[approved_by])
    payer = db.relationship("User", foreign_keys=[paid_by])

    __table_args__ = (
        db.UniqueConstraint("staff_id", "month_year", name="uq_staff_month_payment"),
        db.CheckConstraint("net_amount > 0", name="ck_staff_payment_positive_net"),
    )
