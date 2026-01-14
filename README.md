# SharePoint Azure AI Search Infrastructure

Automated deployment scripts for Azure AI Search with SharePoint integration using Azure AI Foundry and managed identity authentication.


## Diagram

![Architecture Diagram](diagram.png)

## Prerequisites

- Azure CLI installed and authenticated
- Global Administrator or Application Administrator role (for app registration consent)
- Contributor role on Azure subscription

## Quick Start

### 1. Create Azure Resources

Deploy Azure AI Search, Azure AI Foundry, and model deployments:

```bash
./scripts/create_resources.sh \
  -g rg-geba-sp \
  -s ais-geba-sp \
  -f fndry-geba-sp
```

**Parameters:**
- `-g` Resource group name (required)
- `-s` Azure AI Search service name (required)
- `-f` Azure AI Foundry resource name (required)
- `-p` Foundry project name (optional, defaults to `{foundry-name}-project`)
- `-l` Azure region (optional, default: swedencentral)

**Creates:**
- Azure AI Search (Basic SKU) with system-assigned managed identity
- Azure AI Foundry resource (AIServices kind, S0 SKU)
- Azure AI Foundry project
- Model deployments:
  - `text-embedding-3-small` (version 1, GlobalStandard, 10K tokens/min)
  - `gpt-4.1` (version 2025-04-14, GlobalStandard, 10K tokens/min)

**Output:** Prints .env configuration with API keys and endpoints

### 2. Create SharePoint App Registration

Create app registration with federated credentials for managed identity authentication:

```bash
./scripts/create_sp_app_registration.sh \
  -s ais-geba-sp \
  -g rg-geba-sp \
  -e https://geertbaekehotmail.sharepoint.com \
  -n SPIndexer
```

**Parameters:**
- `-s` Azure AI Search service name (required)
- `-g` Resource group name (required)
- `-e` SharePoint endpoint URL (required)
- `-n` App registration name (default: SPIndexer)

**Creates:**
- App registration with Microsoft Graph permissions:
  - Files.Read.All
  - Sites.FullControl.All
  - Sites.Read.All
- Federated credential linked to AI Search managed identity
- Service principal

**Output:** Connection string for .env file

**⚠️ Important:** Manually grant admin consent in Azure Portal:
1. Go to App registrations > [Your App Name]
2. Navigate to API permissions
3. Click "Grant admin consent for your tenant"

### 3. Update .env File

Copy the outputs from steps 1 and 2 to your `.env`:

**From create_resources.sh (step 1):**
```bash
SEARCH_ENDPOINT=https://ais-geba-sp.search.windows.net
API_KEY=<search-api-key>
API_VERSION=2025-11-01-preview

EMBEDDING_ENDPOINT=https://fndry-geba-sp.cognitiveservices.azure.com/
EMBEDDING_KEY=<foundry-key>
EMBEDDING_DEPLOYMENT=text-embedding-3-small
EMBEDDING_MODEL=text-embedding-3-small

CHAT_ENDPOINT=https://fndry-geba-sp.cognitiveservices.azure.com/
CHAT_KEY=<foundry-key>
CHAT_DEPLOYMENT=gpt-4.1
CHAT_MODEL=gpt-4.1
```

**From create_sp_app_registration.sh (step 2):**
```bash
CONNECTION_STRING="SharePointOnlineEndpoint=https://...;ApplicationId=...;FederatedCredentialObjectId=...;TenantId=..."
```

**Additional SharePoint datasource configuration:**
```bash
DATASOURCE_NAME=sharepoint-datasource
CONTAINER_NAME=useQuery
CONTAINER_QUERY=includeLibrariesInSite=https://yoursharepoint.sharepoint.com
RESOURCE_PREFIX=sp-custom  # Prefix for index/datasource/skillset/indexer names
```

### 4. Create SharePoint Index and Indexer

Create the Azure AI Search index with metadata fields, skillset for chunking/embeddings, and indexer:

```bash
cd config
uv run create_index.py
```

**What it does:**
1. **Creates Data Source** - SharePoint connection using the app registration credentials
2. **Creates Index** - Search index with fields for:
   - Text chunks and vector embeddings
   - SharePoint metadata (name, path, web URL, last modified, size, content type, extension)
   - Document metadata (author, creation date, keywords, title, language)
   - Custom SharePoint columns (if specified in ADDITIONAL_COLUMNS)
3. **Creates Skillset** - AI enrichment pipeline:
   - Document chunking (800 chars with 400 overlap)
   - Vector embeddings using your embedding model
   - Image verbalization (if chat model configured)
4. **Creates Indexer** - Orchestrates the pipeline to process SharePoint documents

**Created resources:**
- Data source: `sp-custom-datasource`
- Index: `sp-custom-index`
- Skillset: `sp-custom-skillset`
- Indexer: `sp-custom-indexer`

