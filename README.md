# Housing Society Maintenance System

A modern, production-grade Cooperative Housing Society Management & Maintenance web application built with **Flask**, **Flask-SQLAlchemy**, **Flask-Login**, and **SQLite**.

Designed for seamless administration by society secretaries and intuitive self-service access by resident flat owners and tenants.

---

## 🌟 Key Features

### 1. Robust Authentication & Resident Onboarding
- **Tabbed Login**: Clear separation between Resident Member and Secretary/Admin logins.
- **Self-Service Registration**: Residents register with full name, email, mobile, and select their wing & flat number. Registered accounts default to role `member` and status `pending`.
- **Account Lockout & Rate Limiting**: Automatic 10-minute lockout after 5 consecutive failed login attempts; IP-based registration rate limiting (max 10 requests per hour).
- **Session Security**: Open-redirect protection via `safe_next_url`, and complete session termination on logout.

### 2. Secretary & Admin Management Panel
- **Executive Dashboard**: Real-time billing summary, monthly collection rates, total outstanding dues, building/flat occupancy statistics, and prioritized defaulters table.
- **Resident Approval Workflow**:
  - Review pending registration requests.
  - Approve requests (automatically activates flat assignment and handles primary owner conflicts gracefully).
  - Reject requests with mandatory reason (minimum 5 characters) displayed to the applicant.
  - Reset member passwords on demand.

### 3. Resident Member Portal
- **Multi-Property Context Switcher**: Seamlessly toggle between multiple owned or rented flats.
- **Financial Status Overview**: Dynamic outstanding dues card (highlighted in red if due or green "All Clear"), last payment made, and 12-month billing history.
- **Invoice Breakdown**: Detailed line items per bill (subtotal, late fee penalties, total), instant receipt downloads, and status filtering.
- **Profile Management**: Update contact details with strict mobile validation and automatic audit logging.

### 4. Room-Centric Helpdesk & Complaints
- **Room-Centric Tracking**: Complaints are organized and searched by room number (e.g., `A-101`).
- **File & Photo Evidence**: Residents can upload supporting images or documents (PNG, JPG, PDF up to 2MB) stored securely with UUIDs.
- **Resolution Control**: Transitioning tickets to "Resolved" strictly enforces mandatory resolution notes (minimum 5 characters) and automatically dispatches member notifications.
- **Internal Staff Notes**: Committee members can post private notes hidden from residents, while public comments support two-way resident communication.
- **Cross-Member Isolation**: Strict 403 Forbidden enforcement on accessing complaints belonging to other residents.

### 5. Professional Branding & Indian Localization
- **Dynamic Titles**: `<Page> | <Society Name>` dynamically rendered across all templates.
- **Society Logo Upload**: Upload society emblem in Society Settings (`uploads/logos/`) and preview across headers, bills, and receipts.
- **Indian Currency Formatting**: Native `₹` currency filter with Indian comma grouping (e.g., `₹1,25,000.00`).
- **Modern UI**: Dark-mode glassmorphic theme with Google Fonts (`Outfit` & `Plus Jakarta Sans`), responsive tables, and micro-interactions.

