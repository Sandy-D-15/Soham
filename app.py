from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_from_directory
from werkzeug.utils import secure_filename



from flask_login import (

    LoginManager,

    login_user,

    logout_user,

    login_required,

    current_user

)



from werkzeug.security import (

    check_password_hash,

    generate_password_hash

)





from decimal import Decimal, InvalidOperation
from datetime import datetime
import calendar
import os
import uuid
from config import Config
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
from models.maintenance_bill_item import MaintenanceBillItem
from models.maintenance_payment import MaintenancePayment
from models.payment_receipt import PaymentReceipt
from models.financial_account import FinancialAccount
from models.financial_transaction import FinancialTransaction
from models.expense_category import ExpenseCategory
from models.expense import Expense
from models.audit_log import AuditLog
from models.staff import Staff
from models.staff_payment import StaffPayment
from models.vendor import Vendor
from models.notice import Notice
from models.complaint import Complaint
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)

from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.member import member_bp
from routes.notifications import notifications_bp
from routes.complaints import complaints_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(member_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(complaints_bp)

@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response

@app.errorhandler(403)
def forbidden_handler(e):
    return render_template("errors/403.html"), 403

@app.errorhandler(404)
def not_found_handler(e):
    return render_template("errors/404.html"), 404

@app.errorhandler(500)
def server_error_handler(e):
    return render_template("errors/500.html"), 500

@app.route("/legacy-login", endpoint="login")
def legacy_login_alias():
    return redirect(url_for("auth.login"))

@app.route("/legacy-logout", endpoint="logout", methods=["GET", "POST"])
def legacy_logout_alias():
    return redirect(url_for("auth.logout"))

# -------------------------
# LOGIN MANAGER
# -------------------------

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Please login to continue."





@login_manager.user_loader

def load_user(user_id):



    return db.session.get(

        User,

        int(user_id)

    )





# -------------------------

# HOME

# -------------------------



@app.route("/")

def home():



    if current_user.is_authenticated:



        return redirect(

            url_for("dashboard")

        )



    return redirect(

        url_for("login")

    )





# -------------------------

# LOGIN

# -------------------------



# Note: /login and /logout are now handled by routes.auth (auth_bp)

# -------------------------
# DASHBOARD REDIRECTOR
# -------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "secretary":
        return redirect(url_for("admin.dashboard"))
    elif current_user.role == "member":
        return redirect(url_for("member.dashboard"))
    abort(403)


@app.route("/dashboard/legacy")
@login_required
def dashboard_legacy():

    society = Society.query.first()

    # -------------------------
    # SECRETARY DASHBOARD
    # -------------------------

    if current_user.role == "secretary":

        if not society:
            flash(
                "Please setup society information first."
            )
            return redirect(
                url_for("society_settings")
            )

        total_members = User.query.filter_by(
            role="member",
            is_active=True
        ).count()

        if society:

            total_flats = (
                Flat.query
                .join(
                    Floor,
                    Flat.floor_id == Floor.id
                )
                .join(
                    Wing,
                    Floor.wing_id == Wing.id
                )
                .join(
                    Building,
                    Wing.building_id == Building.id
                )
                .filter(
                    Building.society_id == society.id,
                    Flat.status.is_(True)
                )
                .count()
            )

        else:
            total_flats = 0
                # -------------------------
        # REAL FINANCIAL DASHBOARD
        # -------------------------

        today = datetime.now().date()

        month_start = datetime(
            today.year,
            today.month,
            1
        ).date()

        if today.month == 12:

            next_month_start = datetime(
                today.year + 1,
                1,
                1
            ).date()

        else:

            next_month_start = datetime(
                today.year,
                today.month + 1,
                1
            ).date()


        # CURRENT MONTH MAINTENANCE COLLECTION

        monthly_transactions = (
            FinancialTransaction.query
            .filter(
                FinancialTransaction.society_id == society.id,
                FinancialTransaction.source_type == "MaintenancePayment",
                FinancialTransaction.direction == "Credit",
                FinancialTransaction.transaction_date >= month_start,
                FinancialTransaction.transaction_date < next_month_start
            )
            .all()
        )

        maintenance_collected = sum(
            (
                Decimal(str(transaction.amount))
                for transaction in monthly_transactions
            ),
            Decimal("0.00")
        )


        # PENDING MAINTENANCE

        pending_bills = (
            MaintenanceBill.query
            .filter(
                MaintenanceBill.society_id == society.id,
                MaintenanceBill.balance_amount > 0
            )
            .all()
        )

        pending_maintenance = sum(
            (
                Decimal(str(bill.balance_amount))
                for bill in pending_bills
            ),
            Decimal("0.00")
        )


        # SOCIETY BANK BALANCE

        bank_accounts = (
            FinancialAccount.query
            .filter_by(
                society_id=society.id,
                account_type="Bank",
                status=True
            )
            .all()
        )

        society_bank_balance = Decimal("0.00")

        for account in bank_accounts:

            credit_total = sum(
                (
                    Decimal(str(transaction.amount))
                    for transaction in account.transactions
                    if transaction.direction == "Credit"
                ),
                Decimal("0.00")
            )

            debit_total = sum(
                (
                    Decimal(str(transaction.amount))
                    for transaction in account.transactions
                    if transaction.direction == "Debit"
                ),
                Decimal("0.00")
            )

            opening_balance = Decimal(
                str(account.opening_balance or 0)
            )

            society_bank_balance += (
                opening_balance
                + credit_total
                - debit_total
            )


        # EXPENSE MODULE WILL CONNECT NEXT

        total_expenses = Decimal("0.00")


        # RECENT MAINTENANCE PAYMENTS

        recent_payments = (
            MaintenancePayment.query
            .join(
                MaintenanceBill,
                MaintenancePayment.bill_id
                == MaintenanceBill.id
            )
            .filter(
                MaintenanceBill.society_id
                == society.id
            )
            .order_by(
                MaintenancePayment.payment_date.desc(),
                MaintenancePayment.id.desc()
            )
            .limit(5)
            .all()
        )
                # -------------------------
        # INCOME VS EXPENSE CHART
        # LAST 6 MONTHS
        # -------------------------

        chart_labels = []
        chart_income = []
        chart_expense = []

        current_year = today.year
        current_month = today.month

        for offset in range(5, -1, -1):

            month_number = current_month - offset
            year_number = current_year

            while month_number <= 0:
                month_number += 12
                year_number -= 1

            month_start_date = datetime(
                year_number,
                month_number,
                1
            ).date()

            if month_number == 12:

                month_end_date = datetime(
                    year_number + 1,
                    1,
                    1
                ).date()

            else:

                month_end_date = datetime(
                    year_number,
                    month_number + 1,
                    1
                ).date()


            month_transactions = (
                FinancialTransaction.query
                .filter(
                    FinancialTransaction.society_id
                    == society.id,

                    FinancialTransaction.transaction_date
                    >= month_start_date,

                    FinancialTransaction.transaction_date
                    < month_end_date
                )
                .all()
            )


            income_total = sum(
                (
                    Decimal(str(transaction.amount))
                    for transaction in month_transactions
                    if transaction.direction == "Credit"
                ),
                Decimal("0.00")
            )


            expense_total = sum(
                (
                    Decimal(str(transaction.amount))
                    for transaction in month_transactions
                    if transaction.direction == "Debit"
                ),
                Decimal("0.00")
            )


            chart_labels.append(
                calendar.month_abbr[month_number]
            )

            chart_income.append(
                float(income_total)
            )

            chart_expense.append(
                float(expense_total)
            )
        open_complaints_count = Complaint.query.filter_by(society_id=society.id, status='Open').count() if society else 0
        pending_salaries_count = StaffPayment.query.filter_by(society_id=society.id, status='Pending Approval').count() if society else 0

        return render_template(
            "secretary_dashboard.html",
            total_members=total_members,
            total_flats=total_flats,
            society=society,
            maintenance_collected=maintenance_collected,
            pending_maintenance=pending_maintenance,
            society_bank_balance=society_bank_balance,
            total_expenses=total_expenses,
            recent_payments=recent_payments,
            chart_labels=chart_labels,
            chart_income=chart_income,
            chart_expense=chart_expense,
            open_complaints_count=open_complaints_count,
            pending_salaries_count=pending_salaries_count
        )

    # -------------------------
    # MEMBER DASHBOARD
    # -------------------------

    elif current_user.role == "member":

        assignments = FlatMember.query.filter_by(
            user_id=current_user.id,
            is_active=True
        ).all()

        primary_assignment = FlatMember.query.filter_by(
            user_id=current_user.id,
            is_active=True,
            is_primary=True
        ).first()

        if not primary_assignment and assignments:
            primary_assignment = assignments[0]

        bill_history = []
        latest_bill = None
        latest_payment = None

        if primary_assignment:

            bill_history = (
                MaintenanceBill.query
                .filter_by(
                    flat_id=primary_assignment.flat_id
                )
                .order_by(
                    MaintenanceBill.bill_year.desc(),
                    MaintenanceBill.bill_month.desc()
                )
                .all()
            )

            if bill_history:

                latest_bill = bill_history[0]

                latest_payment = (
                    MaintenancePayment.query
                    .filter_by(
                        bill_id=latest_bill.id
                    )
                    .order_by(
                        MaintenancePayment.payment_date.desc(),
                        MaintenancePayment.id.desc()
                    )
                    .first()
                )

        active_notices = (
            Notice.query
            .filter_by(society_id=society.id, is_active=True)
            .order_by(Notice.is_pinned.desc(), Notice.created_at.desc())
            .limit(3)
            .all()
        ) if society else []

        my_complaints = (
            Complaint.query
            .filter_by(society_id=society.id, member_id=current_user.id)
            .order_by(Complaint.created_at.desc())
            .limit(5)
            .all()
        ) if society else []

        return render_template(
            "member_dashboard.html",
            society=society,
            assignment=primary_assignment,
            assignments=assignments,
            latest_bill=latest_bill,
            latest_payment=latest_payment,
            bill_history=bill_history,
            active_notices=active_notices,
            my_complaints=my_complaints
        )

    return "Access Denied", 403


# -------------------------

# SOCIETY SETTINGS

# -------------------------



@app.route(

    "/society-settings",

    methods=["GET", "POST"]

)

@login_required

def society_settings():



    if current_user.role != "secretary":



        return "Access Denied", 403



    society = Society.query.first()



    if request.method == "POST":



        name = request.form.get(

            "name",

            ""

        ).strip()



        registration_number = request.form.get(

            "registration_number",

            ""

        ).strip()



        address = request.form.get(

            "address",

            ""

        ).strip()



        city = request.form.get(

            "city",

            ""

        ).strip()



        state = request.form.get(

            "state",

            ""

        ).strip()



        pincode = request.form.get(

            "pincode",

            ""

        ).strip()



        official_email = request.form.get(

            "official_email",

            ""

        ).strip()



        phone = request.form.get(

            "phone",

            ""

        ).strip()



        if not society:



            society = Society(

                name=name,

                registration_number=registration_number,

                address=address,

                city=city,

                state=state,

                pincode=pincode,

                official_email=official_email,

                phone=phone

            )



            db.session.add(society)



        else:



            society.name = name



            society.registration_number = (

                registration_number

            )



            society.address = address



            society.city = city



            society.state = state



            society.pincode = pincode



            society.official_email = (

                official_email

            )



            society.phone = phone

        logo_file = request.files.get("logo")
        if logo_file and logo_file.filename:
            ALLOWED_LOGO_EXTS = {"png", "jpg", "jpeg", "svg", "webp"}
            sec_filename = secure_filename(logo_file.filename)
            ext = sec_filename.rsplit(".", 1)[-1].lower() if "." in sec_filename else ""
            if ext not in ALLOWED_LOGO_EXTS:
                flash("Invalid logo format. Please upload PNG, JPG, JPEG, SVG, or WEBP.", "danger")
                return redirect(url_for("society_settings"))
            
            logo_file.seek(0, os.SEEK_END)
            size = logo_file.tell()
            logo_file.seek(0)
            if size > 2 * 1024 * 1024:
                flash("Logo file size exceeds the 2MB limit.", "danger")
                return redirect(url_for("society_settings"))

            logo_folder = os.path.join(app.root_path, "uploads", "logos")
            os.makedirs(logo_folder, exist_ok=True)
            unique_logo_name = f"{uuid.uuid4().hex}_{sec_filename}"
            logo_file.save(os.path.join(logo_folder, unique_logo_name))
            society.logo_filename = unique_logo_name

        db.session.commit()

        flash(
            "Society information saved successfully!"
        )

        return redirect(
            url_for("society_settings")
        )

    return render_template(
        "society_settings.html",
        society=society
    )


@app.route("/society/logo/<path:filename>")
def society_logo(filename):
    folder = os.path.join(app.root_path, "uploads", "logos")
    return send_from_directory(folder, filename)






# -------------------------

# BUILDINGS

# -------------------------



@app.route(

    "/buildings",

    methods=["GET", "POST"]

)

@login_required

def buildings():



    if current_user.role != "secretary":

        return "Access Denied", 403



    society = Society.query.first()



    if not society:

        flash(

            "Please setup society information first."

        )



        return redirect(

            url_for("society_settings")

        )



    if request.method == "POST":



        name = request.form.get(

            "name",

            ""

        ).strip().title()



        address = request.form.get(

            "address",

            ""

        ).strip()



        if not name:



            flash(

                "Building name is required."

            )



            return redirect(

                url_for("buildings")

            )



        existing_building = Building.query.filter_by(

            society_id=society.id,

            name=name

        ).first()



        if existing_building:



            flash(

                "Building with this name already exists."

            )



            return redirect(

                url_for("buildings")

            )



        new_building = Building(

            society_id=society.id,

            name=name,

            address=address,

            status=True

        )



        db.session.add(

            new_building

        )



        db.session.commit()



        flash(

            "Building added successfully!"

        )



        return redirect(

            url_for("buildings")

        )



    building_list = Building.query.filter_by(

        society_id=society.id

    ).order_by(

        Building.name.asc()

    ).all()



    return render_template(

        "buildings.html",

        society=society,

        buildings=building_list

    )

# -------------------------

# WINGS

# -------------------------



@app.route(

    "/buildings/<int:building_id>/wings",

    methods=["GET", "POST"]

)

@login_required

def wings(building_id):



    if current_user.role != "secretary":

        return "Access Denied", 403



    building = Building.query.get_or_404(

        building_id

    )



    society = Society.query.first()



    if not society:

        flash(

            "Please setup society information first."

        )



        return redirect(

            url_for("society_settings")

        )



    if building.society_id != society.id:

        return "Access Denied", 403



    if request.method == "POST":



        name = request.form.get(

            "name",

            ""

        ).strip()



        if not name:



            flash(

                "Wing name is required."

            )



            return redirect(

                url_for(

                    "wings",

                    building_id=building.id

                )

            )



        existing_wing = Wing.query.filter_by(

            building_id=building.id,

            name=name

        ).first()



        if existing_wing:



            flash(

                "Wing with this name already exists."

            )



            return redirect(

                url_for(

                    "wings",

                    building_id=building.id

                )

            )



        new_wing = Wing(

            building_id=building.id,

            name=name,

            status=True

        )



        db.session.add(

            new_wing

        )



        db.session.commit()



        flash(

            "Wing added successfully!"

        )



        return redirect(

            url_for(

                "wings",

                building_id=building.id

            )

        )



    wing_list = Wing.query.filter_by(

        building_id=building.id

    ).order_by(

        Wing.name.asc()

    ).all()



    return render_template(

        "wings.html",

        society=society,

        building=building,

        wings=wing_list

    )

# -------------------------

# FLOORS

# -------------------------



@app.route(

    "/wings/<int:wing_id>/floors",

    methods=["GET", "POST"]

)

@login_required

def floors(wing_id):



    if current_user.role != "secretary":

        return "Access Denied", 403



    wing = Wing.query.get_or_404(wing_id)



    building = wing.building



    society = Society.query.first()



    if not society:

        flash("Please setup society information first.")



        return redirect(

            url_for("society_settings")

        )



    if building.society_id != society.id:

        return "Access Denied", 403



    if request.method == "POST":



        floor_value = request.form.get(

            "floor_number",

            ""

        ).strip()



        if not floor_value:



            flash(

                "Floor number is required."

            )



            return redirect(

                url_for(

                    "floors",

                    wing_id=wing.id

                )

            )



        try:



            floor_number = int(

                floor_value

            )



        except ValueError:



            flash(

                "Floor number must be a valid number."

            )



            return redirect(

                url_for(

                    "floors",

                    wing_id=wing.id

                )

            )



        if floor_number < 0:



            flash(

                "Floor number cannot be negative."

            )



            return redirect(

                url_for(

                    "floors",

                    wing_id=wing.id

                )

            )



        existing_floor = Floor.query.filter_by(

            wing_id=wing.id,

            floor_number=floor_number

        ).first()



        if existing_floor:



            flash(

                "This floor already exists in the selected wing."

            )



            return redirect(

                url_for(

                    "floors",

                    wing_id=wing.id

                )

            )



        new_floor = Floor(

            wing_id=wing.id,

            floor_number=floor_number,

            status=True

        )



        db.session.add(

            new_floor

        )



        db.session.commit()



        flash(

            "Floor added successfully!"

        )



        return redirect(

            url_for(

                "floors",

                wing_id=wing.id

            )

        )



    floor_list = Floor.query.filter_by(

        wing_id=wing.id

    ).order_by(

        Floor.floor_number.asc()

    ).all()



    return render_template(

        "floors.html",

        society=society,

        building=building,

        wing=wing,

        floors=floor_list

    )

# -------------------------

# FLATS

# -------------------------



@app.route(

    "/floors/<int:floor_id>/flats",

    methods=["GET", "POST"]

)

@login_required

def flats(floor_id):



    if current_user.role != "secretary":

        return "Access Denied", 403



    floor = Floor.query.get_or_404(floor_id)



    wing = floor.wing

    building = wing.building



    society = Society.query.first()



    if not society:

        flash(

            "Please setup society information first."

        )



        return redirect(

            url_for("society_settings")

        )



    if building.society_id != society.id:

        return "Access Denied", 403



    if request.method == "POST":



        flat_number = request.form.get(

            "flat_number",

            ""

        ).strip().upper()



        flat_type = request.form.get(

            "flat_type",

            ""

        ).strip()



        carpet_area = request.form.get(

            "carpet_area",

            ""

        ).strip()



        built_up_area = request.form.get(

            "built_up_area",

            ""

        ).strip()



        maintenance_category = request.form.get(

            "maintenance_category",

            ""

        ).strip()



        ownership_status = request.form.get(

            "ownership_status",

            "Owned"

        ).strip()



        occupancy_status = request.form.get(

            "occupancy_status",

            "Vacant"

        ).strip()



        parking_information = request.form.get(

            "parking_information",

            ""

        ).strip()



        if not flat_number:



            flash(

                "Flat number is required."

            )



            return redirect(

                url_for(

                    "flats",

                    floor_id=floor.id

                )

            )



        existing_flat = Flat.query.filter_by(

            floor_id=floor.id,

            flat_number=flat_number

        ).first()



        if existing_flat:



            flash(

                "This flat already exists on the selected floor."

            )



            return redirect(

                url_for(

                    "flats",

                    floor_id=floor.id

                )

            )



        try:



            carpet_area_value = (

                float(carpet_area)

                if carpet_area

                else None

            )



            built_up_area_value = (

                float(built_up_area)

                if built_up_area

                else None

            )



        except ValueError:



            flash(

                "Carpet area and built-up area must be valid numbers."

            )



            return redirect(

                url_for(

                    "flats",

                    floor_id=floor.id

                )

            )



        new_flat = Flat(

            floor_id=floor.id,

            flat_number=flat_number,

            flat_type=flat_type,

            carpet_area=carpet_area_value,

            built_up_area=built_up_area_value,

            maintenance_category=maintenance_category,

            ownership_status=ownership_status,

            occupancy_status=occupancy_status,

            parking_information=parking_information,

            status=True

        )



        db.session.add(

            new_flat

        )



        db.session.commit()



        flash(

            "Flat added successfully!"

        )



        return redirect(

            url_for(

                "flats",

                floor_id=floor.id

            )

        )



    flat_list = Flat.query.filter_by(

        floor_id=floor.id

    ).order_by(

        Flat.flat_number.asc()

    ).all()



    return render_template(

        "flats.html",

        society=society,

        building=building,

        wing=wing,

        floor=floor,

        flats=flat_list

    )            

# -------------------------

# MEMBERS

# -------------------------



@app.route("/members")

@login_required

def members():



    if current_user.role != "secretary":

        return "Access Denied", 403



    search = request.args.get(

        "q",

        ""

    ).strip()



    query = User.query.filter_by(

        role="member"

    )



    if search:



        query = query.filter(

            db.or_(

                User.full_name.ilike(

                    f"%{search}%"

                ),

                User.email.ilike(

                    f"%{search}%"

                ),

                User.mobile.ilike(

                    f"%{search}%"

                )

            )

        )



    member_list = query.order_by(

        User.created_at.desc()

    ).all()



    total_members = User.query.filter_by(

        role="member"

    ).count()



    active_members = User.query.filter_by(

        role="member",

        is_active=True

    ).count()



    inactive_members = User.query.filter_by(

        role="member",

        is_active=False

    ).count()



    return render_template(

        "members.html",

        members=member_list,

        total_members=total_members,

        active_members=active_members,

        inactive_members=inactive_members,

        search=search

    )

# -------------------------

# ASSIGN MEMBER TO FLAT

# -------------------------



@app.route(

    "/members/<int:user_id>/assign-flat",

    methods=["GET", "POST"]

)

@login_required

def assign_member_flat(user_id):



    if current_user.role != "secretary":

        return "Access Denied", 403



    member = User.query.filter_by(

        id=user_id,

        role="member"

    ).first_or_404()



    society = Society.query.first()



    if not society:

        flash(

            "Please setup society information first."

        )



        return redirect(

            url_for("society_settings")

        )



    flats = (

        Flat.query

        .join(

            Floor,

            Flat.floor_id == Floor.id

        )

        .join(

            Wing,

            Floor.wing_id == Wing.id

        )

        .join(

            Building,

            Wing.building_id == Building.id

        )

        .filter(

            Building.society_id == society.id,

            Flat.status.is_(True)

        )

        .order_by(

            Building.name.asc(),

            Wing.name.asc(),

            Floor.floor_number.asc(),

            Flat.flat_number.asc()

        )

        .all()

    )



    if request.method == "POST":



        flat_id = request.form.get(

            "flat_id",

            ""

        )



        relation_type = request.form.get(

            "relation_type",

            "Owner"

        ).strip()



        is_primary = (

            request.form.get("is_primary")

            == "on"

        )



        if not flat_id:



            flash(

                "Please select a flat."

            )



            return redirect(

                url_for(

                    "assign_member_flat",

                    user_id=member.id

                )

            )



        flat = db.session.get(

            Flat,

            int(flat_id)

        )



        if not flat:



            flash(

                "Selected flat does not exist."

            )



            return redirect(

                url_for(

                    "assign_member_flat",

                    user_id=member.id

                )

            )



        existing_assignment = (

            FlatMember.query.filter_by(

                user_id=member.id,

                flat_id=flat.id,

                relation_type=relation_type

            ).first()

        )



        if existing_assignment:



            flash(

                "This member is already assigned to this flat."

            )



            return redirect(

                url_for(

                    "assign_member_flat",

                    user_id=member.id

                )

            )



        if is_primary:



            existing_primary = (

                FlatMember.query.filter_by(

                    user_id=member.id,

                    is_primary=True,

                    is_active=True

                ).all()

            )



            for assignment in existing_primary:

                assignment.is_primary = False



        assignment = FlatMember(

            user_id=member.id,

            flat_id=flat.id,

            relation_type=relation_type,

            is_primary=is_primary,

            is_active=True

        )



        db.session.add(

            assignment

        )



        flat.occupancy_status = "Occupied"



        db.session.commit()



        flash(

            f"{member.full_name} assigned to Flat {flat.flat_number} successfully!"

        )



        return redirect(

            url_for("members")

        )



    current_assignments = (

        FlatMember.query.filter_by(

            user_id=member.id,

            is_active=True

        ).all()

    )



    return render_template(

        "assign_flat.html",

        member=member,

        flats=flats,

        assignments=current_assignments,

        society=society

    )    

# -------------------------

# ADD MEMBER

# -------------------------



@app.route(

    "/members/add",

    methods=["GET", "POST"]

)

@login_required

def add_member():



    if current_user.role != "secretary":

        return "Access Denied", 403



    if request.method == "POST":



        full_name = request.form.get(

            "full_name",

            ""

        ).strip()



        email = request.form.get(

            "email",

            ""

        ).strip().lower()



        mobile = request.form.get(

            "mobile",

            ""

        ).strip()



        password = request.form.get(

            "password",

            ""

        )



        if not full_name:

            flash("Member name is required.")

            return redirect(

                url_for("add_member")

            )



        if not email:

            flash("Email is required.")

            return redirect(

                url_for("add_member")

            )



        if not mobile:

            flash("Mobile number is required.")

            return redirect(

                url_for("add_member")

            )



        if len(password) < 8:

            flash(

                "Password must contain at least 8 characters."

            )



            return redirect(

                url_for("add_member")

            )



        existing_email = User.query.filter_by(

            email=email

        ).first()



        if existing_email:



            flash(

                "This email is already registered."

            )



            return redirect(

                url_for("add_member")

            )



        existing_mobile = User.query.filter_by(

            mobile=mobile

        ).first()



        if existing_mobile:



            flash(

                "This mobile number is already registered."

            )



            return redirect(

                url_for("add_member")

            )



        new_member = User(
            full_name=full_name,
            email=email,
            mobile=mobile,
            password_hash=generate_password_hash(password),
            role="member",
            approval_status="approved",
            must_change_password=True,
            is_active=True
        )



        db.session.add(

            new_member

        )



        db.session.commit()



        flash(

            "Member created successfully!"

        )



        return redirect(

            url_for("members")

        )



    return render_template(

        "add_member.html"

    )

# -------------------------

# MEMBER STATUS

# -------------------------



@app.route(

    "/members/<int:user_id>/toggle-status",

    methods=["POST"]

)

@login_required

def toggle_member_status(user_id):



    if current_user.role != "secretary":

        return "Access Denied", 403



    member = User.query.filter_by(

        id=user_id,

        role="member"

    ).first_or_404()



    member.is_active = not member.is_active



    db.session.commit()



    if member.is_active:



        flash(

            f"{member.full_name} activated successfully."

        )



    else:



        flash(

            f"{member.full_name} deactivated successfully."

        )



    return redirect(

        url_for("members")

    )



# -------------------------

# MAINTENANCE COMPONENTS

# -------------------------



@app.route(

    "/maintenance/components",

    methods=["GET", "POST"]

)

@login_required

def maintenance_components():



    if current_user.role != "secretary":

        return "Access Denied", 403



    society = Society.query.first()



    if not society:



        flash(

            "Please setup society information first."

        )



        return redirect(

            url_for("society_settings")

        )



    if request.method == "POST":



        name = request.form.get(

            "name",

            ""

        ).strip().title()



        description = request.form.get(

            "description",

            ""

        ).strip()



        purpose = request.form.get(

            "purpose",

            ""

        ).strip()



        calculation_method = request.form.get(

            "calculation_method",

            "Fixed"

        ).strip()



        amount_text = request.form.get(

            "amount",

            "0"

        ).strip()



        applicable_to = request.form.get(

            "applicable_to",

            "All Flats"

        ).strip()



        effective_date_text = request.form.get(

            "effective_date",

            ""

        ).strip()



        if not name:



            flash(

                "Component name is required."

            )



            return redirect(

                url_for("maintenance_components")

            )



        allowed_methods = [

            "Fixed",

            "Per Square Foot",

            "Percentage",

            "Quantity × Rate",

            "Manual"

        ]



        if calculation_method not in allowed_methods:



            flash(

                "Invalid calculation method."

            )



            return redirect(

                url_for("maintenance_components")

            )



        try:



            amount = Decimal(

                amount_text

            )



            if amount < 0:

                raise InvalidOperation



        except (InvalidOperation, ValueError):



            flash(

                "Please enter a valid amount."

            )



            return redirect(

                url_for("maintenance_components")

            )



        try:



            effective_date = datetime.strptime(

                effective_date_text,

                "%Y-%m-%d"

            ).date()



        except ValueError:



            flash(

                "Please select a valid effective date."

            )



            return redirect(

                url_for("maintenance_components")

            )



        existing_component = (

            MaintenanceComponent.query.filter_by(

                society_id=society.id,

                name=name

            ).first()

        )



        if existing_component:



            flash(

                "Maintenance component already exists."

            )



            return redirect(

                url_for("maintenance_components")

            )



        component = MaintenanceComponent(

            society_id=society.id,

            name=name,

            description=description,

            purpose=purpose,

            calculation_method=calculation_method,

            amount=amount,

            applicable_to=applicable_to,

            effective_date=effective_date,

            status=True

        )



        db.session.add(

            component

        )



        db.session.commit()



        flash(

            "Maintenance component added successfully!"

        )



        return redirect(

            url_for("maintenance_components")

        )



    components = (

        MaintenanceComponent.query

        .filter_by(

            society_id=society.id

        )

        .order_by(

            MaintenanceComponent.name.asc()

        )

        .all()

    )



    return render_template(

        "maintenance_components.html",

        society=society,

        components=components

    )



# -------------------------

# COMPONENT STATUS

# -------------------------



@app.route(

    "/maintenance/components/<int:component_id>/toggle",

    methods=["POST"]

)

@login_required

def toggle_maintenance_component(component_id):



    if current_user.role != "secretary":

        return "Access Denied", 403



    component = MaintenanceComponent.query.get_or_404(

        component_id

    )



    component.status = not component.status



    db.session.commit()



    if component.status:



        flash(

            f"{component.name} activated."

        )



    else:



        flash(

            f"{component.name} disabled."

        )



    return redirect(

        url_for("maintenance_components")

    )

# -------------------------

# GENERATE MAINTENANCE BILLS

# -------------------------



@app.route(

    "/maintenance/bills/generate",

    methods=["GET", "POST"]

)

@login_required

def generate_maintenance_bills():



    if current_user.role != "secretary":

        return "Access Denied", 403



    society = Society.query.first()



    if not society:

        flash("Please setup society information first.")

        return redirect(url_for("society_settings"))



    current_date = datetime.now()



    selected_year = current_date.year

    selected_month = current_date.month



    if request.method == "POST":



        year_text = request.form.get(

            "bill_year",

            ""

        ).strip()



        month_text = request.form.get(

            "bill_month",

            ""

        ).strip()



        due_date_text = request.form.get(

            "due_date",

            ""

        ).strip()



        try:

            selected_year = int(year_text)

            selected_month = int(month_text)



        except ValueError:

            flash("Please select a valid month and year.")

            return redirect(

                url_for("generate_maintenance_bills")

            )



        if selected_month < 1 or selected_month > 12:

            flash("Invalid billing month.")

            return redirect(

                url_for("generate_maintenance_bills")

            )



        if selected_year < 2000 or selected_year > 2100:

            flash("Invalid billing year.")

            return redirect(

                url_for("generate_maintenance_bills")

            )



        bill_date = datetime(

            selected_year,

            selected_month,

            1

        ).date()



        last_day = calendar.monthrange(

            selected_year,

            selected_month

        )[1]



        month_end_date = datetime(

            selected_year,

            selected_month,

            last_day

        ).date()



        try:

            due_date = datetime.strptime(

                due_date_text,

                "%Y-%m-%d"

            ).date()



        except ValueError:

            flash("Please select a valid due date.")

            return redirect(

                url_for("generate_maintenance_bills")

            )



        if due_date < bill_date:

            flash(

                "Due date cannot be before the billing month."

            )

            return redirect(

                url_for("generate_maintenance_bills")

            )



        components = (

            MaintenanceComponent.query

            .filter(

                MaintenanceComponent.society_id == society.id,

                MaintenanceComponent.status.is_(True),

                MaintenanceComponent.effective_date <= month_end_date

            )

            .order_by(

                MaintenanceComponent.name.asc()

            )

            .all()

        )



        if not components:

            flash(

                "No active maintenance components found for this month."

            )

            return redirect(

                url_for("generate_maintenance_bills")

            )



        unsupported_components = []



        for component in components:



            if component.calculation_method not in [

                "Fixed",

                "Per Square Foot"

            ]:

                unsupported_components.append(

                    component.name

                )



            if component.applicable_to == "Manual":

                unsupported_components.append(

                    component.name

                )



        if unsupported_components:



            names = ", ".join(

                sorted(set(unsupported_components))

            )



            flash(

                "Bill generation stopped. "

                "These components need additional configuration: "

                + names

            )



            return redirect(

                url_for("generate_maintenance_bills")

            )



        flats = (

            Flat.query

            .join(

                Floor,

                Flat.floor_id == Floor.id

            )

            .join(

                Wing,

                Floor.wing_id == Wing.id

            )

            .join(

                Building,

                Wing.building_id == Building.id

            )

            .filter(

                Building.society_id == society.id,

                Flat.status.is_(True)

            )

            .order_by(

                Flat.flat_number.asc()

            )

            .all()

        )



        if not flats:

            flash("No active flats found.")

            return redirect(

                url_for("generate_maintenance_bills")

            )



        for flat in flats:



            for component in components:



                applies = False



                if component.applicable_to == "All Flats":

                    applies = True



                elif (

                    component.applicable_to

                    == flat.maintenance_category

                ):

                    applies = True



                if (

                    applies

                    and component.calculation_method

                    == "Per Square Foot"

                ):

                    if (

                        flat.carpet_area is None

                        or flat.carpet_area <= 0

                    ):

                        flash(

                            f"Flat {flat.flat_number} "

                            "does not have a valid carpet area. "

                            f"Required for {component.name}."

                        )



                        return redirect(

                            url_for(

                                "generate_maintenance_bills"

                            )

                        )



        generated_count = 0

        skipped_count = 0



        try:



            for flat in flats:



                existing_bill = (

                    MaintenanceBill.query

                    .filter_by(

                        flat_id=flat.id,

                        bill_year=selected_year,

                        bill_month=selected_month

                    )

                    .first()

                )



                if existing_bill:

                    skipped_count += 1

                    continue



                subtotal = Decimal("0.00")

                bill_items = []



                for component in components:



                    applies = False



                    if component.applicable_to == "All Flats":

                        applies = True



                    elif (

                        component.applicable_to

                        == flat.maintenance_category

                    ):

                        applies = True



                    if not applies:

                        continue



                    rate = Decimal(

                        str(component.amount)

                    )



                    quantity = Decimal("1.00")



                    if component.calculation_method == "Fixed":



                        amount = rate



                    elif (

                        component.calculation_method

                        == "Per Square Foot"

                    ):



                        quantity = Decimal(

                            str(flat.carpet_area)

                        )



                        amount = rate * quantity



                    else:

                        continue



                    amount = amount.quantize(

                        Decimal("0.01")

                    )



                    subtotal += amount



                    bill_items.append({

                        "component": component,

                        "rate": rate,

                        "quantity": quantity,

                        "amount": amount

                    })



                subtotal = subtotal.quantize(

                    Decimal("0.01")

                )



                if subtotal == Decimal("0.00"):

                    skipped_count += 1

                    continue



                bill = MaintenanceBill(

                    society_id=society.id,

                    flat_id=flat.id,

                    bill_year=selected_year,

                    bill_month=selected_month,

                    bill_date=bill_date,

                    due_date=due_date,

                    subtotal=subtotal,

                    penalty_amount=Decimal("0.00"),

                    total_amount=subtotal,

                    paid_amount=Decimal("0.00"),

                    balance_amount=subtotal,

                    status="Unpaid"

                )



                db.session.add(bill)

                db.session.flush()



                for item in bill_items:



                    component = item["component"]



                    bill_item = MaintenanceBillItem(

                        bill_id=bill.id,

                        component_id=component.id,

                        component_name=component.name,

                        calculation_method=(

                            component.calculation_method

                        ),

                        rate=item["rate"],

                        quantity=item["quantity"],

                        amount=item["amount"]

                    )



                    db.session.add(bill_item)



                generated_count += 1



            db.session.commit()
            AuditLog.log(
                society_id=society.id,
                action="GENERATE_BILLS",
                user_id=current_user.id,
                details=f"Generated {generated_count} maintenance bills for {calendar.month_name[selected_month]} {selected_year}"
            )

        except Exception:



            db.session.rollback()



            flash(

                "Bill generation failed. "

                "No bills were saved."

            )



            return redirect(

                url_for("generate_maintenance_bills")

            )



        month_name = calendar.month_name[

            selected_month

        ]



        flash(

            f"{generated_count} bill(s) generated "

            f"for {month_name} {selected_year}. "

            f"{skipped_count} bill(s) skipped."

        )



        return redirect(

            url_for("generate_maintenance_bills")

        )



    bill_count = (

        MaintenanceBill.query

        .filter_by(

            society_id=society.id,

            bill_year=selected_year,

            bill_month=selected_month

        )

        .count()

    )



    return render_template(

        "generate_maintenance_bills.html",

        society=society,

        current_year=selected_year,

        current_month=selected_month,

        bill_count=bill_count

    )

# -------------------------

# MAINTENANCE BILL LIST

# -------------------------



@app.route("/maintenance/bills")

@login_required

def maintenance_bills():



    if current_user.role != "secretary":

        return "Access Denied", 403



    society = Society.query.first()



    if not society:

        flash("Please setup society information first.")

        return redirect(url_for("society_settings"))



    current_date = datetime.now()



    try:

        selected_month = int(

            request.args.get(

                "month",

                current_date.month

            )

        )



        selected_year = int(

            request.args.get(

                "year",

                current_date.year

            )

        )



    except ValueError:



        selected_month = current_date.month

        selected_year = current_date.year



    if selected_month < 1 or selected_month > 12:

        selected_month = current_date.month



    bills = (

        MaintenanceBill.query

        .filter_by(

            society_id=society.id,

            bill_month=selected_month,

            bill_year=selected_year

        )

        .order_by(

            MaintenanceBill.id.desc()

        )

        .all()

    )



    total_amount = sum(

        (

            bill.total_amount

            for bill in bills

        ),

        Decimal("0.00")

    )



    total_paid = sum(

        (

            bill.paid_amount

            for bill in bills

        ),

        Decimal("0.00")

    )



    total_balance = sum(

        (

            bill.balance_amount

            for bill in bills

        ),

        Decimal("0.00")

    )



    return render_template(

        "maintenance_bills.html",

        society=society,

        bills=bills,

        selected_month=selected_month,

        selected_year=selected_year,

        month_name=calendar.month_name[selected_month],

        total_amount=total_amount,

        total_paid=total_paid,

        total_balance=total_balance

    )
# -------------------------
# MAINTENANCE BILL DETAIL
# -------------------------

@app.route("/maintenance/bills/<int:bill_id>")
@login_required
def maintenance_bill_detail(bill_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:
        flash("Please setup society information first.")
        return redirect(
            url_for("society_settings")
        )

    bill = MaintenanceBill.query.get_or_404(
        bill_id
    )

    if bill.society_id != society.id:
        return "Access Denied", 403

    primary_member = (
        FlatMember.query
        .filter_by(
            flat_id=bill.flat_id,
            is_active=True,
            is_primary=True
        )
        .first()
    )

    payments = (
        MaintenancePayment.query
        .filter_by(
            bill_id=bill.id
        )
        .order_by(
            MaintenancePayment.payment_date.desc(),
            MaintenancePayment.id.desc()
        )
        .all()
    )
    financial_accounts = (
        FinancialAccount.query
        .filter_by(
            society_id=society.id,
            status=True
        )
        .order_by(
            FinancialAccount.account_type.asc(),
            FinancialAccount.name.asc()
        )
        .all()
    )
    return render_template(
        "maintenance_bill_detail.html",
        society=society,
        bill=bill,
        primary_member=primary_member,
        payments=payments,
        financial_accounts=financial_accounts,
        month_name=calendar.month_name[bill.bill_month]
    )


# -------------------------
# RECORD MAINTENANCE PAYMENT
# -------------------------

@app.route(
    "/maintenance/bills/<int:bill_id>/payment",
    methods=["POST"]
)
@login_required
def record_maintenance_payment(bill_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:
        flash("Please setup society information first.")
        return redirect(
            url_for("society_settings")
        )

    bill = MaintenanceBill.query.get_or_404(
        bill_id
    )

    if bill.society_id != society.id:
        return "Access Denied", 403

    amount_text = request.form.get(
        "amount",
        ""
    ).strip()

    payment_date_text = request.form.get(
        "payment_date",
        ""
    ).strip()

    payment_mode = request.form.get(
        "payment_mode",
        ""
    ).strip()
    account_id_text = request.form.get(
        "account_id",
        ""
    ).strip()

    reference_number = request.form.get(
        "reference_number",
        ""
    ).strip()

    notes = request.form.get(
        "notes",
        ""
    ).strip()

    # -------------------------
    # AMOUNT VALIDATION
    # -------------------------

    try:

        amount = Decimal(
            amount_text
        ).quantize(
            Decimal("0.01")
        )

    except (InvalidOperation, ValueError):

        flash(
            "Please enter a valid payment amount."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )

    if amount <= Decimal("0.00"):

        flash(
            "Payment amount must be greater than zero."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )

    current_balance = Decimal(
        str(bill.balance_amount)
    )

    if amount > current_balance:

        flash(
            "Payment amount cannot be greater than outstanding balance."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )

    # -------------------------
    # PAYMENT DATE VALIDATION
    # -------------------------

    try:

        payment_date = datetime.strptime(
            payment_date_text,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        flash(
            "Please select a valid payment date."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )

    if payment_date > datetime.now().date():

        flash(
            "Payment date cannot be in the future."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )

    # -------------------------
    # PAYMENT MODE
    # -------------------------

    allowed_modes = [
        "Cash",
        "UPI",
        "Bank Transfer",
        "Cheque"
    ]

    if payment_mode not in allowed_modes:

        flash(
            "Please select a valid payment mode."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )
        # -------------------------
    # FINANCIAL ACCOUNT
    # -------------------------

    try:

        account_id = int(
            account_id_text
        )

    except (ValueError, TypeError):

        flash(
            "Please select a valid financial account."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )


    financial_account = (
        FinancialAccount.query
        .filter_by(
            id=account_id,
            society_id=society.id,
            status=True
        )
        .first()
    )

    if not financial_account:

        flash(
            "Selected financial account is not available."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )


    # Cash must go to Cash Account
    if (
        payment_mode == "Cash"
        and financial_account.account_type != "Cash"
    ):

        flash(
            "Cash payment must be deposited into Cash Account."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )


    # Non-cash payments must go to Bank Account
    if (
        payment_mode != "Cash"
        and financial_account.account_type != "Bank"
    ):

        flash(
            "UPI, Bank Transfer and Cheque payments "
            "must be deposited into a Bank Account."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )
    # -------------------------
    # CREATE PAYMENT
    # -------------------------

    payment = MaintenancePayment(
        bill_id=bill.id,
        amount=amount,
        payment_date=payment_date,
        payment_mode=payment_mode,
        reference_number=(
            reference_number
            if reference_number
            else None
        ),
        notes=(
            notes
            if notes
            else None
        ),
        recorded_by=current_user.id
    )

    db.session.add(payment)

    db.session.flush()
        # -------------------------
    # FINANCIAL TRANSACTION
    # -------------------------

    financial_transaction = FinancialTransaction(
        society_id=society.id,
        account_id=financial_account.id,
        transaction_date=payment_date,
        transaction_type="Income",
        direction="Credit",
        amount=amount,
        reference_number=(
            reference_number
            if reference_number
            else None
        ),
        description=(
            f"Maintenance payment for "
            f"Bill #{bill.id} - "
            f"{calendar.month_name[bill.bill_month]} "
            f"{bill.bill_year}"
        ),
        source_type="MaintenancePayment",
        source_id=payment.id,
        created_by=current_user.id
    )

    db.session.add(
        financial_transaction
    )

    receipt_number = (
        f"REC-{payment_date.year}-{payment.id:06d}"
    )

    receipt = PaymentReceipt(
        payment_id=payment.id,
        receipt_number=receipt_number,
        generated_by=current_user.id
    )

    db.session.add(receipt)
    

    # -------------------------
    # UPDATE BILL
    # -------------------------

    old_paid = Decimal(
        str(bill.paid_amount)
    )

    new_paid = (
        old_paid + amount
    ).quantize(
        Decimal("0.01")
    )

    total_amount = Decimal(
        str(bill.total_amount)
    )

    new_balance = (
        total_amount - new_paid
    ).quantize(
        Decimal("0.01")
    )

    bill.paid_amount = new_paid
    bill.balance_amount = new_balance

    if new_balance <= Decimal("0.00"):

        bill.balance_amount = Decimal(
            "0.00"
        )

        bill.status = "Paid"

    else:

        bill.status = "Partially Paid"

    try:

        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="RECORD_PAYMENT",
            user_id=current_user.id,
            entity_type="MaintenancePayment",
            entity_id=payment.id,
            details=f"Recorded payment of ₹{amount} for Bill #{bill.id} via {payment_mode} (Receipt #{receipt.receipt_number})"
        )

    except Exception:

        db.session.rollback()

        flash(
            "Payment could not be recorded."
        )

        return redirect(
            url_for(
                "maintenance_bill_detail",
                bill_id=bill.id
            )
        )

    flash(
        "Payment recorded successfully!"
    )

    return redirect(
        url_for(
            "maintenance_bill_detail",
            bill_id=bill.id
        )
    )
# -------------------------
# PAYMENT RECEIPT
# -------------------------

@app.route(
    "/maintenance/payments/<int:payment_id>/receipt"
)
@login_required
def payment_receipt(payment_id):

    payment = MaintenancePayment.query.get_or_404(
        payment_id
    )

    bill = payment.bill

    society = Society.query.first()

    if not society:
        return "Society not found", 404

    if bill.society_id != society.id:
        return "Access Denied", 403

    # -------------------------
    # ACCESS CONTROL
    # -------------------------

    if current_user.role == "secretary":

        pass

    elif current_user.role == "member":

        assignment = FlatMember.query.filter_by(
            user_id=current_user.id,
            flat_id=bill.flat_id,
            is_active=True
        ).first()

        if not assignment:
            return "Access Denied", 403

    else:

        return "Access Denied", 403

    # -------------------------
    # RECEIPT
    # -------------------------

    receipt = PaymentReceipt.query.filter_by(
        payment_id=payment.id
    ).first()

    if not receipt:

        receipt_number = (
            f"REC-{payment.payment_date.year}-{payment.id:06d}"
        )

        receipt = PaymentReceipt(
            payment_id=payment.id,
            receipt_number=receipt_number,
            generated_by=payment.recorded_by
        )

        db.session.add(receipt)
        db.session.commit()

    primary_member = (
        FlatMember.query
        .filter_by(
            flat_id=bill.flat_id,
            is_active=True,
            is_primary=True
        )
        .first()
    )
    
    return render_template(
        "payment_receipt.html",
        society=society,
        payment=payment,
        bill=bill,
        receipt=receipt,
        primary_member=primary_member,
        month_name=calendar.month_name[bill.bill_month]
    )

# -------------------------

# MEMBER BILL DETAIL

# -------------------------



@app.route("/my/bills/<int:bill_id>")

@login_required

def member_bill_detail(bill_id):



    if current_user.role != "member":

        return "Access Denied", 403



    bill = MaintenanceBill.query.get_or_404(

        bill_id

    )



    assignment = FlatMember.query.filter_by(

        user_id=current_user.id,

        flat_id=bill.flat_id,

        is_active=True

    ).first()



    if not assignment:
        society_obj = Society.query.first()
        AuditLog.log(
            society_obj.id if society_obj else None,
            "UNAUTHORIZED_ACCESS_ATTEMPT",
            user_id=current_user.id,
            entity_type="MaintenanceBill",
            entity_id=bill.id,
            details=f"Member {current_user.email} attempted unauthorized access to bill #{bill.id} of flat #{bill.flat_id}",
            ip_address=request.remote_addr
        )
        abort(403)



    society = Society.query.first()


    payments = (
        MaintenancePayment.query
        .filter_by(
            bill_id=bill.id
        )
        .order_by(
            MaintenancePayment.payment_date.desc(),
            MaintenancePayment.id.desc()
        )
        .all()
    )
    return render_template(
        "member_bill_detail.html",
        society=society,
        bill=bill,
        assignment=assignment,
        payments=payments,
        month_name=calendar.month_name[bill.bill_month]
    )
# -------------------------
# EXPENSE CATEGORIES
# -------------------------

@app.route("/expenses/categories")
@login_required
def expense_categories():

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:

        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )

    categories = (
        ExpenseCategory.query
        .filter_by(
            society_id=society.id
        )
        .order_by(
            ExpenseCategory.name.asc()
        )
        .all()
    )

    return render_template(
        "expense_categories.html",
        society=society,
        categories=categories
    )
    # -------------------------
# ADD EXPENSE CATEGORY
# -------------------------

@app.route(
    "/expenses/categories/add",
    methods=["POST"]
)
@login_required
def add_expense_category():

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:

        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )

    name = request.form.get(
        "name",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    if not name:
        flash("Expense category name is required.")
        return redirect(url_for("expense_categories"))

    if len(name) > 100:
        flash("Category name cannot exceed 100 characters.")
        return redirect(url_for("expense_categories"))

    duplicate_category = (
        ExpenseCategory.query
        .filter(
            ExpenseCategory.society_id == society.id,
            db.func.lower(ExpenseCategory.name) == name.lower()
        )
        .first()
    )

    if duplicate_category:
        flash("This expense category already exists.")
        return redirect(url_for("expense_categories"))

    category = ExpenseCategory(
        society_id=society.id,
        name=name,
        description=description or None,
        status=True
    )

    db.session.add(category)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Expense category could not be created.")
        return redirect(url_for("expense_categories"))

    flash("Expense category added successfully!")
    return redirect(url_for("expense_categories"))
# -------------------------
# TOGGLE EXPENSE CATEGORY
# -------------------------

@app.route(
    "/expenses/categories/<int:category_id>/toggle",
    methods=["POST"]
)
@login_required
def toggle_expense_category(category_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:

        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )

    category = (
        ExpenseCategory.query
        .filter_by(
            id=category_id,
            society_id=society.id
        )
        .first_or_404()
    )

    category.status = not category.status

    try:
        db.session.commit()

    except Exception:
        db.session.rollback()

        flash(
            "Expense category status could not be changed."
        )

        return redirect(
            url_for("expense_categories")
        )

    if category.status:

        flash(
            f"{category.name} activated successfully."
        )

    else:

        flash(
            f"{category.name} deactivated successfully."
        )

    return redirect(
        url_for("expense_categories")
    )
    
# -------------------------
# EXPENSE MANAGEMENT
# -------------------------

@app.route("/expenses")
@login_required
def expenses():

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    expense_list = (
        Expense.query
        .filter_by(society_id=society.id)
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
        .all()
    )

    active_categories = (
        ExpenseCategory.query
        .filter_by(society_id=society.id, status=True)
        .order_by(ExpenseCategory.name.asc())
        .all()
    )

    active_accounts = (
        FinancialAccount.query
        .filter_by(society_id=society.id, status=True)
        .order_by(FinancialAccount.account_type.asc(), FinancialAccount.name.asc())
        .all()
    )

    registered_vendors = (
        Vendor.query
        .filter_by(society_id=society.id, status=True)
        .order_by(Vendor.name.asc())
        .all()
    )

    total_expense_amount = sum((Decimal(str(e.amount)) for e in expense_list), Decimal("0.00"))
    paid_expense_amount = sum((Decimal(str(e.amount)) for e in expense_list if e.payment_status == "Paid"), Decimal("0.00"))
    approved_unpaid_amount = sum((Decimal(str(e.amount)) for e in expense_list if e.approval_status == "Approved" and e.payment_status != "Paid"), Decimal("0.00"))
    pending_count = sum(1 for e in expense_list if e.approval_status == "Pending Approval")

    return render_template(
        "expenses.html",
        society=society,
        expenses=expense_list,
        categories=active_categories,
        accounts=active_accounts,
        registered_vendors=registered_vendors,
        total_expense_amount=total_expense_amount,
        paid_expense_amount=paid_expense_amount,
        approved_unpaid_amount=approved_unpaid_amount,
        pending_count=pending_count
    )


# -------------------------
# ADD EXPENSE
# -------------------------

@app.route(
    "/expenses/add",
    methods=["POST"]
)
@login_required
def add_expense():

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    category_id_text = request.form.get("category_id", "").strip()
    vendor_name = request.form.get("vendor_name", "").strip()
    amount_text = request.form.get("amount", "").strip()
    expense_date_text = request.form.get("expense_date", "").strip()
    invoice_reference = request.form.get("invoice_reference", "").strip()
    notes = request.form.get("notes", "").strip()

    try:
        category_id = int(category_id_text)
    except (ValueError, TypeError):
        flash("Please select a valid expense category.")
        return redirect(url_for("expenses"))

    category = (
        ExpenseCategory.query
        .filter_by(id=category_id, society_id=society.id, status=True)
        .first()
    )

    if not category:
        flash("Selected expense category is not available.")
        return redirect(url_for("expenses"))

    if not vendor_name:
        flash("Vendor name is required.")
        return redirect(url_for("expenses"))

    if len(vendor_name) > 150:
        flash("Vendor name is too long.")
        return redirect(url_for("expenses"))

    try:
        amount = Decimal(amount_text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        flash("Please enter a valid expense amount.")
        return redirect(url_for("expenses"))

    if amount <= Decimal("0.00"):
        flash("Expense amount must be greater than zero.")
        return redirect(url_for("expenses"))

    try:
        expense_date = datetime.strptime(expense_date_text, "%Y-%m-%d").date()
    except ValueError:
        flash("Please select a valid expense date.")
        return redirect(url_for("expenses"))

    if expense_date > datetime.now().date():
        flash("Expense date cannot be in the future.")
        return redirect(url_for("expenses"))

    if len(invoice_reference) > 150:
        flash("Invoice / reference number is too long.")
        return redirect(url_for("expenses"))

    if len(notes) > 2000:
        flash("Expense notes cannot exceed 2000 characters.")
        return redirect(url_for("expenses"))

    # Duplicate prevention check
    duplicate_expense = (
        Expense.query.filter(
            Expense.society_id == society.id,
            Expense.vendor_name == vendor_name,
            Expense.amount == amount,
            Expense.expense_date == expense_date,
            Expense.approval_status.in_(["Pending Approval", "Approved"])
        ).first()
    )

    if duplicate_expense:
        flash(f"A matching expense #{duplicate_expense.id} of ₹{amount} for {vendor_name} on {expense_date} already exists.")
        return redirect(url_for("expenses"))

    # Handle optional receipt attachment upload
    receipt_file = request.files.get("receipt_file")
    attachment_path = None
    if receipt_file and receipt_file.filename:
        allowed_exts = {'pdf', 'png', 'jpg', 'jpeg'}
        ext = receipt_file.filename.rsplit('.', 1)[-1].lower() if '.' in receipt_file.filename else ''
        if ext in allowed_exts:
            upload_dir = os.path.join(app.root_path, "static", "uploads", "expenses")
            os.makedirs(upload_dir, exist_ok=True)
            filename = f"exp_{society.id}_{uuid.uuid4().hex[:10]}.{ext}"
            filepath = os.path.join(upload_dir, filename)
            receipt_file.save(filepath)
            attachment_path = f"uploads/expenses/{filename}"
        else:
            flash("Invalid file format for receipt. Allowed: PDF, PNG, JPG, JPEG.")
            return redirect(url_for("expenses"))

    expense = Expense(
        society_id=society.id,
        category_id=category.id,
        vendor_name=vendor_name,
        amount=amount,
        expense_date=expense_date,
        invoice_reference=invoice_reference or None,
        notes=notes or None,
        attachment_path=attachment_path,
        approval_status="Pending Approval",
        payment_status="Unpaid",
        created_by=current_user.id
    )

    db.session.add(expense)

    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="RECORD_EXPENSE",
            user_id=current_user.id,
            entity_type="Expense",
            entity_id=expense.id,
            details=f"Created expense voucher of ₹{amount} for {vendor_name} ({category.name})"
        )
    except Exception:
        db.session.rollback()
        flash("Expense could not be created.")
        return redirect(url_for("expenses"))

    flash("Expense created successfully and sent for approval.")
    return redirect(url_for("expenses"))


# -------------------------
# APPROVE EXPENSE
# -------------------------

@app.route(
    "/expenses/<int:expense_id>/approve",
    methods=["POST"]
)
@login_required
def approve_expense(expense_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    expense = (
        Expense.query
        .filter_by(
            id=expense_id,
            society_id=society.id
        )
        .first_or_404()
    )

    if expense.approval_status != "Pending Approval":
        flash("Only pending expenses can be approved.")
        return redirect(url_for("expenses"))

    expense.approval_status = "Approved"
    expense.approved_by = current_user.id
    expense.approved_at = datetime.now()

    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="APPROVE_EXPENSE",
            user_id=current_user.id,
            entity_type="Expense",
            entity_id=expense.id,
            details=f"Approved expense #{expense.id} of ₹{expense.amount} for {expense.vendor_name}"
        )
    except Exception:
        db.session.rollback()
        flash("Expense could not be approved.")
        return redirect(url_for("expenses"))

    flash("Expense approved successfully.")
    return redirect(url_for("expenses"))


# -------------------------
# REJECT EXPENSE
# -------------------------

@app.route(
    "/expenses/<int:expense_id>/reject",
    methods=["POST"]
)
@login_required
def reject_expense(expense_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    expense = (
        Expense.query
        .filter_by(
            id=expense_id,
            society_id=society.id
        )
        .first_or_404()
    )

    if expense.approval_status != "Pending Approval":
        flash("Only pending expenses can be rejected.")
        return redirect(url_for("expenses"))

    rejection_reason = request.form.get("rejection_reason", "").strip()

    if not rejection_reason:
        flash("Rejection reason is required.")
        return redirect(url_for("expenses"))

    if len(rejection_reason) > 255:
        flash("Rejection reason cannot exceed 255 characters.")
        return redirect(url_for("expenses"))

    expense.approval_status = "Rejected"
    expense.rejected_by = current_user.id
    expense.rejected_at = datetime.now()
    expense.rejection_reason = rejection_reason

    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="REJECT_EXPENSE",
            user_id=current_user.id,
            entity_type="Expense",
            entity_id=expense.id,
            details=f"Rejected expense #{expense.id}: {rejection_reason}"
        )
    except Exception:
        db.session.rollback()
        flash("Expense could not be rejected.")
        return redirect(url_for("expenses"))

    flash("Expense rejected successfully.")
    return redirect(url_for("expenses"))
# -------------------------
# PAY APPROVED EXPENSE
# -------------------------

@app.route(
    "/expenses/<int:expense_id>/pay",
    methods=["POST"]
)
@login_required
def pay_expense(expense_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:

        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )

    expense = (
        Expense.query
        .filter_by(
            id=expense_id,
            society_id=society.id
        )
        .first_or_404()
    )

    # -------------------------
    # EXPENSE STATUS SAFETY
    # -------------------------

    if expense.approval_status != "Approved":

        flash(
            "Only approved expenses can be paid."
        )

        return redirect(
            url_for("expenses")
        )

    if expense.payment_status == "Paid":

        flash(
            "This expense is already paid."
        )

        return redirect(
            url_for("expenses")
        )

    # -------------------------
    # FORM VALUES
    # -------------------------

    payment_mode = request.form.get(
        "payment_mode",
        ""
    ).strip()

    account_id_text = request.form.get(
        "account_id",
        ""
    ).strip()

    payment_reference = request.form.get(
        "payment_reference",
        ""
    ).strip()

    # -------------------------
    # PAYMENT MODE
    # -------------------------

    allowed_modes = [
        "Cash",
        "UPI",
        "Bank Transfer",
        "Cheque"
    ]

    if payment_mode not in allowed_modes:

        flash(
            "Please select a valid payment mode."
        )

        return redirect(
            url_for("expenses")
        )

    # -------------------------
    # FINANCIAL ACCOUNT
    # -------------------------

    try:

        account_id = int(
            account_id_text
        )

    except (ValueError, TypeError):

        flash(
            "Please select a valid financial account."
        )

        return redirect(
            url_for("expenses")
        )

    financial_account = (
        FinancialAccount.query
        .filter_by(
            id=account_id,
            society_id=society.id,
            status=True
        )
        .first()
    )

    if not financial_account:

        flash(
            "Selected financial account is not available."
        )

        return redirect(
            url_for("expenses")
        )

    # -------------------------
    # ACCOUNT TYPE SAFETY
    # -------------------------

    if (
        payment_mode == "Cash"
        and financial_account.account_type != "Cash"
    ):

        flash(
            "Cash expense must be paid from a Cash account."
        )

        return redirect(
            url_for("expenses")
        )

    if (
        payment_mode != "Cash"
        and financial_account.account_type != "Bank"
    ):

        flash(
            "UPI, Bank Transfer and Cheque expenses "
            "must be paid from a Bank account."
        )

        return redirect(
            url_for("expenses")
        )

    # -------------------------
    # DUPLICATE LEDGER SAFETY
    # -------------------------

    existing_transaction = (
        FinancialTransaction.query
        .filter_by(
            society_id=society.id,
            source_type="Expense",
            source_id=expense.id
        )
        .first()
    )

    if existing_transaction:

        flash(
            "A financial transaction already exists "
            "for this expense."
        )

        return redirect(
            url_for("expenses")
        )

    # -------------------------
    # CREATE LEDGER DEBIT
    # -------------------------

    transaction = FinancialTransaction(

        society_id=society.id,

        account_id=financial_account.id,

        transaction_date=datetime.now().date(),

        transaction_type="Expense",

        direction="Debit",

        amount=expense.amount,

        reference_number=(
            payment_reference
            or expense.invoice_reference
            or None
        ),

        description=(
            f"Expense #{expense.id} - "
            f"{expense.vendor_name} - "
            f"{expense.category.name}"
        ),

        source_type="Expense",

        source_id=expense.id,

        created_by=current_user.id
    )

    # -------------------------
    # MARK EXPENSE PAID
    # -------------------------

    expense.payment_status = "Paid"

    expense.payment_mode = payment_mode

    expense.financial_account_id = (
        financial_account.id
    )

    expense.payment_reference = (
        payment_reference or None
    )

    expense.paid_by = current_user.id

    expense.paid_at = datetime.now()

    # -------------------------
    # SAME DATABASE TRANSACTION
    # -------------------------

    db.session.add(transaction)

    try:

        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="DISBURSE_EXPENSE",
            user_id=current_user.id,
            entity_type="Expense",
            entity_id=expense.id,
            details=f"Disbursed payment of ₹{expense.amount} to {expense.vendor_name} from account {financial_account.name} (Txn #{transaction.id})"
        )

    except Exception:

        db.session.rollback()

        flash(
            "Expense payment could not be completed."
        )

        return redirect(
            url_for("expenses")
        )

    flash(
        "Expense paid successfully and "
        "Finance Ledger updated."
    )

    return redirect(
        url_for("expenses")
    )


# -------------------------
# FINANCE ACCOUNTS
# -------------------------

@app.route("/finance/accounts")
@login_required
def finance_accounts():

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:

        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )
    # -------------------------
    # FILTER VALUES
    # -------------------------

    account_id_text = request.args.get(
        "account_id",
        ""
    ).strip()

    direction = request.args.get(
        "direction",
        ""
    ).strip()

    transaction_type = request.args.get(
        "transaction_type",
        ""
    ).strip()

    date_from_text = request.args.get(
        "date_from",
        ""
    ).strip()

    date_to_text = request.args.get(
        "date_to",
        ""
    ).strip()


    # -------------------------
    # ACCOUNTS
    # -------------------------

    accounts = (
        FinancialAccount.query
        .filter_by(
            society_id=society.id
        )
        .order_by(
            FinancialAccount.account_type.asc(),
            FinancialAccount.name.asc()
        )
        .all()
    )


    # -------------------------
    # ACCOUNT BALANCES
    # -------------------------

    account_cards = []

    total_balance = Decimal("0.00")

    for account in accounts:

        credit_total = sum(
            (
                Decimal(str(transaction.amount))
                for transaction in account.transactions
                if transaction.direction == "Credit"
            ),
            Decimal("0.00")
        )

        debit_total = sum(
            (
                Decimal(str(transaction.amount))
                for transaction in account.transactions
                if transaction.direction == "Debit"
            ),
            Decimal("0.00")
        )

        opening_balance = Decimal(
            str(
                account.opening_balance
                or 0
            )
        )

        balance = (
            opening_balance
            + credit_total
            - debit_total
        ).quantize(
            Decimal("0.01")
        )

        total_balance += balance

        account_cards.append({
            "account": account,
            "credit_total": credit_total,
            "debit_total": debit_total,
            "balance": balance
        })


    # -------------------------
    # TRANSACTION QUERY
    # -------------------------

    transaction_query = (
        FinancialTransaction.query
        .filter_by(
            society_id=society.id
        )
    )


    # ACCOUNT FILTER

    selected_account_id = None

    if account_id_text:

        try:

            selected_account_id = int(
                account_id_text
            )

            transaction_query = (
                transaction_query.filter(
                    FinancialTransaction.account_id
                    == selected_account_id
                )
            )

        except ValueError:

            selected_account_id = None


    # DIRECTION FILTER

    allowed_directions = [
        "Credit",
        "Debit"
    ]

    if direction in allowed_directions:

        transaction_query = (
            transaction_query.filter(
                FinancialTransaction.direction
                == direction
            )
        )

    else:

        direction = ""


    # TRANSACTION TYPE FILTER

    allowed_types = [
        "Income",
        "Expense",
        "Transfer",
        "Refund",
        "Adjustment"
    ]

    if transaction_type in allowed_types:

        transaction_query = (
            transaction_query.filter(
                FinancialTransaction.transaction_type
                == transaction_type
            )
        )

    else:

        transaction_type = ""


    # DATE FROM FILTER

    date_from = None

    if date_from_text:

        try:

            date_from = datetime.strptime(
                date_from_text,
                "%Y-%m-%d"
            ).date()

            transaction_query = (
                transaction_query.filter(
                    FinancialTransaction.transaction_date
                    >= date_from
                )
            )

        except ValueError:

            date_from_text = ""


    # DATE TO FILTER

    date_to = None

    if date_to_text:

        try:

            date_to = datetime.strptime(
                date_to_text,
                "%Y-%m-%d"
            ).date()

            transaction_query = (
                transaction_query.filter(
                    FinancialTransaction.transaction_date
                    <= date_to
                )
            )

        except ValueError:

            date_to_text = ""


    # -------------------------
    # FINAL TRANSACTIONS
    # -------------------------

    transactions = (
        transaction_query
        .order_by(
            FinancialTransaction.transaction_date.desc(),
            FinancialTransaction.id.desc()
        )
        .limit(200)
        .all()
    )

    # -------------------------
    # RUNNING BALANCE & REVERSAL STATUS
    # -------------------------
    if selected_account_id:
        acc = FinancialAccount.query.get(selected_account_id)
        current_running = Decimal(str(acc.opening_balance or 0)) if acc else Decimal("0.00")
        chronological_txns = (
            FinancialTransaction.query
            .filter_by(society_id=society.id, account_id=selected_account_id)
            .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
            .all()
        )
    else:
        current_running = sum((Decimal(str(a.opening_balance or 0)) for a in accounts), Decimal("0.00"))
        chronological_txns = (
            FinancialTransaction.query
            .filter_by(society_id=society.id)
            .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
            .all()
        )

    running_balance_map = {}
    for t in chronological_txns:
        amt = Decimal(str(t.amount or 0))
        if t.direction == "Credit":
            current_running += amt
        else:
            current_running -= amt
        running_balance_map[t.id] = current_running

    reversed_txn_ids = set(
        r[0] for r in db.session.query(FinancialTransaction.source_id)
        .filter(FinancialTransaction.society_id == society.id, FinancialTransaction.source_type == "Reversal")
        .all()
        if r[0] is not None
    )

    for t in transactions:
        t.running_balance = running_balance_map.get(t.id, Decimal("0.00"))
        t.is_reversed = t.id in reversed_txn_ids

    return render_template(
        "finance_accounts.html",
        society=society,
        account_cards=account_cards,
        accounts=accounts,
        total_balance=total_balance,
        transactions=transactions,

        selected_account_id=selected_account_id,
        selected_direction=direction,
        selected_transaction_type=transaction_type,
        selected_date_from=date_from_text,
        selected_date_to=date_to_text
    )
