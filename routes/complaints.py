import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from database.db import db
from models.user import User
from models.society import Society
from models.flat import Flat
from models.flat_member import FlatMember
from models.staff import Staff
from models.vendor import Vendor
from models.complaint import Complaint
from models.complaint_comment import ComplaintComment
from models.complaint_history import ComplaintHistory
from models.audit_log import AuditLog
from services.notifications import create_notification, notify_all_admins

complaints_bp = Blueprint("complaints", __name__, url_prefix="/complaints")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}
ALLOWED_MIMETYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB


def _get_society():
    return Society.query.first()


def _get_upload_folder():
    folder = os.path.join(current_app.root_path, "uploads", "complaints")
    os.makedirs(folder, exist_ok=True)
    return folder


def _is_allowed_file(file):
    if not file or not file.filename:
        return False, "No file selected."
    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File format .{ext} is not supported. Please upload JPG, PNG, or PDF files."
    
    # Check mime type
    if file.mimetype and file.mimetype.lower() not in ALLOWED_MIMETYPES:
        return False, "Invalid file type. Only JPEG, PNG, and PDF files are allowed."
    
    # Check file size (max 2MB)
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE_BYTES:
        return False, f"File size ({round(size / (1024 * 1024), 2)}MB) exceeds maximum allowed size of 2MB."
    
    return True, None


@complaints_bp.route("")
@login_required
def index():
    society = _get_society()
    if not society:
        flash("Please setup society information first.", "warning")
        return redirect(url_for("society_settings"))

    is_secretary = (current_user.role == "secretary")

    if is_secretary:
        # Admin / Secretary view: Room-number centric list with filters and search
        status_filter = request.args.get("status", "").strip()
        priority_filter = request.args.get("priority", "").strip()
        category_filter = request.args.get("category", "").strip()
        search_q = request.args.get("q", "").strip().lower()

        query = (
            Complaint.query
            .filter_by(society_id=society.id)
            .outerjoin(Flat, Complaint.flat_id == Flat.id)
            .outerjoin(User, Complaint.member_id == User.id)
        )

        if status_filter and status_filter != "All":
            query = query.filter(Complaint.status == status_filter)
        if priority_filter and priority_filter != "All":
            query = query.filter(Complaint.priority == priority_filter)
        if category_filter and category_filter != "All":
            query = query.filter(Complaint.category == category_filter)

        if search_q:
            query = query.filter(
                db.or_(
                    db.func.lower(Flat.flat_number).contains(search_q),
                    db.func.lower(User.full_name).contains(search_q),
                    db.func.lower(Complaint.title).contains(search_q),
                    db.func.cast(Complaint.id, db.String).contains(search_q)
                )
            )

        complaints_list = query.order_by(Complaint.created_at.desc()).all()

        # Stats counters
        total_count = Complaint.query.filter_by(society_id=society.id).count()
        open_count = Complaint.query.filter_by(society_id=society.id, status="Open").count()
        in_progress_count = Complaint.query.filter_by(society_id=society.id, status="In Progress").count()
        resolved_count = Complaint.query.filter_by(society_id=society.id, status="Resolved").count()

        staff_list = Staff.query.filter_by(society_id=society.id, status=True).all()
        vendor_list = Vendor.query.filter_by(society_id=society.id, status=True).all()

        return render_template(
            "admin_complaints.html",
            society=society,
            complaints=complaints_list,
            total_count=total_count,
            open_count=open_count,
            in_progress_count=in_progress_count,
            resolved_count=resolved_count,
            staff_list=staff_list,
            vendor_list=vendor_list,
            status_filter=status_filter,
            priority_filter=priority_filter,
            category_filter=category_filter,
            search_q=search_q
        )

    else:
        # Resident Member view
        complaints_list = (
            Complaint.query
            .filter_by(society_id=society.id, member_id=current_user.id)
            .order_by(Complaint.created_at.desc())
            .all()
        )

        # Member's assigned flats for the dropdown
        assignments = (
            FlatMember.query
            .filter_by(user_id=current_user.id, is_active=True)
            .all()
        )

        return render_template(
            "complaints.html",
            society=society,
            complaints=complaints_list,
            assignments=assignments
        )