### 6. Security & Audit Trail
- **CSRF Protection**: Universal Flask-WTF CSRF tokens on all POST requests.
- **Security Headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: same-origin` on all HTTP responses.
- **Comprehensive Audit Log**: Tracks logins, logouts, complaint submissions, status changes, profile edits, and unauthorized access attempts.

---

## 🏗️ Architecture

```
society-maintenance-system/
├── app.py                      # Flask app initialization, context processors, global error handlers
├── config.py                   # Environment and DB configuration
├── migrate.py                  # Idempotent database schema migration runner
├── create_secretary.py         # CLI utility to create the initial admin account
├── models/                     # SQLAlchemy data models
│   ├── user.py                 # Users with role, approval status, lockout attributes
│   ├── society.py              # Society legal info and logo filename
│   ├── building.py, wing.py    # Society structure hierarchy
│   ├── floor.py, flat.py       # Flats with occupancy and floor links
│   ├── flat_member.py          # Member-flat mappings (Owner / Tenant)
│   ├── registration_request.py # Resident registration requests
│   ├── complaint.py            # Complaints with room links & attachments
│   ├── complaint_history.py    # Status transition history
│   ├── complaint_comment.py    # Public and internal comments
│   ├── maintenance_bill.py     # Invoices and line items
│   ├── maintenance_payment.py  # Payment records
│   ├── notification.py         # In-app notifications
│   └── audit_log.py            # Immutable system audit trail
├── routes/                     # Blueprint modular controllers
│   ├── auth.py                 # Login, logout, register, password reset
│   ├── admin.py                # Secretary dashboard, requests approval/rejection
│   ├── member.py               # Resident dashboard, bill history, profile
│   ├── complaints.py           # Room-centric helpdesk, uploads, resolutions
│   └── notifications.py        # Notification center
├── services/                   # Business logic services
│   ├── auth.py                 # Lockouts, rate limits, token generation
│   ├── billing.py              # Financial summaries, defaulter calculations
│   └── notifications.py        # In-app notification creation
├── static/                     # CSS, JS, and vendor assets
│   ├── css/main.css            # Design system tokens and glassmorphic styling
│   └── js/main.js              # Theme and responsive interactions
├── templates/                  # Jinja2 templates extending base.html
└── tests/                      # Automated pytest test suite
    ├── test_auth.py            # Authentication, lockouts, registration
    ├── test_admin_requests.py  # Request approval, conflict resolution
    ├── test_member_dashboard.py# Resident dashboard, dues, access control
    ├── test_complaints.py      # Room-centric complaints, uploads, timeline
    ├── test_branding.py        # INR format, dynamic titles, logo upload
    └── test_security.py        # CSRF, security headers, demo scrub check
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Virtualenv (`python -m venv .venv`)

### Installation & Setup

1. **Clone & Setup Virtual Environment**:
   ```bash
   git clone <repo-url>
   cd society-maintenance-system
   python -m venv .venv
   source .venv/bin/activate      # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   Create a `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```
   Configure your environment variables:
   ```ini
   SECRET_KEY=your-production-secret-key-here
   DATABASE_PATH=database/society.db
   FLASK_ENV=development
   ```

3. **Run Schema Migrations**:
   The migration script is idempotent and safely applies all table definitions and column additions without data loss:
   ```bash
   python migrate.py
   ```

4. **Create Initial Secretary / Admin**:
   Run the CLI utility to create your initial administrator account:
   ```bash
   python create_secretary.py
   ```

5. **Run the Application**:
   ```bash
   python app.py
   ```
   Navigate to `http://127.0.0.1:5000` in your web browser.

---

## 🧪 Testing

The repository includes a comprehensive automated test suite testing all workflows and security controls:

```bash
pytest tests/ -v
```

### Test Suite Summary:
- **`tests/test_auth.py`**: Tests self-service registration, role enforcement, lockout after 5 failures, rate limiting, and open redirect protection.
- **`tests/test_admin_requests.py`**: Tests resident request listing, approval, duplicate primary owner conflict resolution, and rejection with mandatory notes.
- **`tests/test_member_dashboard.py`**: Tests multi-flat dues calculation, 12-month bill history, profile update audit logging, and 403 cross-member bill isolation.
- **`tests/test_complaints.py`**: Tests room-number complaint filing, image/document upload validation (PNG/JPG/PDF <= 2MB), room number search, mandatory resolution notes, timeline merging, and internal note isolation.
- **`tests/test_branding.py`**: Tests Indian currency formatting (`₹`), dynamic `<Page> | <Society Name>` titles, and society logo upload and serving.
- **`tests/test_security.py`**: Tests CSRF protection enforcement, HTTP security headers, and zero demo identity leftovers.

---

## 🛡️ Security Best Practices

1. **Universal CSRF Protection**: All POST forms include `{{ csrf_token() }}`.
2. **Access Control**: Every endpoint verifies `current_user.role` and strictly checks entity ownership before serving data or handling actions.
3. **Audit Trail**: Sensitive actions (`LOGIN`, `LOGOUT`, `APPROVE_REQUEST`, `REJECT_REQUEST`, `PROFILE_UPDATED`, `COMPLAINT_CREATED`, `COMPLAINT_UPDATED`, `UNAUTHORIZED_ACCESS_ATTEMPT`) are written to the database audit table.
4. **File Upload Safety**: Uploaded files use `secure_filename`, UUID prefixing, MIME type verification, extension whitelisting, and a strict 2MB limit threshold.