# -------------------------
# ADD FINANCIAL ACCOUNT
# -------------------------

@app.route(
    "/finance/accounts/add",
    methods=["POST"]
)
@login_required
def add_financial_account():

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:

        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )


    # -------------------------
    # FORM VALUES
    # -------------------------

    name = request.form.get(
        "name",
        ""
    ).strip()

    account_type = request.form.get(
        "account_type",
        ""
    ).strip()

    opening_balance_text = request.form.get(
        "opening_balance",
        "0"
    ).strip()


    # -------------------------
    # NAME VALIDATION
    # -------------------------

    if not name:

        flash(
            "Account name is required."
        )

        return redirect(
            url_for("finance_accounts")
        )


    if len(name) > 120:

        flash(
            "Account name cannot exceed 120 characters."
        )

        return redirect(
            url_for("finance_accounts")
        )


    # -------------------------
    # ACCOUNT TYPE VALIDATION
    # -------------------------

    allowed_account_types = [
        "Bank",
        "Cash",
        "Petty Cash"
    ]


    if account_type not in allowed_account_types:

        flash(
            "Please select a valid account type."
        )

        return redirect(
            url_for("finance_accounts")
        )


    # -------------------------
    # OPENING BALANCE VALIDATION
    # -------------------------

    try:

        opening_balance = Decimal(
            opening_balance_text
        ).quantize(
            Decimal("0.01")
        )

    except (InvalidOperation, ValueError):

        flash(
            "Please enter a valid opening balance."
        )

        return redirect(
            url_for("finance_accounts")
        )


    if opening_balance < Decimal("0.00"):

        flash(
            "Opening balance cannot be negative."
        )

        return redirect(
            url_for("finance_accounts")
        )


    # -------------------------
    # DUPLICATE ACCOUNT CHECK
    # -------------------------

    duplicate_account = (
        FinancialAccount.query
        .filter(
            FinancialAccount.society_id
            == society.id,

            db.func.lower(
                FinancialAccount.name
            )
            == name.lower()
        )
        .first()
    )


    if duplicate_account:

        flash(
            "A financial account with this name already exists."
        )

        return redirect(
            url_for("finance_accounts")
        )


    # -------------------------
    # CREATE ACCOUNT
    # -------------------------

    account = FinancialAccount(
        society_id=society.id,
        name=name,
        account_type=account_type,
        opening_balance=opening_balance,
        status=True
    )


    try:

        db.session.add(account)

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "Financial account could not be created."
        )

        return redirect(
            url_for("finance_accounts")
        )


    flash(
        f"{account.name} created successfully!"
    )

    return redirect(
        url_for("finance_accounts")
    )    
