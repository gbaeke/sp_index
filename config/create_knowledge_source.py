#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Create a searchIndex knowledge source that wraps the custom SharePoint index.

This allows you to use your custom index (with metadata fields) in agentic retrieval
via a knowledge base.
"""

import os
import sys
import json
from .shared import load_base_env, validate_config, make_request


def load_config():
    """Load configuration from .env file."""
    load_base_env()
    
    config = {
        "search_endpoint": os.getenv("SEARCH_ENDPOINT"),
        "api_key": os.getenv("API_KEY"),
        "api_version": os.getenv("API_VERSION", "2025-11-01-preview"),
        "resource_prefix": os.getenv("RESOURCE_PREFIX", "sp-custom"),
    }
    
    # Validate required configuration
    validate_config(config, ["search_endpoint", "api_key"])
    
    # Derive names
    config["index_name"] = f"{config['resource_prefix']}-index"
    config["knowledge_source_name"] = f"{config['resource_prefix']}-ks"
    
    return config


def create_knowledge_source(config):
    """Create a searchIndex knowledge source wrapping the custom index."""
    
    # Source data fields for citations - these appear in source_data in the response
    # Fields must be retrievable in the index
    source_data_fields = [
        "metadata_spo_item_weburi",      # Web URL - actual clickable link to SharePoint doc
        "snippet",                       # Content/text snippet
        "metadata_spo_item_name",        # SharePoint item name
        "metadata_author",               # Document author
        "metadata_creation_date",        # Creation date
        "metadata_last_modified",        # Last modified date
        "metadata_title",                # Document title
        "metadata_spo_item_content_type", # Content type (e.g., Document)
        "metadata_spo_item_size",        # File size
        "Department",                    # Custom SharePoint column - Department
    ]
    
    # Fields to search against
    search_fields = [
        "snippet",
        "metadata_author",
        "metadata_title",
        "metadata_spo_item_name",
    ]
    
    knowledge_source = {
        "name": config["knowledge_source_name"],
        "kind": "searchIndex",
        "description": f"Knowledge source wrapping custom SharePoint index '{config['index_name']}' with metadata fields",
        "searchIndexParameters": {
            "searchIndexName": config["index_name"],
            "sourceDataFields": [{"name": field} for field in source_data_fields],
            "searchFields": [{"name": field} for field in search_fields],
        }
    }
    
    response = make_request(
        config, 
        "PUT", 
        f"/knowledgesources/{config['knowledge_source_name']}", 
        knowledge_source
    )
    
    if response.status_code in [200, 201, 204]:
        print(f"✓ Knowledge source '{config['knowledge_source_name']}' created or updated successfully.")
        print(f"\nKnowledge source details:")
        print(f"  - Name: {config['knowledge_source_name']}")
        print(f"  - Index: {config['index_name']}")
        print(f"\nSource data fields (for citations):")
        for field in source_data_fields:
            print(f"    - {field}")
        print(f"\nSearch fields:")
        for field in search_fields:
            print(f"    - {field}")
        # Return JSON if available, else return empty dict
        try:
            return response.json() if response.text else {}
        except:
            return {}
    else:
        print(f"✗ Error creating knowledge source: {response.status_code}")
        print(f"  {response.text}")
        sys.exit(1)


def list_knowledge_sources(config):
    """List all existing knowledge sources."""
    response = make_request(
        config, 
        "GET", 
        "/knowledgesources",
    )
    
    if response.status_code == 200:
        sources = response.json()
        print("Existing Knowledge Sources:")
        for source in sources.get("value", []):
            print(f"  - {source['name']} ({source.get('kind', 'unknown')})")
        return sources
    else:
        print(f"Error listing knowledge sources: {response.status_code}")
        print(f"  {response.text}")
        return None


def delete_knowledge_source(config):
    """Delete the knowledge source."""
    response = make_request(
        config, 
        "DELETE", 
        f"/knowledgesources/{config['knowledge_source_name']}"
    )
    
    if response.status_code in [204, 404]:
        print(f"✓ Knowledge source '{config['knowledge_source_name']}' deleted.")
    else:
        print(f"✗ Error deleting knowledge source: {response.status_code}")
        print(f"  {response.text}")


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Create a searchIndex knowledge source for the custom SharePoint index"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List existing knowledge sources"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the knowledge source"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("SearchIndex Knowledge Source Creator")
    print("=" * 60)
    
    config = load_config()
    
    print(f"\nConfiguration:")
    print(f"  Search Endpoint: {config['search_endpoint']}")
    print(f"  Index Name: {config['index_name']}")
    print(f"  Knowledge Source Name: {config['knowledge_source_name']}")
    
    if args.list:
        print()
        list_knowledge_sources(config)
        return
    
    if args.delete:
        print()
        delete_knowledge_source(config)
        return
    
    print()
    create_knowledge_source(config)
    
    print("\n" + "=" * 60)
    print("Next steps:")
    print(f"  1. Create a knowledge base that references '{config['knowledge_source_name']}'")
    print(f"  2. Use the knowledge base with agentic retrieval")
    print("=" * 60)


if __name__ == "__main__":
    main()
