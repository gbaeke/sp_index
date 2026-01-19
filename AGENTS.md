# Agent Coding Guidelines

This document provides guidance for AI coding agents working in the **anb-sp-index** repository - an Azure AI Search SharePoint Knowledge Source Creator project.

## Project Overview

Python-based tool for creating and managing Azure AI Search indexes from SharePoint data sources with document-level ACL support and agentic retrieval capabilities.

**Tech Stack:**
- Python 3.10+
- Azure AI Search SDK
- Azure Identity & Core libraries
- UV package manager (fast Python installer/runner)
- Bash scripts for infrastructure deployment

## Repository Structure

```
/Users/geertbaeke/projects/sp_index/
├── config/                    # Main Python scripts for index/KB management
│   ├── create_index.py       # Create datasource, index, skillset, indexer
│   ├── create_knowledge_source.py
│   ├── create_knowledge_base.py
│   ├── query_kb.py           # Query knowledge base
│   ├── query_acl.py          # Query with ACL support
│   └── query_elevated.py     # Query with elevated permissions
├── scripts/                   # Bash deployment scripts
│   ├── create_resources.sh   # Deploy Azure resources
│   ├── create_sp_app_registration.sh
│   └── destroy_resources.sh
├── ai_search_jsons/          # JSON templates/configs
├── pyproject.toml            # Python project configuration
├── uv.lock                   # UV lockfile
├── .env.example              # Environment template
└── README.md                 # User documentation

Working directory: /Users/geertbaeke/projects/sp_index/config
```

## Commands

### Running Scripts

All Python scripts use UV shebang (`#!/usr/bin/env -S uv run`) and can be executed directly:

```bash
# From config directory
uv run create_index.py [--run|--status|--reset|--delete]
uv run create_knowledge_source.py [--list|--delete]
uv run create_knowledge_base.py
uv run query_kb.py ["optional query"]

# From project root
cd config && uv run create_index.py
```

### Infrastructure

```bash
# Deploy Azure resources
./scripts/create_resources.sh -g <rg> -s <search-name> -f <foundry-name>

# Create SharePoint app registration
./scripts/create_sp_app_registration.sh -s <search-name> -g <rg> -e <sp-endpoint>

# Cleanup
./scripts/destroy_resources.sh -g <rg> [-y]
```

### Index Management

```bash
# Create all search resources (datasource, index, skillset, indexer)
uv run create_index.py

# Create and immediately run indexer
uv run create_index.py --run

# Check indexer status
uv run create_index.py --status

# Reset and reindex all documents
uv run create_index.py --reset

# Delete all resources
uv run create_index.py --delete
```

### Knowledge Base Operations

```bash
# Create knowledge source wrapping the index
uv run create_knowledge_source.py
uv run create_knowledge_source.py --list
uv run create_knowledge_source.py --delete

# Create knowledge base
uv run create_knowledge_base.py

# Query knowledge base (interactive mode)
uv run query_kb.py

# Query with filter
uv run query_kb.py --filter "Department eq 'IT'" "What are the policies?"

# Query as authenticated user (ACL)
uv run query_acl.py

# Query with elevated permissions (debugging)
uv run query_elevated.py
```

### Testing

**Note:** This project currently has no automated tests. When adding tests:

```bash
# Install pytest as dev dependency
uv add --dev pytest pytest-asyncio

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_index.py

# Run specific test
uv run pytest tests/test_index.py::test_create_datasource

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=config --cov-report=html
```

## Code Style Guidelines

### Python

**File Headers:**
```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "azure-search-documents>=11.7.0b2",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Module docstring describing purpose.

Detailed description of what this script does.
"""
```

**Imports:**
- Standard library imports first
- Third-party imports second
- Local imports last
- Alphabetically sorted within each group
- No wildcard imports (`from module import *`)

```python
import json
import os
import sys

from dotenv import load_dotenv
import requests

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
```

**Formatting:**
- 4-space indentation (no tabs)
- Maximum line length: ~100 characters (flexible, not strict)
- Use double quotes for strings
- Add blank line after imports
- Two blank lines between top-level functions
- One blank line between methods in classes

**Functions:**
```python
def function_name(param1: str, param2: int = 0) -> dict:
    """Short description on one line.
    
    Args:
        param1: Description of param1
        param2: Description of param2 (default: 0)
        
    Returns:
        Dictionary containing result data
    """
    # Implementation
    return result
```

