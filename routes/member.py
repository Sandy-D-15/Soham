import calendar
from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from flask_login import login_required, current_user

from database.db import db
from models.user import User
from models.society import Society
from models.flat import Flat
from models.flat_member import FlatMember
from models.maintenance_bill import MaintenanceBill
from models.maintenance_payment import MaintenancePayment
from models.payment_receipt import PaymentReceipt
from models.complaint import Complaint
from models.notice import Notice
from models.audit_log import AuditLog
from services.auth import role_required, clean_and_validate_mobile, validate_full_name

member_bp = Blueprint("member", __name__, url_prefix="/member")


def _get_society():
    return Society.query.first()


@member_bp.route("/dashboard")
@login_required
@role_required("member")
def dashboard():
    society = _get_society()

    # Query all active flat assignments for the member
    assignments = (
        FlatMember.query
        .filter_by(user_id=current_user.id, is_active=True)
        .all()
    )

    if not assignments:
        # Edge case: No flat assigned yet -> friendly explanation
        return render_template(
            "member_dashboard.html",
            society=society,
            has_assignment=False,
            assignments=[]
        )

    # Determine active flat context (from query param or session, fallback to primary)
    selected_flat_id = request.args.get("flat_id", type=int)
    if not selected_flat_id:
        selected_flat_id = session.get("active_flat_id")

    active_assignment = None
    if selected_flat_id:
        active_assignment = next((a for a in assignments if a.flat_id == selected_flat_id), None)

    if not active_assignment:
        # Fallback: primary assignment or the first one
        active_assignment = next((a for a in assignments if a.is_primary), assignments[0])

    # Store active flat ID in session
    session["active_flat_id"] = active_assignment.flat_id
    active_flat = active_assignment.flat

    # Calculate financial metrics for the active flat
    all_flat_bills = (
        MaintenanceBill.query
        .filter_by(flat_id=active_flat.id)
        .all()
    )

    total_outstanding_dues = sum(
        (Decimal(str(b.balance_amount or 0)) for b in all_flat_bills if b.status != "Paid" and (b.balance_amount or 0) > 0),
        Decimal("0.00")
    )

    # 12-Month bill history
    bill_history = (
        MaintenanceBill.query
        .filter_by(flat_id=active_flat.id)
        .order_by(MaintenanceBill.bill_year.desc(), MaintenanceBill.bill_month.desc())
        .limit(12)
        .all()
    )

    latest_bill = bill_history[0] if bill_history else None

    # Latest payment made for this flat
    latest_payment = (
        MaintenancePayment.query
        .join(MaintenanceBill, MaintenancePayment.bill_id == MaintenanceBill.id)
        .filter(MaintenanceBill.flat_id == active_flat.id)
        .order_by(MaintenancePayment.payment_date.desc(), MaintenancePayment.id.desc())
        .first()
    )

    # Complaints count and recent complaints for member
    active_complaints_count = (
        Complaint.query
        .filter_by(member_id=current_user.id)
        .filter(Complaint.status.in_(["Open", "In Progress"]))
        .count()
    )

    my_complaints = (
        Complaint.query
        .filter_by(member_id=current_user.id)
        .order_by(Complaint.created_at.desc())
        .limit(5)
        .all()
    )

    # Notices count and recent 3
    active_notices_count = (
        Notice.query
        .filter_by(society_id=society.id, is_active=True)
        .count() if society else 0
    )

    active_notices = (
        Notice.query
        .filter_by(society_id=society.id, is_active=True)
        .order_by(Notice.is_pinned.desc(), Notice.created_at.desc())
        .limit(3)
        .all() if society else []
    )

    return render_template(
        "member_dashboard.html",
        society=society,
        has_assignment=True,
        assignments=assignments,
        active_assignment=active_assignment,
        active_flat=active_flat,
        total_outstanding_dues=total_outstanding_dues,
        latest_payment=latest_payment,
        latest_bill=latest_bill,
        bill_history=bill_history,
        active_complaints_count=active_complaints_count,
        my_complaints=my_complaints,
        active_notices_count=active_notices_count,
        active_notices=active_notices,
        calendar=calendar
    )