@complaints_bp.route("/add", methods=["POST"])
@login_required
def add_complaint():
    society = _get_society()
    if not society:
        flash("Please setup society information first.", "warning")
        return redirect(url_for("complaints.index"))

    title = request.form.get("title", "").strip()
    category = request.form.get("category", "Other").strip()
    priority = request.form.get("priority", "Medium").strip()
    description = request.form.get("description", "").strip()
    flat_id_raw = request.form.get("flat_id")

    # Title length: min 5, max 100
    if len(title) < 5 or len(title) > 100:
        flash("Title must be between 5 and 100 characters.", "danger")
        return redirect(url_for("complaints.index"))

    # Description length: min 10, max 1000
    if len(description) < 10 or len(description) > 1000:
        flash("Description must be between 10 and 1000 characters.", "danger")
        return redirect(url_for("complaints.index"))

    # Flat validation
    flat_id = None
    if current_user.role == "member":
        assigned_flats = [a.flat_id for a in FlatMember.query.filter_by(user_id=current_user.id, is_active=True).all()]
        if flat_id_raw and flat_id_raw.isdigit() and int(flat_id_raw) in assigned_flats:
            flat_id = int(flat_id_raw)
        elif assigned_flats:
            flat_id = assigned_flats[0]
        else:
            flash("You do not have an active flat assigned to lodge complaints.", "warning")
            return redirect(url_for("complaints.index"))
    else:
        if flat_id_raw and flat_id_raw.isdigit():
            flat_id = int(flat_id_raw)

    # Optional file attachment upload
    attachment_filename = None
    file = request.files.get("attachment")
    if file and file.filename:
        is_ok, err_msg = _is_allowed_file(file)
        if not is_ok:
            flash(err_msg, "danger")
            return redirect(url_for("complaints.index"))
        
        sec_name = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{sec_name}"
        upload_folder = _get_upload_folder()
        file.save(os.path.join(upload_folder, unique_name))
        attachment_filename = unique_name

    flat_obj = db.session.get(Flat, flat_id) if flat_id else None
    room_label = f"{flat_obj.floor.wing.name if flat_obj.floor and flat_obj.floor.wing else ''}-{flat_obj.flat_number}" if flat_obj else "Common Area"

    complaint = Complaint(
        society_id=society.id,
        member_id=current_user.id,
        flat_id=flat_id,
        title=title,
        category=category,
        priority=priority,
        description=description,
        attachment_path=attachment_filename,
        status="Open"
    )
    db.session.add(complaint)
    db.session.flush()

    # Initial history entry
    hist = ComplaintHistory(
        complaint_id=complaint.id,
        changed_by=current_user.id,
        old_status=None,
        new_status="Open",
        note=f"Ticket submitted by {current_user.full_name} for Flat {room_label}"
    )
    db.session.add(hist)
    db.session.commit()

    # In-app notification to all society admins
    notify_all_admins(
        "New Maintenance Ticket",
        f"New Complaint #{complaint.id}: '{title}' - Flat {room_label} (Priority: {priority})",
        link_url=f"/complaints/{complaint.id}",
        kind="warning" if priority in ["High", "Emergency"] else "info"
    )

    # Audit Log
    AuditLog.log(
        society.id,
        "COMPLAINT_CREATED",
        user_id=current_user.id,
        entity_type="Complaint",
        entity_id=complaint.id,
        details=f"Complaint #{complaint.id} logged for Flat {room_label}: '{title}' ({category})",
        ip_address=request.remote_addr
    )

    flash(f"Maintenance ticket #{complaint.id} logged successfully.", "success")
    return redirect(url_for("complaints.index"))


@complaints_bp.route("/<int:complaint_id>")
@login_required
def detail(complaint_id):
    society = _get_society()
    complaint = Complaint.query.filter_by(id=complaint_id, society_id=society.id).first_or_404()

    # Access check: Secretary can view any; Member can only view their own
    if current_user.role != "secretary" and complaint.member_id != current_user.id:
        abort(403)

    staff_list = Staff.query.filter_by(society_id=society.id, status=True).all() if current_user.role == "secretary" else []
    vendor_list = Vendor.query.filter_by(society_id=society.id, status=True).all() if current_user.role == "secretary" else []

    # Combine comments and history chronologically
    history_records = ComplaintHistory.query.filter_by(complaint_id=complaint.id).order_by(ComplaintHistory.created_at.asc()).all()
    
    comments_query = ComplaintComment.query.filter_by(complaint_id=complaint.id)
    if current_user.role != "secretary":
        # Member only sees public comments
        comments_query = comments_query.filter_by(is_internal=False)
    comments = comments_query.order_by(ComplaintComment.created_at.asc()).all()

    timeline = []
    for h in history_records:
        timeline.append({
            "type": "history",
            "actor": h.actor.full_name if h.actor else "System",
            "time": h.created_at,
            "old_status": h.old_status,
            "new_status": h.new_status,
            "note": h.note
        })
    for c in comments:
        timeline.append({
            "type": "comment",
            "actor": c.author.full_name if hasattr(c, "author") and c.author else (db.session.get(User, c.user_id).full_name if db.session.get(User, c.user_id) else "User"),
            "time": c.created_at,
            "comment": c.comment,
            "is_internal": c.is_internal
        })
    timeline.sort(key=lambda x: x["time"])

    return render_template(
        "complaint_detail.html",
        society=society,
        complaint=complaint,
        staff_list=staff_list,
        vendor_list=vendor_list,
        timeline=timeline,
        comments=comments
    )


