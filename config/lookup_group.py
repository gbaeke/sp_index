#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "python-dotenv>=1.0.0",
#     "azure-identity>=1.15.0",
# ]
# ///
"""
Lookup a Microsoft Entra group by ID and list its members.
"""

import argparse
import os
import sys
from typing import Iterable

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def load_config() -> dict:
    """Load configuration from .env file."""
    load_dotenv()
    tenant_id = os.getenv("TENANT_ID")

    return {
        "tenant_id": tenant_id,
    }


def get_graph_headers() -> dict:
    credential = DefaultAzureCredential()
    token = credential.get_token(GRAPH_SCOPE)

    return {
        "Authorization": f"Bearer {token.token}",
        "Content-Type": "application/json",
    }


def fetch_group(group_id: str, headers: dict) -> dict:
    url = f"{GRAPH_BASE_URL}/groups/{group_id}"
    params = {
        "$select": "id,displayName,mail,securityEnabled,groupTypes",
    }
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def iter_members(group_id: str, headers: dict) -> Iterable[dict]:
    url = f"{GRAPH_BASE_URL}/groups/{group_id}/members"
    params = {
        "$select": "id,displayName,mail,userPrincipalName",
    }

    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()
        for member in payload.get("value", []):
            yield member
        url = payload.get("@odata.nextLink")
        params = None


def describe_group_type(group: dict) -> str:
    group_types = group.get("groupTypes", []) or []
    security_enabled = group.get("securityEnabled", False)

    if "Unified" in group_types:
        return "Microsoft 365 Group"
    if security_enabled:
        return "Security Group"
    if group_types:
        return ", ".join(group_types)
    return "Unknown"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lookup a Microsoft Entra group and list members by group ID"
    )
    parser.add_argument("group_id", type=str, help="Microsoft Entra group object ID")
    args = parser.parse_args()

    config = load_config()
    if config.get("tenant_id"):
        print(f"🔍 Tenant: {config['tenant_id']}")

    headers = get_graph_headers()

    try:
        group = fetch_group(args.group_id, headers)
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "N/A"
        print(f"❌ Failed to fetch group ({status})")
        if exc.response is not None:
            print(exc.response.text)
        print("\nRequired permissions: Group.Read.All or Directory.Read.All")
        sys.exit(1)

    print("=" * 60)
    print("Microsoft Entra Group")
    print("=" * 60)
    print(f"📌 Name: {group.get('displayName', 'N/A')}")
    print(f"🆔 ID: {group.get('id', 'N/A')}")
    print(f"✉️  Mail: {group.get('mail', 'N/A')}")
    print(f"🏷️  Type: {describe_group_type(group)}")
    print()

    try:
        members = list(iter_members(args.group_id, headers))
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "N/A"
        print(f"❌ Failed to fetch members ({status})")
        if exc.response is not None:
            print(exc.response.text)
        print("\nRequired permissions: Group.Read.All or Directory.Read.All")
        sys.exit(1)

    print(f"👥 Members: {len(members)}")
    if not members:
        print("⚠️  No members found.")
        return

    for member in members:
        display = member.get("displayName") or "Unnamed"
        upn = member.get("userPrincipalName")
        mail = member.get("mail")
        identifier = upn or mail or member.get("id", "N/A")
        print(f"   - {display} ({identifier})")


if __name__ == "__main__":
    main()
