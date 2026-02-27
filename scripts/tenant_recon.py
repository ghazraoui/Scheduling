"""
Tenant Recon Script
Queries Microsoft Graph API to understand the current tenant setup:
- Organization info
- Subscribed licenses (SKUs) and available units
- Current user count
- Domain info
"""

import json
import sys
from pathlib import Path

# Use shared config
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_token, graph_get


def main():
    print("=" * 60)
    print("MICROSOFT 365 TENANT RECON")
    print("=" * 60)

    token = get_token()
    print("Authenticated successfully.\n")

    # 1. Organization info
    print("-" * 40)
    print("ORGANIZATION")
    print("-" * 40)
    org = graph_get(token, "/organization")
    if "value" in org:
        for o in org["value"]:
            print(f"  Name:          {o.get('displayName', 'N/A')}")
            print(f"  Tenant ID:     {o.get('id', 'N/A')}")
            print(f"  Country:       {o.get('countryLetterCode', 'N/A')}")
            domains = [d["name"] for d in o.get("verifiedDomains", [])]
            print(f"  Domains:       {', '.join(domains)}")
            print(f"  Created:       {o.get('createdDateTime', 'N/A')}")
    else:
        print(f"  Error: {org}")
    print()

    # 2. Subscribed SKUs (licenses)
    print("-" * 40)
    print("LICENSES (Subscribed SKUs)")
    print("-" * 40)
    skus = graph_get(token, "/subscribedSkus")
    if "value" in skus:
        total_enabled = 0
        total_consumed = 0
        for sku in skus["value"]:
            name = sku.get("skuPartNumber", "Unknown")
            enabled = sku.get("prepaidUnits", {}).get("enabled", 0)
            consumed = sku.get("consumedUnits", 0)
            available = enabled - consumed if isinstance(enabled, int) else "N/A"
            status = sku.get("capabilityStatus", "N/A")
            total_enabled += enabled if isinstance(enabled, int) else 0
            total_consumed += consumed
            print(f"  {name}")
            print(f"    Status:    {status}")
            print(f"    Enabled:   {enabled}")
            print(f"    Consumed:  {consumed}")
            print(f"    Available: {available}")
            # Show included service plans
            plans = sku.get("servicePlans", [])
            key_plans = [
                p["servicePlanName"]
                for p in plans
                if any(
                    kw in p.get("servicePlanName", "").upper()
                    for kw in ["EXCHANGE", "TEAMS", "SHAREPOINT", "CALENDAR", "OUTLOOK"]
                )
            ]
            if key_plans:
                print(f"    Key plans: {', '.join(key_plans)}")
            print()
        print(f"  TOTALS: {total_enabled} enabled, {total_consumed} consumed, {total_enabled - total_consumed} available")
    else:
        print(f"  Error: {skus}")
    print()

    # 3. Current users (count + sample)
    print("-" * 40)
    print("USERS")
    print("-" * 40)
    users = graph_get(token, "/users?$top=999&$select=id,displayName,mail,userPrincipalName,accountEnabled,assignedLicenses,userType&$count=true&$orderby=displayName")
    if "value" in users:
        all_users = users["value"]
        enabled = [u for u in all_users if u.get("accountEnabled")]
        disabled = [u for u in all_users if not u.get("accountEnabled")]
        members = [u for u in all_users if u.get("userType") == "Member"]
        guests = [u for u in all_users if u.get("userType") == "Guest"]

        print(f"  Total:    {len(all_users)}")
        print(f"  Enabled:  {len(enabled)}")
        print(f"  Disabled: {len(disabled)}")
        print(f"  Members:  {len(members)}")
        print(f"  Guests:   {len(guests)}")
        print()
        print("  First 20 users:")
        for u in all_users[:20]:
            status = "active" if u.get("accountEnabled") else "disabled"
            utype = u.get("userType", "?")
            licenses = len(u.get("assignedLicenses", []))
            print(f"    {u.get('displayName', 'N/A'):30s} | {u.get('userPrincipalName', 'N/A'):45s} | {status:8s} | {utype:6s} | {licenses} license(s)")
    else:
        print(f"  Error: {users}")
    print()

    # 4. Domains
    print("-" * 40)
    print("DOMAINS")
    print("-" * 40)
    domains = graph_get(token, "/domains")
    if "value" in domains:
        for d in domains["value"]:
            is_default = " (DEFAULT)" if d.get("isDefault") else ""
            is_verified = "verified" if d.get("isVerified") else "unverified"
            print(f"  {d.get('id', 'N/A'):45s} | {is_verified}{is_default}")
    else:
        print(f"  Error: {domains}")

    print()
    print("=" * 60)
    print("RECON COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
