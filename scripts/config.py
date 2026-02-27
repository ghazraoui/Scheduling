"""
Shared configuration and Graph API helpers for Scheduling project scripts.
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

# Azure AD / Microsoft 365 credentials (loaded from .env)
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")
CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DOMAIN = os.environ.get("AZURE_DOMAIN", "swisslearninggroup.onmicrosoft.com")

# License SKU — Office 365 A1 for faculty
# skuPartNumber: STANDARDWOFFPACK_FACULTY
# Resolved at runtime via /subscribedSkus if not hardcoded
LICENSE_SKU_PART_NUMBER = "STANDARDWOFFPACK_FACULTY"


def get_token():
    """Get an app-only access token using client credentials flow."""
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    resp = requests.post(url, data=data)
    if resp.status_code != 200:
        print(f"Auth failed: {resp.status_code}")
        print(resp.text)
        sys.exit(1)
    return resp.json()["access_token"]


def graph_get(token, endpoint):
    """GET request to Microsoft Graph API with pagination support."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{GRAPH_BASE}{endpoint}", headers=headers)
    if resp.status_code != 200:
        return {"error": resp.status_code, "message": resp.text}
    return resp.json()


def graph_get_all(token, endpoint):
    """GET all pages from a Microsoft Graph API endpoint."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_BASE}{endpoint}"
    all_values = []
    while url:
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return {"error": resp.status_code, "message": resp.text}
        data = resp.json()
        all_values.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return {"value": all_values}


def graph_post(token, endpoint, json_body):
    """POST request to Microsoft Graph API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(f"{GRAPH_BASE}{endpoint}", headers=headers, json=json_body)
    return resp


def graph_delete(token, endpoint):
    """DELETE request to Microsoft Graph API."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.delete(f"{GRAPH_BASE}{endpoint}", headers=headers)
    return resp


CALENDAR_EVENT_SUBJECT = "Teaching"


def resolve_license_sku(token, sku_part_number=LICENSE_SKU_PART_NUMBER, required=True):
    """Look up the SKU ID for a given skuPartNumber from /subscribedSkus.

    Args:
        required: If False, returns None on failure instead of exiting.
                  Use required=False for dry-run mode.
    """
    skus = graph_get(token, "/subscribedSkus")
    if "error" in skus:
        if not required:
            print(f"  Warning: Could not fetch SKUs ({skus.get('error')}). Continuing with placeholder.")
            return None
        print(f"Failed to fetch subscribed SKUs: {skus}")
        sys.exit(1)
    for sku in skus.get("value", []):
        if sku.get("skuPartNumber") == sku_part_number:
            return sku["skuId"]
    if not required:
        print(f"  Warning: SKU '{sku_part_number}' not found. Continuing with placeholder.")
        return None
    print(f"License SKU '{sku_part_number}' not found in tenant.")
    print("Available SKUs:")
    for sku in skus.get("value", []):
        print(f"  {sku.get('skuPartNumber')} -> {sku.get('skuId')}")
    sys.exit(1)
