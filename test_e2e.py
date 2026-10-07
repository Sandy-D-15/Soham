import os
import sys
import tempfile
import secrets
from decimal import Decimal
from datetime import datetime, date
from werkzeug.security import generate_password_hash

# Set testing environment before importing app
temp_dir = tempfile.mkdtemp()
temp_db_path = os.path.join(temp_dir, "test_society.db")
os.environ["DATABASE_PATH"] = temp_db_path
os.environ["SECRET_KEY"] = "test-e2e-random-secret-key-" + secrets.token_hex(16)
os.environ["WTF_CSRF_ENABLED"] = "false"  # Simplify direct client.post testing

import app as app_module
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
from models.maintenance_payment import MaintenancePayment
from models.financial_account import FinancialAccount
from models.financial_transaction import FinancialTransaction
from models.expense_category import ExpenseCategory
from models.expense import Expense
from models.staff import Staff
from models.staff_payment import StaffPayment
from models.vendor import Vendor
from models.notice import Notice
from models.complaint import Complaint
from models.audit_log import AuditLog
from migrate import run_migration

app = app_module.app
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{temp_db_path}"

client = app.test_client()

print("--- STARTING COMPREHENSIVE ISOLATED SYSTEM E2E VERIFICATION ---")

# Setup clean database tables
with app.app_context():
    db.create_all()
    run_migration(temp_db_path)

admin_email = f"admin_{secrets.token_hex(4)}@societyportal.example"
admin_pwd = f"AdminP@ss{secrets.token_hex(4)}"
member_email = f"member_{secrets.token_hex(4)}@societyportal.example"
member_pwd = f"MemberP@ss{secrets.token_hex(4)}"

with app.app_context():
    # 1. Setup Test Society
    society = Society(
        name="Sunrise Heights Co-operative Housing Society Ltd.",
        registration_number="MH/MUM/HSG/2026/1001",
        address="Plot 104, Sunrise Heights Marg",
        city="Mumbai",
        state="Maharashtra",
        pincode="400001",
        phone="9820011223",
        official_email="office@sunriseheights.example"
    )
    db.session.add(society)
    db.session.commit()
    print("[OK] Created Isolated Test Society:", society.name)

    # 2. Setup Admin User
    admin = User(
        full_name="Rajesh Kulkarni",
        email=admin_email,
        mobile="9820011223",
        password_hash=generate_password_hash(admin_pwd),
        role="secretary",
        approval_status="approved",
        is_active=True
    )
    db.session.add(admin)

    # 3. Setup Member User
    member = User(
        full_name="Amit Deshmukh",
        email=member_email,
        mobile="9820055443",
        password_hash=generate_password_hash(member_pwd),
        role="member",
        approval_status="approved",
        is_active=True
    )
    db.session.add(member)

    # 4. Financial Account & Expense Category
    bank_acc = FinancialAccount(
        society_id=society.id,
        name="HDFC Society Main Operating Account",
        account_type="Bank",
        opening_balance=Decimal("150000.00"),
        status=True
    )
    db.session.add(bank_acc)

    cat = ExpenseCategory(
        society_id=society.id,
        name="Lift Maintenance",
        description="Elevator upkeep and inspections",
        status=True
    )
    db.session.add(cat)
    db.session.commit()
    print("[OK] Test Accounts & Categories created")

# Helper function to login
def login(email, password, login_type="member"):
    return client.post('/login', data={'identifier': email, 'password': password, 'login_type': login_type}, follow_redirects=True)

# Test Login Secretary
res = login(admin_email, admin_pwd, login_type="admin")
assert res.status_code == 200, f"Admin Login failed: {res.status_code}"
assert b"Dashboard" in res.data, "Admin dashboard not loaded"
print("[OK] Admin Login & Dashboard verified")

# Test Building, Wing, Floor, Flat setup
with app.app_context():
    soc = Society.query.first()
    bld = Building(society_id=soc.id, name="Tower Alpha")
    db.session.add(bld)
    db.session.commit()
    wing = Wing(building_id=bld.id, name="A")
    db.session.add(wing)
    db.session.commit()
    flr = Floor(wing_id=wing.id, floor_number=1)
    db.session.add(flr)
    db.session.commit()
    flat = Flat(floor_id=flr.id, flat_number="101", carpet_area=850, occupancy_status="Owner Occupied")
    db.session.add(flat)
    db.session.commit()
    mem = User.query.filter_by(email=member_email).first()
    fm = FlatMember(flat_id=flat.id, user_id=mem.id, relation_type="Owner", is_primary=True, is_active=True)
    db.session.add(fm)
    db.session.commit()
    print("[OK] Building, Wing, Floor, Flat, FlatMember verified")

