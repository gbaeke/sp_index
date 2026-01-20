#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "azure-search-documents>=11.7.0b2",
#     "azure-identity>=1.15.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Create a Knowledge Base in Azure AI Search.

This script creates a knowledge base that references the knowledge source
created by create_knowledge_source.py and uses an Azure Foundry model
for chat completion/reasoning.
"""

import os

try:
    from .shared import load_base_env
except ImportError:
    from shared import load_base_env

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeSourceReference,
    AzureOpenAIVectorizerParameters,
    KnowledgeRetrievalOutputMode,
    KnowledgeRetrievalLowReasoningEffort,
)


def main():
    print("=" * 70)
    print("Azure AI Search - Knowledge Base Creator")
    print("=" * 70)

    # Load configuration from .env
    print("\n1. Loading configuration from .env...")
    load_base_env()

    search_endpoint = os.getenv("SEARCH_ENDPOINT")
    api_key = os.getenv("API_KEY")
    
    # Resource prefix (matches the one used in working_solution scripts)
    resource_prefix = os.getenv("RESOURCE_PREFIX", "sp-custom")
    knowledge_source_name = f"{resource_prefix}-ks"
    
    # Knowledge base name
    knowledge_base_name = os.getenv("KNOWLEDGE_BASE_NAME", f"{resource_prefix}-kb")
    
    # Chat completion model (Foundry)
    chat_endpoint = os.getenv("CHAT_ENDPOINT")
    chat_key = os.getenv("CHAT_KEY")
    chat_deployment = os.getenv("CHAT_DEPLOYMENT")
    chat_model = os.getenv("CHAT_MODEL")

    # Validate required config
    missing = []
    if not search_endpoint:
        missing.append("SEARCH_ENDPOINT")
    if not api_key:
        missing.append("API_KEY")
    if not chat_endpoint:
        missing.append("CHAT_ENDPOINT")
    if not chat_key:
        missing.append("CHAT_KEY")
    if not chat_deployment:
        missing.append("CHAT_DEPLOYMENT")
    if not chat_model:
        missing.append("CHAT_MODEL")

    if missing:
        print(f"   ✗ Missing required configuration: {', '.join(missing)}")
        return

    print("   ✓ Configuration loaded successfully")
    print(f"   - Knowledge Source: {knowledge_source_name}")
    print(f"   - Knowledge Base: {knowledge_base_name}")
    print(f"   - Chat Model: {chat_deployment}")

    # Create index client
    index_client = SearchIndexClient(
        endpoint=search_endpoint,
        credential=AzureKeyCredential(api_key)
    )

    # Check if knowledge source exists
    print("\n2. Verifying knowledge source exists...")
    try:
        existing_sources = list(index_client.list_knowledge_sources())
        source_names = [s.name for s in existing_sources]
        if knowledge_source_name not in source_names:
            print(f"   ✗ Knowledge source '{knowledge_source_name}' not found.")
            print(f"   Available sources: {source_names}")
            print("   Please run create_knowledge_source.py first.")
            return
        print(f"   ✓ Knowledge source '{knowledge_source_name}' found")
    except Exception as e:
        print(f"   ✗ Error checking knowledge sources: {e}")
        return

    # Configure the chat completion model (Azure OpenAI / Foundry)
    print("\n3. Configuring chat completion model...")
    aoai_params = AzureOpenAIVectorizerParameters(
        resource_url=chat_endpoint,
        api_key=chat_key,
        deployment_name=chat_deployment,
        model_name=chat_model,
    )

    # Create knowledge base definition
    print("\n4. Creating knowledge base...")
    knowledge_base = KnowledgeBase(
        name=knowledge_base_name,
        description="Knowledge base for SharePoint content with agentic retrieval capabilities.",
        retrieval_instructions="Use this knowledge source to answer questions about SharePoint documents and content.",
        answer_instructions="Provide a concise and informative answer based on the retrieved documents. Include relevant details and cite sources when possible.",
        output_mode=KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS,
        knowledge_sources=[
            KnowledgeSourceReference(name=knowledge_source_name),
        ],
        models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=aoai_params)],
        encryption_key=None,
        retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort,
    )

    try:
        index_client.create_or_update_knowledge_base(knowledge_base)
        print(f"   ✓ Knowledge base '{knowledge_base_name}' created or updated successfully.")
    except Exception as e:
        print(f"   ✗ Error creating knowledge base: {e}")
        return

    # List all knowledge bases
    print("\n5. Listing all knowledge bases...")
    try:
        knowledge_bases = list(index_client.list_knowledge_bases())
        print(f"   Found {len(knowledge_bases)} knowledge base(s):")
        for kb in knowledge_bases:
            print(f"   - {kb.name}")
    except Exception as e:
        print(f"   ✗ Error listing knowledge bases: {e}")

    print("\n" + "=" * 70)
    print("Knowledge base creation completed.")
    print("=" * 70)
    print("\nYou can now query the knowledge base using:")
    print(f"  - REST API: POST {search_endpoint}/knowledgebases/{knowledge_base_name}/retrieve")
    print(f"  - MCP endpoint: {search_endpoint}/knowledgebases/{knowledge_base_name}/mcp")


if __name__ == "__main__":
    main()
