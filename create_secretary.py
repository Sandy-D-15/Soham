#!/usr/bin/env python
"""
Legacy shortcut for seed.py.
Redirects to the new interactive seeder.
"""
import sys
from seed import run_seeder

if __name__ == "__main__":
    print("[*] create_secretary.py has been upgraded to seed.py.")
    force = "--force-new-admin" in sys.argv
    run_seeder(force_new_admin=force, interactive=True)