# -------------------------
# FINANCIAL ACCOUNT EDIT PAGE
# -------------------------

@app.route(
    "/finance/accounts/<int:account_id>/edit-page"
)
@login_required
def edit_financial_account_page(account_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:

        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )


    account = (
        FinancialAccount.query
        .filter_by(
            id=account_id,
            society_id=society.id
        )
        .first_or_404()
    )


    transactions = (
        FinancialTransaction.query
        .filter_by(
            account_id=account.id,
            society_id=society.id
        )
        .all()
    )


    has_transactions = len(transactions) > 0


    credit_total = sum(
        (
            Decimal(str(transaction.amount))
            for transaction in transactions
            if transaction.direction == "Credit"
        ),
        Decimal("0.00")
    )


    debit_total = sum(
        (
            Decimal(str(transaction.amount))
            for transaction in transactions
            if transaction.direction == "Debit"
        ),
        Decimal("0.00")
    )


    opening_balance = Decimal(
        str(account.opening_balance or 0)
    )


    current_balance = (
        opening_balance
        + credit_total
        - debit_total
    ).quantize(
        Decimal("0.01")
    )


    return render_template(
        "edit_financial_account.html",
        society=society,
        account=account,
        has_transactions=has_transactions,
        credit_total=credit_total,
        debit_total=debit_total,
        current_balance=current_balance
    )
