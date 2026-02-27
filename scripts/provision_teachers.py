"""
Provision Microsoft 365 accounts for teachers and assign A1 faculty licenses.

Reads teacher data from data/teachers.json (produced by parse_teachers.py),
creates accounts in Azure AD, and assigns Office 365 A1 for faculty licenses.

Usage:
    python scripts/provision_teachers.py                # dry-run (default)
    python scripts/provision_teachers.py --dry-run      # explicit dry-run
    python scripts/provision_teachers.py --execute       # create accounts for real

Pre-requisites:
    - App registration must have User.ReadWrite.All (application) permission
    - Admin consent must be granted
    - data/teachers.json must exist (run parse_teachers.py first)

Output:
    reports/provision_YYYY-MM-DD_HHMMSS.json
"""

import argparse
import io
import json
import secrets
import string
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding for accented characters
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add scripts dir to path for config import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    DOMAIN,
    get_token,
    graph_get_all,
    graph_post,
    resolve_license_sku,
)


def strip_accents(text):
    """Remove accents from characters (e.g., é -> e, ü -> u)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def generate_upn(firstname, lastname, existing_upns):
    """Generate a unique userPrincipalName.

    Format: firstname.lastname@domain (lowercase, no accents)
    Handles collisions by appending a number: firstname.lastname2@domain
    """
    fn = strip_accents(firstname).lower().replace(" ", "").replace("-", "")
    ln = strip_accents(lastname).lower().replace(" ", ".").replace("-", "")

    # Remove any non-alphanumeric chars except dots
    fn = "".join(c for c in fn if c.isalnum())
    ln = "".join(c for c in ln if c.isalnum() or c == ".")

    base = f"{fn}.{ln}"
    candidate = f"{base}@{DOMAIN}"

    if candidate.lower() not in existing_upns:
        return candidate

    # Collision — append incrementing number
    counter = 2
    while True:
        candidate = f"{base}{counter}@{DOMAIN}"
        if candidate.lower() not in existing_upns:
            return candidate
        counter += 1


def generate_temp_password(length=16):
    """Generate a random temporary password meeting complexity requirements."""
    # Ensure at least one of each required category
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice("!@#$%&*?")

    remaining_length = length - 4
    pool = string.ascii_letters + string.digits + "!@#$%&*?"
    remaining = "".join(secrets.choice(pool) for _ in range(remaining_length))

    # Shuffle all characters together
    password_chars = list(upper + lower + digit + special + remaining)
    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


def fetch_existing_users(token):
    """Fetch all existing users from the tenant. Returns a dict keyed by lowercase UPN."""
    print("Fetching existing users from tenant...")
    result = graph_get_all(
        token,
        "/users?$select=id,displayName,userPrincipalName,accountEnabled,assignedLicenses&$top=999",
    )
    if "error" in result:
        print(f"Failed to fetch users: {result}")
        sys.exit(1)

    users = {}
    for u in result.get("value", []):
        upn = u.get("userPrincipalName", "").lower()
        users[upn] = u
    print(f"Found {len(users)} existing users in tenant.")
    return users


def create_user(token, display_name, upn, mail_nickname, password):
    """Create a new user via POST /users."""
    body = {
        "accountEnabled": True,
        "displayName": display_name,
        "mailNickname": mail_nickname,
        "userPrincipalName": upn,
        "usageLocation": "CH",
        "passwordProfile": {
            "password": password,
            "forceChangePasswordNextSignIn": True,
        },
    }
    resp = graph_post(token, "/users", body)
    return resp


def assign_license(token, user_id, sku_id):
    """Assign a license to a user via POST /users/{id}/assignLicense."""
    body = {
        "addLicenses": [{"skuId": sku_id}],
        "removeLicenses": [],
    }
    resp = graph_post(token, f"/users/{user_id}/assignLicense", body)
    return resp


def main():
    parser = argparse.ArgumentParser(
        description="Provision Microsoft 365 accounts for teachers"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview what would happen without making changes (default)",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        help="Actually create accounts and assign licenses",
    )
    parser.add_argument(
        "--input",
        default="data/teachers.json",
        help="Path to teachers JSON file",
    )
    args = parser.parse_args()

    is_dry_run = not args.execute
    mode_label = "DRY-RUN" if is_dry_run else "EXECUTE"

    # Resolve paths
    project_root = Path(__file__).resolve().parent.parent
    input_path = project_root / args.input

    if not input_path.exists():
        print(f"Error: teachers file not found at {input_path}")
        print("Run parse_teachers.py first to generate it.")
        return 1

    with open(input_path, "r", encoding="utf-8") as f:
        teachers = json.load(f)

    print("=" * 60)
    print(f"TEACHER ACCOUNT PROVISIONING [{mode_label}]")
    print("=" * 60)
    print(f"Teachers in list: {len(teachers)}")
    print(f"Domain: {DOMAIN}")
    print()

    # Authenticate
    token = get_token()
    print("Authenticated successfully.")

    # Fetch existing users
    existing_users = fetch_existing_users(token)
    existing_upns = set(existing_users.keys())

    # Resolve license SKU ID (not required for dry-run)
    sku_id = resolve_license_sku(token, required=not is_dry_run)
    print(f"License SKU ID: {sku_id or '(will resolve at execution time)'}")
    print()

    # Process each teacher
    actions = []
    created_count = 0
    skipped_count = 0
    failed_count = 0
    license_count = 0

    # Track UPNs we're generating in this run (for collision detection)
    run_upns = set(existing_upns)

    for teacher in teachers:
        firstname = teacher["firstname"]
        lastname = teacher["lastname"]
        display_name = f"{firstname} {lastname}"

        upn = generate_upn(firstname, lastname, run_upns)
        mail_nickname = upn.split("@")[0]

        # Check if user already exists (match on UPN or displayName)
        already_exists = False
        existing_match = None

        if upn.lower() in existing_upns:
            already_exists = True
            existing_match = existing_users[upn.lower()]

        if not already_exists:
            # Also check by display name (case-insensitive)
            for eu in existing_users.values():
                if eu.get("displayName", "").lower() == display_name.lower():
                    already_exists = True
                    existing_match = eu
                    break

        if already_exists:
            action_record = {
                "name": display_name,
                "upn": existing_match.get("userPrincipalName", upn),
                "action": "skipped",
                "reason": "already exists",
            }
            actions.append(action_record)
            skipped_count += 1
            print(f"  SKIP  {display_name:30s} (already exists as {existing_match.get('userPrincipalName', '?')})")
            continue

        # Track this UPN so subsequent teachers don't collide
        run_upns.add(upn.lower())

        temp_password = generate_temp_password()

        if is_dry_run:
            action_record = {
                "name": display_name,
                "upn": upn,
                "action": "would_create",
                "license": "Office 365 A1 for faculty",
                "temp_password": "(dry-run)",
            }
            actions.append(action_record)
            created_count += 1
            license_count += 1
            print(f"  CREATE {display_name:30s} -> {upn}")
        else:
            # Actually create the user
            resp = create_user(token, display_name, upn, mail_nickname, temp_password)
            if resp.status_code == 201:
                user_data = resp.json()
                user_id = user_data["id"]
                created_count += 1
                print(f"  CREATED {display_name:30s} -> {upn}")

                # Assign license
                lic_resp = assign_license(token, user_id, sku_id)
                if lic_resp.status_code == 200:
                    license_count += 1
                    action_record = {
                        "name": display_name,
                        "upn": upn,
                        "action": "created",
                        "user_id": user_id,
                        "license": "Office 365 A1 for faculty",
                        "temp_password": temp_password,
                    }
                else:
                    action_record = {
                        "name": display_name,
                        "upn": upn,
                        "action": "created",
                        "user_id": user_id,
                        "license_error": f"{lic_resp.status_code}: {lic_resp.text[:200]}",
                        "temp_password": temp_password,
                    }
                    print(f"    WARNING: License assignment failed: {lic_resp.status_code}")
                actions.append(action_record)
            else:
                failed_count += 1
                error_text = resp.text[:300]
                action_record = {
                    "name": display_name,
                    "upn": upn,
                    "action": "failed",
                    "error": f"{resp.status_code}: {error_text}",
                }
                actions.append(action_record)
                print(f"  FAILED {display_name:30s} -> {resp.status_code}: {error_text[:80]}")

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Mode:             {mode_label}")
    print(f"  Total in list:    {len(teachers)}")
    print(f"  Already existed:  {skipped_count}")
    print(f"  {'Would create' if is_dry_run else 'Created':16s}: {created_count}")
    print(f"  Failed:           {failed_count}")
    print(f"  License assigned: {license_count}")
    print()

    # Write report
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "dry-run" if is_dry_run else "execute",
        "summary": {
            "total_in_list": len(teachers),
            "already_existed": skipped_count,
            "created": created_count,
            "failed": failed_count,
            "license_assigned": license_count,
        },
        "actions": actions,
    }

    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"provision_{timestamp}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report written to: {report_path}")

    return 0


if __name__ == "__main__":
    exit(main())
