#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "python-dotenv>=1.0.0",
#     "azure-identity>=1.15.0",
#     "pyjwt>=2.8.0",
# ]
# ///
"""
Query Azure AI Search index with elevated permissions using Azure AD.
"""

import os
import sys
import requests
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential


def load_config():
    load_dotenv()
    resource_prefix = os.getenv("RESOURCE_PREFIX", "sp-custom")
    search_endpoint = os.getenv("SEARCH_ENDPOINT")
    
    if not search_endpoint:
        print("❌ Missing: SEARCH_ENDPOINT")
        sys.exit(1)
    
    return {
        "search_endpoint": search_endpoint.rstrip("/"),
        "index_name": f"{resource_prefix}-index",
        "api_version": "2025-11-01-preview"
    }


def get_auth_headers():
    credential = DefaultAzureCredential()
    token = credential.get_token("https://search.azure.com/.default")
    
    # Debug: Print token info
    import jwt
    decoded = jwt.decode(token.token, options={"verify_signature": False})
    print("🔑 Token Info:")
    print(f"   Issued for: {decoded.get('oid', 'N/A')} ({decoded.get('upn', decoded.get('unique_name', 'N/A'))})")
    print(f"   App ID: {decoded.get('appid', 'N/A')}")
    print(f"   Audience: {decoded.get('aud', 'N/A')}")
    print(f"   Expires: {decoded.get('exp', 'N/A')}")
    print(f"   Roles: {decoded.get('roles', 'N/A')}")
    print(f"   Token (first 50 chars): {token.token[:50]}...")
    print()
    
    return {
        "Authorization": f"Bearer {token.token}",
        "x-ms-enable-elevated-read": "true",
        "Content-Type": "application/json"
    }


def get_stats(config):
    url = f"{config['search_endpoint']}/indexes/{config['index_name']}/stats"
    try:
        response = requests.get(url, params={"api-version": config["api_version"]}, headers=get_auth_headers())
        response.raise_for_status()
        stats = response.json()
        print(f"📊 Documents: {stats.get('documentCount', 0)}")
        print(f"💾 Storage: {stats.get('storageSize', 0):,} bytes\n")
    except Exception as e:
        print(f"⚠️  Stats unavailable: {e}\n")


def query(config):
    url = f"{config['search_endpoint']}/indexes/{config['index_name']}/docs/search"
    body = {
        "search": "*",
        "select": "snippet,metadata_title,metadata_spo_item_name,UserIds,GroupIds",
        "top": 10,
        "count": True
    }
    
    # Get token for error debugging
    credential = DefaultAzureCredential()
    token = credential.get_token("https://search.azure.com/.default")
    headers = get_auth_headers()
    
    try:
        response = requests.post(url, params={"api-version": config["api_version"]}, headers=headers, json=body)
        response.raise_for_status()
        
        results = response.json()
        values = results.get("value", [])
        
        print(f"🔍 Found: {len(values)} of {results.get('@odata.count', 0)} documents\n")
        
        if not values:
            print("No documents found.")
            return
        
        for idx, doc in enumerate(values, 1):
            print(f"─── Document {idx} ───")
            title = doc.get("metadata_title") or doc.get("metadata_spo_item_name") or "Untitled"
            print(f"   📄 {title}")
            
            user_ids = doc.get("UserIds", [])
            group_ids = doc.get("GroupIds", [])
            
            if user_ids:
                print(f"   👤 UserIds: {len(user_ids)} entries")
                for uid in user_ids[:2]:
                    print(f"      {uid}")
                if len(user_ids) > 2:
                    print(f"      ... +{len(user_ids) - 2} more")
            else:
                print("   ⚠️  UserIds: empty")
            
            if group_ids:
                print(f"   👥 GroupIds: {len(group_ids)} entries")
                for gid in group_ids:
                    print(f"      {gid}")
            else:
                print("   ⚠️  GroupIds: empty")
            
            snippet = doc.get("snippet", "")
            if snippet:
                preview = snippet[:100] + "..." if len(snippet) > 100 else snippet
                print(f"   📝 {preview}")
            print()
        
        has_acls = any(doc.get("UserIds") or doc.get("GroupIds") for doc in values)
        print("✅ ACL fields populated" if has_acls else "⚠️  ACL fields empty")
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP {e.response.status_code}")
        print(f"Response: {e.response.text}")
        print("\n🔐 Full Token for debugging:")
        print(token.token)
        if e.response.status_code == 403:
            print("Required RBAC: Search Index Data Reader")
        elif e.response.status_code == 400 and "elevatedOperations" in e.response.text:
            print("Required: elevatedOperations/read RBAC")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    config = load_config()
    print("=" * 60)
    print("Azure AI Search - Elevated Query (Bypass ACL)")
    print("=" * 60)
    print()
    get_stats(config)
    query(config)