**Naming Conventions:**
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`
- Module-level private: `_single_leading_underscore`

**Type Hints:**
- Use type hints for function parameters and return values
- Not required for obvious types or internal functions
- Use `Optional[T]` for nullable types
- Use `dict`, `list` instead of `Dict`, `List` (Python 3.10+)

**Configuration:**
- Load from `.env` using `python-dotenv`
- Use `os.getenv()` with defaults
- Validate required fields and exit early with clear error messages
- Store config in dict returned by `load_config()` function

**Error Handling:**
```python
# Check response status explicitly
if response.status_code in [200, 201, 204]:
    print(f"✓ Resource created successfully")
    return True
else:
    print(f"✗ Error: {response.status_code}")
    print(f"  {response.text}")
    return False

# Use try-except for SDK operations
try:
    result = client.retrieve(request)
except Exception as e:
    print(f"Error: {e}")
    return None
```

**Logging/Output:**
- Use emoji-prefixed print statements for user-facing output:
  - `📦` for creating/loading resources
  - `✓` for success
  - `✗` for errors
  - `⚠️` for warnings
  - `🔒` for ACL-related operations
  - `📝` for answers/results
  - `🔍` for activity/debugging
  - `📊` for status information
- Use clear, descriptive messages
- Print configuration at script start
- Print summaries at script end

**Command-Line Arguments:**
```python
import argparse

parser = argparse.ArgumentParser(description="Script description")
parser.add_argument("--flag", action="store_true", help="Flag help")
parser.add_argument("--param", type=str, help="Parameter help")
args = parser.parse_args()
```

**Main Entry Point:**
```python
def main():
    """Main execution function."""
    # Parse args, load config, execute logic
    pass

if __name__ == "__main__":
    main()
```

### Bash

**Script Headers:**
```bash
#!/usr/bin/env bash
set -euo pipefail  # Exit on error, undefined vars, pipe failures
```

**Functions:**
```bash
# Function to display usage
usage() {
  cat << EOF
Usage: $0 -g <resource-group> [options]
EOF
  exit 1
}
```

**Variables:**
- Use UPPER_CASE for environment variables and script parameters
- Use lowercase for local variables
- Quote all variable references: `"${VAR}"`
- Provide defaults: `${VAR:-default}`

**Conditionals:**
```bash
if [[ -z "${VAR}" ]]; then
  echo "Error: VAR is required"
  exit 1
fi
```

**Error Messages:**
- Use descriptive error messages
- Exit with non-zero status on errors
- Use `echo "Error: ..."` format

## Important Patterns & Conventions

### Azure AI Search Resources

Resources are named with a prefix (default: `sp-custom`) from `RESOURCE_PREFIX` env var:
- Datasource: `{prefix}-datasource`
- Index: `{prefix}-index`
- Skillset: `{prefix}-skillset`
- Indexer: `{prefix}-indexer`
- Knowledge source: `{prefix}-ks`
- Knowledge base: `{prefix}-kb` (customizable via `KNOWLEDGE_BASE_NAME`)

### Configuration Loading

```python
def load_config():
    """Load configuration from .env file."""
    load_dotenv()
    
    config = {
        "search_endpoint": os.getenv("SEARCH_ENDPOINT"),
        "api_key": os.getenv("API_KEY"),
        # ... more fields
    }
    
    # Validate required fields
    required_fields = ["search_endpoint", "api_key"]
    missing_fields = [f for f in required_fields if not config.get(f)]
    if missing_fields:
        print(f"Error: Missing required configuration: {', '.join(missing_fields)}")
        sys.exit(1)
    
    return config
