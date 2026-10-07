import time
import secrets
import smtplib
from email.mime.text import MIMEText
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import db
from models.user import User
from models.society import Society
from models.building import Building
from models.wing import Wing
from models.floor import Floor
from models.flat import Flat
from models.flat_member import FlatMember
from models.registration_request import RegistrationRequest
from models.notification import Notification
from models.audit_log import AuditLog
from services.auth import (
    role_required,
    safe_next_url,
    validate_password_policy,
    clean_and_validate_mobile,
    validate_full_name,
    is_user_locked,
    record_failed_login,
    record_successful_login,
    generate_reset_token,
    verify_reset_token,
    check_registration_rate_limit
)

auth_bp = Blueprint("auth", __name__)


def _get_society():
    return Society.query.first()


def _get_society_id():
    soc = _get_society()
    return soc.id if soc else 1


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role == "secretary":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("member.dashboard"))

    society = _get_society()

    if request.method == "POST":
        login_type = request.form.get("login_type", "member").strip().lower()
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not identifier or not password:
            flash("Please enter your credentials.", "warning")
            return render_template("login.html", society=society, login_type=login_type, identifier=identifier)

        # Lookup user: by email or mobile (for members)
        user = None
        if "@" in identifier:
            user = User.query.filter(db.func.lower(User.email) == identifier.lower()).first()
        else:
            is_valid_mob, clean_mob = clean_and_validate_mobile(identifier)
            if is_valid_mob:
                user = User.query.filter_by(mobile=clean_mob).first()

        # If user not found, small constant-time delay and generic message
        if not user:
            time.sleep(0.25)
            AuditLog.log(
                _get_society_id(),
                "LOGIN_FAILED",
                details=f"Login failed: User '{identifier}' not found",
                ip_address=request.remote_addr
            )
            flash("Invalid credentials.", "danger")
            return render_template("login.html", society=society, login_type=login_type, identifier=identifier)

        # Check account lockout
        locked, remaining_mins = is_user_locked(user)
        if locked:
            flash(f"Too many failed attempts. Try again in {remaining_mins} minutes.", "danger")
            return render_template("login.html", society=society, login_type=login_type, identifier=identifier)

        # Verify password
        if not check_password_hash(user.password_hash, password):
            record_failed_login(user)
            AuditLog.log(
                _get_society_id(),
                "LOGIN_FAILED",
                user_id=user.id,
                details=f"Invalid password attempt for {user.email}",
                ip_address=request.remote_addr
            )
            flash("Invalid credentials.", "danger")
            return render_template("login.html", society=society, login_type=login_type, identifier=identifier)

        # Check approval status
        if user.approval_status == "pending":
            flash("Your registration is awaiting admin approval.", "warning")
            return render_template("login.html", society=society, login_type=login_type, identifier=identifier)

        if user.approval_status == "rejected":
            reason_str = f" Reason: {user.rejection_reason}" if user.rejection_reason else ""
            flash(f"Your registration was not approved. Please contact the society office.{reason_str}", "danger")
            return render_template("login.html", society=society, login_type=login_type, identifier=identifier)

        # Check active status
        if not user.is_active:
            flash("Your account is inactive. Contact the society office.", "danger")
            return render_template("login.html", society=society, login_type=login_type, identifier=identifier)

        # Role vs. Tab check
        if login_type == "admin" and user.role != "secretary":
            flash("This is not an admin account. Please use Member Login.", "warning")
            return render_template("login.html", society=society, login_type="member", identifier=identifier)

        if login_type == "member" and user.role == "secretary":
            flash("This is an admin account. Please use Admin Login.", "warning")
            return render_template("login.html", society=society, login_type="admin", identifier=identifier)

        # Authentication success
        record_successful_login(user)
        login_user(user, remember=remember)

        AuditLog.log(
            _get_society_id(),
            "LOGIN_SUCCESS",
            user_id=user.id,
            details=f"User {user.email} logged in successfully via {login_type} tab (remember={remember})",
            ip_address=request.remote_addr
        )

        # If user must change password
        if user.must_change_password:
            flash("You must set a new password before proceeding.", "info")
            return redirect(url_for("auth.change_password"))

        # Redirection
        next_url = safe_next_url(request.args.get("next"))
        if next_url:
            return redirect(next_url)

        if user.role == "secretary":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("member.dashboard"))

    return render_template("login.html", society=society, login_type="member")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    if current_user.is_authenticated:
        AuditLog.log(
            _get_society_id(),
            "LOGOUT",
            user_id=current_user.id,
            details=f"User {current_user.email} signed out",
            ip_address=request.remote_addr
        )
        logout_user()
    flash("You have been signed out successfully.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        if current_user.role == "secretary":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("member.dashboard"))

    society = _get_society()
    buildings = Building.query.filter_by(status=True).all()
    wings = Wing.query.filter_by(status=True).all()

    if request.method == "POST":
        # Rate limit check: max 5 per IP per hour
        if check_registration_rate_limit(request.remote_addr):
            flash("Too many registration attempts from this network. Please try again later.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings)

        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile_raw = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        flat_id = request.form.get("flat_id")
        relation_type = request.form.get("relation_type", "Owner").strip()
        notes = request.form.get("notes", "").strip()[:300]
        consent = request.form.get("consent")

        form_data = {
            "full_name": full_name,
            "email": email,
            "mobile": mobile_raw,
            "relation_type": relation_type,
            "notes": notes,
            "building_id": request.form.get("building_id"),
            "wing_id": request.form.get("wing_id"),
            "flat_id": flat_id
        }

        # 1. Consent validation
        if not consent:
            flash("You must confirm that the submitted details are correct.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        # 2. Name validation
        ok_name, name_err = validate_full_name(full_name)
        if not ok_name:
            flash(name_err, "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        # 3. Email validation
        if not email or "@" not in email or "." not in email:
            flash("A valid email address is required.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        existing_email = User.query.filter(db.func.lower(User.email) == email).first()
        if existing_email:
            flash("An account with this email address already exists.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        # 4. Mobile validation
        ok_mob, mobile_cleaned = clean_and_validate_mobile(mobile_raw)
        if not ok_mob:
            flash(mobile_cleaned, "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        existing_mobile = User.query.filter_by(mobile=mobile_cleaned).first()
        if existing_mobile:
            flash("An account with this mobile number already exists.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        # 5. Password validation
        ok_pwd, pwd_err = validate_password_policy(password, email=email, full_name=full_name)
        if not ok_pwd:
            flash(pwd_err, "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        if password != confirm_password:
            flash("Password and confirm password do not match.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        # 6. Flat validation
        if not flat_id:
            flash("Please select your flat.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        flat = db.session.get(Flat, int(flat_id))
        if not flat or not flat.status:
            flash("Selected flat does not exist or is inactive.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        if relation_type not in ("Owner", "Tenant", "Family Member"):
            relation_type = "Owner"

        # Check existing pending request for this flat from this email
        pending_req = (
            RegistrationRequest.query
            .join(User, RegistrationRequest.user_id == User.id)
            .filter(
                RegistrationRequest.requested_flat_id == flat.id,
                RegistrationRequest.status == "pending",
                db.func.lower(User.email) == email
            )
            .first()
        )
        if pending_req:
            flash("A registration request for this flat is already pending approval.", "warning")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

        # Execute single atomic transaction
        try:
            # 1. Create User (ALWAYS role='member', never from form)
            new_user = User(
                full_name=full_name,
                email=email,
                mobile=mobile_cleaned,
                password_hash=generate_password_hash(password),
                role="member",
                approval_status="pending",
                is_active=False,
                failed_attempts=0,
                must_change_password=False
            )
            db.session.add(new_user)
            db.session.flush()

            # 2. Create RegistrationRequest
            req_entry = RegistrationRequest(
                user_id=new_user.id,
                requested_flat_id=flat.id,
                relation_type=relation_type,
                notes=notes,
                status="pending"
            )
            db.session.add(req_entry)

            # 3. Create Admin Notifications
            wing_name = flat.floor.wing.name if flat.floor and flat.floor.wing else ""
            room_label = f"Flat {wing_name}-{flat.flat_number}" if wing_name else f"Flat {flat.flat_number}"
            admins = User.query.filter_by(role="secretary", is_active=True).all()
            for admin in admins:
                db.session.add(Notification(
                    user_id=admin.id,
                    title="New Member Registration",
                    message=f"New registration: {full_name} ({room_label} - {relation_type})",
                    link_url="/admin/requests?status=pending",
                    kind="registration"
                ))

            db.session.commit()

            # 4. Write Audit Log
            AuditLog.log(
                _get_society_id(),
                "REGISTER",
                user_id=new_user.id,
                entity_type="RegistrationRequest",
                entity_id=req_entry.id,
                details=f"Self-registration submitted by {full_name} for {room_label} ({relation_type})",
                ip_address=request.remote_addr
            )

            return redirect(url_for("auth.register_submitted"))

        except Exception as e:
            db.session.rollback()
            flash("An error occurred during registration. Please try again.", "danger")
            return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data=form_data)

    return render_template("register.html", society=society, buildings=buildings, wings=wings, form_data={})


@auth_bp.route("/register/submitted")
def register_submitted():
    society = _get_society()
    return render_template("register_submitted.html", society=society)


@auth_bp.route("/api/register/wings")
def api_wings():
    building_id = request.args.get("building_id")
    query = Wing.query.filter_by(status=True)
    if building_id:
        query = query.filter_by(building_id=int(building_id))
    wings = query.order_by(Wing.name.asc()).all()
    return jsonify([{"id": w.id, "name": w.name, "building_id": w.building_id} for w in wings])


@auth_bp.route("/api/register/flats")
def api_flats():
    wing_id = request.args.get("wing_id")
    if not wing_id:
        return jsonify([])

    flats = (
        Flat.query
        .join(Floor, Flat.floor_id == Floor.id)
        .filter(Floor.wing_id == int(wing_id), Flat.status.is_(True))
        .order_by(Flat.flat_number.asc())
        .all()
    )
    return jsonify([{
        "id": f.id,
        "flat_number": f.flat_number,
        "floor": f.floor.floor_number if f.floor else None,
        "flat_type": f.flat_type or "Residential"
    } for f in flats])


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    society = _get_society()

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(current_user.password_hash, current_password):
            flash("Current password does not match.", "danger")
            return render_template("change_password.html", society=society)

        ok_pwd, pwd_err = validate_password_policy(new_password, email=current_user.email, full_name=current_user.full_name)
        if not ok_pwd:
            flash(pwd_err, "danger")
            return render_template("change_password.html", society=society)

        if new_password != confirm_password:
            flash("New password and confirmation do not match.", "danger")
            return render_template("change_password.html", society=society)

        current_user.password_hash = generate_password_hash(new_password)
        current_user.must_change_password = False
        db.session.commit()

        AuditLog.log(
            _get_society_id(),
            "PASSWORD_CHANGE",
            user_id=current_user.id,
            details=f"User {current_user.email} updated their password",
            ip_address=request.remote_addr
        )

        flash("Your password has been changed successfully.", "success")
        if current_user.role == "secretary":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("member.dashboard"))

    return render_template("change_password.html", society=society)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    society = _get_society()
    mail_server = current_app.config.get("MAIL_SERVER") or ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not mail_server:
            # SMTP not configured
            flash("Please contact the society office to reset your password.", "info")
            return render_template("forgot_password.html", society=society, mail_configured=False)

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for("auth.reset_password", token=token, _external=True)

            # Send email via SMTP if configured
            try:
                msg = MIMEText(
                    f"Hello {user.full_name},\n\n"
                    f"You requested a password reset for {society.name if society else 'the society portal'}.\n"
                    f"Click the link below to set a new password (valid for 30 minutes):\n\n"
                    f"{reset_url}\n\n"
                    f"If you did not request this, please ignore this email.\n"
                )
                msg["Subject"] = f"Password Reset Request | {society.name if society else 'Society'}"
                msg["From"] = current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@society.local")
                msg["To"] = user.email

                port = int(current_app.config.get("MAIL_PORT", 587))
                with smtplib.SMTP(mail_server, port, timeout=10) as server:
                    if current_app.config.get("MAIL_USE_TLS", True):
                        server.starttls()
                    if current_app.config.get("MAIL_USERNAME"):
                        server.login(current_app.config["MAIL_USERNAME"], current_app.config.get("MAIL_PASSWORD", ""))
                    server.send_message(msg)

                AuditLog.log(
                    _get_society_id(),
                    "FORGOT_PASSWORD_REQUEST",
                    user_id=user.id,
                    details=f"Password reset link sent to {user.email}",
                    ip_address=request.remote_addr
                )
            except Exception as e:
                flash("Could not send reset email. Please contact the society office.", "danger")
                return render_template("forgot_password.html", society=society, mail_configured=True)

        flash("If your email is registered, password reset instructions have been sent.", "info")
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html", society=society, mail_configured=bool(mail_server))


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    society = _get_society()
    email = verify_reset_token(token)

    if not email:
        flash("Password reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if not user:
        flash("Account not found.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        ok_pwd, pwd_err = validate_password_policy(new_password, email=user.email, full_name=user.full_name)
        if not ok_pwd:
            flash(pwd_err, "danger")
            return render_template("reset_password.html", society=society, token=token)

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html", society=society, token=token)

        user.password_hash = generate_password_hash(new_password)
        user.must_change_password = False
        user.failed_attempts = 0
        user.locked_until = None
        db.session.commit()

        AuditLog.log(
            _get_society_id(),
            "PASSWORD_RESET_TOKEN",
            user_id=user.id,
            details=f"User {user.email} reset password using security token",
            ip_address=request.remote_addr
        )

        flash("Your password has been reset successfully. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", society=society, token=token)
