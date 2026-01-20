import os
import time
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import AccessToken, get_access_token
from mcp.server.lowlevel.server import request_ctx
import requests
from dotenv import load_dotenv


dotenv_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=dotenv_path)

TENANT_ID = os.getenv("ENTRA_TENANT_ID", "484588df-21e4-427c-b2a5-cc39d6a73281")
AUDIENCE = os.getenv("ENTRA_AUDIENCE", "https://search.azure.com/")
BASE_URL = os.getenv("MCP_BASE_URL", "http://127.0.0.1:8000")

DEFAULT_ISSUERS = [
    f"https://sts.windows.net/{TENANT_ID}/",
    f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
]
issuer_env = os.getenv("ENTRA_ISSUER")
JWT_ISSUER = issuer_env.split(",") if issuer_env else DEFAULT_ISSUERS
JWKS_URI = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"

auth_provider = JWTVerifier(
    jwks_uri=JWKS_URI,
    issuer=JWT_ISSUER,
    audience=[AUDIENCE, AUDIENCE.rstrip("/")],
)

mcp = FastMCP("Azure Search MCP", auth=auth_provider)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def post_with_retry(
    url: str,
    params: dict,
    headers: dict,
    body: dict,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    timeout: int = 30,
) -> requests.Response:
    response: requests.Response | None = None
    for attempt in range(1, max_attempts + 1):
        response = requests.post(url, params=params, headers=headers, json=body, timeout=timeout)

        if response.status_code not in RETRYABLE_STATUS_CODES or attempt == max_attempts:
            return response

        retry_after = response.headers.get("Retry-After")
        try:
            retry_after_seconds = float(retry_after) if retry_after else 0
        except ValueError:
            retry_after_seconds = 0

        backoff = base_delay * (2 ** (attempt - 1))
        time.sleep(max(backoff, retry_after_seconds))

    if response is None:
        raise RuntimeError("Request failed without response.")

    return response


@mcp.tool
def search(query: str, top: int = 5) -> dict:
    """Query Azure AI Search with ACL filtering."""
    token: AccessToken | None = get_access_token()
    if token is None:
        return {"authenticated": False, "error": "Missing user token."}

    token_string = None
    context = request_ctx.get()
    request = getattr(context, "request", None)
    if request is not None:
        headers = getattr(request, "headers", None)
        if headers is not None:
            auth_header = headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token_string = auth_header[7:]

    if not token_string:
        return {"authenticated": False, "error": "User token unavailable."}

    search_endpoint = os.getenv("SEARCH_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("API_KEY")
    resource_prefix = os.getenv("RESOURCE_PREFIX", "sp-custom")
    api_version = os.getenv("SEARCH_API_VERSION", "2025-11-01-preview")

    if not search_endpoint or not api_key:
        return {
            "authenticated": True,
            "error": "Missing SEARCH_ENDPOINT or API_KEY.",
        }

    url = f"{search_endpoint}/indexes/{resource_prefix}-index/docs/search"
    body = {
        "search": query,
        "select": "snippet,metadata_title,metadata_spo_item_name,metadata_spo_item_weburi",
        "top": top,
        "count": True,
    }
    headers = {
        "api-key": api_key,
        "x-ms-query-source-authorization": token_string,
        "Content-Type": "application/json",
    }

    try:
        response = post_with_retry(
            url,
            params={"api-version": api_version},
            headers=headers,
            body=body,
        )
    except requests.exceptions.RequestException as exc:
        return {"authenticated": True, "error": str(exc)}

    if response.status_code >= 400:
        return {
            "authenticated": True,
            "error": f"HTTP {response.status_code}",
            "details": response.text,
        }

    return response.json()


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
