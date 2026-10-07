import os
import io
import pytest
from werkzeug.security import generate_password_hash

from database.db import db
from models.user import User
from models.flat import Flat
from models.flat_member import FlatMember
from models.complaint import Complaint
from models.complaint_comment import ComplaintComment
from models.complaint_history import ComplaintHistory
from models.notification import Notification
from models.audit_log import AuditLog
from tests.conftest import extract_csrf_token


def login_as(client, email, password, role="member"):
    """Helper to authenticate user via the login route."""
    client.get("/logout")
    login_page = client.get("/login")
    token = extract_csrf_token(login_page)
    tab = "admin" if role == "secretary" else "member"
    return client.post("/login", data={
        "csrf_token": token,
        "identifier": email,
        "password": password,
        "login_type": tab
    }, follow_redirects=True)


def test_member_lodge_complaint_with_room_number(app_instance, client):
    """Member files a complaint associated with their assigned flat room number."""
    # Login as member Amit Deshmukh (assigned to Flat 101 in conftest)
    login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")

    complaints_page = client.get("/complaints")
    assert complaints_page.status_code == 200
    token = extract_csrf_token(complaints_page)

    with app_instance.app_context():
        flat1 = Flat.query.filter_by(flat_number="101").first()
        flat_id = flat1.id

    res = client.post("/complaints/add", data={
        "csrf_token": token,
        "flat_id": flat_id,
        "category": "Plumbing",
        "priority": "High",
        "title": "Kitchen sink pipe leaking heavily",
        "description": "Continuous water leaking from beneath the sink causing water pooling in the kitchen."
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"logged successfully" in res.data or b"Kitchen sink pipe leaking" in res.data

    with app_instance.app_context():
        c = Complaint.query.filter_by(title="Kitchen sink pipe leaking heavily").first()
        assert c is not None
        assert c.flat_id == flat_id
        assert c.priority == "High"
        assert c.category == "Plumbing"
        assert c.status == "Open"

        # Check notification dispatched to secretary
        admin = User.query.filter_by(role="secretary").first()
        notif = Notification.query.filter_by(user_id=admin.id).order_by(Notification.id.desc()).first()
        assert notif is not None
        assert "New Maintenance Ticket" in notif.title
        assert "A-101" in notif.message or "101" in notif.message

        # Check audit log
        audit = AuditLog.query.filter_by(entity_type="Complaint", entity_id=c.id).first()
        assert audit is not None
        assert audit.action == "COMPLAINT_CREATED"


def test_complaint_image_upload_success(app_instance, client):
    """Valid image attachment (PNG/JPG) within 2MB is stored securely with UUID and viewable."""
    login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")
    complaints_page = client.get("/complaints")
    token = extract_csrf_token(complaints_page)

    with app_instance.app_context():
        flat1 = Flat.query.filter_by(flat_number="101").first()
        flat_id = flat1.id

    # Simulated valid PNG file
    fake_png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    img_file = (io.BytesIO(fake_png_data), "damage_photo.png")

    res = client.post("/complaints/add", data={
        "csrf_token": token,
        "flat_id": flat_id,
        "category": "Cleanliness",
        "priority": "Medium",
        "title": "Water stain on corridor ceiling",
        "description": "Noticeable brown damp stain expanding near flat 101 doorway.",
        "attachment": img_file
    }, content_type="multipart/form-data", follow_redirects=True)

    assert res.status_code == 200

    with app_instance.app_context():
        c = Complaint.query.filter_by(title="Water stain on corridor ceiling").first()
        assert c is not None
        assert c.attachment_path is not None
        assert c.attachment_path.endswith("damage_photo.png")

        # Test download route
        dl_res = client.get(f"/complaints/attachments/{c.attachment_path}")
        assert dl_res.status_code == 200
        assert dl_res.data == fake_png_data


def test_complaint_file_upload_validation_rejected(app_instance, client):
    """Attachments exceeding 2MB or having invalid extensions are rejected with clear error messages."""
    login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")
    complaints_page = client.get("/complaints")
    token = extract_csrf_token(complaints_page)

    with app_instance.app_context():
        flat1 = Flat.query.filter_by(flat_number="101").first()
        flat_id = flat1.id

    # 1. Invalid extension .exe
    bad_file = (io.BytesIO(b"malicious payload"), "malware.exe")
    res1 = client.post("/complaints/add", data={
        "csrf_token": token,
        "flat_id": flat_id,
        "category": "Other",
        "priority": "Low",
        "title": "Invalid file extension test",
        "description": "Testing rejection of executable file attachment.",
        "attachment": bad_file
    }, content_type="multipart/form-data", follow_redirects=True)

    assert res1.status_code == 200
    assert b"is not supported" in res1.data or b"Only JPEG, PNG, and PDF" in res1.data

    with app_instance.app_context():
        assert Complaint.query.filter_by(title="Invalid file extension test").first() is None

    # 2. Oversized file (>2MB)
    huge_data = b"0" * (2 * 1024 * 1024 + 1024)  # ~2.001 MB
    huge_file = (io.BytesIO(huge_data), "huge_image.jpg")
    res2 = client.post("/complaints/add", data={
        "csrf_token": token,
        "flat_id": flat_id,
        "category": "Other",
        "priority": "Low",
        "title": "Oversized attachment test",
        "description": "Testing rejection of file exceeding 2MB limit threshold.",
        "attachment": huge_file
    }, content_type="multipart/form-data", follow_redirects=True)

    assert res2.status_code == 200
    assert b"exceeds maximum allowed size of 2MB" in res2.data

    with app_instance.app_context():
        assert Complaint.query.filter_by(title="Oversized attachment test").first() is None


def test_secretary_room_number_centric_view_and_filtering(app_instance, client):
    """Secretary sees complaints organized by room numbers, and can filter by status and search by flat."""
    with app_instance.app_context():
        soc = User.query.filter_by(role="secretary").first()
        member = User.query.filter_by(role="member").first()
        flat1 = Flat.query.filter_by(flat_number="101").first()
        flat2 = Flat.query.filter_by(flat_number="102").first()

        # Seed two complaints with different room numbers and statuses
        c1 = Complaint(
            society_id=flat1.floor.wing.building.society_id,
            member_id=member.id,
            flat_id=flat1.id,
            title="Balcony railing loose",
            category="Security",
            priority="High",
            description="Metal railing feels unstable on the balcony side.",
            status="Open"
        )
        c2 = Complaint(
            society_id=flat2.floor.wing.building.society_id,
            member_id=member.id,
            flat_id=flat2.id,
            title="Doorbell wire sparked",
            category="Electrical",
            priority="Medium",
            description="Short circuit when pressing doorbell button.",
            status="Resolved",
            resolution_notes="Electrician replaced chime switch wiring."
        )
        db.session.add_all([c1, c2])
        db.session.commit()

    # Login as secretary
    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")

    # Access /complaints
    resp = client.get("/complaints")
    assert resp.status_code == 200
    assert b"Room-Centric Maintenance Helpdesk" in resp.data
    # Both room numbers and titles present
    assert b"101" in resp.data
    assert b"102" in resp.data
    assert b"Balcony railing loose" in resp.data
    assert b"Doorbell wire sparked" in resp.data

    # Test search query by room number '101'
    search_res = client.get("/complaints?q=101")
    assert search_res.status_code == 200
    assert b"Balcony railing loose" in search_res.data
    assert b"Doorbell wire sparked" not in search_res.data

    # Test filter by status 'Resolved'
    status_res = client.get("/complaints?status=Resolved")
    assert status_res.status_code == 200
    assert b"Doorbell wire sparked" in status_res.data
    assert b"Balcony railing loose" not in status_res.data


def test_complaint_resolution_requires_notes_and_notifies_member(app_instance, client):
    """Transitioning ticket to 'Resolved' strictly requires >= 5 chars resolution notes and notifies member."""
    with app_instance.app_context():
        member = User.query.filter_by(role="member").first()
        flat1 = Flat.query.filter_by(flat_number="101").first()

        c = Complaint(
            society_id=flat1.floor.wing.building.society_id,
            member_id=member.id,
            flat_id=flat1.id,
            title="Water pressure low in shower",
            category="Plumbing",
            priority="Medium",
            description="Shower head has barely any water flow since yesterday.",
            status="In Progress"
        )
        db.session.add(c)
        db.session.commit()
        complaint_id = c.id
        member_id = member.id

    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")

    # Fetch detail page to get CSRF token
    detail_page = client.get(f"/complaints/{complaint_id}")
    assert detail_page.status_code == 200
    token = extract_csrf_token(detail_page)

    # 1. Attempt resolving without resolution notes
    fail_res = client.post(f"/complaints/{complaint_id}/update", data={
        "csrf_token": token,
        "status": "Resolved",
        "assigned_name": "Ramesh Plumber",
        "resolution_notes": ""
    }, follow_redirects=True)

    assert fail_res.status_code == 200
    assert b"Resolution notes are required" in fail_res.data

    with app_instance.app_context():
        chk = db.session.get(Complaint, complaint_id)
        assert chk.status == "In Progress"  # Not changed!

    # 2. Resolve with valid resolution notes (>= 5 chars)
    success_res = client.post(f"/complaints/{complaint_id}/update", data={
        "csrf_token": token,
        "status": "Resolved",
        "assigned_name": "Ramesh Plumber",
        "resolution_notes": "Main pressure valve was partially clogged; cleared debris and restored full flow."
    }, follow_redirects=True)

    assert success_res.status_code == 200
    assert b"updated successfully" in success_res.data

    with app_instance.app_context():
        resolved_c = db.session.get(Complaint, complaint_id)
        assert resolved_c.status == "Resolved"
        assert resolved_c.resolved_by is not None
        assert resolved_c.resolved_at is not None
        assert "Main pressure valve" in resolved_c.resolution_notes

        # Verify notification sent to resident
        notif = Notification.query.filter_by(user_id=member_id, kind="approval").order_by(Notification.id.desc()).first()
        assert notif is not None
        assert "Complaint Resolved" in notif.title
        assert "Water pressure low" in notif.message


def test_complaint_detail_access_control_and_internal_notes(app_instance, client):
    """Cross-member access is blocked (403), comments are added, and internal notes are hidden from residents."""
    with app_instance.app_context():
        member1 = User.query.filter_by(email="amit.deshmukh@example.com").first()
        flat1 = Flat.query.filter_by(flat_number="101").first()

        # Create another member (Vikram Joshi)
        member2 = User(
            full_name="Vikram Joshi",
            email="vikram.joshi@example.com",
            mobile="9820099887",
            password_hash=generate_password_hash("Resident#Pass2026"),
            role="member",
            approval_status="approved",
            is_active=True
        )
        db.session.add(member2)
        db.session.commit()

        c = Complaint(
            society_id=flat1.floor.wing.building.society_id,
            member_id=member1.id,
            flat_id=flat1.id,
            title="Private bedroom ceiling seepage",
            category="Plumbing",
            priority="High",
            description="Water droplets forming on bedroom ceiling.",
            status="Open"
        )
        db.session.add(c)
        db.session.commit()
        complaint_id = c.id

    # 1. Vikram (member2) attempts to view Member1's complaint -> 403 Forbidden!
    login_as(client, "vikram.joshi@example.com", "Resident#Pass2026", role="member")
    forbidden_res = client.get(f"/complaints/{complaint_id}")
    assert forbidden_res.status_code == 403

    # 2. Secretary logs in and posts an internal note
    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")
    sec_page = client.get(f"/complaints/{complaint_id}")
    assert sec_page.status_code == 200
    token = extract_csrf_token(sec_page)

    client.post(f"/complaints/{complaint_id}/comment", data={
        "csrf_token": token,
        "comment": "Internal inspection confirms flat 201 above has faulty tile grouting.",
        "is_internal": "1"
    }, follow_redirects=True)

    # Secretary sees internal note
    sec_view = client.get(f"/complaints/{complaint_id}")
    assert b"Internal Note (Staff Only)" in sec_view.data
    assert b"faulty tile grouting" in sec_view.data

    # 3. Owner (Amit Deshmukh) logs in and views complaint
    login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")
    member_view = client.get(f"/complaints/{complaint_id}")
    assert member_view.status_code == 200
    # Member CANNOT see internal note
    assert b"faulty tile grouting" not in member_view.data
    assert b"Internal Note" not in member_view.data

    # Member posts a public response
    member_token = extract_csrf_token(member_view)
    client.post(f"/complaints/{complaint_id}/comment", data={
        "csrf_token": member_token,
        "comment": "Thank you, please let me know when the technician will arrive."
    }, follow_redirects=True)

    updated_member_view = client.get(f"/complaints/{complaint_id}")
    assert b"please let me know when the technician will arrive" in updated_member_view.data
