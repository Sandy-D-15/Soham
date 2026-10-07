import pytest
from decimal import Decimal
from datetime import date
from werkzeug.security import generate_password_hash

from database.db import db
from models.user import User
from models.flat import Flat
from models.society import Society
from models.flat_member import FlatMember
from models.maintenance_bill import MaintenanceBill
from models.audit_log import AuditLog
from tests.conftest import extract_csrf_token


def login_as(client, email, password, role="member"):
    """Helper to perform member or admin login."""
    login_page = client.get("/login")
    token = extract_csrf_token(login_page)
    tab = "admin" if role == "secretary" else "member"
    return client.post("/login", data={
        "csrf_token": token,
        "identifier": email,
        "password": password,
        "login_type": tab
    }, follow_redirects=True)


def test_member_dashboard_with_assigned_flat(app_instance, client):
    """Member logs in and lands on /member/dashboard with their flat's data and 12-month bill history."""
    # Amit Deshmukh is assigned to Flat 101 in conftest fixture
    login_res = login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")
    assert login_res.status_code == 200

    dash_res = client.get("/member/dashboard")
    assert dash_res.status_code == 200
    assert b"Amit Deshmukh" in dash_res.data
    assert b"101" in dash_res.data
    # Dues card reflects ₹3,000 overdue amount in red / Payment Due
    assert b"Payment Due" in dash_res.data
    assert b"3,000" in dash_res.data
    assert b"12-Month Maintenance History" in dash_res.data


def test_member_dashboard_all_clear_when_zero_dues(app_instance, client):
    """Member with 0 dues sees green 'All Clear' card."""
    with app_instance.app_context():
        # Clear the balance of Flat 101's bill
        bill = MaintenanceBill.query.first()
        bill.paid_amount = Decimal("3000.00")
        bill.balance_amount = Decimal("0.00")
        bill.status = "Paid"
        db.session.commit()

    login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")
    dash_res = client.get("/member/dashboard")
    assert dash_res.status_code == 200
    assert b"All Clear" in dash_res.data


def test_member_dashboard_no_assigned_flat_friendly_page(app_instance, client):
    """Member with no assigned flat sees friendly explanation, not a crash or empty dashboard."""
    with app_instance.app_context():
        # Create approved member without any FlatMember link
        unassigned_user = User(
            full_name="Pooja Mehta",
            email="pooja.m@example.com",
            mobile="9820033221",
            password_hash=generate_password_hash("Pooja#Pass2026"),
            role="member",
            approval_status="approved",
            is_active=True
        )
        db.session.add(unassigned_user)
        db.session.commit()

    login_as(client, "pooja.m@example.com", "Pooja#Pass2026", role="member")
    dash_res = client.get("/member/dashboard")
    assert dash_res.status_code == 200
    # Must contain friendly explanation
    assert b"not yet linked a flat to your profile" in dash_res.data
    assert b"contact your society secretary" in dash_res.data.lower()


def test_cross_member_bill_access_forbidden_and_audited(app_instance, client):
    """Member attempting to view another flat's bill receives 403 and triggers UNAUTHORIZED_ACCESS_ATTEMPT audit log."""
    with app_instance.app_context():
        flat2 = Flat.query.filter_by(flat_number="102").first()
        soc = Society.query.first()

        # Create Bill on Flat 102
        flat2_bill = MaintenanceBill(
            society_id=soc.id,
            flat_id=flat2.id,
            bill_month=10,
            bill_year=2026,
            bill_date=date(2026, 10, 1),
            due_date=date(2026, 10, 15),
            subtotal=Decimal("4000.00"),
            total_amount=Decimal("4000.00"),
            paid_amount=Decimal("0.00"),
            balance_amount=Decimal("4000.00"),
            status="Unpaid"
        )
        db.session.add(flat2_bill)
        db.session.commit()
        bill_id = flat2_bill.id

    # Amit Deshmukh is assigned to Flat 101, NOT Flat 102
    login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")

    # 1. Attempt access via /my/bills/<id>
    res1 = client.get(f"/my/bills/{bill_id}")
    assert res1.status_code == 403
    assert b"403" in res1.data

    # 2. Attempt access via /member/bills/<id>
    res2 = client.get(f"/member/bills/{bill_id}")
    assert res2.status_code == 403
    assert b"403" in res2.data

    # 3. Verify audit log entry
    with app_instance.app_context():
        log = AuditLog.query.filter_by(
            action="UNAUTHORIZED_ACCESS_ATTEMPT",
            entity_id=bill_id
        ).first()
        assert log is not None
        assert "amit.deshmukh@example.com" in log.details


def test_member_profile_view_and_update_with_audit_log(app_instance, client):
    """Member can view and update their profile with validation and audit log."""
    login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")

    # 1. View profile
    view_res = client.get("/member/profile")
    assert view_res.status_code == 200
    assert b"Amit Deshmukh" in view_res.data
    assert b"amit.deshmukh@example.com" in view_res.data
    assert b"101" in view_res.data

    # 2. Update profile with valid new details
    token = extract_csrf_token(view_res)
    new_name = "Amit R. Deshmukh"
    new_mobile = "9820099881"

    post_res = client.post("/member/profile", data={
        "csrf_token": token,
        "full_name": new_name,
        "mobile": new_mobile
    }, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"Profile updated successfully" in post_res.data
    assert new_name.encode() in post_res.data

    # 3. Verify DB and AuditLog
    with app_instance.app_context():
        user = User.query.filter_by(email="amit.deshmukh@example.com").first()
        assert user.full_name == new_name
        assert user.mobile == new_mobile

        log = AuditLog.query.filter_by(action="PROFILE_UPDATED", entity_id=user.id).first()
        assert log is not None
        assert "PROFILE_UPDATED" in log.action