# -------------------------
# EDIT FINANCIAL ACCOUNT
# -------------------------

@app.route(
    "/finance/accounts/<int:account_id>/edit",
    methods=["POST"]
)
@login_required
def edit_financial_account(account_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:
        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )


    account = (
        FinancialAccount.query
        .filter_by(
            id=account_id,
            society_id=society.id
        )
        .first_or_404()
    )


    name = request.form.get(
        "name",
        ""
    ).strip()


    account_type = request.form.get(
        "account_type",
        ""
    ).strip()


    opening_balance_text = request.form.get(
        "opening_balance",
        "0"
    ).strip()


    # -------------------------
    # VALIDATION
    # -------------------------

    if not name:

        flash(
            "Account name is required."
        )

        return redirect(
            url_for("finance_accounts")
        )


    allowed_account_types = [
        "Bank",
        "Cash",
        "Petty Cash"
    ]


    if account_type not in allowed_account_types:

        flash(
            "Invalid account type."
        )

        return redirect(
            url_for("finance_accounts")
        )


    try:

        opening_balance = Decimal(
            opening_balance_text
        ).quantize(
            Decimal("0.01")
        )

    except (InvalidOperation, ValueError):

        flash(
            "Please enter a valid opening balance."
        )

        return redirect(
            url_for("finance_accounts")
        )


    if opening_balance < Decimal("0.00"):

        flash(
            "Opening balance cannot be negative."
        )

        return redirect(
            url_for("finance_accounts")
        )


    # -------------------------
    # DUPLICATE NAME CHECK
    # -------------------------

    duplicate_account = (
        FinancialAccount.query
        .filter(
            FinancialAccount.society_id
            == society.id,

            FinancialAccount.name
            == name,

            FinancialAccount.id
            != account.id
        )
        .first()
    )


    if duplicate_account:

        flash(
            "Another financial account "
            "already uses this name."
        )

        return redirect(
            url_for("finance_accounts")
        )


    # -------------------------
    # ACCOUNT TYPE SAFETY
    # -------------------------

    has_transactions = (
        FinancialTransaction.query
        .filter_by(
            account_id=account.id
        )
        .first()
        is not None
    )
    # -------------------------
