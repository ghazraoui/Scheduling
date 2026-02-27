"""
Pull all tenant accounts with sign-in activity and generate an account review report.

Requires: AuditLog.Read.All (Application) permission for signInActivity.

Usage:
    python scripts/tenant_review.py
"""

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DOMAIN, get_token, graph_get, graph_get_all

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"

# SKU friendly names
SKU_NAMES = {
    "ENTERPRISEPACKPLUS_FACULTY": "Office 365 A5 for Faculty",
    "STANDARDWOFFPACK_FACULTY": "Office 365 A1 for Faculty",
    "OFFICESUBSCRIPTION_FACULTY": "Microsoft 365 Apps for Faculty",
    "FLOW_FREE": "Power Automate Free",
}


def main():
    print("Authenticating...")
    token = get_token()
    print("OK\n")

    # Fetch all users (v1.0 — no signInActivity, that needs Premium)
    print("Fetching all users...")
    endpoint = (
        "/users"
        "?$select=id,displayName,userPrincipalName,accountEnabled,"
        "createdDateTime,assignedLicenses,userType"
        "&$top=999"
    )
    result = graph_get_all(token, endpoint)
    if "error" in result:
        print(f"ERROR fetching users: {result}")
        sys.exit(1)
    all_users = result["value"]
    print(f"Fetched {len(all_users)} accounts")

    # Fetch Office 365 usage report for last-activity dates
    import requests
    print("Fetching Office 365 usage report (180-day window)...")
    headers = {"Authorization": f"Bearer {token}"}
    report_url = "https://graph.microsoft.com/v1.0/reports/getOffice365ActiveUserDetail(period='D180')"
    resp = requests.get(report_url, headers=headers)
    activity_map = {}  # upn -> last_activity_date
    if resp.status_code == 200:
        import csv
        import io as _io
        # Response is CSV
        text = resp.text
        # Sometimes starts with BOM
        if text.startswith("\ufeff"):
            text = text[1:]
        reader = csv.DictReader(_io.StringIO(text))
        for row in reader:
            upn = row.get("User Principal Name", "").lower()
            # Find the most recent activity across all products
            date_fields = [
                "Exchange Last Activity Date",
                "OneDrive Last Activity Date",
                "SharePoint Last Activity Date",
                "Skype For Business Last Activity Date",
                "Yammer Last Activity Date",
                "Teams Last Activity Date",
            ]
            latest = None
            for field in date_fields:
                val = row.get(field, "").strip()
                if val:
                    try:
                        dt = datetime.strptime(val, "%Y-%m-%d")
                        if latest is None or dt > latest:
                            latest = dt
                    except ValueError:
                        pass
            if latest:
                activity_map[upn] = latest
        print(f"  Activity data for {len(activity_map)} users")
    else:
        print(f"  WARNING: Could not fetch usage report ({resp.status_code})")
        print(f"  {resp.text[:300]}")
        print("  Continuing without activity data...")

    print()

    # Fetch SKU mapping
    skus_resp = graph_get(token, "/subscribedSkus")
    sku_map = {}
    if "error" not in skus_resp:
        for sku in skus_resp.get("value", []):
            sku_map[sku["skuId"]] = sku.get("skuPartNumber", "unknown")

    # Load teacher UPNs to exclude
    def _strip_accents(text):
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def _make_upn(firstname, lastname):
        fn = _strip_accents(firstname).lower().replace(" ", "").replace("-", "")
        ln = _strip_accents(lastname).lower().replace(" ", ".").replace("-", "")
        fn = "".join(c for c in fn if c.isalnum())
        ln = "".join(c for c in ln if c.isalnum() or c == ".")
        return f"{fn}.{ln}@{DOMAIN}"

    teachers_file = DATA_DIR / "teachers.json"
    teacher_upns = set()
    if teachers_file.exists():
        with open(teachers_file, encoding="utf-8") as f:
            teachers = json.load(f)
        for t in teachers:
            teacher_upns.add(_make_upn(t["firstname"], t["lastname"]).lower())

    # Process users
    now = datetime.now(timezone.utc)
    accounts = []
    for u in all_users:
        upn = u.get("userPrincipalName", "")

        # Get license info
        licenses = []
        for lic in u.get("assignedLicenses", []):
            sku_id = lic.get("skuId", "")
            part = sku_map.get(sku_id, sku_id)
            licenses.append(part)

        # Get activity from usage report
        last_activity = activity_map.get(upn.lower())
        days_inactive = None
        if last_activity:
            days_inactive = (now - last_activity.replace(tzinfo=timezone.utc)).days

        created = u.get("createdDateTime", "")
        created_date = ""
        age_str = ""
        if created:
            try:
                cd = datetime.fromisoformat(created.replace("Z", "+00:00"))
                created_date = cd.strftime("%Y-%m-%d")
                age_days = (now - cd).days
                if age_days >= 365:
                    age_str = f"{age_days / 365:.1f} yrs"
                elif age_days >= 30:
                    age_str = f"{age_days // 30} mo"
                else:
                    age_str = f"{age_days} days"
            except (ValueError, TypeError):
                pass

        is_teacher = upn.lower() in teacher_upns
        is_guest = u.get("userType") == "Guest"

        # License friendly name
        lic_display = "None"
        if licenses:
            friendly = []
            for l in licenses:
                friendly.append(SKU_NAMES.get(l, l))
            lic_display = ", ".join(friendly)

        # Format last activity
        activity_str = "Never"
        if last_activity:
            activity_str = last_activity.strftime("%Y-%m-%d")

        accounts.append({
            "id": u.get("id"),
            "name": u.get("displayName", ""),
            "upn": upn,
            "enabled": u.get("accountEnabled", False),
            "created": created_date,
            "age": age_str,
            "licenses": licenses,
            "license_display": lic_display,
            "is_teacher": is_teacher,
            "is_guest": is_guest,
            "user_type": u.get("userType", ""),
            "last_activity": activity_str,
            "days_inactive": days_inactive,
        })

    # Save raw JSON
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = REPORTS_DIR / "tenant_accounts_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    print(f"Raw data saved to {raw_path}")

    # Filter non-teacher accounts
    non_teacher = [a for a in accounts if not a["is_teacher"]]
    teachers_list = [a for a in accounts if a["is_teacher"]]

    print(f"\nTotal accounts: {len(accounts)}")
    print(f"Teacher accounts: {len(teachers_list)} (excluded from report)")
    print(f"Non-teacher accounts: {len(non_teacher)}")

    # Categorize
    disabled = [a for a in non_teacher if not a["enabled"]]
    guests = [a for a in non_teacher if a["is_guest"] and a["enabled"]]
    enabled_members = [a for a in non_teacher if a["enabled"] and not a["is_guest"]]

    # Explicit list of shared/functional mailbox UPN prefixes (before @)
    SHARED_UPNS = {
        "genevareception", "lausannereception", "headreceptionlau",
        "montreux.reception", "reception.fribourg", "reception.praha",
        "lausanneteachers", "esa.teachers", "sfs.teachers",
        "wse.teachers", "wseteachers2", "wseczteachers",
        "academic.coordinator", "intern", "marketing.lausanne",
        "marketingcz", "praguelearningcenter", "wseprague",
        "juniors.lausanne", "juniors.geneva", "test.teacher",
    }

    shared = []
    staff = []
    for a in enabled_members:
        local_part = a["upn"].split("@")[0].lower()
        if local_part in SHARED_UPNS:
            shared.append(a)
        else:
            staff.append(a)

    # Generate markdown report
    lines = []
    lines.append("# Microsoft 365 Tenant Account Review")
    lines.append("")
    lines.append(f"**Generated**: {now.strftime('%Y-%m-%d')}")
    lines.append("**Tenant**: swisslearninggroup.onmicrosoft.com")
    lines.append(f"**Total accounts**: {len(accounts)} ({len(teachers_list)} teacher accounts excluded)")
    lines.append(f"**Scope**: All non-teacher accounts — staff, shared mailboxes, guest users")
    lines.append(f"**Sign-in data**: Included (last activity date)")
    lines.append("")

    # Inactivity legend
    lines.append("> **Activity key**: Last Activity = most recent usage across Exchange, OneDrive, SharePoint, Teams (180-day window).")
    lines.append("> \"Never\" means no product usage was recorded. Days inactive = days since last activity.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # License summary
    lic_counts = {}
    for a in non_teacher:
        if not a["licenses"]:
            lic_counts["*(no license)*"] = lic_counts.get("*(no license)*", 0) + 1
        for l in a["licenses"]:
            display = SKU_NAMES.get(l, l)
            lic_counts[display] = lic_counts.get(display, 0) + 1

    lines.append("## License Summary (non-teacher accounts)")
    lines.append("")
    lines.append("| License | Count |")
    lines.append("|---------|-------|")
    for lic, count in sorted(lic_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {lic} | {count} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 1: Disabled accounts
    lines.append(f"## 1. DISABLED ACCOUNTS ({len(disabled)})")
    lines.append("")
    if disabled:
        lines.append("These accounts are already disabled. Can be safely deleted to clean up the directory.")
        lines.append("")
        lines.append("| Name | Email | Created | Age | Last Activity | License |")
        lines.append("|------|-------|---------|-----|---------------|---------|")
        for a in sorted(disabled, key=lambda x: x["created"]):
            email = a["upn"].split("@")[0] + "@..."
            lines.append(f"| {a['name']} | {email} | {a['created']} | {a['age']} | {a['last_activity']} | {a['license_display']} |")
        lines.append("")
        lines.append("**Recommendation**: Delete all. They're disabled and consuming no licenses, but clutter the directory.")
    else:
        lines.append("None found.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 2: Guest accounts
    lines.append(f"## 2. EXTERNAL / GUEST ACCOUNTS ({len(guests)})")
    lines.append("")
    if guests:
        lines.append("Guest users from external organizations. They consume no licenses but have directory access.")
        lines.append("")
        lines.append("| Name | External Email | Created | Age | Last Activity | Days Inactive |")
        lines.append("|------|---------------|---------|-----|---------------|---------------|")
        for a in sorted(guests, key=lambda x: x.get("days_inactive") or 99999, reverse=True):
            ext_email = a["upn"].split("#")[0].replace("_", "@") if "#" in a["upn"] else a["upn"]
            days = str(a["days_inactive"]) if a["days_inactive"] is not None else "N/A"
            lines.append(f"| {a['name']} | {ext_email} | {a['created']} | {a['age']} | {a['last_activity']} | {days} |")
        lines.append("")
        never_signed_in = [a for a in guests if a["last_activity"] == "Never"]
        if never_signed_in:
            lines.append(f"**{len(never_signed_in)} guest(s) have NEVER signed in.** These are likely stale invitations.")
        lines.append("")
        lines.append("**Recommendation**: Review and remove guests that haven't signed in recently or are no longer collaborating.")
    else:
        lines.append("None found.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 3: Shared / functional mailboxes
    lines.append(f"## 3. SHARED / FUNCTIONAL MAILBOXES ({len(shared)})")
    lines.append("")
    if shared:
        lines.append("Not personal accounts — shared inboxes, group mailboxes, or functional accounts.")
        lines.append("")
        lines.append("| Name | Email | Created | Last Activity | License |")
        lines.append("|------|-------|---------|---------------|---------|")
        for a in sorted(shared, key=lambda x: x["name"]):
            email = a["upn"].split("@")[0] + "@..."
            lines.append(f"| {a['name']} | {email} | {a['created']} | {a['last_activity']} | {a['license_display']} |")
        lines.append("")
        lines.append("**Questions**: Could reception desks use A1 instead of A5? Are all teacher group mailboxes still needed?")
    else:
        lines.append("None found.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 4: Staff accounts (the main section)
    lines.append(f"## 4. STAFF ACCOUNTS ({len(staff)})")
    lines.append("")
    if staff:
        # Sort by days inactive (most inactive first), Never = top
        def sort_key(a):
            if a["last_activity"] == "Never":
                return (0, a["name"])  # Never signed in = most concerning
            return (1, -(a["days_inactive"] or 0))

        # Split into concerning and active
        never_signed = [a for a in staff if a["last_activity"] == "Never"]
        inactive_90 = [a for a in staff if a["last_activity"] != "Never" and a["days_inactive"] is not None and a["days_inactive"] >= 90]
        active = [a for a in staff if a["last_activity"] != "Never" and (a["days_inactive"] is None or a["days_inactive"] < 90)]

        if never_signed:
            lines.append(f"### Never Signed In ({len(never_signed)})")
            lines.append("")
            lines.append("These accounts have **never been used**. High candidates for removal.")
            lines.append("")
            lines.append("| Name | Email | Created | Age | License |")
            lines.append("|------|-------|---------|-----|---------|")
            for a in sorted(never_signed, key=lambda x: x["created"]):
                email = a["upn"].split("@")[0] + "@..."
                lines.append(f"| {a['name']} | {email} | {a['created']} | {a['age']} | {a['license_display']} |")
            lines.append("")

        if inactive_90:
            lines.append(f"### Inactive 90+ Days ({len(inactive_90)})")
            lines.append("")
            lines.append("Last sign-in was more than 90 days ago. May no longer be active employees.")
            lines.append("")
            lines.append("| Name | Email | Created | Last Activity | Days Inactive | License |")
            lines.append("|------|-------|---------|---------------|---------------|---------|")
            for a in sorted(inactive_90, key=lambda x: -(x["days_inactive"] or 0)):
                email = a["upn"].split("@")[0] + "@..."
                lines.append(f"| {a['name']} | {email} | {a['created']} | {a['last_activity']} | {a['days_inactive']} | {a['license_display']} |")
            lines.append("")

        if active:
            lines.append(f"### Active (last 90 days) ({len(active)})")
            lines.append("")
            lines.append("| Name | Email | Last Activity | Days Inactive | License |")
            lines.append("|------|-------|---------------|---------------|---------|")
            for a in sorted(active, key=lambda x: x["days_inactive"] or 0, reverse=True):
                email = a["upn"].split("@")[0] + "@..."
                days = str(a["days_inactive"]) if a["days_inactive"] is not None else "N/A"
                lines.append(f"| {a['name']} | {email} | {a['last_activity']} | {days} | {a['license_display']} |")
            lines.append("")
    else:
        lines.append("None found.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary / recommendations
    lines.append("## Recommended Actions")
    lines.append("")
    if disabled:
        lines.append(f"1. **Delete {len(disabled)} disabled accounts** — no impact, just directory cleanup")
    if never_signed:
        lines.append(f"2. **Review {len(never_signed)} staff accounts that have never signed in** — likely candidates for removal")
    if inactive_90:
        lines.append(f"3. **Review {len(inactive_90)} staff accounts inactive 90+ days** — may be former employees")
    never_guests = [a for a in guests if a["last_activity"] == "Never"]
    if never_guests:
        lines.append(f"4. **Remove {len(never_guests)} guest accounts that never signed in** — stale invitations")
    old_guests = [a for a in guests if a["days_inactive"] is not None and a["days_inactive"] >= 365]
    if old_guests:
        lines.append(f"5. **Review {len(old_guests)} guest accounts inactive 1+ year** — likely no longer collaborating")
    lines.append("")

    # Write report
    report_path = REPORTS_DIR / "tenant_account_review.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
