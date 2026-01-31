#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "textual>=0.89.0",
#     "agent-framework>=0.1.0a0",
#     "openai>=1.0.0",
#     "msal>=1.25.0",
#     "pyjwt>=2.8.0",
#     "python-dotenv>=1.0.0",
#     "rich>=13.0.0",
# ]
# ///
"""
Textual TUI for the SharePoint Search Agent.

Provides an interactive terminal interface to query SharePoint documents
using the MCP-backed agent with Entra ID authentication.
"""

import json
import os
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import msal
import jwt
from dotenv import load_dotenv
from rich.markdown import Markdown
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, Static

# Load environment from parent directory
dotenv_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=dotenv_path)

# Configuration
TENANT_ID = os.getenv("ENTRA_TENANT_ID", "484588df-21e4-427c-b2a5-cc39d6a73281")
CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "97a67a49-6a56-45aa-a481-d9fc784a9118")
SCOPE = os.getenv("ENTRA_SCOPE", f"api://{CLIENT_ID}/.default")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")

CHAT_ENDPOINT = os.getenv("CHAT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
CHAT_KEY = os.getenv("CHAT_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
CHAT_DEPLOYMENT = (
    os.getenv("CHAT_DEPLOYMENT") or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
)
CHAT_API_VERSION = (
    os.getenv("CHAT_API_VERSION")
    or os.getenv("AZURE_OPENAI_API_VERSION")
    or "2024-02-15-preview"
)

CACHE_PATH = Path(__file__).resolve().parent / ".msal_token_cache"
ACTIVE_ACCOUNT_PATH = Path(__file__).resolve().parent / ".msal_active_account.json"


@dataclass
class Document:
    """Represents a retrieved document."""

    title: str
    url: str
    snippet: str = ""


@dataclass
class AgentResponse:
    """Response from the agent including retrieved documents."""

    text: str
    documents: list[Document] = field(default_factory=list)


class MessageBox(Static):
    """A bordered message box for chat messages."""

    def __init__(self, content: str, role: str = "system") -> None:
        super().__init__(classes=f"message-box {role}-message")
        self.content_text = content
        self.role = role

    def compose(self) -> ComposeResult:
        if self.role == "user":
            yield Static(f"[bold yellow]You:[/bold yellow] {self.content_text}")
        elif self.role == "assistant":
            yield Static("[bold blue]Assistant:[/bold blue]", classes="role-label")
            yield Static(Markdown(self.content_text), classes="message-content")
        else:
            yield Static(self.content_text)


class SourceItem(Static):
    """A single source/document item in the sources panel."""

    ALLOW_FOCUS = True

    def __init__(self, index: int, doc: Document) -> None:
        super().__init__(classes="source-item")
        self.index = index
        self.doc = doc

    def compose(self) -> ComposeResult:
        # Title with number
        title = self.doc.title if self.doc.title else "Untitled"
        yield Static(
            f"[bold yellow]{self.index}.[/bold yellow] [underline]{title}[/underline]",
            classes="source-title",
        )
        # Snippet preview
        if self.doc.snippet:
            snippet_text = self.doc.snippet[:200] + "..." if len(self.doc.snippet) > 200 else self.doc.snippet
            yield Static(f"  [dim]• {snippet_text}[/dim]", classes="source-snippet")

    def on_click(self) -> None:
        """Open the document URL in browser when clicked."""
        if self.doc.url:
            webbrowser.open(self.doc.url)


class SourcesPanel(Container):
    """Panel showing retrieved sources/documents."""

    def __init__(self) -> None:
        super().__init__(id="sources-panel")
        self.documents: list[Document] = []

    def compose(self) -> ComposeResult:
        yield Static("[bold]Sources (Top 3)[/bold]", id="sources-header")
        yield VerticalScroll(id="sources-list")

    def update_sources(self, documents: list[Document]) -> None:
        """Update the sources list with new documents."""
        self.documents = documents[:3]  # Top 3 only
        sources_list = self.query_one("#sources-list", VerticalScroll)
        sources_list.remove_children()
        
        if not self.documents:
            sources_list.mount(Static("[dim]No sources yet[/dim]", classes="no-sources"))
        else:
            for i, doc in enumerate(self.documents, 1):
                sources_list.mount(SourceItem(i, doc))


class StatusBar(Static):
    """Status bar showing current state and user."""

    status = reactive("Idle")
    user = reactive("")

    def render(self) -> Text:
        if self.user:
            return Text(f"{self.status}  •  Signed in as {self.user}")
        return Text(self.status)


CSS = """
$accent: #d4a520;
$border-color: #3a506b;
$surface-dark: #1a1a2e;
$surface-light: #16213e;

Screen {
    background: $surface-dark;
}

#main-container {
    height: 1fr;
    width: 100%;
}

#content-area {
    height: 1fr;
    width: 100%;
}

#chat-panel {
    width: 3fr;
    height: 100%;
    border: solid $border-color;
    margin: 1 0 1 1;
    padding: 0;
}

#chat-scroll {
    height: 1fr;
    padding: 1 1 0 1;
}

#sources-panel {
    width: 1fr;
    min-width: 28;
    height: 100%;
    border: solid $border-color;
    margin: 1 1 1 0;
    padding: 1 1 0 1;
}

#sources-header {
    height: auto;
    margin-bottom: 0;
    color: white;
}

#sources-list {
    height: 1fr;
}

.source-item {
    height: auto;
    margin: 0 0 1 0;
    padding: 0;
}

.source-title {
    height: auto;
}

.source-snippet {
    height: auto;
    margin-left: 2;
    margin-top: 0;
}

.no-sources {
    color: $text-muted;
}

#bottom-area {
    height: auto;
    width: 100%;
    padding: 1 1 1 1;
}

#status-bar {
    height: 1;
    padding: 0 1;
    margin-bottom: 1;
}

#input-container {
    height: auto;
    background: $surface-light;
    padding: 1 1 0 1;
    margin-bottom: 0;
}

#query-input {
    width: 100%;
    border: none;
    background: $surface-light;
}

#query-input:focus {
    border: none;
}

.message-box {
    height: auto;
    margin: 0 0 1 0;
    padding: 1;
    border: solid $border-color;
}

.user-message {
    background: $surface-light;
}

.assistant-message {
    background: $surface-dark;
    border-left: thick $accent;
}

.system-message {
    background: $surface-dark;
    border: none;
}

.role-label {
    height: auto;
    margin-bottom: 0;
}

.message-content {
    height: auto;
    padding-left: 1;
}

Footer {
    background: $surface-dark;
}

Footer > .footer--key {
    color: $accent;
    background: transparent;
}

Footer > .footer--description {
    color: white;
}
"""


class AgentTUI(App):
    """Textual TUI for SharePoint Search Agent."""

    CSS = CSS
    TITLE = "AgentTui"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+u", "switch_user", "Switch User"),
        Binding("ctrl+s", "select_cached_user", "Select Cached User"),
        Binding("ctrl+o", "sign_out", "Sign Out"),
        Binding("escape", "cancel", "Cancel"),
        Binding("f2", "toggle_raw", "Toggle Raw"),
        Binding("ctrl+p", "palette", "palette"),
    ]

    show_raw = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None
        self.documents: list[Document] = []
        self.raw_responses: list[str] = []
        self.active_account_id: str | None = self._load_active_account_id()
        self.pending_account_selection: list[dict] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            with Horizontal(id="content-area"):
                with VerticalScroll(id="chat-panel"):
                    pass  # Messages will be added dynamically
                yield SourcesPanel()
            with Vertical(id="bottom-area"):
                yield StatusBar(id="status-bar")
                with Container(id="input-container"):
                    yield Input(placeholder="Ask a question...", id="query-input")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app on mount."""
        self.query_one("#query-input", Input).focus()
        # Start authentication
        self.authenticate()

    @work(thread=True)
    def authenticate(self) -> None:
        """Authenticate with Entra ID using device code flow."""
        self._set_status("Authenticating...")

        try:
            token = self._acquire_token_sync()
            self.token = token
            self._set_user_from_token(token)
            self._set_status("Idle")
            self._add_system_message("[green]Authenticated.[/green] Ask a question to begin.")
        except Exception as e:
            self._set_status("Auth Failed")
            self._add_system_message(f"[red]Authentication failed: {e}[/red]")

    def _set_status(self, status: str) -> None:
        """Update status bar from any thread."""
        def update():
            self.query_one("#status-bar", StatusBar).status = status
        self._run_on_app_thread(update)

    def _set_user_from_token(self, token: str) -> None:
        """Extract and display signed-in user from token."""
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
        except Exception:
            return
        self._set_active_account_id_from_claims(decoded)
        user = (
            decoded.get("preferred_username")
            or decoded.get("upn")
            or decoded.get("unique_name")
            or decoded.get("name")
        )
        if not user:
            return

        def update():
            self.query_one("#status-bar", StatusBar).user = user
        self._run_on_app_thread(update)

    def _clear_user(self) -> None:
        """Clear signed-in user from status bar."""
        def update():
            self.query_one("#status-bar", StatusBar).user = ""
        self._run_on_app_thread(update)

    def _add_system_message(self, text: str) -> None:
        """Add a system message to chat."""
        def add():
            chat_panel = self.query_one("#chat-panel", VerticalScroll)
            chat_panel.mount(MessageBox(text, "system"))
            chat_panel.scroll_end()
        self._run_on_app_thread(add)

    def _run_on_app_thread(self, func) -> None:
        """Run a UI update on the app thread safely."""
        if getattr(self, "_thread_id", None) == threading.get_ident():
            func()
        else:
            self.call_from_thread(func)

    def _acquire_token_sync(self, force_device_flow: bool = False) -> str:
        """Synchronously acquire token with device code flow."""
        cache = self._load_token_cache()
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        app = msal.PublicClientApplication(
            client_id=CLIENT_ID,
            authority=authority,
            token_cache=cache,
        )

        if not force_device_flow:
            accounts = app.get_accounts()
            account = self._select_active_account(accounts) or (accounts[0] if accounts else None)
            if account:
                result = app.acquire_token_silent([SCOPE], account=account)
                if result and "access_token" in result:
                    self._save_token_cache(cache)
                    self._set_active_account_from_account(account)
                    return result["access_token"]

        flow = app.initiate_device_flow(scopes=[SCOPE])
        if "user_code" not in flow:
            raise RuntimeError("Failed to initiate device code flow.")

        # Show device code message and open browser to the verification URL
        verification_uri = flow.get("verification_uri") or flow.get("verification_url")
        user_code = flow.get("user_code")
        if verification_uri:
            try:
                webbrowser.open(verification_uri)
            except Exception:
                pass
        if verification_uri and user_code:
            self._add_system_message(
                f"[bold yellow]Sign in to continue[/bold yellow]\n"
                f"Go to: {verification_uri}\n"
                f"Code: [bold]{user_code}[/bold]"
            )
        else:
            self._add_system_message(f"[bold yellow]{flow['message']}[/bold yellow]")

        result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(
                f"Token acquisition failed: {result.get('error_description')}"
            )

        self._save_token_cache(cache)
        self._set_active_account_from_result(app, result)
        return result["access_token"]

    def _load_token_cache(self) -> msal.SerializableTokenCache:
        """Load MSAL token cache."""
        cache = msal.SerializableTokenCache()
        if CACHE_PATH.exists():
            cache.deserialize(CACHE_PATH.read_text())
        return cache

    def _save_token_cache(self, cache: msal.SerializableTokenCache) -> None:
        """Save MSAL token cache."""
        if cache.has_state_changed:
            CACHE_PATH.write_text(cache.serialize())

    def _load_active_account_id(self) -> str | None:
        """Load active account id from disk."""
        if not ACTIVE_ACCOUNT_PATH.exists():
            return None
        try:
            data = json.loads(ACTIVE_ACCOUNT_PATH.read_text())
        except Exception:
            return None
        return data.get("home_account_id")

    def _save_active_account_id(self, home_account_id: str | None) -> None:
        """Persist active account id to disk."""
        if not home_account_id:
            if ACTIVE_ACCOUNT_PATH.exists():
                ACTIVE_ACCOUNT_PATH.unlink()
            return
        ACTIVE_ACCOUNT_PATH.write_text(json.dumps({"home_account_id": home_account_id}))

    def _set_active_account_from_account(self, account: dict) -> None:
        """Persist active account from MSAL account dict."""
        home_account_id = account.get("home_account_id")
        if home_account_id:
            self.active_account_id = home_account_id
            self._save_active_account_id(home_account_id)

    def _set_active_account_from_result(self, app: msal.PublicClientApplication, result: dict) -> None:
        """Persist active account based on device flow result."""
        claims = result.get("id_token_claims") or {}
        username = claims.get("preferred_username") or claims.get("upn")
        if username:
            accounts = app.get_accounts(username=username)
        else:
            accounts = app.get_accounts()
        if accounts:
            self._set_active_account_from_account(accounts[0])

    def _set_active_account_id_from_claims(self, claims: dict) -> None:
        """Set active account id from token claims (oid + tid)."""
        oid = claims.get("oid")
        tid = claims.get("tid")
        if oid and tid:
            home_account_id = f"{oid}.{tid}"
            self.active_account_id = home_account_id
            self._save_active_account_id(home_account_id)

    def _select_active_account(self, accounts: list[dict]) -> dict | None:
        """Find the active account in a list of MSAL accounts."""
        if not self.active_account_id:
            return None
        for account in accounts:
            if account.get("home_account_id") == self.active_account_id:
                return account
        return None

    def _is_token_expired(self, token: str, skew_seconds: int = 60) -> bool:
        """Check if JWT access token is expired or about to expire."""
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
        except Exception:
            return True
        exp = decoded.get("exp")
        if not exp:
            return True
        return (exp - skew_seconds) <= int(time.time())

    @work(thread=True)
    def action_switch_user(self) -> None:
        """Switch to another user by forcing device flow sign-in."""
        self._set_status("Switching user...")
        self.pending_account_selection = None
        self._add_system_message("[yellow]Sign in with the account you want to use.[/yellow]")
        self.token = self._acquire_token_sync(force_device_flow=True)
        self._set_user_from_token(self.token)
        self._add_system_message("[green]Switched user.[/green]")
        self._set_status("Idle")

    @work(thread=True)
    def action_select_cached_user(self) -> None:
        """Select a user from cached accounts."""
        self._set_status("Selecting cached user...")
        cache = self._load_token_cache()
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        app = msal.PublicClientApplication(
            client_id=CLIENT_ID,
            authority=authority,
            token_cache=cache,
        )

        accounts = app.get_accounts()
        if not accounts:
            self._add_system_message("[yellow]No cached accounts available.[/yellow]")
            self._set_status("Idle")
            return

        lines = ["[bold]Select a cached account:[/bold]"]
        for i, account in enumerate(accounts, 1):
            username = account.get("username") or account.get("preferred_username") or "(unknown)"
            lines.append(f"  [bold]{i}.[/bold] {username}")
        lines.append("\nEnter the number in the input box and press Enter.")
        self.pending_account_selection = accounts
        self._add_system_message("\n".join(lines))
        self._set_status("Idle")

    @work(thread=True)
    def action_sign_out(self) -> None:
        """Sign out the active user and clear cached account."""
        self._set_status("Signing out...")
        self.pending_account_selection = None
        cache = self._load_token_cache()
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        app = msal.PublicClientApplication(
            client_id=CLIENT_ID,
            authority=authority,
            token_cache=cache,
        )

        accounts = app.get_accounts()
        active = self._select_active_account(accounts)
        if active:
            app.remove_account(active)
            self._save_token_cache(cache)
        else:
            self._add_system_message("[yellow]No active account to sign out.[/yellow]")

        if CACHE_PATH.exists() and not app.get_accounts():
            CACHE_PATH.unlink()

        self._save_active_account_id(None)
        self.active_account_id = None
        self.token = None
        self._clear_user()
        self._add_system_message("[green]Signed out.[/green]")
        self._set_status("Idle")

    @on(Input.Submitted, "#query-input")
    async def handle_query(self, event: Input.Submitted) -> None:
        """Handle query submission."""
        input_widget = self.query_one("#query-input", Input)
        query = input_widget.value.strip()

        if not query:
            return

        if self.pending_account_selection is not None:
            await self._handle_account_selection(query)
            input_widget.value = ""
            return

        if not self.token:
            chat_panel = self.query_one("#chat-panel", VerticalScroll)
            await chat_panel.mount(MessageBox("[red]Not authenticated. Please wait.[/red]", "system"))
            return

        input_widget.value = ""
        
        # Add user message
        chat_panel = self.query_one("#chat-panel", VerticalScroll)
        await chat_panel.mount(MessageBox(query, "user"))
        chat_panel.scroll_end()
        
        self.run_query(query)

    async def _handle_account_selection(self, selection: str) -> None:
        """Handle selection input for cached accounts."""
        accounts = self.pending_account_selection or []
        self.pending_account_selection = None
        try:
            idx = int(selection) - 1
        except ValueError:
            self._add_system_message("[red]Invalid selection. Use a number from the list.[/red]")
            return

        if idx < 0 or idx >= len(accounts):
            self._add_system_message("[red]Selection out of range.[/red]")
            return

        account = accounts[idx]
        cache = self._load_token_cache()
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        app = msal.PublicClientApplication(
            client_id=CLIENT_ID,
            authority=authority,
            token_cache=cache,
        )

        result = app.acquire_token_silent([SCOPE], account=account)
        if result and "access_token" in result:
            self._save_token_cache(cache)
            self._set_active_account_from_account(account)
            self.token = result["access_token"]
            self._set_user_from_token(self.token)
            self._add_system_message("[green]Switched to selected user.[/green]")
            return

        self._add_system_message(
            "[yellow]Cached token unavailable. Use Switch User to sign in again.[/yellow]"
        )

    @work(exclusive=True)
    async def run_query(self, query: str) -> None:
        """Run a query against the agent."""
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.status = "Thinking..."
        sources_panel = self.query_one(SourcesPanel)
        # Clear sources while the query runs to avoid stale results
        sources_panel.update_sources([])

        try:
            # Refresh token if it's expired or close to expiring
            if not self.token or self._is_token_expired(self.token):
                self._set_status("Refreshing token...")
                self.token = self._acquire_token_sync()
                self._set_user_from_token(self.token)
            response = await self._query_agent(query)

            # Update sources panel
            if response.documents:
                sources_panel.update_sources(response.documents)
            else:
                sources_panel.update_sources([])
            self.documents = response.documents

            # Build response text with source references
            response_text = response.text
            if response.documents:
                # Add source references if not already present
                source_refs = ", ".join([f"[{i}]" for i in range(1, len(response.documents) + 1)])
                if not any(f"[{i}]" in response_text for i in range(1, 4)):
                    response_text += f"\n\n(Source: {source_refs})"

            # Add assistant message
            chat_panel = self.query_one("#chat-panel", VerticalScroll)
            await chat_panel.mount(MessageBox(response_text, "assistant"))
            chat_panel.scroll_end()

        except Exception as e:
            chat_panel = self.query_one("#chat-panel", VerticalScroll)
            await chat_panel.mount(MessageBox(f"[red]Error: {e}[/red]", "system"))
            chat_panel.scroll_end()
        finally:
            status_bar.status = "Idle"

    async def _query_agent(self, query: str) -> AgentResponse:
        """Query the agent and extract documents from the response."""
        from agent_framework import ChatAgent, MCPStreamableHTTPTool
        from agent_framework.azure import AzureOpenAIChatClient

        self._validate_env()

        headers = {"Authorization": f"Bearer {self.token}"}

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
            result = await agent.run(query, tools=mcp_tool)

            # Store detailed debug info for toggle
            debug_lines = [f"Result type: {type(result).__name__}"]
            for attr in dir(result):
                if not attr.startswith("_"):
                    try:
                        val = getattr(result, attr)
                        if not callable(val):
                            val_str = str(val)[:200]
                            debug_lines.append(f"{attr}: {val_str}")
                    except Exception as e:
                        debug_lines.append(f"{attr}: <error: {e}>")
            self.raw_responses.append("\n".join(debug_lines))

            # Extract documents from tool calls/results
            documents = self._extract_documents(result)

            return AgentResponse(text=result.text, documents=documents)

    def _extract_documents(self, result: Any) -> list[Document]:
        """Extract documents from agent result messages/tool outputs."""
        documents: list[Document] = []

        def collect_payloads(obj: Any, payloads: list[dict]) -> None:
            if obj is None:
                return
            if isinstance(obj, dict):
                if "value" in obj and isinstance(obj["value"], list):
                    payloads.append(obj)
                for val in obj.values():
                    collect_payloads(val, payloads)
                return
            if isinstance(obj, (list, tuple)):
                for item in obj:
                    collect_payloads(item, payloads)
                return
            if isinstance(obj, str):
                if "\"value\"" in obj or "metadata_spo_item_weburi" in obj:
                    try:
                        parsed = json.loads(obj)
                    except json.JSONDecodeError:
                        return
                    collect_payloads(parsed, payloads)
                return
            if hasattr(obj, "__dict__"):
                for val in vars(obj).values():
                    collect_payloads(val, payloads)

        payloads: list[dict] = []
        # Walk messages and raw representations
        collect_payloads(getattr(result, "messages", None), payloads)
        collect_payloads(getattr(result, "raw_representation", None), payloads)
        collect_payloads(getattr(result, "raw_response", None), payloads)
        collect_payloads(getattr(result, "output", None), payloads)

        for payload in payloads:
            docs = self._parse_search_results(payload)
            documents.extend(docs)

        # Deduplicate by URL/title
        seen = set()
        unique_docs = []
        for doc in documents:
            key = doc.url or doc.title
            if key and key not in seen:
                seen.add(key)
                unique_docs.append(doc)

        return unique_docs

    def _parse_search_results(self, data: Any) -> list[Document]:
        """Parse search results from various formats."""
        documents: list[Document] = []

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return documents

        if isinstance(data, dict):
            if "value" in data:
                for item in data["value"]:
                    doc = self._parse_document(item)
                    if doc:
                        documents.append(doc)
            else:
                doc = self._parse_document(data)
                if doc:
                    documents.append(doc)

        return documents

    def _parse_document(self, item: dict) -> Document | None:
        """Parse a single document from search results."""
        if not isinstance(item, dict):
            return None

        title = (
            item.get("metadata_title")
            or item.get("metadata_spo_item_name")
            or item.get("title")
            or "Untitled"
        )
        url = item.get("metadata_spo_item_weburi") or item.get("url") or ""
        snippet = item.get("snippet") or item.get("content") or ""

        if title or url:
            return Document(title=title, url=url, snippet=snippet)
        return None

    def _validate_env(self) -> None:
        """Validate required environment variables."""
        missing = []
        if not CHAT_ENDPOINT:
            missing.append("CHAT_ENDPOINT")
        if not CHAT_KEY:
            missing.append("CHAT_KEY")
        if not CHAT_DEPLOYMENT:
            missing.append("CHAT_DEPLOYMENT")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

    def action_clear(self) -> None:
        """Clear the chat log."""
        chat_panel = self.query_one("#chat-panel", VerticalScroll)
        chat_panel.remove_children()
        chat_panel.mount(MessageBox("[bold]Cleared.[/bold] Ask a question to begin.", "system"))
        # Clear sources too
        sources_panel = self.query_one(SourcesPanel)
        sources_panel.update_sources([])

    def action_cancel(self) -> None:
        """Focus the input field."""
        self.query_one("#query-input", Input).focus()

    def action_toggle_raw(self) -> None:
        """Toggle raw response display."""
        self.show_raw = not self.show_raw
        if self.show_raw and self.raw_responses:
            chat_panel = self.query_one("#chat-panel", VerticalScroll)
            # Show more of the raw response for debugging
            raw_text = self.raw_responses[-1]
            chat_panel.mount(MessageBox(f"[dim]{raw_text[:2000]}[/dim]", "system"))
            chat_panel.scroll_end()

def main() -> None:
    """Run the TUI application."""
    app = AgentTUI()
    app.run()


if __name__ == "__main__":
    main()