# OPENING BALANCE SAFETY
# -------------------------

    current_opening_balance = Decimal(
        str(account.opening_balance or 0)
    ).quantize(
        Decimal("0.01")
    )

    if (
        has_transactions
        and opening_balance != current_opening_balance
    ):

        flash(
            "Opening balance cannot be changed "
            "after transactions exist. "
            "Use an adjustment transaction instead."
        )

        return redirect(
            url_for("finance_accounts")
        )

    if (
        has_transactions
        and account.account_type
        != account_type
    ):

        flash(
            "Account type cannot be changed "
            "after transactions exist."
        )

        return redirect(
            url_for("finance_accounts")
        )


    # -------------------------
    # UPDATE ACCOUNT
    # -------------------------

    account.name = name
    account.account_type = account_type
    account.opening_balance = opening_balance


    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "Financial account could not be updated."
        )

        return redirect(
            url_for("finance_accounts")
        )


    flash(
        "Financial account updated successfully!"
    )

    return redirect(
        url_for("finance_accounts")
    )


# -------------------------
# TOGGLE FINANCIAL ACCOUNT
# -------------------------

@app.route(
    "/finance/accounts/<int:account_id>/toggle",
    methods=["POST"]
)
@login_required
def toggle_financial_account(account_id):

    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()

    if not society:

        flash(
            "Please setup society information first."
        )

        return redirect(
            url_for("society_settings")
        )


    account = (
        FinancialAccount.query
        .filter_by(
            id=account_id,
            society_id=society.id
        )
        .first_or_404()
    )
    # -------------------------
    # ACCOUNT DEACTIVATION SAFETY
    # -------------------------

    if account.status:

        other_active_account = (
            FinancialAccount.query
            .filter(
                FinancialAccount.society_id == society.id,
                FinancialAccount.account_type == account.account_type,
                FinancialAccount.status.is_(True),
                FinancialAccount.id != account.id
            )
            .first()
        )

        if not other_active_account:

            flash(
                f"Cannot deactivate {account.name}. "
                f"At least one active {account.account_type} "
                "account must remain available."
            )

            return redirect(
                url_for("finance_accounts")
            )

    account.status = not account.status


    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "Account status could not be changed."
        )

        return redirect(
            url_for("finance_accounts")
        )


    if account.status:

        flash(
            f"{account.name} activated successfully."
        )

    else:

        flash(
            f"{account.name} deactivated successfully."
        )


    return redirect(
        url_for("finance_accounts")
    )
