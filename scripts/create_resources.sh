#!/usr/bin/env bash
set -euo pipefail

# Function to display usage
usage() {
  cat << EOF
Usage: $0 -g <resource-group> -s <search-service-name> -f <foundry-resource-name> [-p <project-name>] [-l <location>]

Required arguments:
  -g    Resource group name
  -s    Azure AI Search service name
  -f    Azure AI Foundry resource name

Optional arguments:
  -p    Foundry project name (default: {foundry-resource-name}-project)
  -l    Location (default: swedencentral)
  -h    Display this help message

Environment variables (optional):
  BUSINESS_OWNER         Business owner tag (default: bizowner)
  TECHNICAL_OWNER        Technical owner tag (default: infra)
  SEARCH_SKU             Search service SKU (default: basic)
  SEARCH_REPLICA_COUNT   Replica count (default: 1)
  SEARCH_PARTITION_COUNT Partition count (default: 1)
  FOUNDRY_SKU            Foundry resource SKU (default: S0)
  EMBEDDING_MODEL        Embedding model name (default: text-embedding-3-small)
  EMBEDDING_MODEL_VERSION Embedding model version (default: 1)
  EMBEDDING_DEPLOYMENT   Embedding deployment name (default: text-embedding-3-small)
  EMBEDDING_CAPACITY     Embedding deployment capacity (default: 10)
  CHAT_MODEL             Chat model name (default: gpt-4.1)
  CHAT_MODEL_VERSION     Chat model version (default: 2025-04-14)
  CHAT_DEPLOYMENT        Chat deployment name (default: gpt-4.1)
  CHAT_CAPACITY          Chat deployment capacity (default: 10)

Example:
  $0 -g rg-sp -s myaisearch -f myfoundry
  $0 -g rg-sp -s myaisearch -f myfoundry -p myproject -l westeurope

EOF
  exit 1
}

# Initialize variables
RG=""
SEARCH_SERVICE_NAME=""
FOUNDRY_RESOURCE_NAME=""
PROJECT_NAME=""
LOCATION=swedencentral

# Parse command line arguments
while getopts "g:s:f:p:l:h" opt; do
  case $opt in
    g) RG="$OPTARG" ;;
    s) SEARCH_SERVICE_NAME="$OPTARG" ;;
    f) FOUNDRY_RESOURCE_NAME="$OPTARG" ;;
    p) PROJECT_NAME="$OPTARG" ;;
    l) LOCATION="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

# Check if required arguments are provided
if [[ -z "$RG" ]] || [[ -z "$SEARCH_SERVICE_NAME" ]] || [[ -z "$FOUNDRY_RESOURCE_NAME" ]]; then
  echo "Error: Resource group, search service name, and foundry resource name are required." >&2
  echo "" >&2
  usage
fi

# Set default project name if not provided
if [[ -z "$PROJECT_NAME" ]]; then
  PROJECT_NAME="${FOUNDRY_RESOURCE_NAME}-project"
fi

# Tag values can be provided via environment variables, otherwise defaults are used
BUSINESS_OWNER=${BUSINESS_OWNER:-bizowner}
TECHNICAL_OWNER=${TECHNICAL_OWNER:-infra}

# Search service settings (override with env vars)
SEARCH_SKU=${SEARCH_SKU:-basic}
SEARCH_REPLICA_COUNT=${SEARCH_REPLICA_COUNT:-1}
SEARCH_PARTITION_COUNT=${SEARCH_PARTITION_COUNT:-1}

# Foundry resource settings (override with env vars)
FOUNDRY_SKU=${FOUNDRY_SKU:-S0}

# Model deployment settings (override with env vars)
EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-small}
EMBEDDING_MODEL_VERSION=${EMBEDDING_MODEL_VERSION:-1}
EMBEDDING_DEPLOYMENT=${EMBEDDING_DEPLOYMENT:-text-embedding-3-small}
EMBEDDING_CAPACITY=${EMBEDDING_CAPACITY:-1}
CHAT_MODEL=${CHAT_MODEL:-gpt-4.1}
CHAT_MODEL_VERSION=${CHAT_MODEL_VERSION:-2025-04-14}
CHAT_DEPLOYMENT=${CHAT_DEPLOYMENT:-gpt-4.1}
CHAT_CAPACITY=${CHAT_CAPACITY:-1}

