import pytest
from database.db import db
from models.user import User
from models.flat import Flat
from models.flat_member import FlatMember
from models.registration_request import RegistrationRequest
from tests.conftest import extract_csrf_token


def test_end_to_end_registration_approval_and_member_login(app_instance, client):
    """
    TASK 1:
    Register -> pending login blocked -> admin approves -> member login succeeds
    -> lands on /member/dashboard with 200 and flat badge.
    Also tests member without flat and without bills return 200.
    """
    # 1. Register a new resident
    reg_page = client.get("/register")
    assert reg_page.status_code == 200
    token = extract_csrf_token(reg_page)

    with app_instance.app_context():
        flat = Flat.query.filter_by(flat_number="102").first()
        flat_id = flat.id

    reg_data = {
        "csrf_token": token,
        "full_name": "Kavita Sharma",
        "email": "kavita.sharma@example.com",
        "mobile": "9819988776",
        "password": "Password@123",
        "confirm_password": "Password@123",
        "flat_id": flat_id,
        "relation_type": "Tenant",
        "consent": "1"
    }
    res_reg = client.post("/register", data=reg_data, follow_redirects=True)
    assert res_reg.status_code == 200

    with app_instance.app_context():
        user = User.query.filter_by(email="kavita.sharma@example.com").first()
        assert user is not None
        assert user.approval_status == "pending"
        assert user.is_active is False

        req = RegistrationRequest.query.filter_by(user_id=user.id).first()
        assert req is not None
        assert req.status == "pending"
        req_id = req.id

    # 2. Verify pending login is blocked
    login_page = client.get("/login")
    token = extract_csrf_token(login_page)
    res_pending_login = client.post("/login", data={
        "csrf_token": token,
        "identifier": "kavita.sharma@example.com",
        "password": "Password@123",
        "login_type": "member"
    }, follow_redirects=True)
    assert res_pending_login.status_code == 200
    assert b"awaiting admin approval" in res_pending_login.data.lower()

    # 3. Admin logs in and approves request
    login_page = client.get("/login")
    token = extract_csrf_token(login_page)
    client.post("/login", data={
        "csrf_token": token,
        "identifier": "admin@sunriseheights.example",
        "password": "Admin#Pass2026",
        "login_type": "admin"
    }, follow_redirects=True)

    requests_page = client.get("/admin/requests")
    assert requests_page.status_code == 200
    admin_token = extract_csrf_token(requests_page)

    res_approve = client.post(f"/admin/requests/{req_id}/approve", data={
        "csrf_token": admin_token
    }, follow_redirects=True)
    assert res_approve.status_code == 200
    assert b"approved" in res_approve.data.lower()

    with app_instance.app_context():
        u = User.query.filter_by(email="kavita.sharma@example.com").first()
        assert u.approval_status == "approved"
        assert u.is_active is True
        assert u.failed_attempts == 0
        assert u.locked_until is None

        fm = FlatMember.query.filter_by(user_id=u.id, is_active=True).first()
        assert fm is not None
        assert fm.flat_id == flat_id
        assert fm.relation_type == "Tenant"

    # Admin logs out
    client.post("/logout", data={"csrf_token": admin_token}, follow_redirects=True)

    # 4. Approved member logs in
    login_page = client.get("/login")
    token = extract_csrf_token(login_page)
    res_member_login = client.post("/login", data={
        "csrf_token": token,
        "identifier": "kavita.sharma@example.com",
        "password": "Password@123",
        "login_type": "member"
    }, follow_redirects=True)
    assert res_member_login.status_code == 200
    assert b"dashboard" in res_member_login.data.lower()

    # 5. Dashboard loads with flat badge and status 200
    res_dash = client.get("/member/dashboard")
    assert res_dash.status_code == 200
    assert b"Welcome, Kavita Sharma" in res_dash.data
    assert b"Flat" in res_dash.data

    # 6. Member hits /admin/* -> gets 403
    res_admin_forbidden = client.get("/admin/dashboard")
    assert res_admin_forbidden.status_code == 403

    # 7. Test member without flat sees friendly message (HTTP 200, never 500)
    with app_instance.app_context():
        # Deactivate flat member
        fm = FlatMember.query.filter_by(user_id=u.id).first()
        fm.is_active = False
        db.session.commit()

    res_no_flat = client.get("/member/dashboard")
    assert res_no_flat.status_code == 200
    assert b"has not yet linked a flat" in res_no_flat.data or b"assigned yet" in res_no_flat.data.lower()

    # 8. Test member with flat but no bills sees friendly empty state (HTTP 200)
    with app_instance.app_context():
        fm = FlatMember.query.filter_by(user_id=u.id).first()
        fm.is_active = True
        db.session.commit()

    res_with_flat = client.get("/member/dashboard")
    assert res_with_flat.status_code == 200
    assert b"No Maintenance Invoices" in res_with_flat.data or "₹0.00".encode("utf-8") in res_with_flat.data


def test_theme_and_dropdown_elements_present(client):
    """
    TASK 2 & 3:
    Verify theme buttons, theme init script, and CSS select/theme tokens.
    """
    # 1. Login page has theme button and flash-free script
    res_login = client.get("/login")
    assert res_login.status_code == 200
    assert b"themeToggleBtn" in res_login.data
    assert b"localStorage.getItem('theme')" in res_login.data

    # 2. Register page has theme button, flash-free script and wing/flat select
    res_reg = client.get("/register")
    assert res_reg.status_code == 200
    assert b"themeToggleBtn" in res_reg.data
    assert b"wingSelect" in res_reg.data
    assert b"flatSelect" in res_reg.data

    # 3. Main CSS contains required select and theme tokens
    res_css = client.get("/static/css/main.css")
    assert res_css.status_code == 200
    css_content = res_css.data.decode("utf-8")

    assert ":root" in css_content
    assert 'color-scheme: dark' in css_content
    assert ':root[data-theme="light"]' in css_content
    assert 'color-scheme: light' in css_content
    assert '--select-bg' in css_content
    assert 'select, select option, select optgroup' in css_content
    assert 'filter: invert(1)' in css_content