# -------------------------

# LOGOUT

# -------------------------



# Note: /logout is now handled by auth_bp.logout


# -------------------------
# CONTEXT PROCESSOR
# -------------------------

def format_inr(value):
    if value is None or value == "":
        return "₹0"
    try:
        val = float(value)
    except (ValueError, TypeError):
        return f"₹{value}"
    
    is_neg = val < 0
    val = abs(val)
    parts = f"{val:.2f}".split(".")
    int_part, dec_part = parts[0], parts[1]

    if len(int_part) <= 3:
        formatted = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3

    res = f"₹{formatted}" if dec_part == "00" else f"₹{formatted}.{dec_part}"
    return f"-{res}" if is_neg else res

app.jinja_env.filters["inr"] = format_inr

@app.context_processor
def inject_common():
    unread = 0
    pending_req_cnt = 0
    open_comp_cnt = 0
    if current_user.is_authenticated:
        from services.notifications import unread_count
        unread = unread_count(current_user.id)
        if current_user.role == "secretary":
            from models.registration_request import RegistrationRequest
            pending_req_cnt = RegistrationRequest.query.filter_by(status="pending").count()
            open_comp_cnt = Complaint.query.filter(Complaint.status.in_(["Open", "In Progress"])).count()

    return dict(
        current_society=Society.query.first(),
        calendar=calendar,
        unread_notif_count=unread,
        pending_requests_count=pending_req_cnt,
        open_complaints_count=open_comp_cnt
    )


