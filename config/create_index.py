#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Create Azure AI Search resources for SharePoint indexing with custom metadata fields.

This script creates:
1. Data Source - SharePoint connection
2. Index - With custom metadata fields (author, creation date, etc.)
3. Skillset - Document chunking, embeddings, and image verbalization
4. Indexer - Orchestrates the pipeline

The resulting index can be used with a searchIndex knowledge source for agentic retrieval.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv


def load_config():
    """Load configuration from .env file."""
    load_dotenv()
    
    config = {
        # Azure AI Search
        "search_endpoint": os.getenv("SEARCH_ENDPOINT"),
        "api_key": os.getenv("API_KEY"),
        "api_version": os.getenv("API_VERSION", "2025-11-01-preview"),
        # SharePoint connection
        "connection_string": os.getenv("CONNECTION_STRING"),
        "container_name": os.getenv("CONTAINER_NAME", "useQuery"),
        "container_query": os.getenv("CONTAINER_QUERY"),  # e.g., includeLibrariesInSite=https://...
        "additional_columns": os.getenv("ADDITIONAL_COLUMNS", "Department"),  # Comma-separated custom columns
        # ACL support
        "enable_acl": os.getenv("ENABLE_ACL", "true").lower() in ["true", "1", "yes"],
        # Resource naming
        "resource_prefix": os.getenv("RESOURCE_PREFIX", "sp-custom"),
        # Embedding model (Azure OpenAI / Foundry)
        "embedding_endpoint": os.getenv("EMBEDDING_ENDPOINT"),
        "embedding_key": os.getenv("EMBEDDING_KEY"),
        "embedding_deployment": os.getenv("EMBEDDING_DEPLOYMENT"),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        "embedding_dimensions": int(os.getenv("EMBEDDING_DIMENSIONS", "1536")),
        # Chat completion model (for image verbalization)
        "chat_endpoint": os.getenv("CHAT_ENDPOINT"),
        "chat_key": os.getenv("CHAT_KEY"),
        "chat_deployment": os.getenv("CHAT_DEPLOYMENT"),
    }
    
    # Validate required configuration
    required_fields = [
        "search_endpoint",
        "api_key",
        "connection_string",
        "embedding_endpoint",
        "embedding_key",
        "embedding_deployment",
    ]
    
    missing_fields = [field for field in required_fields if not config.get(field)]
    if missing_fields:
        print(f"Error: Missing required configuration: {', '.join(missing_fields)}")
        sys.exit(1)
    
    # Derive resource names
    prefix = config["resource_prefix"]
    config["datasource_name"] = f"{prefix}-datasource"
    config["index_name"] = f"{prefix}-index"
    config["skillset_name"] = f"{prefix}-skillset"
    config["indexer_name"] = f"{prefix}-indexer"
    
    return config


def make_request(config, method, path, body=None):
    """Make an HTTP request to Azure AI Search."""
    url = f"{config['search_endpoint']}{path}"
    params = {"api-version": config["api_version"]}
    headers = {
        "api-key": config["api_key"],
        "Content-Type": "application/json",
    }
    
    response = requests.request(
        method=method,
        url=url,
        params=params,
        headers=headers,
        json=body,
    )
    
    return response


def create_datasource(config):
    """Create the SharePoint data source."""
    print(f"\n📦 Creating data source: {config['datasource_name']}")
    
    # Build query with additionalColumns if specified
    query = config.get("container_query")
    additional_cols = config.get("additional_columns")
    
    if additional_cols and query:
        # Append additionalColumns to existing query
        query = f"{query};additionalColumns={additional_cols}"
    elif additional_cols and not query:
        # If no query but we have additional columns, we need a base query
        # User should set CONTAINER_QUERY in .env
        print(f"   ⚠️  Warning: ADDITIONAL_COLUMNS set but no CONTAINER_QUERY. Custom columns may not be indexed.")
        print(f"      Set CONTAINER_QUERY=includeLibrariesInSite=https://yoursite.sharepoint.com/sites/YourSite")
    
    datasource = {
        "name": config["datasource_name"],
        "description": "SharePoint data source for custom indexing with metadata",
        "type": "sharepoint",
        "credentials": {
            "connectionString": config["connection_string"]
        },
        "container": {
            "name": config["container_name"],
            "query": query
        }
    }
    
    # Add ACL ingestion if enabled
    if config.get("enable_acl"):
        datasource["indexerPermissionOptions"] = ["userIds", "groupIds"]
        print(f"   🔒 ACL ingestion enabled (userIds, groupIds)")
    
    response = make_request(config, "PUT", f"/datasources/{config['datasource_name']}", datasource)
    
    if response.status_code in [200, 201, 204]:
        print(f"   ✓ Data source created successfully")
        return True
    else:
        print(f"   ✗ Error creating data source: {response.status_code}")
        print(f"   {response.text}")
        return False


