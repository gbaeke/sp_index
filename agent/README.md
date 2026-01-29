# Agent Framework MCP Client

This folder contains a small Agent Framework CLI that connects to the local MCP
server and uses its `search` tool to retrieve documents before answering.

## Requirements

- Python 3.10+
- Azure OpenAI endpoint + key
- Entra ID app registration that supports device code flow (same one used by `mcp/client.py`)
- MCP server running on `http://localhost:8000/mcp` (default)

## Environment variables

Set these in the root `.env` (loaded automatically):

- `CHAT_ENDPOINT` or `AZURE_OPENAI_ENDPOINT` (required)
- `CHAT_KEY` or `AZURE_OPENAI_API_KEY` (required)
- `CHAT_DEPLOYMENT` or `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` (required)
- `CHAT_API_VERSION` (optional, default: `2024-02-15-preview`)
- `AZURE_OPENAI_API_VERSION` (optional, used if `CHAT_API_VERSION` is unset)
- `ENTRA_TENANT_ID` (optional; defaults to the same values as `mcp/client.py`)
- `ENTRA_CLIENT_ID` (optional; defaults to the same values as `mcp/client.py`)
- `ENTRA_SCOPE` (optional, default: `api://{ENTRA_CLIENT_ID}/.default`)
- `MCP_SERVER_URL` (optional, default: `http://localhost:8000/mcp`)

## Run

From the repo root:

```bash
uv run mcp/server.py
```

In another terminal:

```bash
uv run agent/agent.py
```

On first run, the CLI will prompt you to complete device code authentication.
After that, ask questions at the prompt; the agent will use the MCP tool to
retrieve relevant documents and answer accordingly.

## TUI (Textual)

Run the Textual interface with streaming and top-3 sources panel:

```bash
uv run agent/tui.py
```


## Troubleshooting

If you see a device-code error like:

```
invalid_request: The provided value for the input parameter 'redirect_uri' is not valid.
```

Your Entra app registration is not configured for public client flows. Either:

1. Use the default `ENTRA_CLIENT_ID` (same as `mcp/client.py`) by removing custom values, or
2. Enable **Allow public client flows** on your app registration and add the redirect URI:
   `https://login.microsoftonline.com/common/oauth2/nativeclient`
