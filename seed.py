import os
import sys
import argparse
from getpass import getpass
from werkzeug.security import generate_password_hash

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import app
from database.db import db
from models.user import User
from models.society import Society
from services.auth import validate_password_policy, clean_and_validate_mobile, validate_full_name


def run_seeder(force_new_admin=False, interactive=True, **kwargs):
    with app.app_context():
        print("\n==============================================")
        print("    SOCIETY MAINTENANCE INITIAL SEED WIZARD  ")
        print("==============================================\n")

        # Check existing admin
        existing_admin = User.query.filter_by(role="secretary").first()
        if existing_admin and not force_new_admin:
            print(f"[!] An active society administrator already exists ({existing_admin.email}).")
            print("    To overwrite or add an additional admin, re-run with --force-new-admin flag.\n")
            return False

        if interactive:
            print("Step 1: Housing Society Information")
            print("------------------------------------")
            soc_name = input("Society Name [Sunrise Heights Co-operative Housing Society Ltd.]: ").strip()
            if not soc_name:
                soc_name = "Sunrise Heights Co-operative Housing Society Ltd."

            soc_addr = input("Address: ").strip() or "Plot 104, Sunrise Heights Marg"
            soc_city = input("City [Mumbai]: ").strip() or "Mumbai"
            soc_state = input("State [Maharashtra]: ").strip() or "Maharashtra"
            soc_pin = input("Pincode [400001]: ").strip() or "400001"

            print("\nStep 2: Society Administrator / Secretary Setup")
            print("-----------------------------------------------")
            while True:
                admin_name = input("Admin Full Name: ").strip()
                ok, err = validate_full_name(admin_name)
                if ok:
                    break
                print(f"[!] {err}")

            while True:
                admin_email = input("Admin Email: ").strip().lower()
                if admin_email and "@" in admin_email and "." in admin_email:
                    # check uniqueness
                    if not User.query.filter_by(email=admin_email).first():
                        break
                    print("[!] User with this email already exists.")
                else:
                    print("[!] Please enter a valid email address.")

            while True:
                admin_mob = input("Admin Mobile (10 digits): ").strip()
                ok, mob_clean = clean_and_validate_mobile(admin_mob)
                if ok:
                    if not User.query.filter_by(mobile=mob_clean).first():
                        admin_mob = mob_clean
                        break
                    print("[!] User with this mobile already exists.")
                else:
                    print(f"[!] {mob_clean}")

            while True:
                password = getpass("Admin Password: ").strip()
                confirm = getpass("Confirm Password: ").strip()
                if password != confirm:
                    print("[!] Passwords do not match. Try again.")
                    continue
                ok, err = validate_password_policy(password, email=admin_email, full_name=admin_name)
                if ok:
                    break
                print(f"[!] {err}")
        else:
            soc_name = kwargs.get("soc_name", "Sunrise Heights Co-operative Housing Society Ltd.")
            soc_addr = kwargs.get("soc_addr", "Plot 104, Sunrise Heights Marg")
            soc_city = kwargs.get("soc_city", "Mumbai")
            soc_state = kwargs.get("soc_state", "Maharashtra")
            soc_pin = kwargs.get("soc_pin", "400001")
            admin_name = kwargs.get("admin_name", "Rajesh Kulkarni")
            admin_email = kwargs.get("admin_email", "admin@sunriseheights.example")
            admin_mob = kwargs.get("admin_mob", "9820011223")
            password = kwargs.get("password", "Admin@Secure2026")

        # 1. Society Record
        society = Society.query.first()
        if not society:
            society = Society(
                name=soc_name,
                address=soc_addr,
                city=soc_city,
                state=soc_state,
                pincode=soc_pin,
                official_email=admin_email
            )
            db.session.add(society)
            db.session.flush()
            print(f"[OK] Society '{society.name}' created.")
        else:
            society.name = soc_name
            society.address = soc_addr
            society.city = soc_city
            society.state = soc_state
            society.pincode = soc_pin
            print(f"[OK] Society '{society.name}' updated.")

        # 2. Administrator Record
        admin_user = User.query.filter_by(email=admin_email).first()
        if not admin_user:
            admin_user = User(
                full_name=admin_name,
                email=admin_email,
                mobile=admin_mob,
                password_hash=generate_password_hash(password),
                role="secretary",
                approval_status="approved",
                is_active=True,
                failed_attempts=0,
                must_change_password=False
            )
            db.session.add(admin_user)
            print(f"[OK] Admin user '{admin_user.full_name}' ({admin_user.email}) created.")
        else:
            admin_user.full_name = admin_name
            admin_user.mobile = admin_mob
            admin_user.password_hash = generate_password_hash(password)
            admin_user.role = "secretary"
            admin_user.approval_status = "approved"
            admin_user.is_active = True
            admin_user.failed_attempts = 0
            admin_user.must_change_password = False
            print(f"[OK] Admin user '{admin_user.full_name}' ({admin_user.email}) credentials reset.")

        db.session.commit()
        print("\n[SUCCESS] Initialization completed successfully! You can now log into the management portal.\n")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed housing society and initial administrator.")
    parser.add_argument("--force-new-admin", action="store_true", help="Force creation even if an administrator exists")
    parser.add_argument("--non-interactive", action="store_true", help="Run without prompts with default seed values")
    args = parser.parse_args()

    run_seeder(force_new_admin=args.force_new_admin, interactive=not args.non_interactive)