def create_index(config):
    """Create the search index with metadata fields."""
    print(f"\n📑 Creating index: {config['index_name']}")
    
    prefix = config["resource_prefix"]
    
    # Build fields list
    fields = [
        # Key field
            {
                "name": "uid",
                "type": "Edm.String",
                "key": True,
                "searchable": True,
                "filterable": False,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": False,
                "analyzer": "keyword"
            },
            # Parent document reference (for chunks)
            {
                "name": "snippet_parent_id",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": False
            },
            # Document URL
            {
                "name": "doc_url",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": False
            },
            # Text content chunk
            {
                "name": "snippet",
                "type": "Edm.String",
                "searchable": True,
                "filterable": False,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": False
            },
            # Image parent reference
            {
                "name": "image_snippet_parent_id",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": False
            },
            # Vector embedding
            {
                "name": "snippet_vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "filterable": False,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": False,
                "dimensions": config["embedding_dimensions"],
                "vectorSearchProfile": f"{prefix}-vector-search-profile"
            },
            # ============ METADATA FIELDS ============
            # SharePoint metadata
            {
                "name": "metadata_spo_item_name",
                "type": "Edm.String",
                "searchable": True,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": False
            },
            {
                "name": "metadata_spo_item_path",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": False
            },
            # Web URI - actual clickable link to the SharePoint document
            {
                "name": "metadata_spo_item_weburi",
                "type": "Edm.String",
                "searchable": False,
                "filterable": False,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": False
            },
            {
                "name": "metadata_spo_item_last_modified",
                "type": "Edm.DateTimeOffset",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": False
            },
            {
                "name": "metadata_spo_item_size",
                "type": "Edm.Int64",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": False
            },
            {
                "name": "metadata_spo_item_content_type",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": True
            },
            {
                "name": "metadata_spo_item_extension",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": True
            },
            # Document content metadata (extracted from Office docs, PDFs, etc.)
            {
                "name": "metadata_author",
                "type": "Edm.String",
                "searchable": True,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": True
            },
            {
                "name": "metadata_creation_date",
                "type": "Edm.DateTimeOffset",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": False
            },
            {
                "name": "metadata_last_modified",
                "type": "Edm.DateTimeOffset",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": False
            },
            {
                "name": "metadata_title",
                "type": "Edm.String",
                "searchable": True,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": False
            },
            {
                "name": "metadata_content_type",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": False,
                "facetable": True
            },
            # Custom SharePoint column - Department
            {
                "name": "Department",
                "type": "Edm.String",
                "searchable": True,
                "filterable": True,
                "retrievable": True,
                "stored": True,
                "sortable": True,
                "facetable": True
            },
        ]
    
    # Add ACL fields if enabled
    if config.get("enable_acl"):
        acl_fields = [
            # User IDs for document-level access control
            {
                "name": "UserIds",
                "type": "Collection(Edm.String)",
                "permissionFilter": "userIds",
                "filterable": True,
                "retrievable": True,  # Set to false in production for security
                "searchable": False,
                "sortable": False,
                "facetable": False
            },
            # Group IDs for document-level access control
            {
                "name": "GroupIds",
                "type": "Collection(Edm.String)",
                "permissionFilter": "groupIds",
                "filterable": True,
                "retrievable": True,  # Set to false in production for security
                "searchable": False,
                "sortable": False,
                "facetable": False
            },
        ]
        fields.extend(acl_fields)
        print(f"   🔒 ACL fields added to index (UserIds, GroupIds)")
    
    # Build index definition
    index = {
        "name": config["index_name"],
        "description": "SharePoint index with custom metadata fields for agentic retrieval",
        "fields": fields,
        "similarity": {
            "@odata.type": "#Microsoft.Azure.Search.BM25Similarity"
        },
    }
    
    # Add permission filter option if ACL is enabled
    if config.get("enable_acl"):
        index["permissionFilterOption"] = "enabled"
        print(f"   🔒 Permission filtering enabled")
    
    # Add semantic configuration (required for agentic retrieval)
    index["semantic"] = {
            "defaultConfiguration": f"{prefix}-semantic-configuration",
            "configurations": [
                {
                    "name": f"{prefix}-semantic-configuration",
                    "prioritizedFields": {
                        "prioritizedContentFields": [
                            {"fieldName": "snippet"}
                        ],
                        "prioritizedKeywordsFields": [
                            {"fieldName": "metadata_title"},
                            {"fieldName": "metadata_author"}
                        ]
                    }
                }
            ]
        }
    
    # Add vector search configuration
    index["vectorSearch"] = {
        "algorithms": [
                {
                    "name": f"{prefix}-vector-search-algorithm",
                    "kind": "hnsw",
                    "hnswParameters": {
                        "metric": "cosine",
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500
                    }
                }
            ],
            "profiles": [
                {
                    "name": f"{prefix}-vector-search-profile",
                    "algorithm": f"{prefix}-vector-search-algorithm",
                    "vectorizer": f"{prefix}-vectorizer",
                    "compression": f"{prefix}-scalar-quantization"
                }
            ],
            "vectorizers": [
                {
                    "name": f"{prefix}-vectorizer",
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": config["embedding_endpoint"],
                        "deploymentId": config["embedding_deployment"],
                        "apiKey": config["embedding_key"],
                        "modelName": config["embedding_model"]
                    }
                }
            ],
            "compressions": [
                {
                    "name": f"{prefix}-scalar-quantization",
                    "kind": "scalarQuantization",
                    "scalarQuantizationParameters": {
                        "quantizedDataType": "int8"
                    }
                }
            ]
        }

    
    response = make_request(config, "PUT", f"/indexes/{config['index_name']}", index)
    
    if response.status_code in [200, 201, 204]:
        print(f"   ✓ Index created successfully")
        return True
    else:
        print(f"   ✗ Error creating index: {response.status_code}")
        print(f"   {response.text}")
        return False


