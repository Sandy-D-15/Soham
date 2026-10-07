import secrets
from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from database.db import db
from models.user import User
from models.society import Society
from models.building import Building
from models.wing import Wing
from models.floor import Floor
from models.flat import Flat
from models.flat_member import FlatMember
from models.registration_request import RegistrationRequest
from models.maintenance_bill import MaintenanceBill
from models.maintenance_payment import MaintenancePayment
from models.complaint import Complaint
from models.notice import Notice
from models.audit_log import AuditLog
from services.auth import role_required
from services.billing import get_billing_summary, get_structure_stats, defaulters
from services.notifications import create_notification

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _get_society():
    return Society.query.first()


def _get_society_id():
    soc = _get_society()
    return soc.id if soc else 1


@admin_bp.route("/dashboard")
@login_required
@role_required("secretary")
def dashboard():
    society = _get_society()
    if not society:
        flash("Please setup society information first.", "warning")
        return redirect(url_for("society_settings"))

    # Stat cards metrics via billing service
    billing_data = get_billing_summary(society.id)
    structure_data = get_structure_stats(society.id)

    pending_requests_count = RegistrationRequest.query.filter_by(status="pending").count()
    open_complaints_count = Complaint.query.filter_by(society_id=society.id, status="Open").count()
    emergency_high_count = (
        Complaint.query
        .filter(
            Complaint.society_id == society.id,
            Complaint.status.in_(["Open", "In Progress"]),
            Complaint.priority.in_(["Emergency", "High"])
        )
        .count()
    )

    # Top 5 defaulters
    top_defaulters = defaulters(society.id, limit=5)

    # 5 Recent Complaints (room-number centric)
    recent_complaints = (
        Complaint.query
        .filter_by(society_id=society.id)
        .order_by(Complaint.created_at.desc())
        .limit(5)
        .all()
    )

    # 5 Recent Payments
    recent_payments = (
        MaintenancePayment.query
        .join(MaintenanceBill, MaintenancePayment.bill_id == MaintenanceBill.id)
        .filter(MaintenanceBill.society_id == society.id)
        .order_by(MaintenancePayment.payment_date.desc(), MaintenancePayment.id.desc())
        .limit(5)
        .all()
    )

    # 3 Latest Notices
    latest_notices = (
        Notice.query
        .filter_by(society_id=society.id, is_active=True)
        .order_by(Notice.is_pinned.desc(), Notice.created_at.desc())
        .limit(3)
        .all()
    )

    # 8 Recent Audit Logs
    recent_activity = (
        AuditLog.query
        .filter_by(society_id=society.id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        "admin_dashboard.html",
        society=society,
        pending_requests_count=pending_requests_count,
        structure_data=structure_data,
        billing_data=billing_data,
        open_complaints_count=open_complaints_count,
        emergency_high_count=emergency_high_count,
        top_defaulters=top_defaulters,
        recent_complaints=recent_complaints,
        recent_payments=recent_payments,
        latest_notices=latest_notices,
        recent_activity=recent_activity
    )


@admin_bp.route("/requests")
@login_required
@role_required("secretary")
def requests():
    society = _get_society()
    status_filter = request.args.get("status", "pending").lower()
    search_q = request.args.get("q", "").strip().lower()

    # Query counts for tabs
    pending_count = RegistrationRequest.query.filter_by(status="pending").count()
    approved_count = RegistrationRequest.query.filter_by(status="approved").count()
    rejected_count = RegistrationRequest.query.filter_by(status="rejected").count()

    query = (
        RegistrationRequest.query
        .join(User, RegistrationRequest.user_id == User.id)
        .join(Flat, RegistrationRequest.requested_flat_id == Flat.id)
    )

    if status_filter in ("pending", "approved", "rejected"):
        query = query.filter(RegistrationRequest.status == status_filter)

    if search_q:
        query = query.filter(
            db.or_(
                db.func.lower(User.full_name).contains(search_q),
                db.func.lower(User.email).contains(search_q),
                User.mobile.contains(search_q),
                Flat.flat_number.contains(search_q)
            )
        )

    all_requests = query.order_by(RegistrationRequest.created_at.desc()).all()

    # Attach conflict metadata to pending requests
    request_items = []
    for r in all_requests:
        existing_owner = None
        if r.status == "pending" and r.relation_type == "Owner":
            existing_owner = (
                FlatMember.query
                .filter_by(flat_id=r.requested_flat_id, relation_type="Owner", is_primary=True, is_active=True)
                .first()
            )
        request_items.append({
            "request": r,
            "existing_owner": existing_owner
        })

    return render_template(
        "admin_requests.html",
        society=society,
        request_items=request_items,
        status_filter=status_filter,
        search_q=search_q,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count
    )


@admin_bp.route("/requests/<int:req_id>/approve", methods=["POST"])
@login_required
@role_required("secretary")
def approve_request(req_id):
    req = db.session.get(RegistrationRequest, req_id)
    if not req or req.status != "pending":
        flash("Registration request is no longer pending.", "warning")
        return redirect(url_for("admin.requests"))

    flat = db.session.get(Flat, req.requested_flat_id)
    user = db.session.get(User, req.user_id)
    override_relation = request.form.get("override_relation")

    # Conflict check: duplicate primary owner
    existing_primary = (
        FlatMember.query
        .filter_by(flat_id=flat.id, relation_type="Owner", is_primary=True, is_active=True)
        .first()
    )
    if existing_primary and req.relation_type == "Owner" and not override_relation:
        flash(
            f"Flat {flat.flat_number} already has an active primary owner ({existing_primary.user.full_name}). "
            f"Please approve with an alternate relation (Tenant, Family Member, or Co-owner).",
            "warning"
        )
        return redirect(url_for("admin.requests", status="pending"))

    chosen_relation = override_relation if override_relation else req.relation_type

    try:
        # 1. Update User
        user.approval_status = "approved"
        user.is_active = True
        user.failed_attempts = 0
        user.locked_until = None
        user.approved_by = current_user.id
        user.approved_at = datetime.utcnow()

        # 2. Update Request
        req.status = "approved"
        req.reviewed_by = current_user.id
        req.reviewed_at = datetime.utcnow()

        # 3. Create or activate FlatMember link
        is_primary = (chosen_relation == "Owner" and existing_primary is None)
        existing_fm = FlatMember.query.filter_by(user_id=user.id, flat_id=flat.id, relation_type=chosen_relation).first()
        if existing_fm:
            existing_fm.is_active = True
            existing_fm.is_primary = is_primary
        else:
            fm = FlatMember(
                user_id=user.id,
                flat_id=flat.id,
                relation_type=chosen_relation,
                is_primary=is_primary,
                is_active=True,
                start_date=date.today()
            )
            db.session.add(fm)

        # 4. Notify member
        wing_label = flat.floor.wing.name if flat.floor and flat.floor.wing else ""
        room_label = f"Flat {wing_label}-{flat.flat_number}" if wing_label else f"Flat {flat.flat_number}"
        create_notification(
            user.id,
            "Registration Approved",
            f"Your registration for {room_label} has been approved by the society administration. Welcome!",
            link_url="/member/dashboard",
            kind="approval"
        )

        db.session.commit()

        # 5. Write Audit Log
        AuditLog.log(
            _get_society_id(),
            "REQUEST_APPROVED",
            user_id=current_user.id,
            entity_type="RegistrationRequest",
            entity_id=req.id,
            details=f"Approved member {user.full_name} for {room_label} as {chosen_relation} (is_primary={is_primary})",
            ip_address=request.remote_addr
        )

        flash(f"Registration for {user.full_name} approved successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("An error occurred while approving the request.", "danger")

    return redirect(url_for("admin.requests", status="pending"))


@admin_bp.route("/requests/<int:req_id>/reject", methods=["POST"])
@login_required
@role_required("secretary")
def reject_request(req_id):
    req = db.session.get(RegistrationRequest, req_id)
    if not req or req.status != "pending":
        flash("Registration request is no longer pending.", "warning")
        return redirect(url_for("admin.requests"))

    reason = request.form.get("reason", "").strip()
    if not reason or len(reason) < 5:
        flash("Rejection reason is required (minimum 5 characters).", "danger")
        return redirect(url_for("admin.requests", status="pending"))

    user = db.session.get(User, req.user_id)

    try:
        # 1. Update Request
        req.status = "rejected"
        req.rejection_reason = reason
        req.reviewed_by = current_user.id
        req.reviewed_at = datetime.utcnow()

        # 2. Update User
        user.approval_status = "rejected"
        user.rejection_reason = reason

        # 3. Notify member
        create_notification(
            user.id,
            "Registration Not Approved",
            f"Your registration request was not approved. Reason: {reason}",
            kind="rejection"
        )

        db.session.commit()

        # 4. Audit Log
        AuditLog.log(
            _get_society_id(),
            "REQUEST_REJECTED",
            user_id=current_user.id,
            entity_type="RegistrationRequest",
            entity_id=req.id,
            details=f"Rejected registration for {user.full_name}. Reason: {reason}",
            ip_address=request.remote_addr
        )

        flash(f"Registration for {user.full_name} rejected.", "info")
    except Exception:
        db.session.rollback()
        flash("An error occurred while rejecting the request.", "danger")

    return redirect(url_for("admin.requests", status="pending"))


@admin_bp.route("/requests/bulk-approve", methods=["POST"])
@login_required
@role_required("secretary")
def bulk_approve_requests():
    req_ids = request.form.getlist("request_ids")
    if not req_ids:
        flash("No requests selected for bulk approval.", "warning")
        return redirect(url_for("admin.requests", status="pending"))

    approved_count = 0
    conflict_count = 0

    for r_id in req_ids:
        try:
            req = db.session.get(RegistrationRequest, int(r_id))
            if not req or req.status != "pending":
                continue

            flat = db.session.get(Flat, req.requested_flat_id)
            user = db.session.get(User, req.user_id)

            existing_primary = (
                FlatMember.query
                .filter_by(flat_id=flat.id, relation_type="Owner", is_primary=True, is_active=True)
                .first()
            )
            # Skip if conflict
            if existing_primary and req.relation_type == "Owner":
                conflict_count += 1
                continue

            user.approval_status = "approved"
            user.is_active = True
            user.failed_attempts = 0
            user.locked_until = None
            user.approved_by = current_user.id
            user.approved_at = datetime.utcnow()

            req.status = "approved"
            req.reviewed_by = current_user.id
            req.reviewed_at = datetime.utcnow()

            is_prim = (req.relation_type == "Owner" and existing_primary is None)
            existing_fm = FlatMember.query.filter_by(user_id=user.id, flat_id=flat.id, relation_type=req.relation_type).first()
            if existing_fm:
                existing_fm.is_active = True
                existing_fm.is_primary = is_prim
            else:
                fm = FlatMember(
                    user_id=user.id,
                    flat_id=flat.id,
                    relation_type=req.relation_type,
                    is_primary=is_prim,
                    is_active=True,
                    start_date=date.today()
                )
                db.session.add(fm)

            create_notification(
                user.id,
                "Registration Approved",
                f"Your registration request for Flat {flat.flat_number} has been approved. Welcome!",
                link_url="/member/dashboard",
                kind="approval"
            )
            approved_count += 1
        except Exception:
            continue

    db.session.commit()

    AuditLog.log(
        _get_society_id(),
        "BULK_APPROVE",
        user_id=current_user.id,
        details=f"Bulk approved {approved_count} registration requests ({conflict_count} skipped due to conflicts)",
        ip_address=request.remote_addr
    )

    msg = f"Bulk approved {approved_count} requests successfully."
    if conflict_count > 0:
        msg += f" {conflict_count} requests skipped due to duplicate-owner conflicts."
    flash(msg, "success")

    return redirect(url_for("admin.requests", status="pending"))


@admin_bp.route("/members/<int:user_id>/reset-password", methods=["POST"])
@login_required
@role_required("secretary")
def reset_member_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("Member not found.", "danger")
        return redirect(url_for("members"))

    # Generate random 10-char temporary password
    temp_password = secrets.token_urlsafe(8)[:10]
    user.password_hash = generate_password_hash(temp_password)
    user.must_change_password = True
    user.failed_attempts = 0
    user.locked_until = None
    db.session.commit()

    AuditLog.log(
        _get_society_id(),
        "PASSWORD_RESET_ADMIN",
        user_id=current_user.id,
        entity_type="User",
        entity_id=user.id,
        details=f"Admin generated temporary password reset for member {user.email}",
        ip_address=request.remote_addr
    )

    flash(
        f"Temporary password for {user.full_name}: {temp_password} (This password will only be displayed once. Please share it with the member).",
        "warning"
    )
    return redirect(url_for("members"))