@member_bp.route("/bills")
@login_required
@role_required("member")
def bills():
    society = _get_society()
    assignments = (
        FlatMember.query
        .filter_by(user_id=current_user.id, is_active=True)
        .all()
    )

    if not assignments:
        flash("You do not have any property assigned to view bills.", "info")
        return redirect(url_for("member.dashboard"))

    flat_ids = [a.flat_id for a in assignments]
    status_filter = request.args.get("status")

    query = MaintenanceBill.query.filter(MaintenanceBill.flat_id.in_(flat_ids))
    if status_filter in ("Paid", "Partial", "Unpaid"):
        query = query.filter_by(status=status_filter)

    all_bills = query.order_by(MaintenanceBill.bill_year.desc(), MaintenanceBill.bill_month.desc()).all()

    total_outstanding = sum(
        (Decimal(str(b.balance_amount or 0)) for b in all_bills if (b.balance_amount or 0) > 0),
        Decimal("0.00")
    )

    return render_template(
        "member_bills.html",
        society=society,
        bills=all_bills,
        assignments=assignments,
        total_outstanding=total_outstanding,
        status_filter=status_filter,
        calendar=calendar
    )


@member_bp.route("/bills/<int:bill_id>")
@login_required
@role_required("member")
def bill_detail(bill_id):
    society = _get_society()
    bill = MaintenanceBill.query.get_or_404(bill_id)

    # Cross-member check: Ensure bill belongs to one of user's assigned flats
    assignment = (
        FlatMember.query
        .filter_by(user_id=current_user.id, flat_id=bill.flat_id, is_active=True)
        .first()
    )

    if not assignment:
        AuditLog.log(
            society.id if society else None,
            "UNAUTHORIZED_ACCESS_ATTEMPT",
            user_id=current_user.id,
            entity_type="MaintenanceBill",
            entity_id=bill.id,
            details=f"Member {current_user.email} attempted unauthorized access to bill #{bill.id} belonging to flat #{bill.flat_id}",
            ip_address=request.remote_addr
        )
        abort(403)

    payments = (
        MaintenancePayment.query
        .filter_by(bill_id=bill.id)
        .order_by(MaintenancePayment.payment_date.desc(), MaintenancePayment.id.desc())
        .all()
    )

    return render_template(
        "member_bill_detail.html",
        society=society,
        bill=bill,
        assignment=assignment,
        payments=payments,
        month_name=calendar.month_name[bill.bill_month]
    )


@member_bp.route("/profile", methods=["GET", "POST"])
@login_required
@role_required("member")
def profile():
    society = _get_society()
    assignments = (
        FlatMember.query
        .filter_by(user_id=current_user.id, is_active=True)
        .all()
    )

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        mobile_raw = request.form.get("mobile", "").strip()

        # Validate name
        ok_name, name_err = validate_full_name(full_name)
        if not ok_name:
            flash(name_err, "danger")
            return render_template("member_profile.html", society=society, assignments=assignments)

        # Validate mobile
        ok_mob, mob_res = clean_and_validate_mobile(mobile_raw)
        if not ok_mob:
            flash(mob_res, "danger")
            return render_template("member_profile.html", society=society, assignments=assignments)

        # Check unique mobile
        existing_mob = (
            User.query
            .filter(User.mobile == mob_res, User.id != current_user.id)
            .first()
        )
        if existing_mob:
            flash("Another resident is already registered with this mobile number.", "danger")
            return render_template("member_profile.html", society=society, assignments=assignments)

        # Update user profile
        old_name = current_user.full_name
        old_mobile = current_user.mobile

        current_user.full_name = full_name
        current_user.mobile = mob_res
        db.session.commit()

        AuditLog.log(
            society.id if society else None,
            "PROFILE_UPDATED",
            user_id=current_user.id,
            entity_type="User",
            entity_id=current_user.id,
            details=f"Updated profile: Name ('{old_name}' -> '{full_name}'), Mobile ('{old_mobile}' -> '{mob_res}')",
            ip_address=request.remote_addr
        )

        flash("Profile updated successfully.", "success")
        return redirect(url_for("member.profile"))

    return render_template(
        "member_profile.html",
        society=society,
        assignments=assignments
    )