```

### Making API Requests

```python
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
```

### ACL Support

When `ENABLE_ACL=true`:
- Add ACL fields to index (`UserIds`, `GroupIds` with `permissionFilter`)
- Enable `permissionFilterOption` on index
- Add ACL field mappings to indexer
- Include ACL mappings in skillset projections
- Image verbalization is automatically disabled (API limitation)
- Query requires user token in `x-ms-query-source-authorization` header

## Environment Variables

Required variables (see `.env.example`):
- `SEARCH_ENDPOINT` - Azure AI Search endpoint URL
- `API_KEY` - Search service admin key
- `API_VERSION` - API version (2024-11-01-preview or 2025-11-01-preview for ACL)
- `CONNECTION_STRING` - SharePoint connection string
- `EMBEDDING_ENDPOINT` - Azure OpenAI/Foundry endpoint
- `EMBEDDING_KEY` - Embedding model key
- `EMBEDDING_DEPLOYMENT` - Embedding deployment name

Optional variables:
- `ENABLE_ACL` - Enable document-level access control (default: false)
- `RESOURCE_PREFIX` - Prefix for resource names (default: sp-custom)
- `ADDITIONAL_COLUMNS` - Comma-separated custom SharePoint columns
- `CONTAINER_NAME` - Container type (default: useQuery)
- `CONTAINER_QUERY` - SharePoint query (e.g., includeLibrariesInSite=...)
- `KNOWLEDGE_BASE_NAME` - Custom KB name (default: {prefix}-kb)

## Common Tasks

### Adding a New Script

1. Add shebang and PEP 723 header with dependencies
2. Add module docstring
3. Implement `load_config()` function
4. Implement `main()` function with argparse
5. Add `if __name__ == "__main__":` guard
6. Make executable: `chmod +x script_name.py`
7. Update README.md with usage instructions

### Modifying Index Schema

1. Update field definitions in `create_index.py:create_index()`
2. Update skillset projections in `create_index.py:create_skillset()`
3. Update knowledge source fields in `create_knowledge_source.py`
4. Delete and recreate index: `uv run create_index.py --delete && uv run create_index.py`

### Adding Custom Metadata Fields

1. Add field to `ADDITIONAL_COLUMNS` env var (comma-separated)
2. Add field definition to index fields list
3. Add field to skillset projection mappings
4. Add field to knowledge source `sourceDataFields`
5. Recreate resources

## Best Practices

1. **Always validate configuration** - Exit early with clear error messages
2. **Use descriptive variable names** - `search_endpoint` not `se`
3. **Handle API errors gracefully** - Check status codes and print errors
4. **Print progress indicators** - Users need feedback on long operations
5. **Document ACL implications** - ACL changes behavior significantly
6. **Use defaults wisely** - Provide sensible defaults with env var overrides
7. **Keep functions focused** - One function per resource/operation
8. **Resource naming consistency** - Always use prefix pattern
9. **Clean up on errors** - Suggest using `--delete` when operations fail
10. **Test with both ACL modes** - Behavior differs significantly

## Troubleshooting

**Import errors:** Ensure dependencies are in PEP 723 header
**API errors:** Check API_VERSION matches ACL setting (2025-11-01-preview for ACL)
**Empty results:** Verify indexer ran successfully with `--status`
**Missing metadata:** Verify ADDITIONAL_COLUMNS and CONTAINER_QUERY are set

### ACL Issues

**Symptom: ACL queries return 0 results but elevated queries work**

Root cause: UserIds/GroupIds in index contain SharePoint numeric IDs (e.g., "7", "3") instead of Azure AD GUIDs.

**Why this happens:**
- SharePoint site groups (Owners, Members, Visitors) cannot be resolved to Microsoft Entra IDs
- The indexer falls back to SharePoint's internal numeric IDs
- At query time, Azure AD GUID from user token doesn't match numeric IDs
- Result: No documents match, zero results returned

**Check if you have this issue:**
```bash
uv run query_acl.py
# Look at GroupIds/UserIds:
# ❌ BAD:  ["3", "4", "5"]  (numeric - won't work)
# ✅ GOOD: ["e4a1b234-..."] (36-char GUIDs - will work)
```

**Solutions:**

1. **Replace SharePoint groups with Entra groups (Recommended)**:
   - In SharePoint, replace site groups with Azure AD Security Groups or M365 Groups
   - Reindex: `uv run create_index.py --reset`
   - Verify GUIDs appear: `uv run query_acl.py`

2. **Use remote SharePoint knowledge source**:
   - Delegates permission checking to SharePoint directly
   - Supports full SharePoint permission model
   - See: [Remote SharePoint knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-sharepoint-remote)

3. **Development workarounds**:
   - Disable ACL: Set `ENABLE_ACL=false` in `.env`
   - Use elevated queries: `uv run query_elevated.py`

**Related limitations:**
- ACLs captured on first ingestion only; permission changes require reindex
- SharePoint site groups only work if resolvable to Entra group IDs
- External/guest users not supported
- "Anyone links" and "People in org links" not supported
