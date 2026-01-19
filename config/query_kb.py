#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "azure-search-documents>=11.7.0b2",
#     "azure-identity>=1.15.0",
#     "python-dotenv>=1.0.0",
#     "requests>=2.31.0",
#     "pyjwt>=2.8.0",
# ]
# ///
"""
Query the Knowledge Base using Azure AI Search Agentic Retrieval.

This script sends queries to the knowledge base and retrieves answers
synthesized from the indexed SharePoint content.

With ACL support: If ENABLE_ACL=true, uses user token for permission filtering.
"""

import json
import os
import sys
from .shared import load_base_env
import requests
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    SearchIndexKnowledgeSourceParams,
    KnowledgeRetrievalLowReasoningEffort,
)


def query_knowledge_base(query: str, show_activity: bool = False, show_references: bool = False, filter_expr: str | None = None):
    """Query the knowledge base with a user question.
    
    Args:
        query: The question to ask
        show_activity: Show reasoning activity
        show_references: Show document references
        filter_expr: OData filter expression (e.g., "Department eq 'IT'")
    """
    
    # Load configuration
    load_base_env()
    
    search_endpoint = os.getenv("SEARCH_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("API_KEY")
    enable_acl = os.getenv("ENABLE_ACL", "false").lower() in ["true", "1", "yes"]
    api_version = os.getenv("API_VERSION", "2025-11-01-preview")
    
    # Knowledge base and source names
    resource_prefix = os.getenv("RESOURCE_PREFIX", "sp-custom")
    knowledge_source_name = f"{resource_prefix}-ks"
    knowledge_base_name = os.getenv("KNOWLEDGE_BASE_NAME", f"{resource_prefix}-kb")
    
    # Validate config
    if not search_endpoint or not api_key:
        print("Error: Missing SEARCH_ENDPOINT or API_KEY in .env")
        return None
    
    # If ACL is enabled, use REST API with user token
    # SDK doesn't support x-ms-query-source-authorization header yet
    if enable_acl:
        return query_with_acl(
            search_endpoint, api_key, api_version,
            knowledge_base_name, knowledge_source_name,
            query, show_activity, show_references, filter_expr
        )
    
    # Without ACL: Use SDK (original behavior)
    kb_client = KnowledgeBaseRetrievalClient(
        endpoint=search_endpoint,
        knowledge_base_name=knowledge_base_name,
        credential=AzureKeyCredential(api_key)
    )
    
    # Build retrieval request
    request = KnowledgeBaseRetrievalRequest(
        messages=[
            KnowledgeBaseMessage(
                role="user",
                content=[KnowledgeBaseMessageTextContent(text=query)]
            ),
        ],
        knowledge_source_params=[
            SearchIndexKnowledgeSourceParams(
                knowledge_source_name=knowledge_source_name,
                include_references=True,
                include_reference_source_data=True,
                filter_add_on=filter_expr,
            )
        ],
        include_activity=True,
        retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort,
    )
    
    # Execute retrieval
    print(f"\nQuerying knowledge base '{knowledge_base_name}'...")
    if filter_expr:
        print(f"Filter: {filter_expr}")
    print("-" * 60)
    
    try:
        result = kb_client.retrieve(retrieval_request=request)
    except Exception as e:
        print(f"Error querying knowledge base: {e}")
        return None
    
    # Display response
    if result.response:
        print("\n📝 Answer:\n")
        for resp in result.response:
            for content in resp.content:
                print(content.text)
    else:
        print("No response received.")
    
    # Display activity (reasoning steps) if requested
    if show_activity and result.activity:
        print("\n" + "-" * 60)
        print("🔍 Activity (reasoning steps):\n")
        print(json.dumps([a.as_dict() for a in result.activity], indent=2))
    
    # Display references if requested
    if show_references and result.references:
        print("\n" + "-" * 60)
        print("📚 References:\n")
        print(json.dumps([r.as_dict() for r in result.references], indent=2))
    
    return result


def interactive_mode():
    """Run in interactive chat mode."""
    print("=" * 60)
    print("Azure AI Search - Knowledge Base Query Tool")
    print("=" * 60)
    print("\nType your questions to query the SharePoint knowledge base.")
    print("Commands:")
    print("  /activity        - Toggle showing activity/reasoning steps")
    print("  /refs            - Toggle showing references")
    print("  /filter <expr>   - Set OData filter (e.g., /filter Department eq 'IT')")
    print("  /filter          - Clear filter")
    print("  /quit            - Exit")
    print("-" * 60)
    
    show_activity = False
    show_references = False
    filter_expr = None
    
    while True:
        try:
            query = input("\n❓ Your question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye!")
            break
        
        if not query:
            continue
        
        if query.lower() == "/quit":
            print("Goodbye!")
            break
        elif query.lower() == "/activity":
            show_activity = not show_activity
            print(f"Activity display: {'ON' if show_activity else 'OFF'}")
            continue
        elif query.lower() == "/refs":
            show_references = not show_references
            print(f"References display: {'ON' if show_references else 'OFF'}")
            continue
        elif query.lower().startswith("/filter"):
            parts = query[7:].strip()
            if parts:
                filter_expr = parts
                print(f"Filter set: {filter_expr}")
            else:
                filter_expr = None
                print("Filter cleared")
            continue
        
        query_knowledge_base(query, show_activity, show_references, filter_expr)


def main():
    """Main entry point.
    
    Usage:
        uv run query_kb.py                           # Interactive mode
        uv run query_kb.py "your question"           # Single query
        uv run query_kb.py --filter "Department eq 'IT'" "your question"
    """
    filter_expr = None
    args = sys.argv[1:]
    
    # Parse --filter argument
    if "--filter" in args:
        idx = args.index("--filter")
        if idx + 1 < len(args):
            filter_expr = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
    
    if args:
        # Query provided as command line argument
        query = " ".join(args)
        query_knowledge_base(query, show_activity=False, show_references=True, filter_expr=filter_expr)
    else:
        # Interactive mode
        interactive_mode()


if __name__ == "__main__":
    main()