# -------------------------
# TRANSACTION REVERSAL
# -------------------------

@app.route(
    "/finance/transactions/<int:transaction_id>/reverse",
    methods=["POST"]
)
@login_required
def reverse_financial_transaction(transaction_id):
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    txn = FinancialTransaction.query.filter_by(id=transaction_id, society_id=society.id).first_or_404()

    if txn.source_type == "Reversal":
        flash("A reversal transaction cannot be reversed.")
        return redirect(url_for("finance_accounts"))

    already_reversed = FinancialTransaction.query.filter_by(
        society_id=society.id,
        source_type="Reversal",
        source_id=txn.id
    ).first()

    if already_reversed:
        flash(f"Transaction #{txn.id} has already been reversed (Txn #{already_reversed.id}).")
        return redirect(url_for("finance_accounts"))

    reason = request.form.get("reason", "").strip() or "Manual reversal by Secretary"
    reversal_direction = "Debit" if txn.direction == "Credit" else "Credit"

    reversal_txn = FinancialTransaction(
        society_id=society.id,
        account_id=txn.account_id,
        transaction_date=datetime.now().date(),
        transaction_type="Adjustment",
        direction=reversal_direction,
        amount=txn.amount,
        reference_number=f"REV-{txn.id}",
        description=f"Reversal of Txn #{txn.id} ({txn.description}): {reason}"[:255],
        source_type="Reversal",
        source_id=txn.id,
        created_by=current_user.id
    )

    db.session.add(reversal_txn)
    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="REVERSE_TRANSACTION",
            user_id=current_user.id,
            entity_type="FinancialTransaction",
            entity_id=reversal_txn.id,
            details=f"Reversed Txn #{txn.id} ({txn.direction} ₹{txn.amount}) - Reason: {reason}"
        )
        flash(f"Transaction #{txn.id} reversed successfully with offsetting ledger entry #{reversal_txn.id}.")
    except Exception:
        db.session.rollback()
        flash("Transaction could not be reversed.")

    return redirect(url_for("finance_accounts"))


# -------------------------
# STAFF & WORKERS
# -------------------------

@app.route("/staff")
@login_required
def staff_directory():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    staff_list = Staff.query.filter_by(society_id=society.id).order_by(Staff.status.desc(), Staff.name.asc()).all()
    total_monthly_payroll = sum((Decimal(str(s.salary or 0)) for s in staff_list if s.status), Decimal("0.00"))

    return render_template(
        "staff_directory.html",
        society=society,
        staff_list=staff_list,
        total_monthly_payroll=total_monthly_payroll
    )


@app.route("/staff/add", methods=["POST"])
@login_required
def add_staff():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    name = request.form.get("name", "").strip()
    role = request.form.get("role", "").strip()
    phone = request.form.get("phone", "").strip()
    salary_text = request.form.get("salary", "0").strip()
    joining_date_text = request.form.get("joining_date", "").strip()
    id_proof_number = request.form.get("id_proof_number", "").strip()
    emergency_contact = request.form.get("emergency_contact", "").strip()

    if not name or not role or not phone or not joining_date_text:
        flash("Name, role, phone, and joining date are required.")
        return redirect(url_for("staff_directory"))

    try:
        salary = Decimal(salary_text).quantize(Decimal("0.01"))
        if salary < Decimal("0.00"):
            raise ValueError()
    except Exception:
        flash("Please enter a valid monthly salary.")
        return redirect(url_for("staff_directory"))

    try:
        joining_date = datetime.strptime(joining_date_text, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid joining date.")
        return redirect(url_for("staff_directory"))

    staff_member = Staff(
        society_id=society.id,
        name=name,
        role=role,
        phone=phone,
        salary=salary,
        joining_date=joining_date,
        id_proof_number=id_proof_number or None,
        emergency_contact=emergency_contact or None,
        status=True
    )
    db.session.add(staff_member)
    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="CREATE_STAFF",
            user_id=current_user.id,
            entity_type="Staff",
            entity_id=staff_member.id,
            details=f"Enrolled staff member {name} as {role} with monthly salary ₹{salary}"
        )
        flash(f"Staff member {name} registered successfully.")
    except Exception:
        db.session.rollback()
        flash("Could not register staff member.")

    return redirect(url_for("staff_directory"))


@app.route("/staff/<int:staff_id>/toggle", methods=["POST"])
@login_required
def toggle_staff_status(staff_id):
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    staff = Staff.query.filter_by(id=staff_id, society_id=society.id).first_or_404()
    staff.status = not staff.status
    try:
        db.session.commit()
        status_text = "activated" if staff.status else "deactivated"
        flash(f"Staff member {staff.name} {status_text}.")
    except Exception:
        db.session.rollback()
        flash("Could not update staff status.")

    return redirect(url_for("staff_directory"))


# -------------------------
# STAFF PAYMENTS (PAYROLL)
# -------------------------

@app.route("/staff/payments")
@login_required
def staff_payments():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    now = datetime.now()
    selected_month = request.args.get("month_year", now.strftime("%Y-%m")).strip()
    try:
        datetime.strptime(selected_month, "%Y-%m")
    except ValueError:
        selected_month = now.strftime("%Y-%m")

    payments = (
        StaffPayment.query
        .filter_by(society_id=society.id, month_year=selected_month)
        .order_by(StaffPayment.id.desc())
        .all()
    )

    total_paid_amount = sum((Decimal(str(p.net_amount)) for p in payments if p.status == "Paid"), Decimal("0.00"))
    total_pending_amount = sum((Decimal(str(p.net_amount)) for p in payments if p.status in ["Pending Approval", "Approved"]), Decimal("0.00"))

    accounts = FinancialAccount.query.filter_by(society_id=society.id, status=True).order_by(FinancialAccount.name.asc()).all()

    return render_template(
        "staff_payments.html",
        society=society,
        payments=payments,
        selected_month=selected_month,
        total_paid_amount=total_paid_amount,
        total_pending_amount=total_pending_amount,
        accounts=accounts,
        today_str=now.strftime("%Y-%m-%d")
    )


@app.route("/staff/payments/generate", methods=["POST"])
@login_required
def generate_staff_payments():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    month_year = request.form.get("month_year", "").strip()
    if not month_year:
        flash("Month-Year is required.")
        return redirect(url_for("staff_payments"))

    active_staff = Staff.query.filter_by(society_id=society.id, status=True).all()
    if not active_staff:
        flash("No active staff members found. Please enroll staff first.")
        return redirect(url_for("staff_directory"))

    generated_count = 0
    for s in active_staff:
        existing = StaffPayment.query.filter_by(society_id=society.id, staff_id=s.id, month_year=month_year).first()
        if not existing:
            slip = StaffPayment(
                society_id=society.id,
                staff_id=s.id,
                month_year=month_year,
                base_salary=s.salary,
                bonus_amount=Decimal("0.00"),
                deduction_amount=Decimal("0.00"),
                net_amount=s.salary,
                status="Pending Approval",
                created_by=current_user.id
            )
            db.session.add(slip)
            generated_count += 1

    try:
        db.session.commit()
        if generated_count > 0:
            AuditLog.log(
                society_id=society.id,
                action="GENERATE_SALARY",
                user_id=current_user.id,
                details=f"Generated {generated_count} salary vouchers for {month_year}"
            )
            flash(f"Successfully generated {generated_count} salary slips for {month_year}.")
        else:
            flash(f"Salary slips for {month_year} already exist for all active staff.")
    except Exception:
        db.session.rollback()
        flash("Failed to generate salary slips.")

    return redirect(url_for("staff_payments", month_year=month_year))


@app.route("/staff/payments/<int:payment_id>/approve", methods=["POST"])
@login_required
def approve_staff_payment(payment_id):
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    payment = StaffPayment.query.filter_by(id=payment_id, society_id=society.id).first_or_404()
    if payment.status != "Pending Approval":
        flash("Only pending salary slips can be approved.")
        return redirect(url_for("staff_payments", month_year=payment.month_year))

    payment.status = "Approved"
    payment.approved_by = current_user.id
    payment.approved_at = datetime.now()
    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="APPROVE_SALARY",
            user_id=current_user.id,
            entity_type="StaffPayment",
            entity_id=payment.id,
            details=f"Approved salary slip #{payment.id} of ₹{payment.net_amount} for {payment.staff.name} ({payment.month_year})"
        )
        flash(f"Salary slip for {payment.staff.name} approved.")
    except Exception:
        db.session.rollback()
        flash("Could not approve salary slip.")

    return redirect(url_for("staff_payments", month_year=payment.month_year))


@app.route("/staff/payments/<int:payment_id>/reject", methods=["POST"])
@login_required
def reject_staff_payment(payment_id):
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    payment = StaffPayment.query.filter_by(id=payment_id, society_id=society.id).first_or_404()
    if payment.status != "Pending Approval":
        flash("Only pending salary slips can be rejected.")
        return redirect(url_for("staff_payments", month_year=payment.month_year))

    payment.status = "Rejected"
    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="REJECT_SALARY",
            user_id=current_user.id,
            entity_type="StaffPayment",
            entity_id=payment.id,
            details=f"Rejected salary slip #{payment.id} for {payment.staff.name} ({payment.month_year})"
        )
        flash(f"Salary slip for {payment.staff.name} rejected.")
    except Exception:
        db.session.rollback()
        flash("Could not reject salary slip.")

    return redirect(url_for("staff_payments", month_year=payment.month_year))


@app.route("/staff/payments/<int:payment_id>/disburse", methods=["POST"])
@login_required
def disburse_staff_payment(payment_id):
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    payment = StaffPayment.query.filter_by(id=payment_id, society_id=society.id).first_or_404()
    if payment.status != "Approved":
        flash("Only approved salary slips can be disbursed.")
        return redirect(url_for("staff_payments", month_year=payment.month_year))

    account_id_text = request.form.get("account_id", "").strip()
    payment_mode = request.form.get("payment_mode", "Bank Transfer").strip()
    payment_date_text = request.form.get("payment_date", "").strip()
    reference_number = request.form.get("reference_number", "").strip()
    remarks = request.form.get("remarks", "").strip()

    try:
        account_id = int(account_id_text)
        account = FinancialAccount.query.filter_by(id=account_id, society_id=society.id, status=True).first_or_404()
    except Exception:
        flash("Please select a valid liquid payment account.")
        return redirect(url_for("staff_payments", month_year=payment.month_year))

    try:
        payment_date = datetime.strptime(payment_date_text, "%Y-%m-%d").date()
    except ValueError:
        payment_date = datetime.now().date()

    txn = FinancialTransaction(
        society_id=society.id,
        account_id=account.id,
        transaction_date=payment_date,
        transaction_type="Expense",
        direction="Debit",
        amount=payment.net_amount,
        reference_number=reference_number or f"SAL-{payment.id}",
        description=f"Salary Payout: {payment.staff.name} ({payment.month_year})"[:255],
        source_type="StaffPayment",
        source_id=payment.id,
        created_by=current_user.id
    )

    payment.status = "Paid"
    payment.payment_date = payment_date
    payment.payment_mode = payment_mode
    payment.account_id = account.id
    payment.reference_number = reference_number or None
    payment.remarks = remarks or None
    payment.paid_by = current_user.id
    payment.paid_at = datetime.now()

    db.session.add(txn)
    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="DISBURSE_SALARY",
            user_id=current_user.id,
            entity_type="StaffPayment",
            entity_id=payment.id,
            details=f"Disbursed salary ₹{payment.net_amount} to {payment.staff.name} from {account.name} (Txn #{txn.id})"
        )
        flash(f"Salary of ₹{payment.net_amount} paid successfully to {payment.staff.name} and posted as DEBIT entry #{txn.id}.")
    except Exception:
        db.session.rollback()
        flash("Salary disbursement failed due to database constraint.")

    return redirect(url_for("staff_payments", month_year=payment.month_year))