**Useful commands:**
```bash
# Run the indexer immediately after creation
uv run create_index.py --run

# Check indexer status
uv run create_index.py --status

# Reset and reprocess all documents
uv run create_index.py --reset

# Delete all resources for cleanup
uv run create_index.py --delete
```

**Result:** A searchable index with chunked documents, embeddings, and rich metadata ready for agentic retrieval or RAG applications.

### 5. Create Knowledge Source

Create a searchIndex knowledge source that wraps your custom index for use with agentic retrieval:

```bash
cd config
uv run create_knowledge_source.py
```

**What it does:**
- Creates a `searchIndex` knowledge source that wraps the index created in step 4
- Configures source data fields for citations (web URL, content, author, title, metadata)
- Defines search fields (snippet, author, title, item name)
- Enables the index to be used in Azure AI knowledge bases for agentic retrieval

**Created resource:**
- Knowledge source: `sp-custom-ks` (wraps `sp-custom-index`)

**Useful commands:**
```bash
# List all knowledge sources
uv run create_knowledge_source.py --list

# Delete the knowledge source
uv run create_knowledge_source.py --delete
```

**Result:** A knowledge source ready to be used in Azure AI knowledge bases for agentic RAG applications with rich metadata and citations.

### 6. Create Knowledge Base

Create an Azure AI knowledge base that uses the knowledge source for agentic retrieval:

```bash
cd config
uv run create_knowledge_base.py
```

**What it does:**
- Creates a knowledge base that references the knowledge source from step 5
- Configures the chat completion model (from step 1) for answer synthesis
- Sets retrieval and answer instructions for the agent
- Enables low-effort reasoning for efficient retrieval
- Configures output mode for answer synthesis (not just document retrieval)

**Additional .env configuration needed:**
```bash
KNOWLEDGE_BASE_NAME=sp-custom-kb  # Optional, defaults to {RESOURCE_PREFIX}-kb
```

**Created resource:**
- Knowledge base: `sp-custom-kb` (uses `sp-custom-ks` knowledge source)

**Result:** A fully functional knowledge base that can answer questions about SharePoint documents using agentic retrieval with the chat model, returning synthesized answers with source citations.

**Query endpoints:**
- REST API: `POST {search-endpoint}/knowledgebases/sp-custom-kb/retrieve`
- MCP: `{search-endpoint}/knowledgebases/sp-custom-kb/mcp`
  - This only works with Foundry Agents

### 7. Query the Knowledge Base

Query the knowledge base to get AI-generated answers from your SharePoint content:

```bash
cd config

# Interactive mode - chat with the knowledge base
uv run query_kb.py

# Single query from command line
uv run query_kb.py "What are the latest project updates?"

# Query with OData filter (e.g., filter by Department)
uv run query_kb.py --filter "Department eq 'IT'" "What are the IT policies?"
```

**What it does:**
- Sends natural language queries to the knowledge base
- Retrieves synthesized answers using agentic retrieval
- Returns results with source citations (document references)
- Supports OData filters to narrow search scope
- Shows reasoning activity and references (optional)

**Interactive mode commands:**
- `/activity` - Toggle showing reasoning steps
- `/refs` - Toggle showing document references
- `/filter <expr>` - Set OData filter expression
- `/filter` - Clear filter
- `/quit` - Exit

**Result:** AI-generated answers synthesized from SharePoint documents with:
- Natural language responses
- Source citations with metadata (author, title, web URL, date)
- Document references with relevance scores
- Filtered results based on custom SharePoint columns (Department, etc.)

## Cleanup

Delete resources in reverse order:

```bash
cd config

# Delete knowledge base
# Note: Use Azure Portal or REST API to delete knowledge base
# (No delete script provided in this project)

# Delete knowledge source
uv run create_knowledge_source.py --delete

# Delete search index resources
uv run create_index.py --delete
```

Delete all Azure resources in the resource group:

```bash
./scripts/destroy_resources.sh -g rg-geba-sp
```

Add `-y` to skip confirmation prompt:

```bash
./scripts/destroy_resources.sh -g rg-geba-sp -y
```

**⚠️ Warning:** destroy_resources.sh deletes the entire resource group and all resources within it.

## Authentication Architecture

- **Azure AI Search → SharePoint**: Managed identity authenticates via federated credentials to app registration
- **No secrets stored**: Keyless authentication using workload identity federation
- **App registration**: Acts as bridge between managed identity and SharePoint API

## Configuration Files

- `.env` - Environment variables for application configuration
- `scripts/create_resources.sh` - Infrastructure deployment
- `scripts/create_sp_app_registration.sh` - App registration and federated credentials
- `scripts/destroy_resources.sh` - Resource cleanup
