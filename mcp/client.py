import asyncio
import json
import os
from pathlib import Path

import jwt
import msal
from fastmcp import Client


TENANT_ID = os.getenv("ENTRA_TENANT_ID", "484588df-21e4-427c-b2a5-cc39d6a73281")
CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "97a67a49-6a56-45aa-a481-d9fc784a9118")
SCOPE = os.getenv("ENTRA_SCOPE", "https://search.azure.com/.default")
SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
CACHE_PATH = Path(__file__).resolve().parent / ".msal_token_cache"


def load_token_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        cache.deserialize(CACHE_PATH.read_text())
    return cache


def save_token_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        CACHE_PATH.write_text(cache.serialize())


def acquire_token() -> str:
    """Acquire an Entra ID access token via device code flow."""
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    cache = load_token_cache()
    app = msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=authority,
        token_cache=cache,
    )

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent([SCOPE], account=accounts[0])
        if result and "access_token" in result:
            save_token_cache(cache)
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=[SCOPE])
    if "user_code" not in flow:
        raise RuntimeError("Failed to initiate device code flow.")

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Token acquisition failed: {result.get('error_description')}")

    token = result["access_token"]
    save_token_cache(cache)
    if os.getenv("MCP_DEBUG", ""):
        claims = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        debug_claims = {
            "aud": claims.get("aud"),
            "iss": claims.get("iss"),
            "scp": claims.get("scp"),
            "tid": claims.get("tid"),
        }
        print(f"Token claims: {debug_claims}")

    return token


async def call_search(query: str) -> None:
    """Call the MCP search tool via HTTP transport."""
    token = acquire_token()
    client = Client(SERVER_URL, auth=token)
    async with client:
        result = await client.call_tool("search", {"query": query})
        payload = getattr(result, "data", None)
        if payload is None:
            print(result)
        else:
            print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(call_search("inity"))
