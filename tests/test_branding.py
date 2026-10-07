import io
import os
import re
import pytest

from database.db import db
from models.society import Society
from models.user import User
from app import format_inr
from tests.conftest import extract_csrf_token


def login_as(client, email, password, role="member"):
    """Helper to authenticate user."""
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


def test_inr_currency_formatting():
    """Verify format_inr correctly formats amounts with ₹ symbol and Indian comma grouping."""
    assert format_inr(0) == "₹0"
    assert format_inr(100) == "₹100"
    assert format_inr(1000) == "₹1,000"
    assert format_inr(15000) == "₹15,000"
    assert format_inr(125000) == "₹1,25,000"
    assert format_inr(10000000) == "₹1,00,00,000"
    assert format_inr("3500.50") == "₹3,500.50"
    assert format_inr(-2500) == "-₹2,500"


def test_dynamic_page_titles(app_instance, client):
    """Verify pages dynamically include the active society name in their <title> tag."""
    with app_instance.app_context():
        soc = Society.query.first()
        society_name = soc.name

    # 1. Login page
    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert society_name.encode() in login_page.data

    # 2. Member dashboard
    login_as(client, "amit.deshmukh@example.com", "Resident#Pass2026", role="member")
    member_page = client.get("/member/dashboard")
    assert member_page.status_code == 200
    title_match = re.search(r"<title>(.*?)</title>", member_page.data.decode("utf-8"), re.DOTALL)
    assert title_match is not None
    assert society_name in title_match.group(1)

    # 3. Secretary complaints
    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")
    sec_page = client.get("/complaints")
    assert sec_page.status_code == 200
    title_match2 = re.search(r"<title>(.*?)</title>", sec_page.data.decode("utf-8"), re.DOTALL)
    assert title_match2 is not None
    assert society_name in title_match2.group(1)


def test_society_logo_upload_and_serving(app_instance, client):
    """Secretary can upload a society logo in Society Settings, and the logo is served correctly."""
    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")

    settings_page = client.get("/society-settings")
    assert settings_page.status_code == 200
    token = extract_csrf_token(settings_page)

    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    logo_file = (io.BytesIO(fake_png), "society_emblem.png")

    post_res = client.post("/society-settings", data={
        "csrf_token": token,
        "name": "Sunrise Heights Co-operative Housing Society Ltd.",
        "registration_number": "BOM/HSG/8899/2026",
        "phone": "9820011223",
        "official_email": "admin@sunriseheights.example",
        "address": "Plot 104, Sunrise Heights Marg",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400001",
        "logo": logo_file
    }, content_type="multipart/form-data", follow_redirects=True)

    assert post_res.status_code == 200
    assert b"saved successfully" in post_res.data

    with app_instance.app_context():
        soc = Society.query.first()
        assert soc.logo_filename is not None
        assert "society_emblem.png" in soc.logo_filename
        logo_fname = soc.logo_filename

    # Verify logo download / image route
    logo_res = client.get(f"/society/logo/{logo_fname}")
    assert logo_res.status_code == 200
    assert logo_res.data == fake_png

    # Verify sidebar in base.html displays the logo
    dash_res = client.get("/admin/dashboard")
    assert dash_res.status_code == 200
    assert f"/society/logo/{logo_fname}".encode() in dash_res.data


def test_society_logo_invalid_extension_rejected(app_instance, client):
    """Uploading executable or unsupported file as logo is rejected."""
    login_as(client, "admin@sunriseheights.example", "Admin#Pass2026", role="secretary")
    settings_page = client.get("/society-settings")
    token = extract_csrf_token(settings_page)

    bad_file = (io.BytesIO(b"malicious code"), "exploit.exe")

    res = client.post("/society-settings", data={
        "csrf_token": token,
        "name": "Sunrise Heights Co-operative Housing Society Ltd.",
        "registration_number": "BOM/HSG/8899/2026",
        "phone": "9820011223",
        "official_email": "admin@sunriseheights.example",
        "address": "Plot 104, Sunrise Heights Marg",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400001",
        "logo": bad_file
    }, content_type="multipart/form-data", follow_redirects=True)

    assert res.status_code == 200
    assert b"Invalid logo format" in res.data