def create_skillset(config):
    """Create the skillset for document processing."""
    print(f"\n🔧 Creating skillset: {config['skillset_name']}")
    
    prefix = config["resource_prefix"]
    
    # Build skills list
    skills = [
        # Split document into chunks
        {
            "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
            "name": "SplitSkill",
            "description": "Split document content into chunks",
            "context": "/document",
            "defaultLanguageCode": "en",
            "textSplitMode": "pages",
            "maximumPageLength": 2000,
            "pageOverlapLength": 200,
            "maximumPagesToTake": 0,
            "unit": "characters",
            "inputs": [
                {"name": "text", "source": "/document/content"}
            ],
            "outputs": [
                {"name": "textItems", "targetName": "pages"}
            ]
        },
        # Generate embeddings for text chunks
        {
            "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
            "name": "AzureOpenAIEmbeddingSkill",
            "description": "Generate embeddings for text chunks",
            "context": "/document/pages/*",
            "resourceUri": config["embedding_endpoint"],
            "apiKey": config["embedding_key"],
            "deploymentId": config["embedding_deployment"],
            "dimensions": config["embedding_dimensions"],
            "modelName": config["embedding_model"],
            "inputs": [
                {"name": "text", "source": "/document/pages/*"}
            ],
            "outputs": [
                {"name": "embedding", "targetName": "text_vector"}
            ]
        }
    ]
    
    # Add image verbalization skills if chat model is configured
    # NOTE: ACL ingestion is incompatible with ChatCompletionSkill in preview
    # Image verbalization is automatically disabled when ACL is enabled
    if config.get("chat_endpoint") and config.get("chat_key") and config.get("chat_deployment") and not config.get("enable_acl"):
        # Image verbalization
        skills.append({
            "@odata.type": "#Microsoft.Skills.Custom.ChatCompletionSkill",
            "name": "GenAISkill",
            "description": "Generate descriptions for images",
            "context": "/document/normalized_images/*",
            "uri": f"{config['chat_endpoint']}/openai/deployments/{config['chat_deployment']}/chat/completions?api-version=2024-10-21",
            "httpMethod": "POST",
            "timeout": "PT1M",
            "batchSize": 1,
            "apiKey": config["chat_key"],
            "inputs": [
                {"name": "systemMessage", "source": "='You are tasked with generating concise, accurate descriptions of images, figures, diagrams, or charts in documents.'"},
                {"name": "userMessage", "source": "='Please describe this image.'"},
                {"name": "image", "source": "/document/normalized_images/*/data"}
            ],
            "outputs": [
                {"name": "response", "targetName": "verbalizedImage"}
            ]
        })
        # Embeddings for verbalized images
        skills.append({
            "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
            "name": "VerbalizedImageAzureOpenAIEmbeddingSkill",
            "description": "Generate embeddings for verbalized images",
            "context": "/document/normalized_images/*",
            "resourceUri": config["embedding_endpoint"],
            "apiKey": config["embedding_key"],
            "deploymentId": config["embedding_deployment"],
            "dimensions": config["embedding_dimensions"],
            "modelName": config["embedding_model"],
            "inputs": [
                {"name": "text", "source": "/document/normalized_images/*/verbalizedImage"}
            ],
            "outputs": [
                {"name": "embedding", "targetName": "verbalizedImage_vector"}
            ]
        })
    
    # Index projections - map enriched content to index fields
    selectors = [
        # Text chunks projection
        {
            "targetIndexName": config["index_name"],
            "parentKeyFieldName": "snippet_parent_id",
            "sourceContext": "/document/pages/*",
            "mappings": [
                {"name": "snippet_vector", "source": "/document/pages/*/text_vector"},
                {"name": "snippet", "source": "/document/pages/*"},
                {"name": "doc_url", "source": "/document/metadata_spo_item_path"},
                # Metadata mappings
                {"name": "metadata_spo_item_name", "source": "/document/metadata_spo_item_name"},
                {"name": "metadata_spo_item_path", "source": "/document/metadata_spo_item_path"},
                {"name": "metadata_spo_item_weburi", "source": "/document/metadata_spo_item_weburi"},
                {"name": "metadata_spo_item_last_modified", "source": "/document/metadata_spo_item_last_modified"},
                {"name": "metadata_spo_item_size", "source": "/document/metadata_spo_item_size"},
                {"name": "metadata_spo_item_content_type", "source": "/document/metadata_spo_item_content_type"},
                {"name": "metadata_spo_item_extension", "source": "/document/metadata_spo_item_extension"},
                {"name": "metadata_author", "source": "/document/metadata_author"},
                {"name": "metadata_creation_date", "source": "/document/metadata_creation_date"},
                {"name": "metadata_last_modified", "source": "/document/metadata_last_modified"},
                {"name": "metadata_title", "source": "/document/metadata_title"},
                {"name": "metadata_content_type", "source": "/document/metadata_content_type"},
                # Custom SharePoint column
                {"name": "Department", "source": "/document/Department"},
            ]
        }
    ]
    
    # Add ACL mappings to text chunks if ACL is enabled
    if config.get("enable_acl"):
        selectors[0]["mappings"].extend([
            {"name": "UserIds", "source": "/document/metadata_user_ids"},
            {"name": "GroupIds", "source": "/document/metadata_group_ids"},
        ])
        print("   🔒 ACL mappings added to text chunks")
    
    # Add image projection if chat model is configured
    if config.get("chat_endpoint") and config.get("chat_key") and config.get("chat_deployment"):
        selectors.append({
            "targetIndexName": config["index_name"],
            "parentKeyFieldName": "image_snippet_parent_id",
            "sourceContext": "/document/normalized_images/*",
            "mappings": [
                {"name": "snippet_vector", "source": "/document/normalized_images/*/verbalizedImage_vector"},
                {"name": "snippet", "source": "/document/normalized_images/*/verbalizedImage"},
                {"name": "doc_url", "source": "/document/metadata_spo_item_path"},
                # Metadata mappings for images
                {"name": "metadata_spo_item_name", "source": "/document/metadata_spo_item_name"},
                {"name": "metadata_spo_item_path", "source": "/document/metadata_spo_item_path"},
                {"name": "metadata_spo_item_weburi", "source": "/document/metadata_spo_item_weburi"},
                {"name": "metadata_spo_item_last_modified", "source": "/document/metadata_spo_item_last_modified"},
                {"name": "metadata_spo_item_size", "source": "/document/metadata_spo_item_size"},
                {"name": "metadata_spo_item_content_type", "source": "/document/metadata_spo_item_content_type"},
                {"name": "metadata_spo_item_extension", "source": "/document/metadata_spo_item_extension"},
                {"name": "metadata_author", "source": "/document/metadata_author"},
                {"name": "metadata_creation_date", "source": "/document/metadata_creation_date"},
                {"name": "metadata_last_modified", "source": "/document/metadata_last_modified"},
                {"name": "metadata_title", "source": "/document/metadata_title"},
                {"name": "metadata_content_type", "source": "/document/metadata_content_type"},
                # Custom SharePoint column
                {"name": "Department", "source": "/document/Department"},
            ]
        })
        
        # Add ACL mappings to image chunks if ACL is enabled
        if config.get("enable_acl"):
            selectors[-1]["mappings"].extend([
                {"name": "UserIds", "source": "/document/metadata_user_ids"},
                {"name": "GroupIds", "source": "/document/metadata_group_ids"},
            ])
            print("   🔒 ACL mappings added to image chunks")
    
    skillset = {
        "name": config["skillset_name"],
        "description": "Skillset for SharePoint indexing with metadata extraction",
        "skills": skills,
        "indexProjections": {
            "selectors": selectors,
            "parameters": {
                "projectionMode": "skipIndexingParentDocuments"
            }
        }
    }
    
    response = make_request(config, "PUT", f"/skillsets/{config['skillset_name']}", skillset)
    
    if response.status_code in [200, 201, 204]:
        print(f"   ✓ Skillset created successfully")
        return True
    else:
        print(f"   ✗ Error creating skillset: {response.status_code}")
        print(f"   {response.text}")
        return False


