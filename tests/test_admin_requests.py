import pytest
from datetime import date
from flask_login import login_user

from database.db import db
from models.user import User
from models.flat import Flat
from models.flat_member import FlatMember
from models.registration_request import RegistrationRequest
from models.notification import Notification
from models.audit_log import AuditLog
from tests.conftest import extract_csrf_token


def login_as(client, email, password, role="secretary"):
    """Helper to perform login through the login page."""
    login_page = client.get("/login")
    token = extract_csrf_token(login_page)
    tab = "admin" if role == "secretary" else "member"
    return client.post("/login", data={
        "csrf_token": token,
        "identifier": email,
        "password": password,
        "login_type": tab
    }, follow_redirects=True)


def test_admin_requests_access_control(app_instance, client):
    """Non-admin hitting /admin/* receives 403 error page."""
    # 1. Anonymous user redirected to login
    res = client.get("/admin/requests")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    # 2. Member logs in and hits admin routes -> gets 403
    login_res = login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")
    assert login_res.status_code == 200

    res_req = client.get("/admin/requests")
    assert res_req.status_code == 403
    assert b"403" in res_req.data

    res_dash = client.get("/admin/dashboard")
    assert res_dash.status_code == 403
    assert b"403" in res_dash.data


def test_admin_requests_list_and_dashboard(app_instance, client):
    """Admin can view requests page and dashboard with accurate stats."""
    # Admin login
    res = login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")
    assert res.status_code == 200

    # View requests list
    req_page = client.get("/admin/requests")
    assert req_page.status_code == 200
    assert b"Registration Requests" in req_page.data

    # View dashboard
    dash_page = client.get("/admin/dashboard")
    assert dash_page.status_code == 200
    assert b"Dashboard" in dash_page.data
    assert b"101" in dash_page.data
    assert b"Amit Deshmukh" in dash_page.data


def test_admin_approve_request(app_instance, client):
    """
    Approving a request:
    - Sets RegistrationRequest.status = 'approved'
    - Sets User.approval_status = 'approved', User.is_active = True
    - Creates a FlatMember entry linking user to flat
    - Creates an in-app Notification for the member
    - Writes an AuditLog entry
    - Allows the member to log in
    """
    with app_instance.app_context():
        flat2 = Flat.query.filter_by(flat_number="102").first()

    # 1. Register a new resident for Flat 102
    reg_page = client.get("/register")
    token = extract_csrf_token(reg_page)
    reg_res = client.post("/register", data={
        "csrf_token": token,
        "full_name": "Sunil Gavaskar",
        "email": "sunil.g@example.com",
        "mobile": "9819922334",
        "flat_id": flat2.id,
        "relation_type": "Owner",
        "password": "Sunil#Gavaskar2026",
        "confirm_password": "Sunil#Gavaskar2026",
        "consent": "1"
    }, follow_redirects=True)
    assert reg_res.status_code == 200
    assert b"Registration Submitted" in reg_res.data

    with app_instance.app_context():
        user = User.query.filter_by(email="sunil.g@example.com").first()
        assert user is not None
        assert user.approval_status == "pending"

        req = RegistrationRequest.query.filter_by(user_id=user.id).first()
        assert req is not None
        assert req.status == "pending"
        req_id = req.id

    # 2. Member cannot login yet
    member_login = login_as(client, "sunil.g@example.com", "Sunil#Gavaskar2026", role="member")
    assert b"awaiting admin approval" in member_login.data

    # 3. Admin logs in and approves request
    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")
    req_view = client.get(f"/admin/requests")
    token = extract_csrf_token(req_view)

    approve_res = client.post(f"/admin/requests/{req_id}/approve", data={
        "csrf_token": token
    }, follow_redirects=True)
    assert approve_res.status_code == 200
    assert b"approved successfully" in approve_res.data

    # 4. Verify DB state
    with app_instance.app_context():
        req = db.session.get(RegistrationRequest, req_id)
        assert req.status == "approved"

        user = db.session.get(User, req.user_id)
        assert user.approval_status == "approved"
        assert user.is_active is True
        assert user.approved_by is not None

        # FlatMember entry created
        fm = FlatMember.query.filter_by(user_id=user.id, flat_id=flat2.id).first()
        assert fm is not None
        assert fm.relation_type == "Owner"
        assert fm.is_active is True

        # Notification created
        notif = Notification.query.filter_by(user_id=user.id).first()
        assert notif is not None
        assert "Approved" in notif.title

        # AuditLog entry created
        log = AuditLog.query.filter_by(action="REQUEST_APPROVED", entity_id=req_id).first()
        assert log is not None
        assert "Sunil Gavaskar" in log.details

    # 5. Logout admin and verify newly approved member can now log in
    client.post("/logout", data={"csrf_token": extract_csrf_token(client.get("/admin/dashboard"))})
    member_login = login_as(client, "sunil.g@example.com", "Sunil#Gavaskar2026", role="member")
    assert member_login.status_code == 200
    assert b"Sunil Gavaskar" in member_login.data


