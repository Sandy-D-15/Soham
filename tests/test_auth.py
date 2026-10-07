import pytest
from datetime import datetime, timedelta
from database.db import db
from models.user import User
from models.flat import Flat
from models.flat_member import FlatMember
from models.registration_request import RegistrationRequest
from tests.conftest import extract_csrf_token


def test_registration_creates_pending_member(client, app_instance):
    # 1. Fetch register page for CSRF token
    get_res = client.get("/register")
    assert get_res.status_code == 200
    csrf_token = extract_csrf_token(get_res)
    assert csrf_token != ""

    with app_instance.app_context():
        flat = Flat.query.filter_by(flat_number="102").first()
        flat_id = flat.id

    # 2. Submit valid registration
    post_res = client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "full_name": "Kavita Sharma",
            "email": "kavita.sharma@example.com",
            "mobile": "9819988776",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "flat_id": flat_id,
            "relation_type": "Owner",
            "notes": "Flat purchased in 2025",
            "consent": "1",
        },
        follow_redirects=True,
    )
    assert post_res.status_code == 200
    assert "Registration Submitted" in post_res.get_data(as_text=True)

    # 3. Verify DB state: user is pending, request is pending, no FlatMember link
    with app_instance.app_context():
        user = User.query.filter_by(email="kavita.sharma@example.com").first()
        assert user is not None
        assert user.role == "member"
        assert user.approval_status == "pending"

        req = RegistrationRequest.query.filter_by(user_id=user.id).first()
        assert req is not None
        assert req.status == "pending"
        assert req.requested_flat_id == flat_id

        # Verify NO flat_members link created yet
        fm = FlatMember.query.filter_by(user_id=user.id).first()
        assert fm is None


def test_registration_ignores_smuggled_role(client, app_instance):
    get_res = client.get("/register")
    csrf_token = extract_csrf_token(get_res)

    with app_instance.app_context():
        flat = Flat.query.filter_by(flat_number="103").first()
        flat_id = flat.id

    # Smuggle role='secretary' in POST body
    client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "full_name": "Smuggler User",
            "email": "smuggler@example.com",
            "mobile": "9820099887",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "flat_id": flat_id,
            "relation_type": "Tenant",
            "consent": "1",
            "role": "secretary",
        },
        follow_redirects=True,
    )

    with app_instance.app_context():
        user = User.query.filter_by(email="smuggler@example.com").first()
        assert user is not None
        assert user.role == "member"  # Must ALWAYS remain member


def test_registration_duplicate_email_or_mobile(client, app_instance):
    get_res = client.get("/register")
    csrf_token = extract_csrf_token(get_res)

    with app_instance.app_context():
        flat = Flat.query.first()
        flat_id = flat.id

    # Duplicate email
    res1 = client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "full_name": "Duplicate Email Test",
            "email": "amit.deshmukh@example.com",  # Already exists in fixture
            "mobile": "9821100220",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "flat_id": flat_id,
            "consent": "1",
        },
        follow_redirects=True,
    )
    assert "already exists" in res1.get_data(as_text=True)

    # Duplicate mobile
    res2 = client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "full_name": "Duplicate Mobile Test",
            "email": "unique.user@example.com",
            "mobile": "9820055443",  # Already exists in fixture
            "password": "Password@123",
            "confirm_password": "Password@123",
            "flat_id": flat_id,
            "consent": "1",
        },
        follow_redirects=True,
    )
    assert "already exists" in res2.get_data(as_text=True)


def test_login_pending_user_refused(client, app_instance):
    with app_instance.app_context():
        from werkzeug.security import generate_password_hash
        u = User(
            full_name="Kavita Pending",
            email="kavita.pending@example.com",
            mobile="9877700011",
            password_hash=generate_password_hash("Password@123"),
            role="member",
            approval_status="pending",
            is_active=True,
        )
        db.session.add(u)
        db.session.commit()

    get_res = client.get("/login")
    csrf = extract_csrf_token(get_res)

    res = client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login_type": "member",
            "identifier": "kavita.pending@example.com",
            "password": "Password@123",
        },
        follow_redirects=True,
    )
    assert "awaiting admin approval" in res.get_data(as_text=True)