def create_indexer(config):
    """Create the indexer to orchestrate the pipeline."""
    print(f"\n🔄 Creating indexer: {config['indexer_name']}")
    
    indexer = {
        "name": config["indexer_name"],
        "description": "Indexer for SharePoint with metadata extraction",
        "dataSourceName": config["datasource_name"],
        "skillsetName": config["skillset_name"],
        "targetIndexName": config["index_name"],
        "disabled": False,
        "schedule": {
            "interval": "P1D",  # Daily
        },
        "parameters": {
            "maxFailedItems": -1,
            "maxFailedItemsPerBatch": -1,
            "configuration": {
                "dataToExtract": "contentAndMetadata",
                "parsingMode": "default",
                "allowSkillsetToReadFileData": True,
                "imageAction": "generateNormalizedImages" if (config.get("chat_deployment") and not config.get("enable_acl")) else "none"
            }
        },
        "fieldMappings": [
            # Map SharePoint path to doc_url (for non-chunked scenarios)
            {
                "sourceFieldName": "metadata_spo_item_path",
                "targetFieldName": "doc_url"
            }
            # Note: Custom SharePoint columns from additionalColumns are auto-mapped
            # to fields with matching names (e.g., Department -> metadata_Department needs no mapping)
        ]
    }
    
    # Add ACL field mappings if enabled
    if config.get("enable_acl"):
        indexer["fieldMappings"].extend([
            {
                "sourceFieldName": "metadata_user_ids",
                "targetFieldName": "UserIds"
            },
            {
                "sourceFieldName": "metadata_group_ids",
                "targetFieldName": "GroupIds"
            }
        ])
        print(f"   🔒 ACL field mappings added (metadata_user_ids -> UserIds, metadata_group_ids -> GroupIds)")
    
    indexer["outputFieldMappings"] = []
    
    # Warn if image verbalization is skipped due to ACL
    if config.get("enable_acl") and config.get("chat_deployment"):
        print("   ⚠️  Image verbalization disabled (incompatible with ACL in preview)")
    
    response = make_request(config, "PUT", f"/indexers/{config['indexer_name']}", indexer)
    
    if response.status_code in [200, 201, 204]:
        print(f"   ✓ Indexer created successfully")
        return True
    else:
        print(f"   ✗ Error creating indexer: {response.status_code}")
        print(f"   {response.text}")
        return False


