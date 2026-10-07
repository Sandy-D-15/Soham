import re
import time
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict
from flask import abort, redirect, url_for, flash, request, current_app
from flask_login import current_user
from itsdangerous import URLSafeTimedSerializer
from database.db import db
from models.user import User


def role_required(*roles):
    """Decorator ensuring that the logged-in user possesses one of the allowed roles."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.path))
            if current_user.role not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def safe_next_url(target):
    """Allow only relative paths that start with '/' and not '//' or '/\'."""
    if not target:
        return None
    target = target.strip()
    if target.startswith("/") and not target.startswith("//") and not target.startswith("/\\"):
        return target
    return None


def validate_password_policy(password, email="", full_name=""):
    """
    Validate password:
    - Min 8 chars
    - At least 1 letter and 1 number
    - Not identical to email or full name
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."
    
    pwd_lower = password.strip().lower()
    if email and pwd_lower == email.strip().lower():
        return False, "Password cannot be identical to your email address."
    if full_name and pwd_lower == full_name.strip().lower():
        return False, "Password cannot be identical to your full name."
    return True, ""


def clean_and_validate_mobile(mobile_raw):
    """
    Normalizes mobile numbers:
    - Strips spaces, non-digits, leading +91 or 0
    - Enforces exactly 10 digits starting with 6, 7, 8, or 9
    """
    if not mobile_raw:
        return False, "Mobile number is required."
    digits = re.sub(r"\D", "", str(mobile_raw))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    
    if len(digits) == 10 and digits[0] in "6789":
        return True, digits
    return False, "Mobile number must be exactly 10 digits and start with 6, 7, 8, or 9."


def validate_full_name(name):
    """
    Validate full name:
    - 3-100 characters
    - Letters, spaces, '.', ''', '-' only
    """
    if not name or len(name.strip()) < 3 or len(name.strip()) > 100:
        return False, "Full name must be between 3 and 100 characters."
    if not re.match(r"^[A-Za-z\s\.\'\-]+$", name.strip()):
        return False, "Full name can only contain letters, spaces, dots, hyphens, and apostrophes."
    return True, ""


def is_user_locked(user):
    """Checks whether the user account is temporarily locked due to failed login attempts."""
    if user.locked_until and user.locked_until > datetime.utcnow():
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
        return True, remaining
    return False, 0


def record_failed_login(user):
    """
    Increments failed login attempts.
    After 5 attempts, sets locked_until = now + 10 mins and resets counter.
    """
    user.failed_attempts = (user.failed_attempts or 0) + 1
    if user.failed_attempts >= 5:
        user.locked_until = datetime.utcnow() + timedelta(minutes=10)
        user.failed_attempts = 0
    db.session.commit()


def record_successful_login(user):
    """Resets failed login attempts and updates last_login_at."""
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    db.session.commit()


def generate_reset_token(user_email):
    """Generates a secure signed token for password reset."""
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return s.dumps(user_email.strip().lower(), salt="password-reset-society-token")


def verify_reset_token(token, max_age_seconds=1800):
    """Validates password reset token within max age (default 30 mins)."""
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        email = s.loads(token, salt="password-reset-society-token", max_age=max_age_seconds)
        return email
    except Exception:
        return None


# Rate limiter for self-registration: max 5 attempts per IP per hour
_registration_attempts_by_ip = defaultdict(list)

def check_registration_rate_limit(ip_address, max_attempts=5, window_seconds=3600):
    """Returns True if rate limited, False if allowed."""
    if current_app and current_app.config.get("TESTING"):
        return False
    now = time.time()
    cutoff = now - window_seconds
    recent = [t for t in _registration_attempts_by_ip[ip_address] if t > cutoff]
    if len(recent) >= max_attempts:
        _registration_attempts_by_ip[ip_address] = recent
        return True
    recent.append(now)
    _registration_attempts_by_ip[ip_address] = recent
    return False