# -------------------------
# VENDORS & CONTRACTORS
# -------------------------

@app.route("/vendors")
@login_required
def vendors():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    vendor_list = Vendor.query.filter_by(society_id=society.id).order_by(Vendor.status.desc(), Vendor.name.asc()).all()
    return render_template(
        "vendors.html",
        society=society,
        vendors=vendor_list
    )


@app.route("/vendors/add", methods=["POST"])
@login_required
def add_vendor():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    name = request.form.get("name", "").strip()
    service_type = request.form.get("service_type", "").strip()
    contact_person = request.form.get("contact_person", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    address = request.form.get("address", "").strip()
    gst_number = request.form.get("gst_number", "").strip()
    pan_number = request.form.get("pan_number", "").strip()

    if not name or not service_type or not phone:
        flash("Vendor name, service type, and contact phone are required.")
        return redirect(url_for("vendors"))

    existing = Vendor.query.filter(Vendor.society_id == society.id, db.func.lower(Vendor.name) == name.lower()).first()
    if existing:
        flash(f"Vendor '{name}' already exists.")
        return redirect(url_for("vendors"))

    vendor = Vendor(
        society_id=society.id,
        name=name,
        service_type=service_type,
        contact_person=contact_person or None,
        phone=phone,
        email=email or None,
        address=address or None,
        gst_number=gst_number or None,
        pan_number=pan_number or None,
        status=True
    )
    db.session.add(vendor)
    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="CREATE_VENDOR",
            user_id=current_user.id,
            entity_type="Vendor",
            entity_id=vendor.id,
            details=f"Added vendor {name} ({service_type})"
        )
        flash(f"Vendor {name} registered successfully.")
    except Exception:
        db.session.rollback()
        flash("Could not register vendor.")

    return redirect(url_for("vendors"))


@app.route("/vendors/<int:vendor_id>/toggle", methods=["POST"])
@login_required
def toggle_vendor_status(vendor_id):
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    vendor = Vendor.query.filter_by(id=vendor_id, society_id=society.id).first_or_404()
    vendor.status = not vendor.status
    try:
        db.session.commit()
        status_text = "activated" if vendor.status else "deactivated"
        flash(f"Vendor {vendor.name} {status_text}.")
    except Exception:
        db.session.rollback()
        flash("Could not update vendor status.")

    return redirect(url_for("vendors"))


# -------------------------
# NOTICES & CIRCULARS
# -------------------------

@app.route("/notices")
@login_required
def notices():
    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("login"))

    notices_list = (
        Notice.query
        .filter_by(society_id=society.id, is_active=True)
        .order_by(Notice.is_pinned.desc(), Notice.created_at.desc())
        .all()
    )
    return render_template(
        "notices.html",
        society=society,
        notices=notices_list
    )


@app.route("/notices/add", methods=["POST"])
@login_required
def add_notice():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "General").strip()
    priority = request.form.get("priority", "Normal").strip()
    content = request.form.get("content", "").strip()
    expires_at_text = request.form.get("expires_at", "").strip()
    is_pinned = bool(request.form.get("is_pinned"))

    if not title or not content:
        flash("Notice title and content are required.")
        return redirect(url_for("notices"))

    expires_at = None
    if expires_at_text:
        try:
            expires_at = datetime.strptime(expires_at_text, "%Y-%m-%d").date()
        except ValueError:
            pass

    attachment_file = request.files.get("attachment_file")
    attachment_path = None
    if attachment_file and attachment_file.filename:
        allowed_exts = {'pdf', 'png', 'jpg', 'jpeg'}
        ext = attachment_file.filename.rsplit('.', 1)[-1].lower() if '.' in attachment_file.filename else ''
        if ext in allowed_exts:
            upload_dir = os.path.join(app.root_path, "static", "uploads", "notices")
            os.makedirs(upload_dir, exist_ok=True)
            filename = f"notice_{society.id}_{uuid.uuid4().hex[:10]}.{ext}"
            filepath = os.path.join(upload_dir, filename)
            attachment_file.save(filepath)
            attachment_path = f"uploads/notices/{filename}"

    notice = Notice(
        society_id=society.id,
        title=title,
        content=content,
        category=category,
        priority=priority,
        attachment_path=attachment_path,
        is_pinned=is_pinned,
        is_active=True,
        expires_at=expires_at,
        created_by=current_user.id
    )
    db.session.add(notice)
    try:
        db.session.commit()
        AuditLog.log(
            society_id=society.id,
            action="PUBLISH_NOTICE",
            user_id=current_user.id,
            entity_type="Notice",
            entity_id=notice.id,
            details=f"Broadcasted notice '{title}' ({priority})"
        )
        flash("Notice published successfully to community board.")
    except Exception:
        db.session.rollback()
        flash("Failed to publish notice.")

    return redirect(url_for("notices"))


@app.route("/notices/<int:notice_id>/toggle-pin", methods=["POST"])
@login_required
def toggle_notice_pin(notice_id):
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    notice = Notice.query.filter_by(id=notice_id, society_id=society.id).first_or_404()
    notice.is_pinned = not notice.is_pinned
    db.session.commit()
    return redirect(url_for("notices"))


@app.route("/notices/<int:notice_id>/delete", methods=["POST"])
@login_required
def delete_notice(notice_id):
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    notice = Notice.query.filter_by(id=notice_id, society_id=society.id).first_or_404()
    notice.is_active = False
    db.session.commit()
    flash("Notice removed from board.")
    return redirect(url_for("notices"))


# -------------------------
# COMPLAINTS & HELPDESK (Handled by routes/complaints.py via complaints_bp)
# -------------------------

@app.route("/complaints_legacy", endpoint="complaints")
@login_required
def legacy_complaints():
    return redirect(url_for("complaints.index"))


# -------------------------
# REPORTS & STATEMENTS
# -------------------------

@app.route("/reports")
@login_required
def reports_index():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    # Maintenance Collections
    bills = MaintenanceBill.query.filter_by(society_id=society.id).all()
    total_billed = sum((Decimal(str(b.total_amount or 0)) for b in bills), Decimal("0.00"))
    total_collected = sum((Decimal(str(b.paid_amount or 0)) for b in bills), Decimal("0.00"))
    total_outstanding = sum((Decimal(str(b.balance_amount or 0)) for b in bills), Decimal("0.00"))
    collection_rate = (float(total_collected) / float(total_billed) * 100) if total_billed > 0 else 0.0

    # General Ledger Inflows / Outflows
    all_txns = FinancialTransaction.query.filter_by(society_id=society.id).all()
    total_ledger_credits = sum((Decimal(str(t.amount or 0)) for t in all_txns if t.direction == "Credit"), Decimal("0.00"))
    total_ledger_debits = sum((Decimal(str(t.amount or 0)) for t in all_txns if t.direction == "Debit"), Decimal("0.00"))

    # Accounts Liquid Funds
    accounts = FinancialAccount.query.filter_by(society_id=society.id, status=True).all()
    total_liquid_balance = Decimal("0.00")
    for acc in accounts:
        c = sum((Decimal(str(t.amount)) for t in acc.transactions if t.direction == "Credit"), Decimal("0.00"))
        d = sum((Decimal(str(t.amount)) for t in acc.transactions if t.direction == "Debit"), Decimal("0.00"))
        total_liquid_balance += (Decimal(str(acc.opening_balance or 0)) + c - d)

    # Defaulters Roster
    defaulters_raw = (
        db.session.query(
            Flat.id,
            Flat.flat_number,
            Building.name.label("building_name"),
            Wing.name.label("wing_name"),
            db.func.sum(MaintenanceBill.balance_amount).label("total_due"),
            db.func.count(MaintenanceBill.id).label("unpaid_bills_count")
        )
        .join(Floor, Flat.floor_id == Floor.id)
        .join(Wing, Floor.wing_id == Wing.id)
        .join(Building, Wing.building_id == Building.id)
        .join(MaintenanceBill, MaintenanceBill.flat_id == Flat.id)
        .filter(Building.society_id == society.id, MaintenanceBill.balance_amount > 0)
        .group_by(Flat.id)
        .order_by(db.desc("total_due"))
        .all()
    )

    defaulters = []
    for d in defaulters_raw:
        primary_member = (
            FlatMember.query
            .filter_by(flat_id=d.id, is_active=True)
            .order_by(FlatMember.is_primary.desc())
            .first()
        )
        defaulters.append({
            "flat_number": d.flat_number,
            "building_wing": f"{d.building_name} - Wing {d.wing_name}",
            "resident_name": primary_member.user.full_name if primary_member and primary_member.user else "Unassigned",
            "phone": primary_member.user.phone if primary_member and primary_member.user else "—",
            "unpaid_bills_count": d.unpaid_bills_count,
            "total_due": d.total_due
        })

    # Expenses by Category
    category_expenses = []
    categories = ExpenseCategory.query.filter_by(society_id=society.id).all()
    for cat in categories:
        cat_expenses = Expense.query.filter_by(category_id=cat.id, payment_status="Paid").all()
        cat_total = sum((Decimal(str(e.amount)) for e in cat_expenses), Decimal("0.00"))
        if cat_expenses:
            category_expenses.append({
                "name": cat.name,
                "count": len(cat_expenses),
                "total": cat_total
            })

    return render_template(
        "reports.html",
        society=society,
        total_billed=total_billed,
        total_collected=total_collected,
        total_outstanding=total_outstanding,
        collection_rate=collection_rate,
        total_ledger_credits=total_ledger_credits,
        total_ledger_debits=total_ledger_debits,
        total_liquid_balance=total_liquid_balance,
        defaulters=defaulters,
        category_expenses=category_expenses
    )


# -------------------------
# AUDIT LOGS
# -------------------------

@app.route("/audit-logs")
@login_required
def audit_logs():
    if current_user.role != "secretary":
        return "Access Denied", 403

    society = Society.query.first()
    if not society:
        flash("Please setup society information first.")
        return redirect(url_for("society_settings"))

    selected_action = request.args.get("action", "").strip()
    query = AuditLog.query.filter_by(society_id=society.id)
    if selected_action:
        query = query.filter_by(action=selected_action)

    logs = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(150).all()

    return render_template(
        "audit_logs.html",
        society=society,
        logs=logs,
        selected_action=selected_action
    )


# -------------------------
# CREATE TABLES & DEFAULT DATA
# -------------------------

with app.app_context():

    db.create_all()

    society = Society.query.first()

    if society:

        default_accounts = [
            {
                "name": "Society Bank Account",
                "account_type": "Bank"
            },
            {
                "name": "Cash Account",
                "account_type": "Cash"
            },
            {
                "name": "Petty Cash Account",
                "account_type": "Petty Cash"
            }
        ]

        for account_data in default_accounts:

            existing_account = (
                FinancialAccount.query
                .filter_by(
                    society_id=society.id,
                    name=account_data["name"]
                )
                .first()
            )

            if not existing_account:

                account = FinancialAccount(
                    society_id=society.id,
                    name=account_data["name"],
                    account_type=account_data[
                        "account_type"
                    ],
                    opening_balance=Decimal("0.00"),
                    status=True
                )

                db.session.add(account)

        db.session.commit()
            # -------------------------
    # DEFAULT EXPENSE CATEGORIES
    # -------------------------

    if society:

        default_expense_categories = [
            "Electricity",
            "Water Charges",
            "Repairs & Maintenance",
            "Security",
            "Cleaning",
            "Other"
        ]

        for category_name in default_expense_categories:

            existing_category = (
                ExpenseCategory.query
                .filter_by(
                    society_id=society.id,
                    name=category_name
                )
                .first()
            )

            if not existing_category:

                category = ExpenseCategory(
                    society_id=society.id,
                    name=category_name,
                    status=True
                )

                db.session.add(category)

        db.session.commit()

    print(
        "Database tables and financial accounts ready!"
    )




# -------------------------

# RUN APPLICATION

# -------------------------



if __name__ == "__main__":



    app.run(debug=True)