# Check if az CLI is available
if ! command -v az >/dev/null 2>&1; then
  echo "az CLI not found. Install Azure CLI and login to the desired subscription." >&2
  exit 2
fi

# Ensure we are logged in and have a subscription
if ! az account show >/dev/null 2>&1; then
  echo "Not logged in to Azure CLI. Run 'az login' and select the correct subscription." >&2
  exit 2
fi

echo "Ensuring resource group '$RG' exists (create or update)..."
az group create --name "$RG" --location "$LOCATION" --tags BusinessOwner="$BUSINESS_OWNER" TechnicalOwner="$TECHNICAL_OWNER" >/dev/null
echo "Resource group '$RG' is ready."

echo "\nCreating or updating Azure AI Search service '$SEARCH_SERVICE_NAME' with system managed identity..."
az search service create \
  --name "$SEARCH_SERVICE_NAME" \
  --resource-group "$RG" \
  --sku "$SEARCH_SKU" \
  --location "$LOCATION" \
  --replica-count "$SEARCH_REPLICA_COUNT" \
  --partition-count "$SEARCH_PARTITION_COUNT" \
  --identity-type SystemAssigned \
  --auth-options aadOrApiKey \
  --aad-auth-failure-mode http403 \
  --tags BusinessOwner="$BUSINESS_OWNER" TechnicalOwner="$TECHNICAL_OWNER"
echo "Search service '$SEARCH_SERVICE_NAME' is ready with Azure AD authentication enabled."

# Create Azure AI Foundry resource and project
echo "\nChecking whether Azure AI Foundry resource '$FOUNDRY_RESOURCE_NAME' exists in resource group '$RG'..."
if az cognitiveservices account show --name "$FOUNDRY_RESOURCE_NAME" --resource-group "$RG" >/dev/null 2>&1; then
  echo "Foundry resource '$FOUNDRY_RESOURCE_NAME' already exists. No action taken."
else
  echo "Creating Azure AI Foundry resource '$FOUNDRY_RESOURCE_NAME' (kind=AIServices, sku=$FOUNDRY_SKU) in '$LOCATION'..."
  az cognitiveservices account create \
    --name "$FOUNDRY_RESOURCE_NAME" \
    --resource-group "$RG" \
    --kind AIServices \
    --sku "$FOUNDRY_SKU" \
    --location "$LOCATION" \
    --custom-domain "$FOUNDRY_RESOURCE_NAME" \
    --allow-project-management \
    --tags BusinessOwner="$BUSINESS_OWNER" TechnicalOwner="$TECHNICAL_OWNER" \
    --yes
  echo "Foundry resource '$FOUNDRY_RESOURCE_NAME' created."
fi

echo "\nChecking whether Foundry project '$PROJECT_NAME' exists..."
if az cognitiveservices account show --name "$PROJECT_NAME" --resource-group "$RG" >/dev/null 2>&1; then
  echo "Foundry project '$PROJECT_NAME' already exists. No action taken."
else
  echo "Creating Foundry project '$PROJECT_NAME' on resource '$FOUNDRY_RESOURCE_NAME'..."
  az cognitiveservices account project create \
    --name "$FOUNDRY_RESOURCE_NAME" \
    --project-name "$PROJECT_NAME" \
    --resource-group "$RG" \
    --location "$LOCATION"
  echo "Foundry project '$PROJECT_NAME' created."
fi

# Deploy embedding model
echo "\nChecking whether embedding model deployment '$EMBEDDING_DEPLOYMENT' exists..."
if az cognitiveservices account deployment show \
  --name "$FOUNDRY_RESOURCE_NAME" \
  --resource-group "$RG" \
  --deployment-name "$EMBEDDING_DEPLOYMENT" 2>/dev/null | grep -q "provisioningState"; then
  echo "Embedding deployment '$EMBEDDING_DEPLOYMENT' already exists. No action taken."