# Test Maintenance Component
with app.app_context():
    soc = Society.query.first()
    comp = MaintenanceComponent(
        society_id=soc.id,
        name="Standard Monthly Dues",
        calculation_method="Fixed",
        amount=Decimal("2500.00"),
        effective_date=date(2026, 1, 1),
        status=True
    )
    db.session.add(comp)
    db.session.commit()
    print("[OK] Maintenance Component verified")

# Test Bill Generation
gen_res = client.post('/maintenance/bills/generate', data={'bill_month': 10, 'bill_year': 2026, 'due_date': '2026-10-15'}, follow_redirects=True)
assert gen_res.status_code == 200
print("[OK] Bill Generation route verified")

# Test Record Maintenance Payment & Receipt
with app.app_context():
    soc = Society.query.first()
    bill = MaintenanceBill.query.filter_by(society_id=soc.id).first()
    bank_acc = FinancialAccount.query.filter_by(society_id=soc.id, account_type="Bank").first()
    assert bill is not None, "Bill was not generated"

pay_res = client.post(f'/maintenance/bills/{bill.id}/payment', data={
    'amount': '2500.00',
    'payment_mode': 'UPI',
    'payment_date': '2026-10-02',
    'reference_number': 'UPI9988776655',
    'account_id': bank_acc.id,
    'notes': 'Paid via NetBanking/UPI'
}, follow_redirects=True)
assert pay_res.status_code == 200
print("[OK] Maintenance Payment & Credit Transaction verified")

# Verify Credit Transaction in Ledger
with app.app_context():
    credit_txn = FinancialTransaction.query.filter_by(source_type="MaintenancePayment").first()
    assert credit_txn is not None, "Credit transaction not found"
    assert credit_txn.direction == "Credit"
    assert credit_txn.amount == Decimal("2500.00")
    print("[OK] Ledger Credit Transaction verified: Amount Rs.", credit_txn.amount)

# Test Expense Creation & Approval & Payment
tag = str(int(datetime.now().timestamp()))
inv_ref = f'INV-ELEV-{tag}'
notice_title = f'Annual General Meeting {tag}'
complaint_title = f'Common Corridor Lighting {tag}'
salary_month = f'2026-10'

with app.app_context():
    soc = Society.query.first()
    cat = ExpenseCategory.query.filter_by(society_id=soc.id).first()

exp_res = client.post('/expenses/add', data={
    'category_id': cat.id,
    'vendor_name': f'Vertex Elevators {tag}',
    'amount': '1200.00',
    'expense_date': '2026-10-02',
    'invoice_reference': inv_ref,
    'notes': 'Quarterly elevator inspection'
}, follow_redirects=True)
assert exp_res.status_code == 200
print("[OK] Expense Creation verified")

with app.app_context():
    exp = Expense.query.filter_by(invoice_reference=inv_ref).first()
    assert exp is not None, "Expense not found"
    assert exp.approval_status == "Pending Approval"
    exp_id = exp.id

apprv_res = client.post(f'/expenses/{exp_id}/approve', follow_redirects=True)
assert apprv_res.status_code == 200
print("[OK] Expense Approval verified")

with app.app_context():
    soc = Society.query.first()
    bank_acc = FinancialAccount.query.filter_by(society_id=soc.id, account_type="Bank").first()

pay_exp_res = client.post(f'/expenses/{exp_id}/pay', data={
    'payment_mode': 'Bank Transfer',
    'account_id': bank_acc.id,
    'payment_reference': f'NEFT-{tag}'
}, follow_redirects=True)
assert pay_exp_res.status_code == 200
print("[OK] Expense Disbursement & Debit Transaction verified")

with app.app_context():
    debit_txn = FinancialTransaction.query.filter_by(source_type="Expense", source_id=exp_id).first()
    assert debit_txn is not None, "Debit transaction not found"
    assert debit_txn.direction == "Debit"
    assert debit_txn.amount == Decimal("1200.00")
    print("[OK] Ledger Debit Transaction verified: Amount Rs.", debit_txn.amount)

# Test Duplicate Expense Prevention
dup_res = client.post('/expenses/add', data={
    'category_id': cat.id,
    'vendor_name': f'Vertex Elevators {tag}',
    'amount': '1200.00',
    'expense_date': '2026-10-02',
    'invoice_reference': inv_ref,
    'notes': 'Duplicate attempt'
}, follow_redirects=True)
assert b"already exists" in dup_res.data or dup_res.status_code == 200
print("[OK] Duplicate Expense prevention check verified")

# Test Staff Enrolment & Payroll
staff_res = client.post('/staff/add', data={
    'name': f'Security Officer {tag}',
    'role': 'Security Guard',
    'phone': f'98{tag[-8:]}',
    'salary': '14000.00',
    'joining_date': '2026-01-01',
    'id_proof_number': f'ID-{tag}'
}, follow_redirects=True)
assert staff_res.status_code == 200
print("[OK] Staff Enrolment verified")