def test_login_rejected_user_refused(client, app_instance):
    with app_instance.app_context():
        from werkzeug.security import generate_password_hash
        rej_user = User(
            full_name="Rejected Member",
            email="rejected@example.com",
            mobile="9866600022",
            password_hash=generate_password_hash("Password@123"),
            role="member",
            approval_status="rejected",
            rejection_reason="Unverified sale agreement",
            is_active=True,
        )
        db.session.add(rej_user)
        db.session.commit()

    get_res = client.get("/login")
    csrf = extract_csrf_token(get_res)

    res = client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login_type": "member",
            "identifier": "rejected@example.com",
            "password": "Password@123",
        },
        follow_redirects=True,
    )
    data = res.get_data(as_text=True)
    assert "not approved" in data
    assert "Unverified sale agreement" in data


def test_login_role_tab_mismatch_refused(client, app_instance):
    get_res = client.get("/login")
    csrf = extract_csrf_token(get_res)

    # 1. Member account on Admin tab
    res1 = client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login_type": "admin",
            "identifier": "amit.deshmukh@example.com",
            "password": "Resident#Pass2026",
        },
        follow_redirects=True,
    )
    assert "This is not an admin account. Please use Member Login." in res1.get_data(as_text=True)

    # 2. Admin account on Member tab
    res2 = client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login_type": "member",
            "identifier": "admin@sunriseheights.example",
            "password": "Admin#Pass2026",
        },
        follow_redirects=True,
    )
    assert "This is an admin account. Please use Admin Login." in res2.get_data(as_text=True)


def test_account_lockout_after_5_failed_attempts(client, app_instance):
    get_res = client.get("/login")
    csrf = extract_csrf_token(get_res)

    # Make 5 failed attempts
    for _ in range(5):
        client.post(
            "/login",
            data={
                "csrf_token": csrf,
                "login_type": "admin",
                "identifier": "admin@sunriseheights.example",
                "password": "WrongPassword999",
            },
            follow_redirects=True,
        )

    # 6th attempt should show locked message
    res = client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login_type": "admin",
            "identifier": "admin@sunriseheights.example",
            "password": "WrongPassword999",
        },
        follow_redirects=True,
    )
    assert "Too many failed attempts" in res.get_data(as_text=True)


def test_safe_next_url(client, app_instance):
    get_res = client.get("/login")
    csrf = extract_csrf_token(get_res)

    # Malicious external URL
    res = client.post(
        "/login?next=https://evil.com/phishing",
        data={
            "csrf_token": csrf,
            "login_type": "admin",
            "identifier": "admin@sunriseheights.example",
            "password": "Admin#Pass2026",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "evil.com" not in res.location
    assert res.location in ("/admin/dashboard", "/dashboard")


def test_dashboard_redirects_by_role(client, app_instance):
    get_res = client.get("/login")
    csrf = extract_csrf_token(get_res)

    # Login as member
    client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login_type": "member",
            "identifier": "amit.deshmukh@example.com",
            "password": "Resident#Pass2026",
        },
        follow_redirects=True,
    )

    dash_res = client.get("/dashboard", follow_redirects=False)
    assert dash_res.status_code == 302
    assert dash_res.location == "/member/dashboard"

    client.get("/logout", follow_redirects=True)

    # Login as admin with fresh CSRF token
    get_res_admin = client.get("/login")
    csrf_admin = extract_csrf_token(get_res_admin)

    client.post(
        "/login",
        data={
            "csrf_token": csrf_admin,
            "login_type": "admin",
            "identifier": "admin@sunriseheights.example",
            "password": "Admin#Pass2026",
        },
        follow_redirects=True,
    )

    dash_res_admin = client.get("/dashboard", follow_redirects=False)
    assert dash_res_admin.status_code == 302
    assert dash_res_admin.location == "/admin/dashboard"