else
  echo "Deploying embedding model '$EMBEDDING_MODEL' (version $EMBEDDING_MODEL_VERSION) as '$EMBEDDING_DEPLOYMENT'..."
  az cognitiveservices account deployment create \
    --name "$FOUNDRY_RESOURCE_NAME" \
    --resource-group "$RG" \
    --deployment-name "$EMBEDDING_DEPLOYMENT" \
    --model-name "$EMBEDDING_MODEL" \
    --model-version "$EMBEDDING_MODEL_VERSION" \
    --model-format OpenAI \
    --sku-capacity "$EMBEDDING_CAPACITY" \
    --sku-name GlobalStandard
  
  if [ $? -eq 0 ]; then
    echo "Embedding model '$EMBEDDING_DEPLOYMENT' deployed successfully."
  else
    echo "ERROR: Failed to deploy embedding model '$EMBEDDING_DEPLOYMENT'." >&2
  fi
fi

# Deploy chat model
echo "\nChecking whether chat model deployment '$CHAT_DEPLOYMENT' exists..."
if az cognitiveservices account deployment show \
  --name "$FOUNDRY_RESOURCE_NAME" \
  --resource-group "$RG" \
  --deployment-name "$CHAT_DEPLOYMENT" 2>/dev/null | grep -q "provisioningState"; then
  echo "Chat deployment '$CHAT_DEPLOYMENT' already exists. No action taken."
else
  echo "Deploying chat model '$CHAT_MODEL' (version $CHAT_MODEL_VERSION) as '$CHAT_DEPLOYMENT'..."
  az cognitiveservices account deployment create \
    --name "$FOUNDRY_RESOURCE_NAME" \
    --resource-group "$RG" \
    --deployment-name "$CHAT_DEPLOYMENT" \
    --model-name "$CHAT_MODEL" \
    --model-version "$CHAT_MODEL_VERSION" \
    --model-format OpenAI \
    --sku-capacity "$CHAT_CAPACITY" \
    --sku-name GlobalStandard
  
  if [ $? -eq 0 ]; then
    echo "Chat model '$CHAT_DEPLOYMENT' deployed successfully."
  else
    echo "ERROR: Failed to deploy chat model '$CHAT_DEPLOYMENT'." >&2
  fi
fi

echo "\n✅ All resources created successfully!"
echo "\nResource Summary:"
echo "  Resource Group:        $RG"
echo "  Location:              $LOCATION"
echo "  AI Search:             $SEARCH_SERVICE_NAME"
echo "  Foundry Resource:      $FOUNDRY_RESOURCE_NAME"
echo "  Foundry Project:       $PROJECT_NAME"
echo "  Embedding Deployment:  $EMBEDDING_DEPLOYMENT"
echo "  Chat Deployment:       $CHAT_DEPLOYMENT"

# Retrieve API keys
echo "\nRetrieving API keys..."
SEARCH_API_KEY=$(az search admin-key show --resource-group "$RG" --service-name "$SEARCH_SERVICE_NAME" --query primaryKey -o tsv)
FOUNDRY_API_KEY=$(az cognitiveservices account keys list --resource-group "$RG" --name "$FOUNDRY_RESOURCE_NAME" --query key1 -o tsv)

# Print .env configuration
echo "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Copy and paste these settings into your .env file:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "# Azure AI Search configuration"
echo "SEARCH_ENDPOINT=https://${SEARCH_SERVICE_NAME}.search.windows.net"
echo "API_KEY=${SEARCH_API_KEY}"
echo "API_VERSION=2025-11-01-preview"
echo ""
echo "# Embedding Model (Microsoft Foundry)"
echo "EMBEDDING_ENDPOINT=https://${FOUNDRY_RESOURCE_NAME}.cognitiveservices.azure.com/"
echo "EMBEDDING_KEY=${FOUNDRY_API_KEY}"
echo "EMBEDDING_DEPLOYMENT=${EMBEDDING_DEPLOYMENT}"
echo "EMBEDDING_MODEL=${EMBEDDING_MODEL}"
echo ""
echo "# Chat Completion Model (Microsoft Foundry)"
echo "CHAT_ENDPOINT=https://${FOUNDRY_RESOURCE_NAME}.cognitiveservices.azure.com/"
echo "CHAT_KEY=${FOUNDRY_API_KEY}"
echo "CHAT_DEPLOYMENT=${CHAT_DEPLOYMENT}"
echo "CHAT_MODEL=${CHAT_MODEL}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