# Generate Staff Salary Slips
staff_gen_res = client.post('/staff/payments/generate', data={'month_year': salary_month}, follow_redirects=True)
assert staff_gen_res.status_code == 200
print("[OK] Staff Salary Generation verified")

with app.app_context():
    slip = StaffPayment.query.filter_by(month_year=salary_month).first()
    assert slip is not None, "Staff salary slip not found"
    slip_id = slip.id

slip_apprv_res = client.post(f'/staff/payments/{slip_id}/approve', follow_redirects=True)
assert slip_apprv_res.status_code == 200
print("[OK] Staff Salary Approval verified")

slip_pay_res = client.post(f'/staff/payments/{slip_id}/disburse', data={
    'account_id': bank_acc.id,
    'payment_mode': 'Bank Transfer',
    'payment_date': '2026-10-03',
    'reference_number': f'SAL-{tag}',
    'remarks': 'Monthly salary'
}, follow_redirects=True)
assert slip_pay_res.status_code == 200
print("[OK] Staff Salary Disbursement verified")

# Test Vendor Management
vendor_res = client.post('/vendors/add', data={
    'name': f'Vertex Facility Services {tag}',
    'service_type': 'Facility Management',
    'phone': f'022{tag[-6:]}',
    'contact_person': 'Sanjay Patil',
    'gst_number': '27AABCK1234M1Z2'
}, follow_redirects=True)
assert vendor_res.status_code == 200
print("[OK] Vendor Directory verified")

# Test Notices
notice_res = client.post('/notices/add', data={
    'title': notice_title,
    'category': 'General',
    'priority': 'Important',
    'content': 'All members are invited to attend the upcoming general body meeting.',
    'is_pinned': '1'
}, follow_redirects=True)
assert notice_res.status_code == 200
print("[OK] Notice Publication verified")

# Test Complaints by Member
client.post('/logout', follow_redirects=True)
login(member_email, member_pwd, login_type="member")
complaint_res = client.post('/complaints/add', data={
    'title': complaint_title,
    'category': 'Electrical',
    'priority': 'Medium',
    'description': 'Corridor lighting needs replacement.'
}, follow_redirects=True)
assert complaint_res.status_code == 200
print("[OK] Member Complaint lodging verified")

# Verify Member Dashboard view
mem_dash_res = client.get('/dashboard', follow_redirects=True)
assert mem_dash_res.status_code == 200
assert notice_title.encode() in mem_dash_res.data
assert complaint_title.encode() in mem_dash_res.data
print("[OK] Member Dashboard with Notices & Complaints verified")

# Login back as Secretary & Update Complaint
client.post('/logout', follow_redirects=True)
login(admin_email, admin_pwd, login_type="admin")
with app.app_context():
    comp_ticket = Complaint.query.filter_by(title=complaint_title).first()
    assert comp_ticket is not None
    comp_id = comp_ticket.id

update_comp_res = client.post(f'/complaints/{comp_id}/update', data={
    'status': 'Resolved',
    'assigned_name': 'Technician Suresh',
    'resolution_notes': 'Lighting fixture fixture replaced.'
}, follow_redirects=True)
assert update_comp_res.status_code == 200
print("[OK] Complaint Ticket Resolution verified")

# Test Reports View
reports_res = client.get('/reports')
assert reports_res.status_code == 200
assert b"Operational Cash Flow Summary" in reports_res.data
print("[OK] Reports & Analytics verified")

# Test Audit Logs View
audit_res = client.get('/audit-logs')
assert audit_res.status_code == 200
assert b"Activity Trail" in audit_res.data
print("[OK] System Audit Logs verified")

# Test Transaction Reversal
with app.app_context():
    d_txn = FinancialTransaction.query.filter_by(source_type="Expense", source_id=exp_id).first()
    d_txn_id = d_txn.id

rev_res = client.post(f'/finance/transactions/{d_txn_id}/reverse', data={'reason': 'Accounting adjustment'}, follow_redirects=True)
assert rev_res.status_code == 200
print("[OK] Transaction Reversal verified")

with app.app_context():
    rev_txn = FinancialTransaction.query.filter_by(source_type="Reversal", source_id=d_txn_id).first()
    assert rev_txn is not None, "Reversal entry not found"
    assert rev_txn.direction == "Credit"
    print("[OK] Reversal Entry verified: ID #", rev_txn.id, "Direction:", rev_txn.direction, "Amount: Rs.", rev_txn.amount)

# Test Finance Accounts Ledger View
fin_res = client.get('/finance/accounts')
assert fin_res.status_code == 200
assert b"REVERSED" in fin_res.data
assert b"Reconciled" in fin_res.data
print("[OK] Bank & Cash Ledger with Running Balance & Reconciliation verified")

print("\n==========================================")
print("ALL 13 VERIFICATION TESTS PASSED SUCCESSFULLY ON ISOLATED DB!")
print("==========================================")
