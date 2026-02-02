#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "azure-search-documents>=11.7.0b2",
#     "azure-identity>=1.16.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Create a remote SharePoint knowledge source and knowledge base, then query it.

IMPORTANT: Querying a remote SharePoint knowledge source requires the logged-on user to have a Copilot license in Microsoft 365. If the user does NOT have a Copilot license, retrieval will fail with a Forbidden error.
For users without a Copilot license, use the "searchIndex" (indexed) knowledge source instead, which does not require Copilot.

This script uses the logged-on user's identity for both creation and query.
It assumes the user has permissions in Azure AI Search and SharePoint.
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    KnowledgeBase,
    KnowledgeSourceReference,
    RemoteSharePointKnowledgeSource,
    RemoteSharePointKnowledgeSourceParameters,
)
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalMinimalReasoningEffort,
    KnowledgeRetrievalSemanticIntent,
    RemoteSharePointKnowledgeSourceParams,
)


def load_config() -> dict:
    """Load configuration from .env file."""
    load_dotenv()

    config = {
        "search_endpoint": os.getenv("SEARCH_ENDPOINT"),
        "api_version": os.getenv("API_VERSION", "2025-11-01-preview"),
        "resource_prefix": os.getenv("RESOURCE_PREFIX", "sp-custom"),
        "knowledge_base_name": os.getenv("KNOWLEDGE_BASE_NAME"),
    }

    if not config.get("knowledge_base_name"):
        config["knowledge_base_name"] = f"{config['resource_prefix']}-kb"

    missing = [key for key in ("search_endpoint", "knowledge_base_name") if not config.get(key)]
    if missing:
        print(f"Error: Missing required configuration: {', '.join(missing)}")
        sys.exit(1)

    config["knowledge_source_name"] = os.getenv(
        "KS_NAME", f"{config['resource_prefix']}-remote-sp-ks"
    )
    config["ks_description"] = os.getenv(
        "KS_DESCRIPTION", "Remote SharePoint knowledge source"
    )
    config["ks_filter_expression"] = os.getenv("KS_FILTER_EXPRESSION")
    config["ks_resource_metadata"] = os.getenv("KS_RESOURCE_METADATA", "Author,Title")
    config["ks_container_type_id"] = os.getenv("KS_CONTAINER_TYPE_ID")
    config["filter_add_on"] = os.getenv("KS_FILTER_EXPRESSION_ADD_ON")

    return config


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def create_or_update_knowledge_source(index_client: SearchIndexClient, config: dict) -> None:
    """Create or update a remote SharePoint knowledge source."""
    parameters = RemoteSharePointKnowledgeSourceParameters(
        filter_expression=config.get("ks_filter_expression"),
        resource_metadata=parse_csv(config.get("ks_resource_metadata")),
        container_type_id=config.get("ks_container_type_id"),
    )
    knowledge_source = RemoteSharePointKnowledgeSource(
        name=config["knowledge_source_name"],
        description=config["ks_description"],
        remote_share_point_parameters=parameters,
    )

    index_client.create_or_update_knowledge_source(knowledge_source)
    print(f"✓ Knowledge source '{config['knowledge_source_name']}' created or updated.")


def create_or_update_knowledge_base(index_client: SearchIndexClient, config: dict) -> None:
    """Create or update a knowledge base referencing the knowledge source."""
    knowledge_base = KnowledgeBase(
        name=config["knowledge_base_name"],
        knowledge_sources=[
            KnowledgeSourceReference(name=config["knowledge_source_name"])
        ],
    )

    index_client.create_or_update_knowledge_base(knowledge_base)
    print(f"✓ Knowledge base '{config['knowledge_base_name']}' created or updated.")


def build_request(query: str, config: dict) -> KnowledgeBaseRetrievalRequest:
    request = KnowledgeBaseRetrievalRequest(
        include_activity=True,
        retrieval_reasoning_effort=KnowledgeRetrievalMinimalReasoningEffort(),
        intents=[KnowledgeRetrievalSemanticIntent(search=query)],
        knowledge_source_params=[
            RemoteSharePointKnowledgeSourceParams(
                knowledge_source_name=config["knowledge_source_name"],
                filter_expression_add_on=config.get("filter_add_on"),
                include_references=True,
                include_reference_source_data=True,
            )
        ],
    )
    return request


def main() -> None:
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Create a remote SharePoint knowledge source and knowledge base, then query it."
    )
    parser.add_argument(
        "query",
        help="Question or prompt to retrieve against SharePoint (Copilot license REQUIRED for remote querying)."
    )
    parser.add_argument(
        "--skip-create",
        action="store_true",
        help="Skip creating/updating the knowledge source and knowledge base.",
    )
    args = parser.parse_args()

    config = load_config()

    print("=" * 60)
    print("Remote SharePoint Knowledge Base")
    print("=" * 60)
    print(f"Search Endpoint: {config['search_endpoint']}")
    print(f"Knowledge Source: {config['knowledge_source_name']}")
    print(f"Knowledge Base: {config['knowledge_base_name']}")

    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(
        endpoint=config["search_endpoint"],
        credential=credential,
    )

    if not args.skip_create:
        print("\n📦 Creating or updating knowledge source and knowledge base...")
        create_or_update_knowledge_source(index_client, config)
        create_or_update_knowledge_base(index_client, config)

    kb_client = KnowledgeBaseRetrievalClient(
        endpoint=config["search_endpoint"],
        knowledge_base_name=config["knowledge_base_name"],
        credential=credential,
    )

    request = build_request(args.query, config)
    token = credential.get_token("https://search.azure.com/.default").token
    try:
        result = kb_client.retrieve(
            retrieval_request=request,
            x_ms_query_source_authorization=token,
        )
    except Exception as ex:
        err_msg = str(ex)
        if "403" in err_msg or "Forbidden" in err_msg or "Authorization Failed" in err_msg:
            print("\n✗ Authorization Failed: This feature requires an active Microsoft Copilot license for the querying user.")
            print("✗ Remote SharePoint retrieval is not available without a Copilot license. Use the 'searchIndex' knowledge source workflow instead if Copilot is not licensed.")
            sys.exit(2)
        else:
            print(f"\n✗ Retrieval query failed: {err_msg}")
            sys.exit(3)

    print("\n📝 Response:")
    if result.response:
        content = result.response[0].content[0]
        text = getattr(content, "text", str(content))
        print(text)
    else:
        print("No response content returned.")

    print("\n📊 Activity:")
    for activity in result.activity or []:
        if hasattr(activity, "as_dict"):
            payload = activity.as_dict()
        elif hasattr(activity, "__dict__"):
            payload = activity.__dict__
        else:
            payload = {"type": "unknown", "value": str(activity)}
        activity_type = payload.get("type", "unknown")
        print(f"- {activity_type}: {json.dumps(payload, indent=2)}")


if __name__ == "__main__":
    main()
