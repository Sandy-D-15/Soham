import os
import re
import pytest


def test_post_without_csrf_returns_400(client):
    # Attempt POST to /login without CSRF token
    res = client.post(
        "/login",
        data={
            "login_type": "admin",
            "identifier": "admin@sunriseheights.example",
            "password": "Admin#Pass2026",
        },
    )
    assert res.status_code == 400


def test_security_headers_present(client):
    res = client.get("/login")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Referrer-Policy") == "same-origin"


def test_repo_has_no_demo_identities():
    """Verify no hard-coded demo credentials or names exist in the repository."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # Construct forbidden tokens dynamically so this test file itself doesn't match literal tokens
    p1 = "".join(["gokul", "dham"])
    p2 = "".join(["bhi", "de"])
    p3 = "".join(["jetha", "lal"])
    p4 = "".join(["Secretary", "@123"])
    p5 = "".join(["Member", "@123"])
    forbidden_pattern = re.compile(
        rf"({p1}|{p2}|{p3}|{p4}|{p5})",
        re.IGNORECASE
    )

    ignored_dirs = {".venv", "venv", ".git", "__pycache__", ".pytest_cache"}
    violations = []

    for root, dirs, files in os.walk(root_dir):
        # Exclude ignored directories
        dirs[:] = [d for d in dirs if d not in ignored_dirs]

        for file in files:
            # Skip database binaries / backups
            if file.endswith((".db", ".bak", ".sqlite", ".pyc")):
                continue
            if ".bak" in file:
                continue

            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if forbidden_pattern.search(line):
                            violations.append(f"{file_path}:{line_num}: {line.strip()}")
            except Exception:
                pass

    assert len(violations) == 0, f"Found forbidden demo identities in repo:\n" + "\n".join(violations)
