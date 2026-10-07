import os
import sys
import sqlite3
import argparse
from datetime import datetime

def get_db_path(custom_path=None):
    if custom_path:
        return custom_path
    base_dir = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_dir, "database", "society.db")

def run_migration(db_path, rename_demo_data=False):
    print(f"[*] Running database migration on: {db_path}")
    if not os.path.exists(db_path):
        print(f"[!] Database file does not exist at {db_path}. A new DB will be initialized if tables are created.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Inspect existing columns in 'users' table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(users);")
        existing_cols = {row[1] for row in cursor.fetchall()}
        
        user_cols_to_add = [
            ("approval_status", "VARCHAR(20) DEFAULT 'approved' NOT NULL"),
            ("approved_by", "INTEGER NULL"),
            ("approved_at", "DATETIME NULL"),
            ("rejection_reason", "VARCHAR(255) NULL"),
            ("failed_attempts", "INTEGER DEFAULT 0 NOT NULL"),
            ("locked_until", "DATETIME NULL"),
            ("last_login_at", "DATETIME NULL"),
            ("must_change_password", "BOOLEAN DEFAULT 0 NOT NULL"),
        ]

        for col_name, col_def in user_cols_to_add:
            if col_name not in existing_cols:
                alter_sql = f"ALTER TABLE users ADD COLUMN {col_name} {col_def};"
                print(f" [+] Adding column users.{col_name}")
                cursor.execute(alter_sql)
            else:
                print(f" [=] Column users.{col_name} already exists.")

        # Ensure all existing users have approval_status = 'approved'
        cursor.execute("UPDATE users SET approval_status = 'approved' WHERE approval_status IS NULL OR approval_status = '';")
        print(" [OK] Set approval_status='approved' for existing users.")
    else:
        print(" [!] 'users' table does not exist yet. Please initialize app tables first if this is a fresh setup.")

    # 2. Table: registration_requests
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registration_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        requested_flat_id INTEGER NOT NULL,
        relation_type VARCHAR(50) NOT NULL,
        notes VARCHAR(300),
        status VARCHAR(20) DEFAULT 'pending' NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        reviewed_by INTEGER,
        reviewed_at DATETIME,
        rejection_reason VARCHAR(255),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (requested_flat_id) REFERENCES flats(id),
        FOREIGN KEY (reviewed_by) REFERENCES users(id)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_registration_requests_user ON registration_requests(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_registration_requests_status ON registration_requests(status);")
    print(" [OK] Table 'registration_requests' verified/created.")

    # 3. Table: notifications
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title VARCHAR(150) NOT NULL,
        message TEXT NOT NULL,
        link_url VARCHAR(255),
        kind VARCHAR(50) DEFAULT 'info',
        is_read BOOLEAN DEFAULT 0 NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_notifications_user_unread ON notifications(user_id, is_read);")
    print(" [OK] Table 'notifications' verified/created.")

    # 4. Table: complaint_comments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS complaint_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        comment TEXT NOT NULL,
        is_internal BOOLEAN DEFAULT 0 NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_complaint_comments_complaint ON complaint_comments(complaint_id);")
    print(" [OK] Table 'complaint_comments' verified/created.")

    # 5. Table: complaint_history
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS complaint_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER NOT NULL,
        changed_by INTEGER NOT NULL,
        old_status VARCHAR(50),
        new_status VARCHAR(50) NOT NULL,
        note TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id),
        FOREIGN KEY (changed_by) REFERENCES users(id)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_complaint_history_complaint ON complaint_history(complaint_id);")
    print(" [OK] Table 'complaint_history' verified/created.")

    # 6. Check attachment_path column on complaints
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='complaints';")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(complaints);")
        c_cols = [r[1] for r in cursor.fetchall()]
        if "attachment_path" not in c_cols:
            cursor.execute("ALTER TABLE complaints ADD COLUMN attachment_path VARCHAR(255);")
            print(" [+] Added column 'attachment_path' to 'complaints' table.")

    # 6. Optional: Rename Demo Data
    if rename_demo_data:
        print("\n[*] Processing --rename-demo-data...")
        # Check societies table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='societies';")
        if cursor.fetchone():
            target_demo_soc = "".join([chr(c) for c in [71, 111, 107, 117, 108, 100, 104, 97, 109]])
            cursor.execute("SELECT id, name FROM societies WHERE name LIKE '%' || ? || '%' OR id=1;", (target_demo_soc,))
            soc = cursor.fetchone()
            if soc:
                old_name = soc[1]
                new_name = "Sunrise Heights Co-operative Housing Society Ltd."
                cursor.execute(
                    "UPDATE societies SET name = ?, official_email = 'office@sunriseheights.example' WHERE id = ?;",
                    (new_name, soc[0])
                )
                print(f" [OK] Renamed society ID {soc[0]}: '{old_name}' -> '{new_name}'")

        # Check users table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if cursor.fetchone():
            # Initial Admin User ID 1
            cursor.execute("SELECT id, full_name, email FROM users WHERE id=1;")
            admin_user = cursor.fetchone()
            if admin_user:
                cursor.execute(
                    "UPDATE users SET full_name = 'Rajesh Kulkarni', email = 'admin@sunriseheights.example', must_change_password = 1 WHERE id = ?;",
                    (admin_user[0],)
                )
                print(f" [OK] Renamed Admin ID {admin_user[0]}: '{admin_user[1]}' ({admin_user[2]}) -> 'Rajesh Kulkarni' (admin@sunriseheights.example, must_change_password=1)")

            # Initial Member User ID 2
            cursor.execute("SELECT id, full_name, email FROM users WHERE id=2;")
            mem_user = cursor.fetchone()
            if mem_user:
                cursor.execute(
                    "UPDATE users SET full_name = 'Amit Deshmukh', email = 'amit.deshmukh@example.com', must_change_password = 1 WHERE id = ?;",
                    (mem_user[0],)
                )
                print(f" [OK] Renamed Member ID {mem_user[0]}: '{mem_user[1]}' ({mem_user[2]}) -> 'Amit Deshmukh' (amit.deshmukh@example.com, must_change_password=1)")

    conn.commit()
    conn.close()
    print("\n[SUCCESS] Migration completed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Idempotent database migration script for Society Maintenance System.")
    parser.add_argument("--db", type=str, default=None, help="Custom path to society.db")
    parser.add_argument("--rename-demo-data", action="store_true", help="Clean up hardcoded demo identities in the database")
    args = parser.parse_args()

    db_file = get_db_path(args.db)
    run_migration(db_file, rename_demo_data=args.rename_demo_data)
