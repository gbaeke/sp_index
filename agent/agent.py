#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework>=0.1.0a0",
#     "openai>=1.0.0",
#     "msal>=1.25.0",
#     "pyjwt>=2.8.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Interactive Agent Framework CLI that uses an MCP server for retrieval.

This agent connects to the local MCP server on http://localhost:8000/mcp by default,
authenticates with Entra ID device code flow, and uses the MCP tool to retrieve
documents before answering.
"""

import asyncio
import os
from pathlib import Path

import msal
from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient
from dotenv import load_dotenv


dotenv_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=dotenv_path)

TENANT_ID = os.getenv("ENTRA_TENANT_ID", "484588df-21e4-427c-b2a5-cc39d6a73281")
CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "97a67a49-6a56-45aa-a481-d9fc784a9118")
SCOPE = os.getenv("ENTRA_SCOPE", f"api://{CLIENT_ID}/.default")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")

CHAT_ENDPOINT = os.getenv("CHAT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
CHAT_KEY = os.getenv("CHAT_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
CHAT_DEPLOYMENT = (
    os.getenv("CHAT_DEPLOYMENT")
    or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
)
CHAT_API_VERSION = (
    os.getenv("CHAT_API_VERSION")
    or os.getenv("AZURE_OPENAI_API_VERSION")
    or "2024-02-15-preview"
)

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
    return token


def validate_env() -> None:
    missing = []
    if not CHAT_ENDPOINT:
        missing.append("CHAT_ENDPOINT")
    if not CHAT_KEY:
        missing.append("CHAT_KEY")
    if not CHAT_DEPLOYMENT:
        missing.append("CHAT_DEPLOYMENT")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


async def chat_loop() -> None:
    validate_env()
    token = acquire_token()
    headers = {"Authorization": f"Bearer {token}"}

    chat_client = AzureOpenAIChatClient(
        api_key=CHAT_KEY,
        endpoint=CHAT_ENDPOINT,
        deployment_name=CHAT_DEPLOYMENT,
        api_version=CHAT_API_VERSION,
    )
    instructions = (
        "You answer questions using the MCP search tool. "
        "Always call the MCP tool to retrieve relevant documents before answering. "
        "If no documents are found, say you could not find relevant content."
    )

    async with (
        MCPStreamableHTTPTool(
            name="SharePoint Search MCP",
            url=MCP_SERVER_URL,
            headers=headers,
        ) as mcp_tool,
        ChatAgent(
            chat_client=chat_client,
            name="SharePointDocsAgent",
            instructions=instructions,
        ) as agent,
    ):
        print("Type a question, or 'exit' to quit.")
        while True:
            try:
                question = input("\n> ").strip()
            except EOFError:
                print("\nExiting.")
                return

            if not question:
                continue
            if question.lower() in {"exit", "quit"}:
                print("Exiting.")
                return

            result = await agent.run(question, tools=mcp_tool)
            print(result.text)


def main() -> None:
    """Run the interactive MCP-backed agent."""
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