def run_indexer(config):
    """Trigger the indexer to start indexing."""
    print(f"\n▶️  Running indexer: {config['indexer_name']}")
    
    response = make_request(config, "POST", f"/indexers/{config['indexer_name']}/run")
    
    if response.status_code == 202:
        print(f"   ✓ Indexer started successfully")
        return True
    else:
        print(f"   ✗ Error running indexer: {response.status_code}")
        print(f"   {response.text}")
        return False


def reset_indexer(config):
    """Reset the indexer to reprocess all documents."""
    print(f"\n🔄 Resetting indexer: {config['indexer_name']}")
    
    response = make_request(config, "POST", f"/indexers/{config['indexer_name']}/reset")
    
    if response.status_code in [204, 202]:
        print(f"   ✓ Indexer reset successfully")
        return True
    else:
        print(f"   ✗ Error resetting indexer: {response.status_code}")
        print(f"   {response.text}")
        return False


def get_indexer_status(config):
    """Get the current status of the indexer."""
    print(f"\n📊 Checking indexer status: {config['indexer_name']}")
    
    response = make_request(config, "GET", f"/indexers/{config['indexer_name']}/status")
    
    if response.status_code == 200:
        status = response.json()
        print(f"   Status: {status.get('status', 'unknown')}")
        if status.get('lastResult'):
            last = status['lastResult']
            print(f"   Last run: {last.get('status', 'unknown')}")
            print(f"   Items processed: {last.get('itemsProcessed', 0)}")
            print(f"   Items failed: {last.get('itemsFailed', 0)}")
        return status
    else:
        print(f"   ✗ Error getting status: {response.status_code}")
        return None


