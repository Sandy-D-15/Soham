import os
import sys
import tempfile
import secrets
import pytest

# Ensure workspace root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from decimal import Decimal
from datetime import date
from werkzeug.security import generate_password_hash

from database.db import db
from models.user import User
from models.society import Society
from models.building import Building
from models.wing import Wing
from models.floor import Floor
from models.flat import Flat
from models.flat_member import FlatMember
from models.maintenance_component import MaintenanceComponent
from models.maintenance_bill import MaintenanceBill
from models.financial_account import FinancialAccount
from migrate import run_migration


@pytest.fixture
def app_instance():
    # Setup isolated unique temp DB per test
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, f"test_{secrets.token_hex(4)}.db")
    os.environ["DATABASE_PATH"] = db_path
    os.environ["SECRET_KEY"] = "pytest-secure-test-secret-key-2026"
    os.environ["FLASK_ENV"] = "development"

    import app as app_module
    test_app = app_module.app
    test_app.config["TESTING"] = True
    test_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    test_app.config["WTF_CSRF_ENABLED"] = True

    with test_app.app_context():
        db.engine.dispose()
        db.drop_all()
        db.create_all()
        run_migration(db_path)

        # Create base society
        soc = Society(
            name="Sunrise Heights Co-operative Housing Society Ltd.",
            address="Plot 104, Sunrise Heights Marg",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            official_email="admin@sunriseheights.example"
        )
        db.session.add(soc)
        db.session.commit()

        # Create Building, Wing, Floor, Flats
        bld = Building(society_id=soc.id, name="Tower Alpha")
        db.session.add(bld)
        db.session.commit()

        wing = Wing(building_id=bld.id, name="A")
        db.session.add(wing)
        db.session.commit()

        flr = Floor(wing_id=wing.id, floor_number=1)
        db.session.add(flr)
        db.session.commit()

        flat1 = Flat(floor_id=flr.id, flat_number="101", carpet_area=800, occupancy_status="Owner Occupied")
        flat2 = Flat(floor_id=flr.id, flat_number="102", carpet_area=900, occupancy_status="Vacant")
        flat3 = Flat(floor_id=flr.id, flat_number="103", carpet_area=850, occupancy_status="Vacant")
        db.session.add_all([flat1, flat2, flat3])
        db.session.commit()

        # Create Admin
        admin = User(
            full_name="Rajesh Kulkarni",
            email="admin@sunriseheights.example",
            mobile="9820011223",
            password_hash=generate_password_hash("Admin#Pass2026"),
            role="secretary",
            approval_status="approved",
            is_active=True
        )
        db.session.add(admin)

        # Create Approved Member with flat1
        member = User(
            full_name="Amit Deshmukh",
            email="amit.deshmukh@example.com",
            mobile="9820055443",
            password_hash=generate_password_hash("Resident#Pass2026"),
            role="member",
            approval_status="approved",
            is_active=True
        )
        db.session.add(member)
        db.session.commit()

        fm = FlatMember(
            flat_id=flat1.id,
            user_id=member.id,
            relation_type="Owner",
            is_primary=True,
            is_active=True,
            start_date=date(2026, 1, 1)
        )
        db.session.add(fm)

        # Create bank account & bill for member
        bank_acc = FinancialAccount(
            society_id=soc.id,
            name="Society Operating Account",
            account_type="Bank",
            opening_balance=Decimal("50000.00"),
            status=True
        )
        db.session.add(bank_acc)

        bill = MaintenanceBill(
            society_id=soc.id,
            flat_id=flat1.id,
            bill_month=10,
            bill_year=2026,
            bill_date=date(2026, 10, 1),
            due_date=date(2026, 10, 15),
            subtotal=Decimal("3000.00"),
            total_amount=Decimal("3000.00"),
            paid_amount=Decimal("0.00"),
            balance_amount=Decimal("3000.00"),
            status="Unpaid"
        )
        db.session.add(bill)
        db.session.commit()

    yield test_app

    with test_app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def extract_csrf_token(response):
    """Utility to parse csrf_token from rendered HTML forms."""
    import re
    html = response.get_data(as_text=True)
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not match:
        match = re.search(r'name=[\'"]csrf_token[\'"]\s+value=[\'"]([^\'"]+)[\'"]', html)
    if not match:
        match = re.search(r'content="([^"]+)"\s+name="csrf-token"', html)
    if not match:
        match = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    return match.group(1) if match else ""