@complaints_bp.route("/<int:complaint_id>/update", methods=["POST"])
@login_required
def update_complaint(complaint_id):
    if current_user.role != "secretary":
        abort(403)

    society = _get_society()
    complaint = Complaint.query.filter_by(id=complaint_id, society_id=society.id).first_or_404()

    new_status = request.form.get("status", complaint.status).strip()
    assigned_name = request.form.get("assigned_name", "").strip()
    assigned_to_type = request.form.get("assigned_to_type", complaint.assigned_to_type)
    resolution_notes = request.form.get("resolution_notes", "").strip()

    # Rule: If transitioning to Resolved, resolution_notes is required (min 5 chars)
    if new_status in ("Resolved", "Closed") and complaint.status not in ("Resolved", "Closed"):
        if not resolution_notes or len(resolution_notes) < 5:
            flash("Resolution notes are required (minimum 5 characters) to resolve a ticket.", "danger")
            return redirect(url_for("complaints.detail", complaint_id=complaint.id))

    old_status = complaint.status
    complaint.status = new_status
    if assigned_name:
        complaint.assigned_name = assigned_name
        complaint.assigned_to_type = assigned_to_type
    
    if resolution_notes:
        complaint.resolution_notes = resolution_notes

    if new_status in ("Resolved", "Closed") and not complaint.resolved_at:
        complaint.resolved_at = datetime.utcnow()
        complaint.resolved_by = current_user.id

    # Append History
    history_note = resolution_notes if (new_status in ["Resolved", "Closed"] and resolution_notes) else (f"Assigned to: {assigned_name}" if assigned_name else f"Status changed to {new_status}")
    hist = ComplaintHistory(
        complaint_id=complaint.id,
        changed_by=current_user.id,
        old_status=old_status,
        new_status=new_status,
        note=history_note
    )
    db.session.add(hist)
    db.session.commit()

    # Notify member
    if new_status == "Resolved":
        create_notification(
            complaint.member_id,
            "Complaint Resolved",
            f"Your complaint #{complaint.id} ('{complaint.title}') has been marked as Resolved. Notes: {resolution_notes}",
            link_url=f"/complaints/{complaint.id}",
            kind="approval"
        )
    elif old_status != new_status:
        create_notification(
            complaint.member_id,
            "Complaint Status Updated",
            f"Your complaint #{complaint.id} is now '{new_status}'.",
            link_url=f"/complaints/{complaint.id}",
            kind="info"
        )

    # Audit Log
    AuditLog.log(
        society.id,
        "COMPLAINT_UPDATED",
        user_id=current_user.id,
        entity_type="Complaint",
        entity_id=complaint.id,
        details=f"Complaint #{complaint.id} updated: status '{old_status}' -> '{new_status}', assigned '{complaint.assigned_name or 'None'}'",
        ip_address=request.remote_addr
    )

    flash(f"Complaint #{complaint.id} updated successfully.", "success")
    return redirect(url_for("complaints.detail", complaint_id=complaint.id))


@complaints_bp.route("/<int:complaint_id>/comment", methods=["POST"])
@login_required
def add_comment(complaint_id):
    society = _get_society()
    complaint = Complaint.query.filter_by(id=complaint_id, society_id=society.id).first_or_404()

    if current_user.role != "secretary" and complaint.member_id != current_user.id:
        abort(403)

    comment_text = request.form.get("comment", "").strip()
    if not comment_text or len(comment_text) < 2:
        flash("Comment cannot be empty.", "warning")
        return redirect(url_for("complaints.detail", complaint_id=complaint.id))

    is_internal = bool(request.form.get("is_internal")) and (current_user.role == "secretary")

    comment = ComplaintComment(
        complaint_id=complaint.id,
        user_id=current_user.id,
        comment=comment_text,
        is_internal=is_internal
    )
    db.session.add(comment)
    db.session.commit()

    # Notify counterpart
    if current_user.role == "secretary" and not is_internal:
        create_notification(
            complaint.member_id,
            "New Response on Ticket",
            f"Society manager commented on complaint #{complaint.id}: '{comment_text[:80]}...'",
            link_url=f"/complaints/{complaint.id}"
        )
    elif current_user.role == "member":
        notify_all_admins(
            "Resident Response",
            f"Resident {current_user.full_name} commented on complaint #{complaint.id}: '{comment_text[:80]}...'",
            link_url=f"/complaints/{complaint.id}"
        )

    flash("Comment added.", "success")
    return redirect(url_for("complaints.detail", complaint_id=complaint.id))


@complaints_bp.route("/attachments/<filename>")
@login_required
def download_attachment(filename):
    upload_folder = _get_upload_folder()
    return send_from_directory(upload_folder, filename)