def delete_resources(config):
    """Delete all created resources (for cleanup)."""
    print("\n🗑️  Deleting resources...")
    
    # Delete in reverse order
    for resource_type, name_key in [
        ("indexers", "indexer_name"),
        ("skillsets", "skillset_name"),
        ("indexes", "index_name"),
        ("datasources", "datasource_name"),
    ]:
        name = config[name_key]
        response = make_request(config, "DELETE", f"/{resource_type}/{name}")
        if response.status_code in [204, 404]:
            print(f"   ✓ Deleted {resource_type}/{name}")
        else:
            print(f"   ✗ Error deleting {resource_type}/{name}: {response.status_code}")


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Create Azure AI Search resources for SharePoint indexing with metadata"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete existing resources instead of creating"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the indexer after creation"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check indexer status"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the indexer to reprocess all documents"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("SharePoint Index Resources Creator")
    print("=" * 60)
    
    # Load configuration
    config = load_config()
    
    print(f"\nConfiguration:")
    print(f"  Search Endpoint: {config['search_endpoint']}")
    print(f"  Resource Prefix: {config['resource_prefix']}")
    print(f"  Embedding Model: {config['embedding_model']}")
    print(f"  Image Verbalization: {'Enabled' if config.get('chat_deployment') else 'Disabled'}")
    print(f"  ACL Support: {'Enabled' if config.get('enable_acl') else 'Disabled'}")
    
    if args.delete:
        delete_resources(config)
        return
    
    if args.status:
        get_indexer_status(config)
        return
    
    if args.reset:
        reset_indexer(config)
        run_indexer(config)
        return
    
    # Create resources in order
    success = True
    
    if success:
        success = create_datasource(config)
    
    if success:
        success = create_index(config)
    
    if success:
        success = create_skillset(config)
    
    if success:
        success = create_indexer(config)
    
    if success and args.run:
        run_indexer(config)
    
    # Summary
    print("\n" + "=" * 60)
    if success:
        print("✅ All resources created successfully!")
        print(f"\nCreated resources:")
        print(f"  - Data source: {config['datasource_name']}")
        print(f"  - Index: {config['index_name']}")
        print(f"  - Skillset: {config['skillset_name']}")
        print(f"  - Indexer: {config['indexer_name']}")
        print(f"\nNext steps:")
        print(f"  1. Run the indexer: uv run create_sp_index_resources.py --run")
        print(f"  2. Check status: uv run create_sp_index_resources.py --status")
        print(f"  3. Create a searchIndex knowledge source pointing to '{config['index_name']}'")
    else:
        print("❌ Some resources failed to create. Check errors above.")
        print("   You may need to run with --delete first to clean up.")
    print("=" * 60)


if __name__ == "__main__":
    main()