def test_admin_approve_duplicate_owner_conflict(app_instance, client):
    """
    If requested relation is Owner and flat already has an owner,
    direct approval is prevented with a warning, requiring alternate relation override.
    """
    with app_instance.app_context():
        # Flat 101 already has Amit Deshmukh as Owner
        flat1 = Flat.query.filter_by(flat_number="101").first()

    # Register another user as Owner for Flat 101
    reg_page = client.get("/register")
    token = extract_csrf_token(reg_page)
    client.post("/register", data={
        "csrf_token": token,
        "full_name": "Ramesh Powar",
        "email": "ramesh.p@example.com",
        "mobile": "9820088776",
        "flat_id": flat1.id,
        "relation_type": "Owner",
        "password": "Ramesh#Pass2026",
        "confirm_password": "Ramesh#Pass2026",
        "consent": "1"
    }, follow_redirects=True)

    with app_instance.app_context():
        req = RegistrationRequest.query.join(User, RegistrationRequest.user_id == User.id).filter(User.email == "ramesh.p@example.com").first()
        assert req is not None
        req_id = req.id

    # Admin login
    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")
    req_view = client.get("/admin/requests")
    token = extract_csrf_token(req_view)

    # Approve without override -> should warn and reject direct primary owner duplicate
    res_conflict = client.post(f"/admin/requests/{req_id}/approve", data={
        "csrf_token": token
    }, follow_redirects=True)
    assert res_conflict.status_code == 200
    assert b"already has an active primary owner" in res_conflict.data

    with app_instance.app_context():
        req = db.session.get(RegistrationRequest, req_id)
        assert req.status == "pending"

    # Now approve with override relation = Tenant
    token = extract_csrf_token(client.get("/admin/requests"))
    res_override = client.post(f"/admin/requests/{req_id}/approve", data={
        "csrf_token": token,
        "override_relation": "Tenant"
    }, follow_redirects=True)
    assert res_override.status_code == 200
    assert b"approved successfully" in res_override.data

    with app_instance.app_context():
        req = db.session.get(RegistrationRequest, req_id)
        assert req.status == "approved"
        fm = FlatMember.query.filter_by(user_id=req.user_id, flat_id=flat1.id).first()
        assert fm is not None
        assert fm.relation_type == "Tenant"


def test_admin_reject_request(app_instance, client):
    """
    Rejecting a request:
    - Requires reason (at least 5 characters)
    - Sets RegistrationRequest.status = 'rejected'
    - Sets User.approval_status = 'rejected'
    - Creates in-app Notification
    - Writes AuditLog entry
    - Member login displays rejection reason
    """
    with app_instance.app_context():
        flat3 = Flat.query.filter_by(flat_number="103").first()

    # Register new user
    reg_page = client.get("/register")
    token = extract_csrf_token(reg_page)
    client.post("/register", data={
        "csrf_token": token,
        "full_name": "Kiran More",
        "email": "kiran.more@example.com",
        "mobile": "9811122233",
        "flat_id": flat3.id,
        "relation_type": "Tenant",
        "password": "Kiran#Pass2026",
        "confirm_password": "Kiran#Pass2026",
        "consent": "1"
    }, follow_redirects=True)

    with app_instance.app_context():
        req = RegistrationRequest.query.join(User, RegistrationRequest.user_id == User.id).filter(User.email == "kiran.more@example.com").first()
        req_id = req.id
        user_id = req.user_id

    # Admin login
    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")

    # 1. Reject without reason -> fails validation
    token = extract_csrf_token(client.get("/admin/requests"))
    res_empty_reason = client.post(f"/admin/requests/{req_id}/reject", data={
        "csrf_token": token,
        "reason": "bad"  # only 3 chars
    }, follow_redirects=True)
    assert b"minimum 5 characters" in res_empty_reason.data

    with app_instance.app_context():
        req = db.session.get(RegistrationRequest, req_id)
        assert req.status == "pending"

    # 2. Reject with valid reason
    token = extract_csrf_token(client.get("/admin/requests"))
    rejection_reason = "Tenancy agreement verification failed"
    res_reject = client.post(f"/admin/requests/{req_id}/reject", data={
        "csrf_token": token,
        "reason": rejection_reason
    }, follow_redirects=True)
    assert res_reject.status_code == 200
    assert b"rejected" in res_reject.data

    with app_instance.app_context():
        req = db.session.get(RegistrationRequest, req_id)
        assert req.status == "rejected"
        assert req.rejection_reason == rejection_reason

        user = db.session.get(User, user_id)
        assert user.approval_status == "rejected"
        assert user.rejection_reason == rejection_reason

        # Notification & AuditLog
        notif = Notification.query.filter_by(user_id=user_id).first()
        assert notif is not None
        assert rejection_reason in notif.message

        log = AuditLog.query.filter_by(action="REQUEST_REJECTED", entity_id=req_id).first()
        assert log is not None

    # 3. Member attempts login -> receives informative rejection message with reason
    client.post("/logout", data={"csrf_token": extract_csrf_token(client.get("/admin/dashboard"))})
    member_login = login_as(client, "kiran.more@example.com", "Kiran#Pass2026", role="member")
    assert b"not approved" in member_login.data.lower()
    assert rejection_reason.encode() in member_login.data
